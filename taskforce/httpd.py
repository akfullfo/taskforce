#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ________________________________________________________________________
#
#  Copyright (C) 2014 Andrew Fullford
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ________________________________________________________________________
#

import sys, errno, re, logging
from cgi import parse_header, parse_multipart
try:
	import socketserver
	import http.server as http_server
	from urllib.parse import parse_qs, urlparse
except:
	import SocketServer as socketserver
	import BaseHTTPServer as http_server
	from urlparse import parse_qs, urlparse

from __init__ import __version__ as taskforce_version

class HTTP_handler(http_server.BaseHTTPRequestHandler):
	server_version = 'taskforce/' + taskforce_version

	#  Uncomment if we want to keep the python version a secret
	#sys_version = ''

	def fault(self, code, message):
		self.send_response(code)
		if code < 500:
			self.server.log.warning("HTTP %d on '%s' -- %s", code, self.path, message)
			message = message.encode('utf-8')
			self.send_header("Content-Type", "text/plain")
			self.send_header("Content-Length", len(message))
			self.end_headers()
			self.wfile.write(message)
		else:
			self.server.log.error("HTTP %d on '%s' -- %s", code, self.path, message, exc_info=True)
			self.end_headers()

	def do_GET(self):
		try:
			resp = self.server.serve_get(self.path)
			if not resp:
				self.fault(404, self.path + ' not found')
				return
			if type(resp) != tuple or len(resp) != 2:
				self.fault(500, 'Bad callback response for ' + self.path)
			content, content_type = resp
		except Exception as e:
			self.fault(500, "Callback error -- " + str(e))
			return
		content = content.encode('utf-8')
		self.send_response(200)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", len(content))
		self.end_headers()
		self.wfile.write(content)

	def do_POST(self):
		try:
			ctype, pdict = parse_header(self.headers['content-type'])
			if ctype == 'multipart/form-data':
				postdict = parse_multipart(self.rfile, pdict)
			elif ctype == 'application/x-www-form-urlencoded':
				length = int(self.headers['content-length'])
				postdict = parse_qs(self.rfile.read(length), keep_blank_values=1)
			else:
				postdict = {}
		except Exception as e:
			self.fault(400, "Parse error -- " + str(e))
			return
		try:
			resp = self.server.serve_post(self.path, postdict)
			if not resp:
				self.fault(404, self.path + ' not found')
				return
			if type(resp) != tuple or len(resp) != 2:
				self.fault(500, 'Bad callback response for ' + self.path)
			content, content_type = resp
		except Exception as e:
			self.fault(500, "Callback error -- " + str(e))
			return

		content = content.encode('utf-8')
		self.send_response(200)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", len(content))
		self.end_headers()
		self.wfile.write(content)

	def log_message(self, fmt, *fargs): self.server.log.info(fmt, *fargs)

class Server(socketserver.ThreadingMixIn, socketserver.TCPServer, object):
	"""
	Creates a threaded http service.  The returned object can be watched
	via taskforce.poll(), select.select(), etc.  When activiity is detected,
	the handle_request() method should be invoked.  This starts a thread to
	handle the request.  URL paths are handled with callbacks which need
	to be established before any activity might occur.  If no callback
	is registered for a given path, the embedded handler will report a
	404 error.  Any exceptions raised by the callback result in a 500
	error.

	Parameters:

	  host		- The address to listen on, defaults to Server.def_host.
	  port		- The port to listen on, defaults to Server.def_port.
	  timeout	- The timeout in seconds (float) for handler reads.
	  log		- A 'logging' object to log errors and activity.
"""
	def_host = 'localhost'
	def_port = 8080
	allow_reuse_address = True
	daemon_threads = True

	def __init__(self, host=def_host, port=def_port, timeout=2, log=None):
		super(Server, self).__init__((host, port), HTTP_handler)
		if timeout > 0:
			self.timeout = timeout
		else:
			self.timeout = None
		if log:
			self.log = log
		else:
			self.log = logging.getLogger(__name__)
			self.log.addHandler(logging.NullHandler())
		self.get_registrations = {}
		self.post_registrations = {}

	def get_request(self):
		info = super(Server, self).get_request()
		if self.timeout:
			info[0].settimeout(self.timeout)
		return info

	def register_get(self, regex, callback):
		"""
		Register a regex for processing HTTP GET
		requests.  If the callback is None, any
		existing registration is removed.
	"""
		if callback is None:
			if regex in self.get_registrations:
				del self.get_registrations[regex]
		else:
			self.get_registrations[regex] = (re.compile(regex), callback)

	def register_post(self, regex, callback):
		"""
		Register a regex for processing HTTP POST
		requests.  If the callback is None, any
		existing registration is removed.

		The callback will be called as:
	
			callback(path, postdict)
	"""
		if callback is None:
			if regex in self.post_registrations:
				del self.post_registrations[regex]
		else:
			self.post_registrations[regex] = (re.compile(regex), callback)

	def _match_path(self, path, registrations):
		match_len = 0
		matched = None
		for ex, callback in registrations.values():
			m = ex.match(path)
			if m:
				l = len(m.group(0))
				if l > match_len:
					match_len = l
					matched = callback
		return matched

	def serve_get(self, path):
		"""
		Find a GET callback for the given HTTP path, call it and
		return the results.  The callback is called with
		one argument, the path used to match it.  The callback
		must return a tuple:

			(content, content_type)

		If multiple registrations match the path, the one with
		the longest matching text will be used.  Matches are
		always anchored at the start of the path.

		None is returned if no registered callback is willing
		to handle a path.
	"""
		if path is None: return None

		matched = self._match_path(path, self.get_registrations)
		if matched is None:
			return None
		else:
			return matched(path)

	def serve_post(self, path, postdict):
		"""
		Find a POST callback for the given HTTP path, call it and
		return the results.  The callback is called with the path
		used to match it and a dict of vars from the POST body.
		The callback must return a tuple:

			(content, content_type)

		If multiple registrations match the path, the one with
		the longest matching text will be used.  Matches are
		always anchored at the start of the path.

		None is returned if no registered callback is willing
		to handle a path.
	"""
		matched = self._match_path(path, self.post_registrations)
		if matched is None:
			return None
		else:
			return matched(path, postdict)

