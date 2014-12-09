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

import sys, os, select, errno

PL_SELECT = 0
PL_POLL = 1
PL_KQUEUE = 2
#PL_EPOLL = 3	# Possible future implementation

POLLIN = 1
POLLPRI = 2
POLLOUT = 4
POLLERR = 8
POLLHUP = 16
POLLNVAL = 32

class Error(Exception):
	"""
	This exception is raise for any internally detected problems.
	Using an Exception subclass allows the caller to detect internal
	exceptions as distinct from those raised by the underlying
	services.
"""
	pass

class poll(object):
	"""
	Presents an interface consitent with select.poll() but uses
	select.kqueue(), select.poll() or select.select() depending on services
	availale from the O/S.

	The service is selected automatically and will typically be the best
	choice but it may be overridden with the set_mode() method which must
	be used before the first register() call.  get_available_modes() returns
	the modes possible on this O/S.

	There are a few differences to the select.poll() interface:

	1.  poll.Error exceptions are raised by this module to distinguish them from
	    the underlying select.* object exceptions.  As a special case, the
	    select.error exception for EINTR is reraised as IOError(errno=EINTR)
	    so callers do not have to catch the multple inconsistent forms.  Other
	    than this case, no special attempt is made to make exceptions consistent
	    across the underlying services.

	2.  The events that are available across all modes are POLLIN and POLLOUT.
	    POLLPRI is not available with PL_KQUEUE so if you actually need this,
	    you will probably have to force PL_SELECT mode.  PL_SELECT mode should
	    be available on all systems.

	3.  select.poll() accepts integer file descriptors and object with a fileno()
	    method that returns an integer file descriptor.  However, the event that
	    fires when an object is used for registration holds the file descriptor
	    returned by the fileno() method rather than the object itself.  On the
	    other hand, select.select() returns the object if that is what was used
	    in the input lists.

	    This module adopts the select behavior regardless of the underlying
	    mode, as it is generally more useful.  I'm sure somebody will
	    explain to me soon why that's not actually true.
"""
	def __init__(self):
		self._mode_map = dict((val, nam) for nam, val in globals().items() if nam.startswith('PL_'))
		self._poll_map = dict((val, nam) for nam, val in globals().items() if nam.startswith('POLL'))
		self._poll_keys = self._poll_map.keys()
		self._poll_keys.sort()
		self._available_modes = set()
		self._has_registered = False
		self._fd_map = {}

		self._mode = None
		if 'kqueue' in dir(select) and callable(select.kqueue):
			if self._mode is None:
				self._mode = PL_KQUEUE
			self._available_modes.add(PL_KQUEUE)
		if 'poll' in dir(select) and callable(select.poll):
			if self._mode is None:
				self._mode = PL_POLL
			self._available_modes.add(PL_POLL)
		if 'select' in dir(select) and callable(select.select):
			if self._mode is None:
				self._mode = PL_SELECT
			self._available_modes.add(PL_SELECT)
		else:
			raise Error("System supports neither select.poll() nor select.select()")

	def get_mode(self):
		return self._mode

	def set_mode(self, mode):
		if self._has_registered:
			raise Error("Mode can't be set once register() has been called")
		if mode in self._available_modes:
			old_mode = self._mode
			self._mode = mode
			return old_mode
		else:
			raise Error("Mode '%s' is not available" % (self.get_mode_name(mode),))

	def get_mode_name(self, mode=None):
		if mode is None:
			mode = self._mode
		if mode in self._mode_map:
			return self._mode_map[mode]
		else:
			return "Mode" + str(mode)

	def get_available_modes(self):
		return self._available_modes

	def get_available_mode_names(self):
		names = []
		modes = self._mode_map.keys()
		modes.sort()
		for mode in modes:
			if mode in self._available_modes:
				names.append(self.get_mode_name(mode))
		return names

	def get_event(self, evmask):
		s = ''
		for bit in self._poll_keys:
			if evmask & bit:
				if s:
					s += ','
				s += self._poll_map[bit]
		return s

	def register(self, fo, eventmask=POLLIN|POLLOUT):
		if isinstance(fo, (int, long)):
			fd = fo
		elif hasattr(fo, 'fileno') and callable(fo.fileno):
			fd = fo.fileno()
		else:
			raise Error("File object '%s' is neither 'int' nor object with fileno() method" % (str(fo),))
		if not isinstance(fd, (int, long)):
			raise Error("File object '%s' fileno() method did not return an 'int'" % (str(fo),))
		if not self._has_registered:
			if self._mode == PL_KQUEUE:
				self._kq = select.kqueue()
			elif self._mode == PL_POLL:
				self._poll = select.poll()
			elif self._mode == PL_SELECT:
				self._rfos = set()
				self._wfos = set()
				self._xfos = set()
			self._has_registered = True
		if self._mode == PL_KQUEUE:
			if eventmask & POLLPRI:
				raise Error("POLLPRI is not supported in %s mode", self.get_mode_name(self._mode))
			self.unregister(fo)
			kl = []
			if eventmask & POLLIN:
				kl.append(select.kevent(fo, filter=select.KQ_FILTER_READ, flags=select.KQ_EV_ADD))
			if eventmask & POLLOUT:
				kl.append(select.kevent(fo, filter=select.KQ_FILTER_WRITE, flags=select.KQ_EV_ADD))
			self._fd_map[fd] = fo
			self._kq.control(kl, 0, 0)
		elif self._mode == PL_POLL:
			self._fd_map[fd] = fo
			return self._poll.register(fo, eventmask)
		elif self._mode == PL_SELECT:
			self.unregister(fo)
			self._fd_map[fd] = fo
			if eventmask & POLLIN:
				self._rfos.add(fo)
			if eventmask & POLLOUT:
				self._wfos.add(fo)
			if eventmask & POLLPRI:
				self._xfos.add(fo)

	def modify(self, fo, eventmask):
		if self._mode == PL_KQUEUE:
			self.register(fo, eventmask)
		elif self._mode == PL_POLL:
			return self._poll.modify(fo, eventmask)
		elif self._mode == PL_SELECT:
			self.register(fo, eventmask)

	def unregister(self, fo):
		if isinstance(fo, (int, long)):
			fd = fo
		elif hasattr(fo, 'fileno') and callable(fo.fileno):
			fd = fo.fileno()
		else:
			raise Error("File object '%s' is neither 'int' nor object with fileno() method" % (str(fo),))
		if fd in self._fd_map:
			del self._fd_map[fd]
		if self._mode == PL_KQUEUE:
			ev = select.kevent(fo, filter=select.KQ_FILTER_READ, flags=select.KQ_EV_DELETE)
			try: self._kq.control([ev], 0, 0)
			except: pass
			ev = select.kevent(fo, filter=select.KQ_FILTER_WRITE, flags=select.KQ_EV_DELETE)
			try: self._kq.control([ev], 0, 0)
			except: pass
		elif self._mode == PL_POLL:
			return self._poll.unregister(fo)
		elif self._mode == PL_SELECT:
			self._rfos.discard(fo)
			self._wfos.discard(fo)
			self._xfos.discard(fo)

	def poll(self, timeout=None):
		if self._mode == PL_KQUEUE:
			if timeout is not None:
				timeout /= 1000.0
			evlist = []
			try:
				kelist = self._kq.control(None, 1024, timeout)
			except OSError as e:
				if e.errno == errno.EINTR:
					raise IOError(e.errno, e.strerror)
				else:
					raise e
			if not kelist:
				return evlist
			for ke in kelist:
				fd = ke.ident
				if fd not in self._fd_map:
					raise Error("Unknown fd '%s' in kevent" % (str(fd),))
				if ke.filter == select.KQ_FILTER_READ:
					evlist.append((self._fd_map[fd], POLLIN))
				elif ke.filter == select.KQ_FILTER_WRITE:
					evlist.append((self._fd_map[fd], POLLOUT))
				else:
					raise Error("Unexpected filter 0x%x from kevent for fd %d" % (ke.filter, fd))
			return evlist
		elif self._mode == PL_POLL:
			evlist = []
			pllist = self._poll.poll(timeout)
			for pl in pllist:
				(fd, mask) = pl
				if fd not in self._fd_map:
					raise Error("Unknown fd '%s' in select.poll()" % (str(fd),))
				evlist.append((self._fd_map[fd], mask))
			return evlist
		elif self._mode == PL_SELECT:
			if timeout is not None:
				timeout /= 1000.0
			try:
				rfos, wfos, xfos = select.select(self._rfos, self._wfos, self._xfos, timeout)
			except select.error as e:
				if e[0] == errno.EINTR:
					raise IOError(e[0], e[1])
				else:
					raise e

			#  select.select() already returns the registered object so no need
			#  to map through _fd_map.
			#
			evlist = []
			for fo in xfos:
				evlist.append((fo, POLLPRI))
			for fo in rfos:
				evlist.append((fo, POLLIN))
			for fo in wfos:
				evlist.append((fo, POLLOUT))
			return evlist

