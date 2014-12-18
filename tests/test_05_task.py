
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

import os, sys, logging, errno, time
import support
import taskforce.poll as poll
import taskforce.task as task

start_dir = os.path.realpath('.')
base_dir = "tests"
test_dir = os.path.realpath(os.path.join(base_dir, 'tmp'))
examples_dir = os.path.realpath("examples")
examples_bin = os.path.join(examples_dir, "bin")
config_file = 'example.conf'
roles_file = os.path.join(test_dir, 'test.roles')
test_roles = ['frontend', 'backend']

class Test(object):

	@classmethod
	def setUpAll(self):
		self.log = support.logger()
		self.log.info("%s started", self.__module__)

		self.start_fds = len(support.find_open_fds())
		self.startenv = {}
		for tag in ['PATH', 'PYTHONPATH']:
			if tag in os.environ:
				self.startenv[tag] = os.environ[tag]

		self.log.info("%d files open before task testing", self.start_fds)
		if not os.path.isdir(test_dir):
			os.mkdir(test_dir, 0777)
		self.file_list = [roles_file]

	@classmethod
	def tearDownAll(self):
		for path in self.file_list:
			try: os.unlink(path)
			except: pass
		if os.path.isdir(test_dir):
			os.rmdir(test_dir)
		self.log.info("%s ended", self.__module__)

	def setUp(self):
		self.log.info("setup: cd %s", examples_dir)
		os.chdir(examples_dir)

	def tearDown(self):
		self.log.info("teardown: cd %s", start_dir)
		os.chdir(start_dir)

	def set_path(self, tag, val):
		if tag in self.startenv:
			os.environ[tag] = val + ':' + self.startenv[tag]
		else:
			os.environ[tag] = val
		
	def set_roles(self, roles):
		if not type(roles) is list:
			roles = [roles]
		with open(roles_file, 'w') as f:
			f.write('\n'.join(roles) + '\n')

	def Test_A_check_config(self):
		self.set_roles(test_roles[0])
		self.set_path('PATH', examples_bin)
		l = task.legion(log=self.log)
		l.set_roles_file(roles_file)
		l.set_config_file(config_file)