if __name__ == "__main__":
	import argparse, json
	import poll

	def_host = Server.def_host
	def_port = Server.def_port

	def getter(path):
		global args
		ans = {
			u'English': u'hello, world',
			u'français': u'bonjour le monde',
			u'deutsch': u'hallo welt',
			u'ελληνικά': u'γεια σας, στον κόσμο',
			u'español': u'hola mundo',
			u'ไทย': u'สวัสดี โลก',
			u'日本人': u'こんにちは世界',
			u'Nihonjin': u"kon'nichiwa sekai",
			u'中国': u'你好世界',
			u'Zhōngguó': u'nǐ hǎo shìjiè',
		}
		if args.json:
			return (json.dumps(ans, indent=4)+'\n', 'application/json')
		else:
			text = """<html>
<head>
	<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	<meta charset="UTF-8">
</head>
<body>
<center>
<table width=600>
"""
			for lang in sorted(ans, key=lambda x: x.lower()):
				text += '\t<tr><td align="center">%s</td>' % (lang, )
				text += '<td align="center"><font size="15">%s</font></td></tr>\n' % (ans[lang],)
			text += """</table>
</center>
</body>
</html>
"""
			return (text, 'text/html; charset=utf-8')

	def poster(path, postdict):
		global log
		u = urlparse(path)
		log.info("For path: %s", path)
		p = postdict.copy()
		if u.query:
			q = parse_qs(u.query)
			log.debug("Query held: %s", str(q))
			p.update(q)
		q = {}
		for tag in p:
			vals = []
			for v in p[tag]:
				if type(v) is not str:
					v = v.decode('utf-8')
				vals.append(v)
			if type(tag) is not str:
				tag = tag.decode('utf-8')
			q[tag] = vals
		for tag in sorted(q):
			log.info("\t%s = '%s'", tag, ','.join(q[tag]))
		return ('ok\n', 'text/plain')

	p = argparse.ArgumentParser(description="Manage tasks and process pools")

	p.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Verbose logging for debugging')
	p.add_argument('-q', '--quiet', action='store_true', dest='quiet', help='Quiet logging, warnings and errors only')
	p.add_argument('-j', '--json', action='store_true', dest='json', help='Publish JSON instead of HTML')
	p.add_argument('-l', '--listen', action='store', dest='listen', default='%s:%d' % (def_host, def_port),
			help='Listen address in "[hostname]:[port]" format. Default is "%s:%d"' % (def_host, def_port))

	args = p.parse_args()

	log = logging.getLogger()
	log.addHandler(logging.StreamHandler())
	if args.verbose:
		log.setLevel(logging.DEBUG)
	elif args.quiet:
		log.setLevel(logging.INFO)
	else:
		log.setLevel(logging.INFO)

	m = re.match(r'^(.*):(.*)$', args.listen)
	host = None
	port = None
	if m:
		host = m.group(1)
		try:
			port = int(m.group(2))
		except:
			log.error("Port must be an integer")
			sys.exit(2)
	else:
		host = args.listen
	if not host: host = def_host
	if not port: port = def_port

	httpd = Server(host=host, port=port, timeout = 5, log = log)

	httpd.register_get(r'/.*', getter)
	httpd.register_post(r'/.*', poster)

	pset = poll.poll()
	pset.register(httpd, poll.POLLIN)

	log.info("Listening on " + str(httpd.server_address))
	while True:
		try:
			evlist = pset.poll(5000)
		except OSError as e:
			if e.errno != errno.EINTR:
				raise e
			else:
				log.info("Interrupted poll()")
				continue
		if not evlist:
			log.debug("Timeout")
			continue
		for item, mask in evlist:
			try:
				item.handle_request()
			except Exception as e:
				self.log.warning("HTTP error -- %s", str(e))
