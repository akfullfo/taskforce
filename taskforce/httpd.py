#!/usr/bin/env python
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

import sys, errno
try:
	import socketserver
	import http.server as http_server
except:
	import SocketServer as socketserver
	import BaseHTTPServer as http_server

from __init__ import __version__ as taskforce_version

class HTTP_handler(http_server.BaseHTTPRequestHandler):
	server_version = 'taskforce/' + taskforce_version

	#  Uncomment if we want to keep the python version a secret
	#sys_version = ''

	def do_GET(self):
		global exiting
		print("Handling " + self.path)
		resp = "Hello, world\n"
		self.send_response(200)
		self.send_header("Content-Type", 'text/plain')
		self.send_header("Content-Lenght", len(resp))
		self.end_headers()
		self.wfile.write(resp.encode('utf-8'))

class Server(socketserver.ThreadingMixIn, socketserver.TCPServer, object):
	allow_reuse_address = True
	daemon_threads = True

	def __init__(self, address='127.0.0.1', port=8080, timeout=2):
		super(Server, self).__init__((address, port), HTTP_handler)
		if timeout > 0:
			self.timeout = timeout
		else:
			self.timeout = None

	def get_request(self):
		info = super(Server, self).get_request()
		if self.timeout:
			info[0].settimeout(self.timeout)
		return info

if __name__ == "__main__":
	import poll

	httpd = Server()

	pset = poll.poll()
	pset.register(httpd, poll.POLLIN)

	print("Listening on " + str(httpd.server_address))
	while True:
		try:
			evlist = pset.poll(5000)
		except OSError as e:
			if e.errno != errno.EINTR:
				raise e
			else:
				print("Interrupted poll()")
				continue
		if not evlist:
			print("Timeout")
			continue
		for item, mask in evlist:
			try:
				item.handle_request()
			except Exception as e:
				self.log.warning("HTTP error -- %s", str(e))
