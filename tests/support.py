
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

import os, subprocess, fcntl, errno, logging

class env(object):
	"""
	Set up some generally useful parameters and manage the creation
	and destruction of the temp working dir.
"""
	def __init__(self, base='.'):
		self.base_dir = os.path.realpath(base)
		self.bin_dir = os.path.join(self.base_dir, "bin")
		self.test_dir = os.path.join(self.base_dir, "tests")
		self.temp_dir = os.path.join(self.test_dir, "tmp")
		self.examples_dir = os.path.realpath("examples")
		self.working_dir = self.examples_dir
		self.examples_bin = os.path.join(self.examples_dir, "bin")
		self.config_file = os.path.join(self.examples_dir, "example.conf")
		self.roles_file = os.path.join(self.temp_dir, 'test.roles')
		self.test_roles = ['frontend', 'backend']
		if not os.path.isdir(self.temp_dir):
			os.mkdir(self.temp_dir, 0777)

	def __del__(self):
		if os.path.isdir(self.temp_dir):
			os.rmdir(self.temp_dir)

def logger():
	if logger.log:
		return logger.log
	handler = logging.StreamHandler()
	handler.setFormatter(logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s"))
	logger.log = logging.getLogger(__name__)
	logger.log.addHandler(handler)
	log_level = None

	#  This cuts the logging noise in the travis output.
	#  Set NOSE_LOG_LEVEL in .travis.yml
	#
	if 'NOSE_LOG_LEVEL' in os.environ:
		try:
			log_level = getattr(logging, os.environ['NOSE_LOG_LEVEL'].upper())
		except:
			pass
		if log_level is None:
			try:
				log_level = int(os.environ['NOSE_LOG_LEVEL'])
			except:
				pass
	if log_level is None:
		log_level = logging.INFO
	logger.log.setLevel(log_level)
	return logger.log
logger.log = None

def find_open_fds():
	cnt = 0
	fds = []
	for fd in range(1024):
		try:
			os.fstat(fd)
			fds.append(fd)
		except:
			pass
	return fds

class taskforce(object):
	"""
	Start a taskforce process via subproccess().  taskforce is started with
	logging to stderr and stdout and stderr collected.  The log level can
	be set witht the 'verbose' param (default True means debug level).
	The follow() method can be used to read the log output in a non-blocking manner.

	The process will be destroyed when the object is removed, or when the
	close() method is called.
"""
	@classmethod
	def command_line(self, e, *args, **params):
		cmd = [
			os.path.join(e.bin_dir, 'taskforce'),
			'--log-stderr',
			'--config-file', e.config_file,
			'--roles-file', e.roles_file
		]
		if 'verbose' not in params or params.get('verbose'):
			cmd.append('--verbose')
		if args:
			cmd.extend(args)
		return cmd

	def __init__(self, e, *args, **params):
		cmd = self.command_line(e, *args, **params)
		with open('/dev/null', 'r') as dev_null:
			self.proc = subprocess.Popen(cmd,
					bufsize=1,
					stdin=dev_null,
					stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT,
					close_fds=True,
					cwd=e.working_dir,
					universal_newlines=True)
		fl = fcntl.fcntl(self.proc.stdout.fileno(), fcntl.F_GETFL)
		fcntl.fcntl(self.proc.stdout.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)

	def __del__(self):
		self.close()

	def close(self):
		if self.proc is None:
			return
		if self.proc.returncode is not None:
			return
		self.proc.terminate()
		for i in range(20):
			if self.proc.poll() is not None:
				break
		if self.proc.returncode is None:
			self.proc.kill()
			self.proc.wait()
		ret = self.proc.returncode
		self.proc = None
		return ret

	def follow(self):
		if self.proc is None:
			raise Exception("Attempt to follow() a closed process")
		try:
			return self.proc.stdout.readline().rstrip()
		except Exception as e:
			if e[0] == errno.EAGAIN:
				return None
			raise e
		#if self.proc.poll() is not None: return ''
