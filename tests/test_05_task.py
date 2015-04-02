
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

import os, sys, time, logging, errno, re
import support
import taskforce.poll as poll
import taskforce.task as task

env = support.env(base='.')

#  These values depend on the examples.conf configuration and will need to be updated
#  if the configuration is changed to add or remove processes.
#
expected_frontback_process_count = 8
expected_frontend_process_count = 7
expected_backend_process_count = 3

class Test(object):

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
		
	def find_children(self, tf, roles=None):
		kids = support.proctree().processes[tf.pid].children
		self.log.info("Processes for %s: %d", roles, len(kids))
		k = 0
		for kid in kids:
			k += 1
			self.log.debug("    %2d %s", k, kid.command)
		return k

	def set_roles(self, roles):
		if not type(roles) is list:
			roles = [roles]
		fname = env.roles_file + '.tmp'
		with open(fname, 'w') as f:
			f.write('\n'.join(roles) + '\n')
		os.rename(fname, env.roles_file)

	def Test_A_check_config(self):
		self.set_path('PATH', env.examples_bin)
		self.set_path('PYTHONPATH', env.base_dir)
		self.set_path('EXAMPLES_BASE', env.examples_dir)
		self.set_roles(env.test_roles[0])
		l = task.legion(log=self.log)
		l.set_roles_file(env.roles_file)
		l.set_config_file(env.config_file)

	def Test_B_sanity(self):
		self.log.info("Will run: %s", ' '.join(support.taskforce.command_line(env, ['--sanity'])))
		tf = support.taskforce(env, ['--sanity'], log=self.log)
		sanity_established = tf.search(r'Sanity check completed ok', log=self.log)
		tf.close()
		assert sanity_established

	def Test_C_role_switch(self):
		self.set_path('PATH', env.examples_bin)
		self.log.info("PATH: %s", os.environ['PATH'])
		os.environ['EXAMPLES_BASE'] = env.examples_dir
		new_roles = env.test_roles
		self.set_roles(new_roles)
		self.log.info("Setting roles %s", new_roles)
		self.log.info("Will run: %s", ' '.join(support.taskforce.command_line(env, [])))
		tf = support.taskforce(env, [], log=self.log)

		new_roles = env.test_roles
		self.log.info("Checking startup of %s roles", new_roles)
		db_started = tf.search([r"Task 'db_server' already started", r"task 'firewall' pid"], log=self.log)
		assert db_started
		kids = len(support.proctree().processes[tf.pid].children) 
		assert self.find_children(tf, roles=new_roles) == expected_frontback_process_count
		self.log.info("Startup ok")

		new_roles = env.test_roles[0]
		self.log.info("Switching to role %s", new_roles)
		self.set_roles(new_roles)
		db_stopped = tf.search([r"event_target.proc_exit.*task 'db_server'", r"Task 'ws_server' already started"],
														log=self.log)
		assert db_stopped
		assert self.find_children(tf, roles=new_roles) == expected_frontend_process_count
		self.log.info("Switch to %s ok, pid to check is %d", new_roles, tf.pid)

		new_roles = env.test_roles[1]
		self.log.info("Switching to role %s", new_roles)
		self.set_roles(new_roles)
		db_restarted = tf.search([
			r"Task 'db_server' already started",
			r"Task 'db_server' a[l]ready started",  #  Bit of a kludge to be sure we see this at least twice
			r"Task 'httpd' already started" ], log=self.log)
		assert db_restarted
		assert self.find_children(tf, roles=new_roles) == expected_backend_process_count
		self.log.info("Switch to %s ok, pid to check is %d", new_roles, tf.pid)

		support.check_procsim_errors(self.__module__, env, log=self.log)

		tf.close()
