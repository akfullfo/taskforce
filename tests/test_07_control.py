
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

import os, sys, time, logging, errno, re, json
import support
from taskforce.utils import get_caller as my, deltafmt
import taskforce.poll as poll
import taskforce.task as task
import taskforce.http

env = support.env(base='.')

class Test(object):

	#ctrl_address = os.path.join('/tmp', 's.' + __module__)
	ctrl_address = '127.0.0.1:3210'
	std_args = [
		'--expires', '60',
		'--http', ctrl_address,
		'--certfile', env.cert_file
	]

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
		self.log.info("setup: cd %s", env.examples_dir)
		self.reset_env()
		os.chdir(env.examples_dir)

	def tearDown(self):
		self.log.info("teardown: cd %s", env.base_dir)
		self.reset_env()
		os.chdir(env.base_dir)

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

	def Test_A_get_status(self):
		self.set_path('PATH', env.examples_bin)
		self.log.info("PATH: %s", os.environ['PATH'])
		os.environ['EXAMPLES_BASE'] = env.examples_dir
		self.set_roles(env.test_roles)
		self.log.info("Base dir '%s', tmp dir '%s'", env.base_dir, env.temp_dir)
		self.log.info("Set roles %s", env.test_roles)
		self.log.info("Will run: %s", ' '.join(support.taskforce.command_line(env, self.std_args)))
		tf = support.taskforce(env, self.std_args, log=self.log, forget=True, verbose=False)

		#  Allow time for taskforce process to start
		time.sleep(2)

		httpc = taskforce.http.Client(address=self.ctrl_address, ssl=True, log=self.log)

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

		support.check_procsim_errors(self.__module__, env, log=self.log)
		tf.close()

		assert toi_started is not None
