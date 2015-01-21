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

import os, sys, stat, errno, re, logging
from cgi import parse_header, parse_multipart
from . import utils
try:
	import socketserver
	import http.server as http_server
	from urllib.parse import parse_qs, urlparse
except:
	import SocketServer as socketserver
	import BaseHTTPServer as http_server
	from urlparse import parse_qs, urlparse

from .__init__ import __version__ as taskforce_version

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
			self.server.log.error("HTTP %d on '%s' -- %s", code, self.path, message)
			self.end_headers()

	def do_GET(self):
		try:
			resp = self.server.serve_get(self.path)
			if not resp:
				self.fault(404, self.path + ' not found')
				return
			if type(resp) != tuple or len(resp) != 3:
				self.fault(500, 'Bad callback response for ' + self.path)
			code, content, content_type = resp
		except Exception as e:
			self.server.log.warning("Traceback -- %s", str(e), exc_info=True)
			self.fault(500, "Callback error -- " + str(e))
			return
		content = content.encode('utf-8')
		self.send_response(code)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", len(content))
		self.end_headers()
		self.wfile.write(content)

	def do_POST(self):
		try:
			ctype, pdict = parse_header(self.headers['content-type'])
			if ctype == 'multipart/form-data':
				postmap = parse_multipart(self.rfile, pdict)
			elif ctype == 'application/x-www-form-urlencoded':
				length = int(self.headers['content-length'])
				postmap = parse_qs(self.rfile.read(length), keep_blank_values=1)
			else:
				postmap = {}
		except Exception as e:
			self.fault(400, "Parse error -- " + str(e))
			return
		try:
			resp = self.server.serve_post(self.path, postmap)
			if not resp:
				self.fault(404, self.path + ' not found')
				return
			if type(resp) != tuple or len(resp) != 3:
				self.fault(500, 'Bad callback response for ' + self.path)
			code, content, content_type = resp
		except Exception as e:
			self.server.log.warning("Traceback -- %s", str(e), exc_info=True)
			self.fault(500, "Callback error -- " + str(e))
			return

		content = content.encode('utf-8')
		self.send_response(code)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", len(content))
		self.end_headers()
		self.wfile.write(content)

	def log_message(self, fmt, *fargs): self.server.log.info(fmt, *fargs)

class BaseServer(object):
	get_registrations = {}
	post_registrations = {}

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
	
			callback(path, postmap)
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

			(code, content, content_type)

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

	def serve_post(self, path, postmap):
		"""
		Find a POST callback for the given HTTP path, call it and
		return the results.  The callback is called with the path
		used to match it and a dict of vars from the POST body.
		The callback must return a tuple:

			(code, content, content_type)

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
			return matched(path, postmap)

class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer, BaseServer):
	daemon_threads = True
	allow_reuse_address = True

	def __init__(self, host, port, timeout, log):
		self.host = host
		self.port = port
		self.timeout = timeout
		self.log = log
		self.log.info("HTTP service listening on tcp %s:%d", host, port)
		super(TCPServer, self).__init__((host, port), HTTP_handler)

	def close(self):
		pass

	def get_request(self):
		info = super(TCPServer, self).get_request()
		if self.timeout:
			info[0].settimeout(self.timeout)
		return info

class UnixStreamServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer, BaseServer):
	daemon_threads = True
	allow_reuse_address = True

	def __init__(self, path, timeout, log):
		self.path = path
		self.timeout = timeout
		self.log = log
		self.log.info("HTTP service listening on udom '%s'", path)
		if os.path.exists(self.path):
			try:
				st = os.stat(self.path)
				if stat.S_ISSOCK(st.st_mode):
					try:
						os.unlink(self.path)
						self.log.info("Removed existing udom socket '%s'", self.path)
					except Exception as e:
						self.log.warning("Could not unlink existing udom socket '%s' -- %s",
													self.path, str(e))
				else:
					raise Exception("Existing path '%s' is not a socket", self.path)
			except Exception as e:
				self.log.warning("Could not stat existing udom socket '%s' -- ignoring %s", self.path, str(e))
		super(UnixStreamServer, self).__init__(path, HTTP_handler)

	def close(self):
		if self.path and os.path.exists(self.path):
			try: os.unlink(self.path)
			except: pass
		self.path = None

	def get_request(self):
		info = super(UnixStreamServer, self).get_request()
		if self.timeout:
			info[0].settimeout(self.timeout)
		return info

#  Default when no address is provided
def_address = 'localhost:8080'

#  Used when a TCP address is provided with no port
def_port = 8080

def server(address=None, timeout=2, log=None):
	"""
	Creates a threaded http service.  The returned object can be watched
	via taskforce.poll(), select.select(), etc.  When activiity is detected,
	the handle_request() method should be invoked.  This starts a thread to
	handle the request.  URL paths are handled with callbacks which need
	to be established before any activity might occur.  If no callback
	is registered for a given path, the embedded handler will report a
	404 error.  Any exceptions raised by the callback result in a 500
	error.

	This function just instantiates either a TCPServer or UnixStreamServer based
	on the address information in the "host" param.  The UnixStreamServer class
	is used for addresses containing a "/", otherwise the TCPServer class is
	used.  To create a Udom service in the current directory, use './name'.
	If TCP is selected and no port is provided using the ":" syntax, then
	def_port will be used.
	
	The BaseServer provides the code for registering HTTP handler callbacks.

	Parameters:

	  address	- The address to listen on, defaults to "def_address".
	  		  This may be specified as "[host][:port]" for TCP, or
			  as "path" to select a Udom service (path must contain
			  at least one "/" character).
	  timeout	- The timeout in seconds (float) for handler reads.
	  log		- A 'logging' object to log errors and activity.
"""
	if log:
		log = log
	else:
		log = logging.getLogger(__name__)
		log.addHandler(logging.NullHandler())
	if not timeout:
		timeout = None

	if not address:
		address = def_address

	if address.find('/') >=0 :
		return UnixStreamServer(address, timeout, log)

	port = None
	m = re.match(r'^(.*):(.*)$', address)
	if m:
		log.debug("Matched host '%s', port '%s'", m.group(1), m.group(2))
		host = m.group(1)
		try:
			port = int(m.group(2))
		except:
			raise Exception("TCP listen port must be an integer")
	else:
		host = address
		log.debug("No match, proceding with host '%s'", host)
	if not port:
		port = self.def_port
	return TCPServer(host, port, timeout, log)

def merge_query(path, postmap, force_unicode=True):
	"""
	Merges params parsed from the URI into the mapping from
	the POST body and returns a new dict with the values.

	This is a convenience function that gives use a dict
	a bit like PHP's $_REQUEST array.  The original 'postmap'
	is preserved so the caller can identify a param's source
	if necessary.
"""
	u = urlparse(path)
	p = postmap.copy()
	if u.query:
		q = parse_qs(u.query)
		p.update(q)

	#  "p" now holds the merged mapping.  The rest of the
	#  code is to coerce the values to unicode in a manner
	#  that works for Python2 and Python3
	#
	if force_unicode:
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
		p = q
	return p
