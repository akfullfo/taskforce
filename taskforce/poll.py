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

import sys, os, select

PL_SELECT = 0
PL_POLL = 1
PL_KQUEUE = 2	# Possible future implementation
PL_EPOLL = 2	# Possible future implementation

POLLIN = 1
POLLPRI = 2
POLLOUT = 4
POLLERR = 8
POLLHUP = 16
POLLNVAL = 32

class poll(object):
	"""
	Presents an interface consitent with select.poll() but uses
	select.select() if select.poll() is no available.
"""
	def __init__(self):
		self._mode_map = dict((val, nam) for nam, val in globals().items() if nam.startswith('PL_'))
		self._poll_map = dict((val, nam) for nam, val in globals().items() if nam.startswith('POLL'))
		self._poll_keys = self._poll_map.keys()
		self._poll_keys.sort()

		if 'poll' in dir(select) and callable(select.poll):
			self._mode = PL_POLL
			self._poll = select.poll()
		elif 'select' in dir(select) and callable(select.select):
			self._mode = PL_SELECT
		else:
			raise Exception("System supports neither select.poll() nor select.select()")

	def get_mode(self):
		return self._mode

	def get_mode_name(self, mode=None):
		if mode is None:
			mode = self._mode
		if mode in self._mode_map:
			return self._mode_map[mode]
		else:
			return "Mode" + str(mode)

	def get_event(self, evmask):
		s = ''
		for bit in self._poll_keys:
			if evmask & bit:
				if s:
					s += ','
				s += self._poll_map[bit]
		return s

	def register(self, fd, eventmask=POLLIN|POLLPRI|POLLOUT):
		if self._mode == PL_POLL:
			return self._poll.register(fd, eventmask)
		else:
			pass

	def modify(self, fd, eventmask):
		if self._mode == PL_POLL:
			return self._poll.modify(fd, eventmask)
		else:
			pass

	def unregister(self, fd):
		if self._mode == PL_POLL:
			return self._poll.unregister(fd)
		else:
			pass

	def poll(self, timeout=None):
		if self._mode == PL_POLL:
			return self._poll.poll(timeout)
		else:
			pass

if __name__ == '__main__':
	import argparse, random

	p = argparse.ArgumentParser(
		formatter_class=argparse.RawDescriptionHelpFormatter,
		description="Test the %s module\n%s" %
		(os.path.splitext(os.path.basename(__file__))[0], poll.__doc__))

	p.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Verbose logging for debugging')
	p.add_argument('-q', '--quiet', action='store_true', dest='quiet', help='Warnings and errors only')

	args = p.parse_args()

	data = '*'
	pset = poll()
	print "Using poll mode", pset.get_mode_name()

	#  Run basic test using a self pipe
	rd, wd = os.pipe()
	pset.register(rd)		#  Check register with default event mask
	pset.register(rd, POLLOUT)	#  Check re-register
	pset.modify(rd, POLLIN)		#  Check modify
	os.write(wd, data)
	evlist = pset.poll(50)
	if not evlist:
		raise Exception("poll() gave empty event list when it should have had one entry")
	for ev in evlist:
		efd, emask = ev
		if efd != rd:
			raise Exception("poll() returned event on fd %d, %d expected" % (efd, rd))
		print "Event on fd %d is %s" % (efd, pset.get_event(emask))
	ret = os.read(rd, 10240)
	if ret != '*':
		raise Exception("Read returned '%s', '%s' expected" % (ret, data))
	evlist = pset.poll(500)
	if evlist:
		raise Exception("poll() returned events when timeout expected")
	print "Tests completed ok"
	sys.exit(0)
