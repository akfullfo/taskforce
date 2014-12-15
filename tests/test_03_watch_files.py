
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
import taskforce.watch_files as watch_files
import support

working_dir = "tests/work"

base_file_list = ["test_a", "test_b", "test_c"]

class Test(object):

	@classmethod
	def setUpAll(self, mode=None):
		self.log = support.logger()
		self.log.info("%s started", self.__module__)

		self.start_fds = len(support.find_open_fds())

		self.log.info("%d files open before watch started", self.start_fds)
		if not os.path.isdir(working_dir):
			os.mkdir(working_dir, 0777)
		self.file_list = []
		for fname in base_file_list:
			path = os.path.join(working_dir, fname)
			with open(path, 'w') as f:
				f.write(path + '\n')
				self.file_list.append(path)

	@classmethod
	def tearDownAll(self):
		for path in self.file_list:
			try: os.unlink(path)
			except: pass
		if os.path.isdir(working_dir):
			os.rmdir(working_dir)
		self.log.info("%s ended", self.__module__)

	def Test_A_add(self):
		snoop = watch_files.watch(log=self.log, timeout=0.1, limit=3)
		self.log.info("Watching in %s mode", snoop.get_mode_name())
		snoop.add(self.file_list)

		self.log.info("%d files open watching %d paths with watch started",
							len(support.find_open_fds()), len(snoop.paths_open))

	def Test_B_autodel(self):
		del_fds = len(support.find_open_fds())
		self.log.info("%d files open after auto object delete", del_fds)
		assert del_fds == self.start_fds

	def Test_C_remove(self):
		snoop = watch_files.watch(log=self.log, timeout=0.1, limit=3)
		snoop.add(self.file_list)
		added_fds = len(support.find_open_fds())
		assert len(self.file_list) > 1
		snoop.remove(self.file_list[1])
		remove_fds = len(support.find_open_fds())
		self.log.info("%d files open after remove", remove_fds)
		if snoop.get_mode() == watch_files.WF_INOTIFYX:
			#  inotify doesn't need open files for watches
			assert remove_fds == added_fds
		else:
			assert remove_fds == added_fds - 1

	def Test_D_missing(self):
		snoop = watch_files.watch(log=self.log, timeout=0.1, limit=3)
		log_level = self.log.getEffectiveLevel()
		try:
			#  Mask the log message as we expect a failure
			self.log.setLevel(logging.CRITICAL)
			snoop.add('/tmp/file/is/missing/really', missing=False)
			self.log.setLevel(log_level)
			self.log.error("Add of missing file was successful when it should fail")
			added = True
		except Exception as e:
			self.log.setLevel(log_level)
			self.log.info("Received missing exception ok -- %s", str(e))
			added = False
		assert not added

	def Test_E_watch(self):
		snoop = watch_files.watch(log=self.log, timeout=0.1, limit=3)
		snoop.add(self.file_list)
		self.log.info("%d files open watching %d paths with watch started",
							len(support.find_open_fds()), len(snoop.paths_open))
		touched = False
		pset = poll.poll()
		pset.register(snoop, poll.POLLIN)
		while True:
			try:
				evlist = pset.poll(1000)
			except OSError as e:
				self.log.info("poll() exception -- %s", str(e))
				if e.errno != errno.EINTR:
					raise e
			if not evlist:
				self.log.info("poll() timeout, will touch")
				snoop.scan()
				with open(self.file_list[0], 'w') as f:
					f.write(self.file_list[0] + '\n')
				touched = True
				continue
			if not touched:
				self.log.info("Premature change detected")
				for path in snoop.get():
					self.log.info('    %s', path)
				continue
			self.log.info('Change detected')
			assert touched
			for path in snoop.get():
				self.log.info('    %s', path)
				assert path == self.file_list[0]
			break
		fds_open = snoop.fds_open.copy()
		fds_open[snoop.fileno()] = '*control*'
		del_fds = support.find_open_fds()
		self.log.info("%d files open after watch: %s", len(del_fds), str(del_fds))
		self.log.info("paths known to watcher: %s", str(fds_open))

	def Test_F_cleanup_test(self):
		del_fds = len(support.find_open_fds())
		self.log.info("%d files open after object delete", del_fds)
		assert del_fds == self.start_fds
