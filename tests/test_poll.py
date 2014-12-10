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

import os
import taskforce.poll

class Test(object):

	@classmethod
	def setUpAll(self, mode=None):

		self.pset = taskforce.poll.poll()
		if mode is not None:
			self.pset.set_mode(mode)

		print "Using mode", self.pset.get_mode_name(), "of available", self.pset.get_available_mode_names()

		#  Run basic test using a self pipe
		self.rd, self.wd = os.pipe()
		print "setUp exit"

	@classmethod
	def tearDownAll(self):
		print "In tearDown"
		try: os.close(self.rd)
		except: pass
		try: os.close(self.wd)
		except: pass

	def Test_A_register_default(self):
		self.pset.register(self.rd)

	def Test_B_reregister(self):
		self.pset.register(self.rd, taskforce.poll.POLLOUT)

	def Test_C_modify(self):
		self.pset.modify(self.rd, taskforce.poll.POLLIN)

	def Test_D_write_read(self):
		data = '*'
		os.write(self.wd, data)
		evlist = self.pset.poll(50)
		if not evlist:
			raise Exception("poll() gave empty event list when it should have had one entry")
		for ev in evlist:
			efd, emask = ev
			if efd != self.rd:
				raise Exception("poll() returned event on fd %d, %d expected" % (efd, self.rd))
			print "Event on fd %d is %s" % (efd, self.pset.get_event(emask))
		ret = os.read(self.rd, 10240)
		if ret != data:
			raise Exception("Read returned '%s', '%s' expected" % (ret, data))

	def Test_E_timeout(self):
		import time
		timeout_delay = 500
		max_timeout_slop = 30

		start = time.time()
		evlist = self.pset.poll(timeout_delay)
		duration = int(round((time.time() - start) * 1000))
		if evlist:
			raise Exception("poll() returned events when timeout expected")
		delta = abs(timeout_delay - duration)
		if delta > max_timeout_slop:
			raise Exception("poll() timeout deviation of %d msecs detected" % (delta,))
		print "poll() timeout delta was %d msecs" % (delta,)

	def Test_F_pollout(self):
		self.pset.register(self.wd, taskforce.poll.POLLOUT)

		data = "0123456789012"
		data_len = len(data)
		total = 0

		#  Fill up the pipe and detect when write will block
		while True:
			evlist = self.pset.poll(50)
			wr_ok = False
			for ev in evlist:
				efd, emask = ev
				if efd == self.wd and (emask & taskforce.poll.POLLOUT) != 0:
					wr_ok = True
			if not wr_ok:
				print "Pipe buffer full after %d bytes" % (total,)
				break
			cnt = os.write(self.wd, data)
			total += cnt
			if cnt < data_len:
				print "Short write of %d after %d bytes" % (cnt, total)

		#  Now drain the pipe, detect when read will block, and check the byte count
		expected_total = total
		total = 0
		while True:
			evlist = self.pset.poll(50)
			rd_ok = False
			for ev in evlist:
				efd, emask = ev
				if efd == self.rd and (emask & taskforce.poll.POLLIN) != 0:
					rd_ok = True
			if not rd_ok:
				print "Pipe emptied %d bytes" % (total,)
				break
			ret = os.read(self.rd, 1024)
			cnt = len(ret)
			total += cnt
			if cnt < 1024:
				print "Short read of %d after %d bytes" % (cnt, total)
		if total != expected_total:
			raise Exception("Pipe read total %d, %d expected" % (total, expected_total))

	def Test_G_funregister(self):
		self.pset.unregister(self.wd)
		self.pset.unregister(self.rd)

	def Test_H_fileobj(self):
		#  Check registering with a file object instead of a descriptor
		data = "0123456789012"

		f = os.fdopen(self.rd, 'r')
		self.pset.register(f, taskforce.poll.POLLIN)

		os.write(self.wd, data)
		evlist = self.pset.poll(50)
		if not evlist:
			raise Exception("file object poll() gave empty event list when it should have had one entry")
		for ev in evlist:
			efd, emask = ev
			if isinstance(efd, (int, long)):
				raise Exception("File object poll() returned event on fd %d instead of %s" % (efd, str(f)))
			if efd != f:
				raise Exception("file object poll() returned event with %s, %s expected" % (str(efd), str(f)))
			print "Event on %s is %s" % (str(efd), self.pset.get_event(emask))

		#  You can't actually call f.read() as this will loop for more data until pipe is closed
		ret = os.read(f.fileno(), 1024)
		try: f.close()
		except: pass
		if ret != data:
			raise Exception("File object read returned '%s', '%s' expected" % (ret, data))
