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

import os, sys, time, re, signal, fcntl, errno, logging
import support
import taskforce.utils as utils
from taskforce.utils import get_caller as my

env = support.env(base='.')

def my_module_level():
	here = my()
	support.logger().info("%s at module level", here)
	assert here.startswith('test_01_utils.my_module_level()')

class my_class_init(object):
	"""
This text is used in the module_description test.  Normally it
would include details about what this class is for, its parameters,
how it is typically used.
"""
	def __init__(self):
		here = my()
		support.logger().info("%s at class init level", here)
		assert here.startswith('my_class_init()')

class Test(object):
	"""
This text is used in the module_description test.  Normally it
would include details about what this class is for, its parameters,
how it is typically used.
"""

	@classmethod
	def setUpAll(self, mode=None):
		self.log = support.logger()
		self.log.info("%s started", self.__module__)

	@classmethod
	def tearDownAll(self):
		self.log.info("%s ended", self.__module__)

	def set_path(self, tag, val):
		if tag in os.environ:
			os.environ[tag] = val + ':' + os.environ[tag]
		else:
			os.environ[tag] = val

	def Test_A_my(self):
		has_place = re.compile(r'\[\+\d+\s+[^\]]+\]')
		
		here = my(log=self.log)
		self.log.info("%s with no class reference", here)
		assert here.startswith('Test.Test_A_my()')

		here = my(self)
		self.log.info("%s with class reference", here)
		assert here.startswith('Test.Test_A_my()')

		my_module_level()
		my_class_init()

		here = my(self, place=True, log=self.log)
		self.log.info("%s with place forced on", here)
		assert has_place.search(here)

		here = my(self, place=False, log=self.log)
		self.log.info("%s with place forced off", here)
		assert not has_place.search(here)

		my(self, persist_place=True, log=self.log)
		here = my(self, log=self.log)
		self.log.info("%s with persistent place forced on", here)
		assert has_place.search(here)

		my(self, persist_place=False, log=self.log)
		here = my(self, log=self.log)
		self.log.info("%s with persistent place forced off", here)
		assert not has_place.search(here)

	def Test_B_ses(self):
		assert "%d thing%s found" % (0, utils.ses(0))					== '0 things found'
		assert "%d item%s found" % (1, utils.ses(1))					== '1 item found'
		assert "%d process%s found" % (2, utils.ses(2, 'es'))				== '2 processes found'
		assert "%d quantit%s found" % (3, utils.ses(3, 'ies', 'y'))			== '3 quantities found'
		assert "%d famil%s found" % (4, utils.ses(4, singular='y', plural='ies'))	== '4 families found'
		assert utils.ses(0) == 's'
		assert utils.ses(1) == ''
		assert utils.ses(2, 'es') == 'es'
		assert utils.ses(1, 'ies', 'y') == 'y'
		assert utils.ses(3, 'ies', 'y') == 'ies'
		assert utils.ses(1, singular='y', plural='ies') == 'y'
		assert utils.ses(4, singular='y', plural='ies') == 'ies'

	def Test_C_versions(self):
		version_with_chars = '1.2.3.4c'
		version_with_chars_key = '000001.000002.000003.4c'
		test_versions = ['2', '1.2', '1.2.3.4', 'abc', '1.2.3.14', '1.2.3.3', '1.2.3.4.3', version_with_chars]
		sorted_versions = ['1.2', '1.2.3.3', '1.2.3.4', '1.2.3.4.3', '1.2.3.14', '1.2.3.4c', '2', 'abc']
		test_versions.sort(key=utils.version_sort_key)

		self.log.info("Sorted test versions: %s", test_versions)
		assert test_versions == sorted_versions

		verkey = utils.version_sort_key(version_with_chars)
		self.log.info("Version '%s' becomes '%s'", version_with_chars, verkey)
		assert version_with_chars_key == verkey


		test_filenames = {
			'release-1.2.3.4.tar': 'release-0001.0002.0003.0004.tar',
			'release_1.2.3.4.tar': 'release_0001.0002.0003.0004.tar',
			'release-a1.2.3.4.tar': 'release-a1.0002.0003.0004.tar'
		}
		for (fname, expected) in test_filenames.items():
			res = utils.version_sort_key(fname, digits=4)
			self.log.info('Prefix test on file name "%s" gives key "%s"', fname, res)
			assert res == expected

		versions = {
			('2', '1.2'): +1,
			('1.2', '1.2.3.4'): -1,
			('1.2.3', '1.2.3.0'): -1,
			('1.2.3.4.3', '1.2.3.4c'): +1,
			(123, 123): 0,
			(321, 123): +1,
			(None, None): 0,
			(None, '1.2.3'): -1,
			('1.2.3', None): +1,
			('release-1.2.3.5.tar', 'release-1.2.3.4.tar'): +1,
			('release-1.2.3.5.tar', 'release_1.2.3.4.tar'): -1,
			('release_1.2.3.5.tar', 'release-1.2.3.4.tar'): 1,
			('release-1.2.3.4.tgz', 'release-1.2.3.4.tar'): 0,
		}
		for (pair, expected) in versions.items():
			res = utils.version_cmp(pair[0], pair[1])
			self.log.info("'%s' cmp '%s' = %+d", pair[0], pair[1], res)
			assert res == expected

	def Test_D_deltafmt(self):

		short_match = re.compile(r'^0\.\d+s$')
		now = time.time()
		delta = utils.deltafmt(time.time()-now, decimals=6)
		self.log.info("Delta = %s", delta)
		assert short_match.match(delta)

		assert utils.deltafmt(time.time()-now) == '0.00s'

		assert utils.deltafmt('abc') == '(bad delta: abc)'

		known_deltas = {
			60.0: '1m0.0s',
			600.0: '10m0s',
			3600.0: '1h0m0s',
			2*24*3600+60.0: '48h1m0s'
		}
		for delta, expected in known_deltas.items():
			res = utils.deltafmt(delta)
			self.log.info("Delta of %.2f = %s", delta, res)
			assert res == expected

	def Test_E_setproctitle(self):
		new_title = utils.appname() + ' testing mode'
		old_title = utils.setproctitle(new_title)

		if old_title:
			cur_title = utils.setproctitle(new_title)
			self.log.info("Title changed from '%s' to '%s'", old_title, cur_title)
			assert new_title == cur_title
		else:
			self.log.info("Process title change not supported")

	def Test_F_time2iso(self):
		now = time.time()

		#  Make sure we are not operating in UTC as that causes the terse, non-utc pattern match to fail
		#
		os.environ['TZ'] = 'America/Chicago'

		variations = [
			(False, False, None, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$'),
			(True, False, None, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00$'),
			(False, True, None, r'^\d{8}T\d{6}\.\d{3}[+-]\d{2}:\d{2}$'),
			(True, True, 0, r'^\d{8}T\d{6}Z$'),
			(True, True, 6, r'^\d{8}T\d{6}\.\d{6}Z$')
		]
		for utc, terse, decimals, regex in variations:
			if decimals is None:
				res = utils.time2iso(now, utc=utc, terse=terse)
				self.log.info("time2iso(now, utc=%s, terse=%s) gives '%s'", utc, terse, res)
			else:
				res = utils.time2iso(now, utc=utc, terse=terse, decimals=decimals)
				self.log.info("time2iso(now, utc=%s, terse=%s, decimals=%d) gives '%s'", utc, terse, decimals, res)
			assert re.match(regex, res)

	def Test_G_module_description(self):
		lines = utils.module_description(self.__module__, __doc__, __file__).splitlines()
		self.log.info("Autogenerated module description ...")
		for line in lines:
			self.log.info("%s", line)
		assert len(lines) > 10

	def Test_H_signals(self):
		signals = {
			signal.SIGHUP: 'SIGHUP',
			signal.SIGTERM: 'SIGTERM',
			signal.SIGKILL: 'SIGKILL',
			1024: 'SIG1024'
		}
		for signo, expected in signals.items():
			res = utils.signame(signo)
			self.log.info("Signal %d gives '%s'", signo, res)
			assert res == expected

		signames = {
			'hup': signal.SIGHUP,
			'term': signal.SIGTERM,
			'int': signal.SIGINT,
			'kill': signal.SIGKILL,
			'HUP': signal.SIGHUP,
			'1': signal.SIGHUP,
			1: signal.SIGHUP,
			'sighup': signal.SIGHUP,
			'SIGHUP': signal.SIGHUP,
			'junk': None
		}
		for signame, expected in signames.items():
			res = utils.signum(signame)
			self.log.info("Signal %s gives %s", signame, res)
			assert res == expected

	def Test_I_statusfmt(self):
		statuses = {
			0: 'exited ok',
			0x02: 'died on SIGINT',
			0x02|0x80: 'died on SIGINT (core dumped)',
			0x02<<8: 'exited 2',
			0x7FFFFF7F: 'unknown exit code 0x7fffff7f'
		}
		for code, expected in statuses.items():
			res = utils.statusfmt(code)
			self.log.info("Code 0x%04x gives: %s", code, res)
			assert res == expected

	def Test_J_format_cmd(self):
		cmds = [
			(['cmd', 'arg with spaces', '-k', 'value'], "cmd 'arg with spaces' -k value"),
			(['cmd', "it's an squote", '-k', 'value with space'], """cmd 'it'"'"'s an squote' -k 'value with space'"""),
			(None, ""),
			([None, None, None], 'None None None'),
			('cmd', 'cmd'),
			('cmd and arg', "'cmd and arg'")
		]
		for cmd, expected in cmds:
			res = utils.format_cmd(cmd)
			self.log.info("Command gave: %s", res)
			assert res == expected

	def now_open(self, maxfd):
		isopen = set()
		for fd in range(0, maxfd):
			try:
				fcntl.fcntl(fd, fcntl.F_GETFD)
				isopen.add(fd)
			except (OSError, IOError) as e:
				if e.errno != errno.EBADF:
					raise e
		return isopen

	def Test_K_closeall(self):
		maxfd = utils.sys_maxfd()
		self.log.info("System MAX fd = %d", maxfd)
		assert maxfd > 20
		start_fds = self.now_open(maxfd)
		self.log.info("Pretest open fds: %s", start_fds)
		rd = os.open(os.devnull, os.O_RDONLY)
		wd = os.open(os.devnull, os.O_WRONLY)
		open_fds = set(start_fds)
		open_fds.add(rd)
		open_fds.add(wd)
		self.log.info("Test open fds: %s", open_fds)
		assert open_fds == self.now_open(maxfd)
		utils.closeall(exclude=list(start_fds))
		post_fds = self.now_open(maxfd)
		self.log.info("Post test open fds: %s", post_fds)
		assert post_fds == start_fds

		#  Exclude using a set, with a file object mixed in
		#
		with open(os.devnull, 'r') as f:
			exclude_fds = set(start_fds)
			exclude_fds.add(f)
			start_fds = self.now_open(maxfd)
			utils.closeall(exclude=exclude_fds)
			post_fds = self.now_open(maxfd)
			self.log.info("Set with object open fds: %s", post_fds)
			assert post_fds == start_fds

		#  Exclude with a bad object mixed in
		#
		exclude_fds = set(start_fds)
		exclude_fds.add(self)
		start_fds = self.now_open(maxfd)
		utils.closeall(exclude=exclude_fds)
		post_fds = self.now_open(maxfd)
		self.log.info("Set with object open fds: %s", post_fds)
		assert post_fds == start_fds

		closed = utils.closeall(exclude=range(100))
		assert closed == None
		closed = utils.closeall(exclude=range(100), maxfd=True)
		assert closed == None
		closed = utils.closeall(exclude=range(100), maxfd=2000)
		assert closed == None
		closed = utils.closeall(exclude=range(100), beyond=100)
		assert closed == None

		fd = os.open(os.devnull, os.O_RDONLY)
		fd_set = set(range(100))
		fd_set.remove(fd)
		res = utils.closeall(exclude=fd_set)
		self.log.info("Closeall restricted to single fd %d gave %d", fd, res)
		assert res == fd

		res = utils.log_filenos(self.log)
		self.log.info("Fd of own logging: %s", str(res))
		assert res[0] > 0

		res = utils.log_filenos(self)
		self.log.info("Fd of bogus logging: %s", str(res))
		assert res == []

	def Test_L_pidclaim(self):
		args = list(sys.argv)
		args.pop(0)
		pidfile = './%s.pid' % (utils.appname(),)

		#  Run the test as a forked process so we can test for
		#  pid file creation and removal.
		#
		start = time.time()
		pid = os.fork()
		if pid == 0:
			args = ['pidclaim']
			self.set_path('PYTHONPATH', env.base_dir)
			if 'NOSE_WITH_COVERAGE' in os.environ:
				exe = 'coverage'
				args.append('run')
			else:
				exe = 'python'
			args.extend(['tests/scripts/pidclaim', pidfile])
			self.log.info("%s child, running '%s' %s", my(self), exe, args)
			os.execvp(exe, args)
		else:
			time.sleep(1)
			self.log.info("Child PID is: %d", pid)
			with open(pidfile, 'r') as f:
				claim_pid = int(f.readline().strip())
				self.log.info("PID read back as: %d", claim_pid)
			assert claim_pid == pid
			(wpid, status) = os.wait()
			self.log.info("Child ran %s", utils.deltafmt(time.time() - start, decimals=3))
			self.log.info("Child %s", utils.statusfmt(status))
			assert status == 0
			assert not os.path.exists(pidfile)

		#  Bad pid param
		#
		log_level = self.log.getEffectiveLevel()
		try:
			#  Mask the log message as we expect a failure
			self.log.setLevel(logging.CRITICAL)
			utils.pidclaim(pid='abc')
			self.log.setLevel(log_level)
			expected_error_occurred = False
		except Exception as e:
			self.log.setLevel(log_level)
			self.log.info("%s Received expected bad pid error -- %s", my(self), str(e))
			expected_error_occurred = True
		assert expected_error_occurred

		#  Invalid pid param
		#
		log_level = self.log.getEffectiveLevel()
		try:
			#  Mask the log message as we expect a failure
			self.log.setLevel(logging.CRITICAL)
			utils.pidclaim(pid=0)
			self.log.setLevel(log_level)
			expected_error_occurred = False
		except Exception as e:
			self.log.setLevel(log_level)
			self.log.info("%s Received expected invalid pid error -- %s", my(self), str(e))
			expected_error_occurred = True
		assert expected_error_occurred
