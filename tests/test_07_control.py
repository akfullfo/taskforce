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

import os, sys, time, logging, errno, re, json, tempfile
import support
from taskforce.utils import get_caller as my, deltafmt, statusfmt
import taskforce.poll as poll
import taskforce.task as task
import taskforce.http

env = support.env(base='.')

class Test(object):

	unx_address = os.path.join('/tmp', 's.' + __module__)
	tcp_address = '127.0.0.1:3210'

	@classmethod
	def setUpAll(self):
		self.log = support.logger()
		self.log.info("%s started", self.__module__)

		self.start_fds = len(support.find_open_fds())
		self.startenv = {}
		self.delenv = []
		for tag in ['PATH', 'PYTHONPATH', 'EXAMPLES_BASE']:
			if tag in os.environ:
				self.startenv[tag] = os.environ[tag]
			else:
				self.delenv.append(tag)

		self.log.info("%d files open before task testing", self.start_fds)
		self.file_list = [env.roles_file]

	@classmethod
	def tearDownAll(self):
		for path in self.file_list:
			try: os.unlink(path)
			except: pass
		self.log.info("%s ended", self.__module__)

	def setUp(self):
		self.log.info("setup")
		self.tf = None
		self.reset_env()

	def tearDown(self):
		self.log.info("teardown")
		if self.tf:
			self.stop_tf()
		self.reset_env()

	def set_path(self, tag, val):
		if tag in self.startenv:
			os.environ[tag] = val + ':' + self.startenv[tag]
		else:
			os.environ[tag] = val

	def reset_env(self):
		for tag in self.startenv:
			os.environ[tag] = self.startenv[tag]
		for tag in self.delenv:
			if tag in os.environ:
				del(os.environ[tag])
		
	def set_roles(self, roles):
		if not type(roles) is list:
			roles = [roles]
		fname = env.roles_file + '.tmp'
		with open(fname, 'w') as f:
			f.write('\n'.join(roles) + '\n')
		os.rename(fname, env.roles_file)

	def start_tf(self, address, use_ssl=None, allow_control=False):
		"""
		Start a taskforce "examples" run with control set to the specified
		address.

		This starts the background process, then probes the control channel
		to make sure it is up and running.

		It returns the http client instance.  The process instance is recorded
		in the "tf" attribute.
	"""
		self.set_path('PATH', env.examples_bin)
		self.log.info("PATH: %s", os.environ['PATH'])
		os.environ['EXAMPLES_BASE'] = env.examples_dir
		self.set_roles(env.test_roles)
		self.log.info("Base dir '%s', tmp dir '%s'", env.base_dir, env.temp_dir)
		self.log.info("Set roles %s", env.test_roles)

		cargs = ['--expires', '60']
		cargs.extend(['--certfile', '' if use_ssl is None else env.cert_file])
		cargs.extend(['--http', address])
		if allow_control:
			cargs.append('--allow-control')

		tf_out = tempfile.NamedTemporaryFile(delete=False)
		self.tf_path = tf_out.name
		self.log.info("With output to '%s', will run: %s",
					self.tf_path, ' '.join(support.taskforce.command_line(env, cargs)))

		self.tf = support.taskforce(env, cargs, log=self.log, save=tf_out, verbose=True)

		start = time.time()
		give_up = start + 10
		last_exc = None
		while time.time() < give_up:
			try:
				httpc = taskforce.http.Client(address=address, use_ssl=use_ssl, log=self.log)
				last_exc = None
				break
			except Exception as e:
				last_exc = e
				self.log.debug("%s Connection attempt failed after %s -- %s",
								my(self), deltafmt(time.time() - start), str(e))
			time.sleep(0.5)
		if last_exc:
			self.log.error("%s Connection attempt failed after %s -- %s",
							my(self), deltafmt(time.time() - start), str(e), exc_info=True)
			raise last_exc

		#  Allow time for full process function
		#time.sleep(1)

		return httpc

	def stop_tf(self):
		if not self.tf:
			self.log.info("Taskforce child already closed")
			return
		ret = self.tf.close()
		self.tf = None
		status = statusfmt(ret)

		output = None
		if self.tf_path:
			try:
				with open(self.tf_path, 'r') as f:
					output = f.readlines()
			except Exception as e:
				self.log.warning("Could not open taskforce child output '%s' -- %s", self.tf_path, str(e))
			try:
				os.unlink(self.tf_path)
			except Exception as e:
				self.log.warning("Could not remove taskforce child output '%s' -- %s", self.tf_path, str(e))
			self.tf_path = None
		else:
			self.log.warning("Taskforce child output path was not set")
		if ret == 0:
			if output:
				self.log.debug("Taskforce child exited %s, output follows ...", status)
				for line in output:
					self.log.debug("    ]  %s", line.rstrip())
			else:
				self.log.debug("Taskforce child exited %s with no output", status)
		else:
			if output:
				self.log.warning("Taskforce child exited %s, output follows ...", status)
				for line in output:
					self.log.warning("    ]  %s", line.rstrip())
			else:
				self.log.warning("Taskforce child exited %s with no output", status)


	def Test_A_https_tcp_status(self):

		httpc = self.start_tf(self.tcp_address, use_ssl=False)

		#  Check the version info is sane
		resp = httpc.getmap('/status/version')
		self.log.info("Version info: %s", str(resp))
		assert 'taskforce' in resp

		#  Try a bogus format
		try:
			resp = httpc.getmap('/status/version?indent=4&fmt=xml')
			assert "No 'version' exception on bad 'fmt'" is False
		except Exception as e:
			self.log.info("%s Expected 'version' exception on bad format: %s", my(self), str(e))

		give_up = time.time() + 30
		toi = 'db_server'
		toi_started = None
		while time.time() < give_up:
			resp = httpc.getmap('/status/tasks')
			self.log.debug('Resp %s', json.dumps(resp, indent=4))
			if toi in resp:
				if 'processes' in resp[toi] and len(resp[toi]['processes']) > 0:
					if 'started_t' in resp[toi]['processes'][0]:
						toi_started = resp[toi]['processes'][0]['started_t']
						self.log.info("%s Task of interest '%s' started %s ago",
								my(self), toi, deltafmt(time.time() - toi_started))
						break
					else:
						self.log.info("%s Task of interest '%s' is has procs", my(self), toi)
				else:
					self.log.info("%s Task of interest '%s' is known", my(self), toi)
			time.sleep(9)

		#  Try a bogus format
		try:
			resp = httpc.getmap('/status/tasks?indent=4&fmt=xml')
			assert "No 'tasks' exception on bad 'fmt'" is False
		except Exception as e:
			self.log.info("%s Expected 'tasks' exception on bad format: %s", my(self), str(e))

		#  Check the config info is sane
		resp = httpc.getmap('/status/config?pending=0')
		assert 'tasks' in resp

		#  Try a bogus format
		try:
			resp = httpc.getmap('/status/config?indent=4&fmt=xml')
			assert "No 'config' exception on bad 'fmt'" is False
		except Exception as e:
			self.log.info("%s Expected 'config' exception on bad format: %s", my(self), str(e))

		support.check_procsim_errors(self.__module__, env, log=self.log)
		self.stop_tf()

		assert toi_started is not None

	def Test_B_http_unx_status(self):

		httpc = self.start_tf(self.unx_address, use_ssl=None)

		#  Check the version info is sane
		resp = httpc.getmap('/status/version')
		self.log.info("Version info: %s", str(resp))
		assert 'taskforce' in resp

		#  Try a control operation that should be disabled on this path
		try:
			resp = httpc.post('/manage/control?db_server=off')
			assert "No exception on unauthorized control" is False
		except Exception as e:
			self.log.info("%s Expected exception on bad url: %s", my(self), str(e))

		#  Again but with different arg layout
		try:
			resp = httpc.post('/manage/control', query={'db_server': 'off'})
			assert "No exception on unauthorized control" is False
		except Exception as e:
			self.log.info("%s Expected exception on bad url: %s", my(self), str(e))

		#  Try an illegal URL
		try:
			resp = httpc.getmap('/')
			assert "No exception on bad url" is False
		except Exception as e:
			self.log.info("%s Expected exception on bad url: %s", my(self), str(e))

		support.check_procsim_errors(self.__module__, env, log=self.log)
		self.stop_tf()

	def Test_C_https_unx_status(self):

		httpc = self.start_tf(self.unx_address, use_ssl=False, allow_control=True)

		#  Check the version info is sane
		resp = httpc.getmap('/status/version')
		self.log.info("Version info: %s", str(resp))
		assert 'taskforce' in resp

		#  Check the version info is sane via postmap
		resp = httpc.postmap('/status/version')
		assert 'taskforce' in resp

		#  Send a now-valid command but have it expect a JSON return, which doesn't happen
		log_level = self.log.getEffectiveLevel()
		try:
			#  Mask the log message as we expect a failure
			self.log.setLevel(logging.CRITICAL)
			resp = httpc.postmap('/manage/control', valuemap={'db_server': 'off'})
			assert "No exception on bad JSON return" is False
		except Exception as e:
			self.log.info("%s Expected exception on bad url: %s", my(self), str(e))
		finally:
			self.log.setLevel(log_level)

		#  Turn task back on.
		(code, content, content_type) = httpc.post('/manage/control', valuemap={'db_server': 'wait'})

		assert code < 300

		support.check_procsim_errors(self.__module__, env, log=self.log)
		self.stop_tf()
