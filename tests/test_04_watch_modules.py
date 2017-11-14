
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

import os, sys, logging, errno, time, gc
import taskforce.poll as poll
import taskforce.utils as utils
import taskforce.watch_modules as watch_modules
import support

env = support.env(base='.')

working_dir = os.path.join(env.temp_dir, "work")
test_modules = ["test_module_1", "test_module_2", "test_module_3"]
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
            os.mkdir(working_dir, 0x1FF)
        self.module_list = []
        self.file_list = []
        self.change_target = None
        prev_module = None
        for fname in reversed(test_modules):
            path = os.path.join(working_dir, fname + '.py')
            self.test_module = path
            with open(path, 'w') as f:
                if prev_module:
                    f.write("import " + prev_module + "\n")
                prev_module = fname
                f.write(module_content)
                f.close()
            self.module_list.append(path)
            if self.change_target is None:
                self.change_target = path
            self.file_list.append(path)
            self.file_list.append(path + 'c')
        self.module_path = os.path.join(env.test_dir, self.__module__)

    @classmethod
    def tearDownAll(self):
        for path in self.file_list:
            try: os.unlink(path)
            except: pass
        if os.path.isdir(working_dir):
            os.rmdir(working_dir)

        #  Make sure all objects are freed which closes file descriptors.
        #  In python3 there seems to be a race condition between delayed
        #  garbage colletion and "nose" doing post-test cleanup.
        #
        gc.collect()
        self.log.info("%s ended", self.__module__)

    def Test_A_add(self):
        snoop = watch_modules.watch(log=self.log, module_path=working_dir)
        snoop.add(self.test_module)

        names = {}
        for m in snoop.modules:
            for name in snoop.modules[m]:
                if name in names:
                    names[name].append(m)
                else:
                    names[name] = [m]
        for name in names:
            self.log.info("Watching '%s' modules ...", name)
            for m in names[name]:
                self.log.info("    %s", m)
        self.log.info("Found %d modules, %d expected", len(snoop.modules), len(test_modules))
        assert len(snoop.modules) == len(test_modules)

    def Test_B_remove(self):
        snoop = watch_modules.watch(log=self.log, module_path=working_dir)
        for m in self.module_list:
            snoop.add(m)
        self.log.info("Before remove: %d module%s for %d command%s",
                len(snoop.modules), '' if len(snoop.modules) == 1 else 's',
                len(snoop.names), '' if len(snoop.names) == 1 else 's')
        before = len(snoop.names)
        snoop.remove(self.module_list[1])
        self.log.info("After remove: %d module%s for %d command%s",
                len(snoop.modules), '' if len(snoop.modules) == 1 else 's',
                len(snoop.names), '' if len(snoop.names) == 1 else 's')
        assert len(snoop.names) == before - 1

    def Test_C_watch(self):
        snoop = watch_modules.watch(log=self.log, module_path=working_dir)
        snoop.add(self.test_module)
        self.log.info("Watch setup: %d module%s for %d command%s",
                len(snoop.modules), '' if len(snoop.modules) == 1 else 's',
                len(snoop.names), '' if len(snoop.names) == 1 else 's')
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
                with open(self.change_target, 'w') as f:
                    f.write(module_content)
                touched = True
                continue
            if not touched:
                self.log.info("Premature change detected")
                for path in snoop.get():
                    self.log.info('    %s', path)
                continue
            self.log.info('Change detected')
            assert touched
            for name, path, module_list in snoop.get(timeout=0):
                self.log.info('    %s', path)
                assert path == os.path.realpath(self.test_module)
            break
        del pset
        del_fds = support.find_open_fds()
        self.log.info("%d files open after watch: %s", len(del_fds), str(del_fds))
        self.log.info("paths known to watcher: %s", support.known_fds(snoop._watch, log=self.log))

    def Test_D_autodel(self):
        del_fds = len(support.find_open_fds())
        self.log.info("%d files open after auto object delete", del_fds)
        assert del_fds == self.start_fds
