
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

base_dir = "tests"
working_dir = os.path.join(base_dir, "work")

class Test(object):

	@classmethod
	def setUpAll(self, mode=None):
		self.log = support.logger()
		self.log.info("%s started", self.__module__)

		self.start_fds = len(support.find_open_fds())

		self.log.info("%d files open before task testing", self.start_fds)
		if not os.path.isdir(working_dir):
			os.mkdir(working_dir, 0777)

	@classmethod
	def tearDownAll(self):
		if os.path.isdir(working_dir):
			os.rmdir(working_dir)
		self.log.info("%s ended", self.__module__)

	def Test_A_add(self):
		pass
