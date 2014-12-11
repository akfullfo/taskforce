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

import os, sys, time, signal, fcntl, errno
import taskforce.utils as utils

class Test(object):

	@classmethod
	def setUpAll(self, mode=None):
		pass

	@classmethod
	def tearDownAll(self):
		pass

	def Test_A_ses(self):
		assert "%d thing%s found" % (0, utils.ses(0))					== '0 things found'
		assert "%d item%s found" % (1, utils.ses(1))					== '1 item found'
		assert "%d process%s found" % (2, utils.ses(2, 'es'))				== '2 processes found'
		assert "%d quantit%s found" % (3, utils.ses(3, 'ies', 'y'))			== '3 quantities found'
		assert "%d famil%s found" % (4, utils.ses(4, singular='y', plural='ies'))	== '4 families found'

	def Test_B_setproctitle(self):
		"""
		This has to just not raise an exception
		Not all systems support setproctitle()
	"""
		new_title = utils.appname() + ' testing mode'
		print 'New title is:', new_title
		old_title = utils.setproctitle(new_title)

		if old_title == new_title:
			print "Title unchanged from '%s'" % (old_title,)
		elif old_title:
			print "Title changed from '%s' to '%s'" % (old_title, new_title)
		else:
			print "Process title change not supported"

	def Test_C_versions(self):
		version_list = ['2', '1.2', '2.1', '1.2.3.4', 'abc', '1.2.3.4c', '1.2.3.14', '1.2.3.3', '1.2.3.4.3']
		expect_list  = ['1.2', '1.2.3.3', '1.2.3.4', '1.2.3.4.3', '1.2.3.14', '1.2.3.4c', '2', '2.1', 'abc']
		version_list.sort(key=utils.version_sort_key)
		assert version_list == expect_list

		fnamecheck = [
			('release-1.2.3.4.tar', 'release-0001.0002.0003.0004.tar'),
			('release_1.2.3.4.tar', 'release_0001.0002.0003.0004.tar'),
			('release-a1.2.3.4.tar', 'release-a1.0002.0003.0004.tar')
		]
		for fname, keyname in fnamecheck:
			keygen = utils.version_sort_key(fname, digits=4)
			assert keygen == keyname

		versions = [
			('2', '1.2', 1),
			('1.2', '1.2.3.4', -1),
			('1.2.3', '1.2.3.0', -1),
			('1.2.3.4.3', '1.2.3.4c', 1),
			(321, 123, 1),
			(None, None, -1),
			(None, '1.2.3', -1),
			('1.2.3', None, 1),
			('release-1.2.3.5.tar', 'release-1.2.3.4.tar', 1),
			('release-1.2.3.5.tar', 'release_1.2.3.4.tar', -1),	#  becaue dash is less than uscore
			('release-1.2.3.4.tgz', 'release-1.2.3.4.tar', 0)	#  trailing non-numbers ignored
		]
		for left, right, result in versions:
			print "Does '%s' cmp '%s' == %d?" % (left, right, result)
			assert utils.version_cmp(left, right) == result

	def Test_D_pidclaim(self):
		args = list(sys.argv)
		args.pop(0)
		pidfile = './%s.pid' % (utils.appname(),)

		#  Run the test as a forked process so we can test for
		#  pid file creation and removal.
		#
		start = time.time()
		pid = os.fork()
		if pid == 0:
			os.execlp('tests/scripts/pidclaim', 'pidclaim', pidfile)
		else:
			time.sleep(1)
			print "Child PID is:", pid
			with open(pidfile, 'r') as f:
				claim_pid = int(f.readline().strip())
				print "PID read back as:", claim_pid
			assert claim_pid == pid
			(wpid, status) = os.wait()
			print "Child ran", utils.deltafmt(time.time() - status, decimals=3)
			print "Child", utils.statusfmt(status)
			assert status == 0
			assert not os.path.exists(pidfile)

	def Test_D_signal_names(self):
		sig_list = [
			('int', signal.SIGINT, 'SIGINT'),
			('kill', signal.SIGKILL, 'SIGKILL'),
			('sigterm', signal.SIGTERM, 'SIGTERM'),
			('1', signal.SIGHUP, 'SIGHUP')
		]
		for name, number, canon in sig_list:
			num = utils.signum(name)
			nam = utils.signame(num)
			print "Checking %s => %d => %s" % (name, num, nam)
			assert num == number
			assert nam == canon

	def now_open(self, maxfd):
		isopen = set()
		for fd in range(0, maxfd):
			try:
				fcntl.fcntl(fd, fcntl.F_GETFD)
				isopen.add(fd)
			except Exception as e:
				if e[0] != errno.EBADF:
					raise e
		return isopen

	def Test_E_closeall(self):
		maxfd = utils.sys_maxfd()
		print "System MAX fd =", maxfd
		assert maxfd > 20
		start_fds = self.now_open(maxfd)
		print "Pretest open fds:", start_fds
		rd = os.open('/dev/null', os.O_RDONLY)
		wd = os.open('/dev/null', os.O_WRONLY)
		open_fds = set(start_fds)
		open_fds.add(rd)
		open_fds.add(wd)
		print "Test open fds:", open_fds
		assert open_fds == self.now_open(maxfd)
		utils.closeall(exclude=list(start_fds))
		post_fds = self.now_open(maxfd)
		print "Post test open fds:", post_fds
		assert post_fds == start_fds
