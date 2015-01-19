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

import os, json
import support
import taskforce.poll
import taskforce.httpd
try:
	from http.client import HTTPConnection
	from urllib.parse import parse_qs, urlparse
except:
	from httplib import HTTPConnection
	from urlparse import parse_qs, urlparse

class Test(object):

	http_host = '127.0.0.1'
	http_port = 56789
	http_test_map = {
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

	@classmethod
	def setUpAll(self, mode=None):
		self.log = support.logger()
		self.log.info("%s started", self.__module__)

	@classmethod
	def tearDownAll(self):
		self.log.info("%s ended", self.__module__)

	def getter(self, path):
		u = urlparse(path)
		self.log.info("GET path '%s', query '%s'", u.path, u.query)
		if u.path.endswith('/json'):
			return (json.dumps(self.http_test_map, indent=4)+'\n', 'application/json')
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
			for lang in sorted(self.http_test_map, key=lambda x: x.lower()):
				text += '\t\t<tr><td align="center">%s</td>' % (lang, )
				text += '<td align="center"><font size="15">%s</font></td></tr>\n' % (self.http_test_map[lang],)
			text += """</table>
	</center>
</body>
</html>
"""
			return (text, 'text/html; charset=utf-8')

	def poster(self, path, postdict):
		u = urlparse(path)
		log.info("For path: %s", path)
		p = postdict.copy()
		if u.query:
			q = parse_qs(u.query)
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
		return ('ok\n', 'text/plain')

	def Test_A_open_close(self):
		httpd = taskforce.httpd.Server(host=self.http_host, port=self.http_port, log=self.log)
		self.log.info("Server listening on: %s", str(httpd.server_address))
		l = support.listeners(log=self.log)
		self.log.info("Service active, listening on port %d: %s", self.http_port, l.get(self.http_port))
		assert self.http_port in l
		del httpd
		l = support.listeners(log=self.log)
		self.log.info("Service deleted, listening on port %d: %s", self.http_port, l.get(self.http_port))
		assert self.http_port not in l

	def Test_B_get(self):
		httpd = taskforce.httpd.Server(host=self.http_host, port=self.http_port, log=self.log)
		httpd.register_get(r'/test/.*', self.getter)

		httpc = HTTPConnection(self.http_host, self.http_port, timeout=5)
		httpc.request('GET', '/test/json')

		pset = taskforce.poll.poll()
		pset.register(httpd, taskforce.poll.POLLIN)

		#  This is a little bit tricky because we are talking to ourselves,
		#  so immediately enter a poll loop, and collect the response once
		#  the daemon thread has been started.
		#
		self.log.info("Listening on " + str(httpd.server_address))
		httpr = None
		while True:
			try:
				evlist = pset.poll(5000)
			except OSError as e:
				if e.errno != errno.EINTR:
					raise e
				else:
					self.log.info("Interrupted poll()")
					continue
			if not evlist:
				raise Exception("Event loop timed out")
			handled = False
			for item, mask in evlist:
				if item == httpd:
					try:
						item.handle_request()
					except Exception as e:
						self.log.warning("HTTP error -- %s", str(e))
				elif item == httpr:
					assert item.getheader('Content-Type') == 'application/json'
					text = httpr.read().decode('utf-8')
					self.log.info('%d byte response received', len(text))
					self.log.debug('Answer ...')
					for line in text.splitlines():
						self.log.debug('%s', line)
					ans = json.loads(text)
					assert ans == self.http_test_map
					return
				else:
					raise Exception("Unknown event item: " + str(item))
			if not handled:
				httpr = httpc.getresponse()
				pset.register(httpr, taskforce.poll.POLLIN)
				self.log.info("HTTP response object successfully registered")
				handled = True
