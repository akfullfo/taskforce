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

import sys, os, time, select, logging
import modulefinder
from . import watch_files
from . import utils
from .utils import ses

class watch(object):
    """
    Sets up an instance that can be included in a select/poll set.  The
    descriptor will become readable whenever python script changes, or
    when there is a change in a module it statically imports.

    Because the class has a fileno() method, the class instance
    can generally be used directly with select/poll.

    The following params can be set when the class is initialized
    and overridden in methods where appropriate.

      module_path - A python list or os.pathsep-separated string of
            directories.  os.pathsep is ':' on Unix systems.
            This provides the search path to find modules.
            The default is to use sys.path.
      path       -  The PATH value to use to find commands.  Default
            is the PATH environment value.
      log        -  A logging instance.

    In addition, params supported by watch_files will be relayed to it.
"""
    def __init__(self, **params):
        self._params = params
        self._watch = watch_files.watch(**params)
        self._discard = logging.getLogger(__name__)
        self._discard.addHandler(logging.NullHandler())
        self.names = {}
        self.modules = {}

    def fileno(self):
        return self._watch.fileno()

    def _getparam(self, tag, default = None, **params):
        val = params.get(tag)
        if val is None:
            val = self._params.get(tag)
        if val is None:
            val = default
        return val

    def _build(self, name, **params):
        """
        Rebuild operations by removing open modules that no longer need to be
        watched, and adding new modules if they are not currently being watched.

        This is done by comparing self.modules to watch_files.paths_open
    """
        log = self._getparam('log', self._discard, **params)

        #  Find all the modules that no longer need watching
        #
        rebuild = False
        wparams = params.copy()
        wparams['commit'] = False
        for path in list(self._watch.paths_open):
            if path in self.modules:
                continue
            try:
                self._watch.remove(path, **wparams)
                rebuild = True
            except Exception as e:
                log.warning("Remove of watched module %r failed -- %s", path, e)
            log.debug("Removed watch for path %r", path)

        #  Find all the modules that are new and should be watched
        #
        for path in list(self.modules):
            if path not in self._watch.paths_open:
                try:
                    self._watch.add(path, **wparams)
                    rebuild = True
                except Exception as e:
                    log.error("watch failed on module %r -- %s", path, e)
                    continue
        if rebuild:
            self._watch.commit(**params)

    def get(self, **params):
        """
        Return a list of commands that where affected by a recent change
        (following a poll() return for the controlling file descriptor).

        Each list element is a tuple:

            (name, command_path, module_list)

        The event queue will be read multiple times and reads continue
        until a timeout occurs.
    """
        log = self._getparam('log', self._discard, **params)

        changes = {}
        paths = self._watch.get(**params)

        #  On each event, de-invert the tree to produce a
        #  list of changes by command name.
        #
        for path in paths:
            if path in self.modules:
                for name in self.modules[path]:
                    if name in changes:
                        if path not in changes[name]:
                            changes[name].append(path)
                    else:
                        changes[name] = [path]
            else:
                log.warning("Path %r had no matching watch entry", path)
        names = list(changes)
        log.debug("Change was to %d name%s", len(names), ses(len(names)))
        names.sort()
        resp = []
        for name in names:
            resp.append((name, self.names.get(name), changes[name]))
        return resp

    def add(self, name, command_path=None, **params):
        """
        Add a command to the list of commands being watched.  "name"
        should be a unique value that can be used as a dictionary
        index.  It is typically, but not necessarily, the command
        name.  The value is returned when the command or modules for
        the command change and is used with the remove() method.

        "command_path" is a path to the command executable, which
        must be a python program.  If it includes no directory elements,
        the "path" param or the system PATH will be used to find the
        command's full path.

        If "command_path" is not specified, "name" will be used.  An
        exception is raised if the program file cannot be found.
    """
        log = self._getparam('log', self._discard, **params)
        module_path = self._getparam('module_path', sys.path, **params)

        if module_path:
            if type(module_path) is not list:
                if module_path.find(os.pathsep) >= 0:
                    module_path = module_path.split(os.pathsep)
                else:
                    module_path = [module_path]
        else:
            module_path = None
        log.debug("module_path: %s", str(module_path))

        if not command_path:
            command_path = name

        command = None
        if os.path.basename(command_path) == command_path:
            #  When the command has no directory elements (ie, the base name is the same as the name)
            #  search the system path.  Prefer a file that is both readable and executable but failing
            #  that, accept one that is only readable.
            #
            path_list = self._getparam('path', os.environ['PATH'], **params).split(os.pathsep)
            for dir in path_list:
                path = os.path.join(dir, command_path)
                try:
                    if os.access(path, os.R_OK|os.X_OK):
                        command = path
                        break
                except:
                    continue
            if command is None:
                for dir in path_list:
                    path = os.path.join(dir, command_path)
                    try:
                        if os.access(path, os.R_OK):
                            command = path
                            break
                    except:
                        continue
        if command is None and os.access(command_path, os.R_OK):
            command = command_path
        if command is None:
            log.error("failed to find %r", command_path)
            raise Exception("Could not locate command %r" % (command_path,))
        command = os.path.realpath(command)

        #  It would be nice if ModuleFinder() would retain state between runs so
        #  that it does not have to descend the tree for each command.  Unfortunately
        #  all state appears to be held in its "modules" attribute which then accumulates
        #  module references on each run_script() call.  That would wrongly attribute
        #  modules to subsequent scripts so we have to re-instantiate the class for
        #  each script.
        #
        finder = modulefinder.ModuleFinder(path=module_path)
        finder.run_script(command)

        #  If the name was used previously, remove all references
        #
        if name in self.names:
            log.debug("Removing existing entries for %r", name)
            self.remove(name)
        self.names[name] = command

        #  Build an inverted list of files and associated command names, starting
        #  with the command path itself.
        #
        rebuild = False
        if command in self.modules:
            if name in self.modules[command]:
                log.debug("Name %r already present in %r", name, command)
            else:
                log.debug("Command for %r added to %r", name, command)
                self.modules[command].append(name)
        else:
            log.debug("Command %r added for %r", command, name)
            self.modules[command] = [name]
            rebuild = True
        for modname, mod in list(finder.modules.items()):
            path = mod.__file__
            if not path:
                log.debug("Skipping module %r -- no __file__ in module", modname)
                continue
            path = os.path.realpath(path)
            if path in self.modules:
                if name in  self.modules[path]:
                    log.debug("Name %r already present in %r", name, command)
                else:
                    log.debug("%r added to %r", name, path)
                    self.modules[path].append(name)
            else:
                log.debug("%r added for %r", path, name)
                self.modules[path] = [name]
                rebuild = True
        if rebuild:
            self._build(name, **params)

    def remove(self, name, **params):
        """
        Delete a command from the watched list.  This involves removing
        the command from the inverted watch list, then possibly
        rebuilding the event set if any modules no longer need watching.
    """
        log = self._getparam('log', self._discard, **params)

        if name not in self.names:
            log.error("Attempt to remove %r which was never added", name)
            raise Exception("Command %r has never been added" % (name,))
        del self.names[name]
        rebuild = False
        for path in list(self.modules):
            if name in self.modules[path]:
                self.modules[path].remove(name)
            if len(self.modules[path]) == 0:
                del self.modules[path]
                rebuild = True
        if rebuild:
            self._build(name, **params)

    def scan(self):
        """
        This should to be called periodically.  It is critical when
        the file watcher is in WF_POLLING mode but even in WF_KQUEUE,
        it is needed to reattach module files that are replaced via
        a rename, as, for example, is done by rsync.
    """
        self._watch.scan()