if __name__ == '__main__':
	import argparse, time

	mode_names = dict((nam[3:], val) for nam, val in globals().items() if nam.startswith('PL_'))

	p = argparse.ArgumentParser(
		formatter_class=argparse.RawDescriptionHelpFormatter,
		description="Test the %s module\n%s" %
		(os.path.splitext(os.path.basename(__file__))[0], poll.__doc__))

	p.add_argument('-m', '--mode', action='store', dest='mode',
		help='Override automatic mode selection. Possible modes are: %s.  Not all modes are available on all systems'%
				(mode_names.keys(),))

	args = p.parse_args()

	data = '*'
	timeout_delay = 500

	pset = poll()

	if args.mode is not None:
		mode = mode_names.get(args.mode.upper())
		if mode is None:
			raise Exception("Attempt to set unknown mode '%s'.  Known modes are: %s" % (args.mode, mode_names.keys()))
		pset.set_mode(mode)

	print "Using mode", pset.get_mode_name(), "of available", pset.get_available_mode_names()

	#  Run basic test using a self pipe
	rd, wd = os.pipe()

	#  Check register with default event mask
	pset.register(rd)

	#  Check re-register
	pset.register(rd, POLLOUT)

	#  Check modify
	pset.modify(rd, POLLIN)

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
	if ret != data:
		raise Exception("Read returned '%s', '%s' expected" % (ret, data))
	start = time.time()

	#  Check timeout (no data expected)
	evlist = pset.poll(timeout_delay)
	duration = int(round((time.time() - start) * 1000))
	if evlist:
		raise Exception("poll() returned events when timeout expected")
	delta = abs(timeout_delay - duration)
	if delta > 30:
		raise Exception("poll() timeout deviation of %d msecs detected" % (delta,))
	print "poll() timeout delta was %d msecs" % (delta,)

	#  Check POLLOUT
	pset.register(wd, POLLOUT)

	data = "0123456789012"
	data_len = len(data)
	total = 0

	#  Fill up the pipe and detect when write will block
	while True:
		evlist = pset.poll(50)
		wr_ok = False
		for ev in evlist:
			efd, emask = ev
			if efd == wd and (emask & POLLOUT) != 0:
				wr_ok = True
		if not wr_ok:
			print "Pipe buffer full after %d bytes" % (total,)
			break
		cnt = os.write(wd, data)
		total += cnt
		if cnt < data_len:
			print "Short write of %d after %d bytes" % (cnt, total)

	#  Now drain the pipe, detect when read will block, and check the byte count
	expected_total = total
	total = 0
	while True:
		evlist = pset.poll(50)
		rd_ok = False
		for ev in evlist:
			efd, emask = ev
			if efd == rd and (emask & POLLIN) != 0:
				rd_ok = True
		if not rd_ok:
			print "Pipe emptied %d bytes" % (total,)
			break
		ret = os.read(rd, 1024)
		cnt = len(ret)
		total += cnt
		if cnt < 1024:
			print "Short read of %d after %d bytes" % (cnt, total)
	if total != expected_total:
		raise Exception("Pipe read total %d, %d expected" % (total, expected_total))

	pset.unregister(wd)
	pset.unregister(rd)

	#  Check registering with a file object instead of a descriptor
	f = os.fdopen(rd, 'r')
	pset.register(f, POLLIN)

	os.write(wd, data)
	evlist = pset.poll(50)
	if not evlist:
		raise Exception("file object poll() gave empty event list when it should have had one entry")
	for ev in evlist:
		efd, emask = ev
		if isinstance(efd, (int, long)):
			raise Exception("File object poll() returned event on fd %d instead of %s" % (efd, str(f)))
		if efd != f:
			raise Exception("file object poll() returned event with %s, %s expected" % (str(efd), str(f)))
		print "Event on %s is %s" % (str(efd), pset.get_event(emask))

	#  You can't actually call f.read() as this will loop for more data
	ret = os.read(f.fileno(), 1024)
	if ret != data:
		raise Exception("File object read returned '%s', '%s' expected" % (ret, data))

	print "Tests completed ok"
	sys.exit(0)
