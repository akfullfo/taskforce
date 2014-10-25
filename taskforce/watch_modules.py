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

import sys, os, time, select
import modulefinder
import watch_files
import utils
#import ns_log
#from ns_log import ns_Caller as my

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
	  log	     -  An ns_log instance for logging.

	In addition, params supported by ns_watch_files will be relayed to it.
"""
	def __init__(self, **params):
		self._params = params
		self._watch = ns_watch_files.watch(**params)
		self._discard = ns_log.logger(name=__name__, handler='discard')
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
		Rebuild kevent operations by removing open modules
		that no longer need to be watched, and adding new
		modules if they are not currently being watched.

		This is done by comparing self.modules to
		ns_watch_files.paths_open
	"""
		log = self._getparam('log', self._discard, **params)

		#  Find all the modules that no longer need watching
		#
		rebuild = False
		wparams = params.copy()
		wparams['commit'] = False
		for path in self._watch.paths_open.keys():
			if path in self.modules:
				continue
			try:
				self._watch.remove(path, **wparams)
				rebuild = True
			except Exception as e:
				log.warning("%s Remove of watched module '%s' failed -- %s", my(self), path, str(e))
			log.debug("%s Removed watch for path '%s'", my(self), path)

		#  Find all the modules that are new and should be watched
		#
		for path in self.modules.keys():
			if path not in self._watch.paths_open:
				try:
					self._watch.add(path, **wparams)
					rebuild = True
				except Exception as e:
					log.error("%s watch failed on module '%s' -- %s", my(self), path, str(e))
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
				log.warning("%s Path '%s' had no matching watch entry", my(self), path)
		names = changes.keys()
		log.debug("%s Change was to %d name%s", my(self), len(names), '' if len(names) == 1 else 's')
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
			log.error("%s failed to find '%s'", my(self), command_path)
			raise Exception("Could not locate command '%s'" % (command_path,))
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
			log.debug("%s Removing existing entries for '%s'", my(self), name)
			self.remove(name)
		self.names[name] = command

		#  Build an inverted list of files and associated command names, starting
		#  with the command path itself.
		#  
		rebuild = False
		if command in self.modules:
			if name in self.modules[command]:
				log.debug("%s Name '%s' already present in '%s'", my(self), name, command)
			else:
				log.debug("%s Command for '%s' added to '%s'", my(self), name, command)
				self.modules[command].append(name)
		else:
			log.debug("%s Command '%s' added for '%s'", my(self), command, name)
			self.modules[command] = [name]
			rebuild = True
		for modname, mod in finder.modules.iteritems():
			path = mod.__file__
			if not path:
				log.debug("%s Skipping module '%s' -- no __file__ in module", my(self), modname)
				continue
			path = os.path.realpath(path)
			if path in self.modules:
				if name in  self.modules[path]:
					log.debug("%s Name '%s' already present in '%s'", my(self), name, command)
				else:
					log.debug("%s '%s' added to '%s'", my(self), name, path)
					self.modules[path].append(name)
			else:
				log.debug("%s '%s' added for '%s'", my(self), path, name)
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
			log.error("%s Attempt to remove '%s' which was never added", my(self), name)
			raise Exception("Command '%s' has never been added" % (name,))
		del self.names[name]
		rebuild = False
		for path in self.modules.keys():
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

if __name__ == '__main__':
	import argparse, random

	p = argparse.ArgumentParser(
		formatter_class=argparse.RawDescriptionHelpFormatter,
		description="Test the %s module\n%s" %
		(os.path.splitext(os.path.basename(__file__))[0], watch.__doc__))

	p.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Verbose logging for debugging')
	p.add_argument('-q', '--quiet', action='store_true', dest='quiet', help='Warnings and errors only')
	p.add_argument('-p', '--module-path', action='store', dest='module_path', help='Module path list (commonly $PYTHONPATH)')
	p.add_argument('-s', '--show', action='store_true', dest='show',
					help='Print the list of files that would be watched and exit')
	p.add_argument('command', nargs='+', help='List of applications to watch')

	p.set_defaults(verbose=False)
	p.set_defaults(quiet=False)

	args = p.parse_args()

	log = ns_log.logger()
	if args.verbose:
		log.setLevel(ns_log.DEBUG)
	if args.quiet:
		log.setLevel(ns_log.WARNING)

	snoop = watch(log=log, module_path=args.module_path)
	for command in args.command:
		snoop.add(command)

	if args.show:
		names = {}
		for m in snoop.modules:
			for name in snoop.modules[m]:
				if name in names:
					names[name].append(m)
				else:
					names[name] = [m]
		for name in names:
			print name+':'
			for m in names[name]:
				print "\t" + m
		sys.exit(0)

	#  test remove if we have a lot to choose from
	if len(args.command) > 2:
		rand_discard = args.command[random.randrange(len(args.command))]
		print "Randomly discarding %s to test removal" % (rand_discard,)
		snoop.remove(rand_discard)

	print "Watching %d module%s for %d command%s" % (len(snoop.modules), '' if len(snoop.modules) == 1 else 's',
							 len(snoop.names), '' if len(snoop.names) == 1 else 's')
	while True:
		if select.select([snoop], [], [], 60) == ([],[],[]):
			log.debug("Select timed out")
			continue
		print 'Changes detected ...'
		for name, path, module_list in snoop.get(timeout=0):
			print '    ', name, module_list
	raise SystemExit(0)
