
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
import taskforce.poll as poll
import taskforce.utils as utils
import taskforce.watch_modules as watch_modules
import support

test_package = "work"
working_dir = os.path.join("tests", test_package)
test_modules = ["test_module_1", "test_module_2"]
module_content = """
def test_function():
	pass
"""

class Test(object):

	@classmethod
	def setUpAll(self, mode=None):
		self.log = support.logger()
		self.log.info("%s started", self.__module__)

		self.start_fds = len(support.find_open_fds())

		self.log.info("%d files open before watch started", self.start_fds)
		if not os.path.isdir(working_dir):
			os.mkdir(working_dir, 0777)
		self.module_list = []
		self.file_list = []
		for fname in test_modules:
			path = os.path.join(working_dir, fname + '.py')
			with open(path, 'w') as f:
				f.write(module_content)
				self.module_list.append(test_package + '.' + fname)
			self.file_list.append(path)
			self.file_list.append(path + 'c')

	@classmethod
	def tearDownAll(self):
		for path in self.file_list:
			try: os.unlink(path)
			except: pass
		if os.path.isdir(working_dir):
			os.rmdir(working_dir)
		self.log.info("%s ended", self.__module__)

	def Test_A_add(self):
		pass
