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

import sys, os, fcntl, pwd, grp, signal, errno, time, socket, select, yaml, re
import logging
from . import utils
from .utils import ses, deltafmt, statusfmt
from . import poll
from . import watch_files
from . import watch_modules
from . import httpd
from . import manage
from . import status

#  The seconds before a SIGTERM sent to a task is
#  escalated to a SIGKILL.
#
sigkill_escalation = 5

#  The limit that the legion.manage() method will wait
#  for tasks to complete after a SIGTERM is relayed.
#  This should always be longer than sigkill_escalation.
#
sigterm_limit = sigkill_escalation*2

#  These timeouts affect how rapidily the idle management is called.
#  short_cycle is used when a task requests a rapid revisit, long_cycle
#  is used otherwise.
#
def_short_cycle = 0.25
def_long_cycle = 5

#  Delay before a task's process will be re-executed.
#
reexec_delay = 5

#  Point at which idle processing will be run regardless of other demands.
#
idle_starvation = def_long_cycle*3

#  The module information published into the command formatting context and the environment
#  of child processes is prefixed with this string to isolate the name space as best as possible.
#
context_prefix = 'Task_'

#  Attempt service reconnects only this often
#
service_retry_limit = 5

#  Issue repetitive messages only this frequently (in seconds).
#
repetition_limit = 60

def legion_create_handler(obj):
	"""
	Signal handlers can't be standard class methods because the signal
	callback does not include the object reference (self).  To work
	around this we use a closure the carry the object reference.
"""
	def _handler(sig, frame):
		obj._sig_handler(sig, frame)

	if '_sig_handler' not in dir(obj):							# pragma: no cover
		raise Excecption("Object instance has no _sig_handler method")
	return _handler

class LegionReset(Exception):
	"""
Raised by the legion instance when it is requesting that the caller
completely reset and restart.  This will happen if a SIGHUP is received
or in the registered program receives a module change event.
"""
	def __init__(self):
		pass
	def __str__(self):
		return "Legion reset"

class TaskError(Exception):
	def __init__(self, name, message):
		self.name = name
		self.message = message

	def __str__(self):
		return "%s: %s" % ('Legion' if self.name is None else self.name, self.message)

_fmt_context_isvar = re.compile(r'^\{(\w+)\}$')
def _fmt_context(arg_list, context):
	"""
	Iterate on performing a format operation until the formatting makes no
	further changes.  This allows for the substitution of context values that
	themselves have context values.  To prevent infinite loops due to direct
	or indirect self-reference, the total number of attempts is limited.

	On any error, the string formatted so far is returned.

	For convenience, if passed a list, each element will be formatted and
	the resulting list will be returned
"""
	if arg_list is None:
		return arg_list
	just_one = False
	if not isinstance(arg_list, list):
		arg_list = [arg_list]
		just_one = True
	ans = []
	for arg in arg_list:
		if arg is None:									# pragma: no cover
			continue
		for attempt in range(0, 10):
			res = None
			try:
				m = _fmt_context_isvar.match(arg)
				if m and m.group(1) in context and context[m.group(1)] is None:
					#  Handle case where the var is in the context will
					#  value None.  If this is left to formatting, it
					#  gets converted to the string value "None".
					#
					break
				else:
					res = arg.format(**context)
					if res == arg:
						break
				arg = res
			except:
				if res is None:
					#  If the formatting fails, revert to
					#  last successful value and stop.
					#
					res = arg
				break
		ans.append(res)
	return (ans[0] if just_one else ans)

std_process_dest = '/dev/null'
def _exec_process(cmd_list, base_context, instance=0, log=None):
	"""
	Process execution tool.

	The forks and execs a process with args formatted according to a context.
	This is implemented as a module function to make it available to
	event_targets, legion and tasks.

	The args are:

	cmd_list	- The path and arg vector
	context		- Task's context
	instance	- An integer instance number used with multi-process tasks
	log		- Logging object (default is nothing logged).

	The context is used to format command args.  In addition, these values will
	be used to change the process execution environment:

	procname	- Changes the process name of the executed command (but not the path executed).
	user		- Does a setuid for the process
	group		- Does a setgid for the process
	cwd		- Does a chdir before executing

	The passed context is extended to include these specific runtime values which
	are only available for cmd_list substitution.

	context_prefix+'pid'		-  The process ID of the child process
	context_prefix+'instance'	-  The instance number (0 if not provided)
	context_prefix+'uid'		-  The numeric uid (based on 'user' if set, getuid() otherwise)
	context_prefix+'gid'		-  The numeric gid (based on 'group' if set, getgid() otherwise)
"""
	if not log:									# pragma: no cover
		log = logging.getLogger(__name__)
		log.addHandler(logging.NullHandler())

	#  Get a copy of the context so changes here will not affect the
	#  task's base context.
	#
	context = base_context.copy()

	#  Make sure we have a normalized clone of the cmd_list
	#
	cmd_list = list(cmd_list)
	name = context.get(context_prefix+'name', cmd_list[0])
	log.debug("Starting %s instance %d", name, instance)

	procname = _fmt_context(context.get(context_prefix+'procname'), context)
	user = _fmt_context(context.get(context_prefix+'user'), context)
	group = _fmt_context(context.get(context_prefix+'group'), context)
	cwd = _fmt_context(context.get(context_prefix+'cwd'), context)

	#  Do the user setup early so we can throw an Exception on failure.
	#  Identity errors are considered fatal as we do not want to run
	#  a process at a higher priv if it was explicitly set to something
	#  else.
	#
	proc_uid = os.geteuid()
	proc_gid = os.getegid()
	do_setuid = (proc_uid != os.getuid())
	do_setgid = (proc_gid != os.getgid())
	if user is not None:
		pw = None
		try:
			uid = int(user)
			try: pw = pwd.getpwuid(uid)
			except: pass								# pragma: no cover
		except: pass
		if pw is None:
			try:
				pw = pwd.getpwnam(user)
			except Exception as e:
				raise TaskError(name, "Bad user %s -- %s" % (repr(user), str(e)))
		if proc_uid != pw.pw_uid:
			proc_uid = pw.pw_uid
			do_setuid = True
		if proc_gid != pw.pw_gid:
			proc_gid = pw.pw_gid
			do_setgid = True
	if group is not None:
		gr = None
		try:
			gid = int(group)
			try: gr = grp.getgrgid(gid)
			except: pass
		except: pass
		if gr is None:
			try:
				gr = grp.getgrnam(group)
			except Exception as e:
				raise TaskError(name, "Bad group '%s' -- %s" % (group, str(e)))
		if proc_uid is not None and proc_gid != gr.gr_gid:
			log.info("gid for user '%s' (%d) overridden by group '%s' (%d)", user, proc_gid, group, gr.gr_gid)
			proc_gid = gr.gr_gid
			do_setgid = True

	if cwd is not None and not os.path.isdir(cwd):
		raise TaskError(name, "Directory for cwd setting '%s' does not exist" % (cwd,))

	#  Add in per-process context
	#
	context[context_prefix+'instance'] = instance
	context[context_prefix+'started'] = time.time()
	context[context_prefix+'uid'] = proc_uid
	context[context_prefix+'gid'] = proc_gid

	pid = os.fork()

	#  Parent just returns pid
	if pid > 0:
		return pid

	#  This section is processing the child.  Exceptions from this point must
	#  never escape to outside handlers or we might create zombie init tasks.
	#
	try:
		# Add the pid to the context now that we have it.
		#
		context[context_prefix+'pid'] = os.getpid()

		#  Set up the requested process environment
		#
		if do_setgid:
			try:
				os.setgid(proc_gid)
				log.debug("Setgid to %d succeeded in child '%s', instance %d", proc_gid, name, instance)
			except Exception as e:
				log.error("Setgid to %d failed in child '%s', instance %d -- %s",
						proc_gid, name, instance, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
				os._exit(81)
		if do_setuid:
			try:
				os.setuid(proc_uid)
				log.debug("Setuid to %d succeeded in child '%s', instance %d", proc_uid, name, instance)
			except Exception as e:
				log.error("Setuid to %d failed in child '%s', instance %d -- %s",
						proc_uid, name, instance, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
				os._exit(82)
		if cwd is not None:
			try:
				os.chdir(cwd)
				log.debug("Chdir to '%s' succeeded in child '%s', instance %d", cwd, name, instance)
			except Exception as e:
				log.error("Chdir to '%s' failed in child '%s', instance %d -- %s",
						cwd, name, instance, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
				os._exit(83)

		#  Build formatted command
		#
		prog = _fmt_context(cmd_list[0], context)
		cmd = []
		if procname:
			cmd_list.pop(0)
			cmd.append(_fmt_context(context['procname'], context))
		for a in cmd_list:
			cmd.append(_fmt_context(a, context))

		log.info("child, Execing: %s <%s>", prog, utils.format_cmd(cmd))
	except Exception as e:
		#  Log any exceptions here while we still can.  After the closeall,
		#  bets are off.
		#
		log.error("Child processing failed for task '%s', instance %d -- %s",
				name, instance, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
		os._exit(84)
	try:
		retain_fds = [0,1,2]
		for log_fd in utils.log_filenos(log):
			if log_fd not in retain_fds:
				retain_fds.append(log_fd)
		utils.closeall(exclude=retain_fds)
		fd = None
		try: os.close(0)
		except: pass
		try:
			fd = os.open(std_process_dest, os.O_RDONLY)
		except Exception as e:
			log.error("child read open of %s failed -- %s", std_process_dest, str(e))
		if fd != 0:
			log.error("child failed to redirect stdin to %s", std_process_dest)

		try: os.close(1)
		except: pass
		try:
			fd = os.open('/dev/null', os.O_WRONLY)
		except Exception as e:
			log.error("child write open of %s failed -- %s", std_process_dest, str(e))
		if fd != 1:
			log.error("child failed to redirect stdout to %s", std_process_dest)

		#  Build a fresh environment based on context, with None values excluded and
		#  all other values as strings, formatted where appropriate:
		#
		env = {}
		for tag, val in context.items():
			if val is None:
				continue
			val = _fmt_context(str(val), context)
			if val is not None:
				env[tag] = val
	except Exception as e:
		#  At this point we can still send logs to stderr, so log these
		#  too, just in case.
		#
		log.error("Child processing failed for task '%s', instance %d -- %s",
			name, instance, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
		os._exit(85)
	try:
		try: os.close(2)
		except: pass
		try: os.dup(1)
		except: pass

		os.execvpe(prog, cmd, env)
	except:
		pass
	#  There is no way to report an exception here, so hopefully the exit code will
	#  be evidence enough.  When child output logging is supported, this can be reworked.
	#
	os._exit(86)

class event_target(object):
	"""
This class encapsulates an action, providing an opaque object that can be registered
with the legion to be invoked when an event is triggered.  The handler includes a
parent which will be either a task object or the legion object itself.

A key may be specified which allows the event to be later deregistered.  If it is not
provided, the "parent" value is used.

The actions are generally:

-  Change state info in the parent.  A parent-specific method
   will be called (the handler) which will have knowledge of the
   parent's state information.

-  Start a command, potentially registering a furthe event handler
   to handle the command completion.

Whenever an event occurs, the target will be called as "ev.handle(details)".  This
method will then call the specific handler that was set up.  The "details" value
is event-sepecific and optional.  For example, in the case of a process-exit
event, it will be the exit status.

Handlers must never execute any code that could block for any significant amount
of time.  For example, local file system access involving minimal transfers is
OK, but network access even to local daemons must not be performed.  Network
access must be done with blocking activity fed through the legion event loop.
"""
	def __init__(self, parent, handler_name, key=None, arg=None, **params):
		self._parent = parent
		self._key = parent if key is None else key
		self._params = dict(params)
		self._discard = logging.getLogger(__name__)
		self._discard.addHandler(logging.NullHandler())
		self._name = parent._name if hasattr(parent, '_name') else None

		handler_names = set([method for method in dir(self)
						if not method.startswith('_') and callable(getattr(self, method))])
		for internal in ['get_key', 'get_name', 'handle']:
			handler_names.discard(internal)
		if handler_name not in handler_names:
			raise TaskError(self._name, "'%s' is not a valid handler in '%s' class" %
										(handler_name, self.__class__.__name__))
		self._handler_name = handler_name
		self._handler = getattr(self, handler_name)
		self._handler_arg = arg

	def get_key(self):
		return self._key

	def get_name(self):
		return self._name

	def handle(self, details=None):
		log = self._params.get('log', self._discard)
		log.debug("Received %s(%s) event for '%s', details: %s",
				self._handler_name, '' if self._handler_arg is None else str(self._handler_arg),
				str(self._name), str(details))
		return self._handler(details)

	def command(self, details):
		"""
		Handles executing a command-based event.  This starts the command
		as specified in the 'commands' section of the task config.

		A separate event is registered to handle the command exit.  This
		simply logs the exit status.
	"""
		log = self._params.get('log', self._discard)
		if '_config_running' not in dir(self._parent) or 'commands' not in self._parent._config_running:
			log.error("Event parent '%s' has no 'commands' config section", self._name)
			return
		commands = self._parent._config_running['commands']
		if self._handler_arg not in commands:
			#  For now, at least, we implement a predefined command 'stop' if there is no
			#  explicit stop.  This probably needs more work because it needs to handle
			#  async commands where 'stop' would translate to a SIGTERM of the pid file.
			#
			if self._handler_arg == 'stop':
				self._parent.stop()
			else:
				log.error("Event parent '%s' has no '%s' command configured", self._name, self._handler_arg)
			return
		pid = _exec_process(commands[self._handler_arg], self._parent._context, log=log)
		log.info("Forked pid %d for %s(%s)", pid, self._name, str(self._handler_arg))
		self._parent._legion.proc_add(event_target(self._parent, 'command_exit', key=pid, arg=self._handler_arg, log=log))

	def command_exit(self, details):
		"""
		Handle the event when a utility command exits.
	"""
		log = self._params.get('log', self._discard)
		pid = self._key
		status = details
		why = statusfmt(status)
		if status:
			log.warning("pid %d for %s(%s) %s", pid, self._name, str(self._handler_arg), why)
		else:
			log.info("pid %d for %s(%s) %s", pid, self._name, str(self._handler_arg), why)

	def proc_exit(self, details):
		"""
		Handle the event when one of the task processes exits.
	"""
		log = self._params.get('log', self._discard)
		pid = self._key
		exit_code = details
		why = statusfmt(exit_code)
		proc = None
		for p in self._parent._proc_state:
			if pid == p.pid:
				proc = p
		if proc is None:
			log.error("Legion reported exit of unknown pid %s for task '%s' which %s",
								str(pid), self._name, why)
			return

		now = time.time()
		proc.pid = None
		proc.exit_code = exit_code
		proc.exited = now
		proc.pending_sig = None
		proc.next_sig = None
		self._parent._last_status = exit_code
		extant = len(self._parent.get_pids())
		if extant == 0:
			self._parent._started = None
			self._parent._stopping = None
			self._parent._stopped = now
			self._parent.onexit()
		else:
			log.debug("Task '%s' still has %d process%s running", self._name, extant, ses(extant, 'es'))
		if exit_code and not self._parent._terminated:
			log.warning("Task '%s' pid %d %s -- unexpected error exit", self._name, pid, why)
		else:
			log.info("Task '%s' pid %d %s", self._name, pid, why)

	def signal(self, details):
		"""
		Send a signal to all task processes.
	"""
		log = self._params.get('log', self._discard)
		if '_signal' not in dir(self._parent) or not callable(getattr(self._parent, '_signal')):
			log.error("Event parent '%s' has no '_signal' method", self._name)
			return
		sig = utils.signum(self._handler_arg)
		if sig is None:
			log.error("Invalid signal '%s' for task '%s'", self._handler_arg, sig._name)
			return
		log.info("sending %s to all '%s' processes", utils.signame(sig), self._name)
		self._parent._signal(sig)

	def legion_config(self, details):
		"""
		This just sets a flag to indicate that the config should be reloaded.
		That centralizes the reload code, but more important, it puts reloads in
		the event loop.  This avoids a problem when a config-change and the
		code needed to support it arrive in the same upgrade.  Even if the config
		change is seen first, the load will fail and then then code change is
		seen and the program will restart to pick up the code change.
	"""
		self._parent._reload_config = time.time()

	def legion_reset(self, details):
		now = time.time()
		self._parent._exiting = now
		self._parent._resetting = now
		self._parent.stop_all()

class Context(object):
	"""
	Base class for legion and task to hold common code dealing with
	context processing.
"""
	def _context_defines(self, context, conf):
		"""
		Apply any defines and role_defines from the current config.
		The config might be at the task level or the global (top) level.
		The order is such that a role_defines value will override
		a normal defines value.
	"""
		if conf and 'defines' in conf and isinstance(conf['defines'], dict):
			context.update(conf['defines'])
		if hasattr(self, '_legion'):
			roles = self._legion.get_roles()
		else:
			roles = self.get_roles()
		if conf and roles and 'role_defines' in conf and isinstance(conf['role_defines'], dict):
			for role in conf['role_defines']:
				if role in roles:
					context.update(conf['role_defines'][role])

	def _context_defaults(self, context, conf):
		"""
		Apply any defaults and role_defaults from the current config.
		The config might be at the task level or the global (top) level.
		The order is such that a role_defaults value will be applied before
		a normal defaults value so if present, the role_defaults is preferred.
	"""
		if hasattr(self, '_legion'):
			roles = self._legion.get_roles()
		else:
			roles = self.get_roles()
		if conf and roles and 'role_defaults' in conf and isinstance(conf['role_defaults'], dict):
			for role in conf['role_defaults']:
				if role in roles:
					for tag, val in conf['role_defaults'][role].items():
						if tag not in context:
							context[tag] = val
		if conf and 'defaults' in conf and isinstance(conf['defaults'], dict):
			for tag, val in conf['defaults'].items():
				if tag not in context:
					context[tag] = val

	def _get_list(self, value, context=None):
		"""
		Get a configuration value.  The result is None if "value" is None,
		otherwise the result is a list.

		"value" may be a list, dict, or str value.

		If a list, each element of the list may be a list, dict, or
		str value, and the value extraction proceeds recursively.

		During processing, if a dict is encountered, each element of
		the dict is checked for existence in the context.  If it
		exists the associated value will be processed recursively as
		before.

		The final result will be the flattened list resulting from the
		recursion.  Even if the initial "value" is a str, the result
		will be a list, with one element.
	"""
		log = self._params.get('log', self._discard)
		res = []
		if value is None:
			return res
		if context is None:
			context = self._context
		if isinstance(value, list):
			log.debug("Processing list %s", value)
			for v in value:
				res.extend(self._get_list(v, context=context))
		elif isinstance(value, dict):
			log.debug("Processing dict %s", value)
			for k in value:
				if k in context:
					res.extend(self._get_list(value[k], context=context))
		else:
			log.debug("Processing value '%s'", value)
			res.append(value)
		return res

	def _get(self, value, context=None, default=None):
		"""
		Similar to _get_list() except that the return value is required
		to be a str.  This calls _get_list() to retrieve the value,
		but raises an exception unless the return is None or a
		single-valued list when that value will be returned.

		If a default value is provided, it will be returned if the
		value passed is None.  It is not applied during recursion,
		but will be applied if the result of the recursion is None.
	"""
		if value is None:
			return default

		ret = self._get_list(value, context=context)
		if ret is None:
			return default
		name = getattr(self, '_name', None)
		if isinstance(ret, list):
			if len(ret) == 0:
				raise TaskError(name, "Value '%s' resolved to an empty list" % (value,))
			elif len(ret) == 1:
				return ret[0]
			else:
				raise TaskError(name, "Value '%s' resolved to a multi-valued list %s" % (value, str(ret)))
		else:
			raise TaskError(name, "Value '%s' resolved to unexpect type %s" % (value, type(ret).__name__))

class legion(Context):
	"""
Manage a group of daemons running disconnected from direct user interaction.
And yes, "legion" is the accepted collective noun for daemons ...
http://en.wikipedia.org/wiki/Legion_(demon)

The basic steps are to assoicate a legion with a configuration file (this
will ultimately be multiple files and watched config directories in future).
Once the legion has a configuration set, it is managed, which starts an event
loop.

The event loop will exit only if a SIGHUP or SIGTERM is received, and after tasks
have been shut down.  The action of these signals is the same except that manage()
returns on SIGTERM and raises LegionReset on SIGHUP.  If the caller receives
LegionReset it should restart, preferably by re-execing itself.  This is used to
perform a complete reset, including freeing any resources and restarting all
unadoptable tasks.

Events feeding the loop are process exit, signals, and file system changes.
Included in the file system change events are files being watched on behalf
of tasks, and the configuration file.  A change in the configuration file
will cause the legion to re-apply the new configurations to existing tasks
as well as stop and start tasks as needed.

Params are:
	log		- a logging object.  If not specified, log messages
			  will be discarded

	module_path     - a os.pathsep-separated string or a list of paths
			  to watch for module changes.  The default is to use
			  PYTHONPATH.  If the param is present and empty,
			  sys.path is used.  Caution should be used here
			  because this can cause the list of watched files
			  to grow very large.  The PYTHONPATH default is
			  normally a very good choice.
	http		- Listen address for HTTP management and statistics
			  service.
	control		- If true, allow operations that can change the legion
			  state such as change task control, resetting or
			  stopping the legion.
	certfile	- Enable SSL using this certificate file.
	expires		- Gives number of seconds before instance should
			  expire and shut itself down.  This is typically
			  only used for testing to ensure an instance does
			  not run forever in the case where the testing
			  sequence fails shut it down.
"""
	all_controls = frozenset(['off', 'once', 'event', 'wait', 'nowait', 'adopt', 'suspend'])
	run_controls = frozenset(set(list(all_controls)) - set(['off']))
	once_controls = frozenset(['once', 'event'])

	def __init__(self, **params):
		self._params = dict(params)
		self._discard = logging.getLogger(__name__)
		self._discard.addHandler(logging.NullHandler())

		log = self._params.get('log', self._discard)

		self.expires = None
		time_to_die = self._params.get('expires')
		if time_to_die:
			try:
				time_to_die = float(time_to_die)
				self.expires = time.time() + time_to_die
				log.info("Expire time set to %s from now", deltafmt(time_to_die))
			except Exception as e:
				log.warn("Bad 'expires' param value '%s' ignored", time_to_die)

		#  Set to the program name (as delivered by set_own_module).
		#  This is used to successfully dispatch legion events.
		#
		self._name = None

		#  Set to the time a termination signal is received.  When set, the
		#  manage() method will exit as soon as only adoptable tasks remain,
		#  or the sigterm_limit is reached.  If the termination signal is
		#  SIGHUP, self._resetting is also set.  This causes a LegionReset
		#  exception to be raised once task exit processing is complete.
		#
		self._exiting = None
		self._resetting = None

		#  Flag to request all tasks be stopped on the next management
		#  cycle.
		#
		self._do_stop_all = False

		#  The timeout on the next event wait.  Events will cause an earlier
		#  return, but idle processing can be accelerated by setting this
		#  value low.  The next_timeout() method provides a convenient
		#  method of managing the value.
		#
		self._timeout = 0.0

		#  Flag that a config change is pending.  The change will then
		#  be loaded as part of the idle processing in the event loop.
		#
		self._reload_config = None

		#  For any signals that will be caught, this records an existing
		#  function disposition.  If the signal arrives, the legion handler
		#  will chain to the the prior function.
		#
		self._signal_prior = {}

		#  Path to the roles file
		#
		self._roles_file = None

		#  The role-set is used to cause only tasks that mention
		#  an included role, or mention no roles, to be processes
		#  in an apply() call.  The possible role-set values are:
		#
		#	()	-  Empty set means only tasks with no
		#		   roles configured will be started
		#	True	-  Disable role filtering, all tasks
		#		   will be processed in apply() call.
		#		   This is the default mode.
		#	(roles)	-  A valid set of role names limits
		#		   processing to roles specified or
		#		   tasks with no roles.
		#
		self._role_set = None

		#  Used to build the prior context.  Can go away when the context is kept
		#  in the task.
		#
		self.prev_role_set = None

		self._config_file = None

		#  Most recently loaded config (dict from YAML)
		#
		self._config_running = None

		#  Currently running http servers, empty list if none.
		#
		self._http_servers = []

		#  The poll.poll() instance used by the event loop
		#
		self._pset = None

		try: self.host = socket.gethostname()
		except: self.host = None
		try: self.fqdn = socket.getfqdn()
		except: self.fqdn = None

		#  Index of all associated tasks by name
		#
		self._tasknames = {}
		self._tasks = set()
		self._tasks_scoped = set()

		#  Association of all pids with the task that owns the process
		#
		self._procs = {}

		#  The file watcher object.  This covers local watches like
		#  the config and role files, and files watched on behalf
		#  of tasks including non-python program executables.
		#
		self._watch_files = watch_files.watch(log=log, timeout=0.1, missing=True)
		self._file_event_map = {}
		if self._watch_files.get_mode() == watch_files.WF_POLLING:
			log.warning("watch_files.watch() has ended up in polling mode")
		else:
			log.info("watch_files.watch() is in %s mode", self._watch_files.get_mode_name())

		#  The module watcher object.  This covers module changes for the program
		#  itself and for managed programs that are flagged as python.
		#  See the 'module_path' param about how to limit the extent of the
		#  modules being watched.
		#
		self._watch_modules = watch_modules.watch(log=log, timeout=0.3,
						module_path=self._params.get('module_path', os.environ.get('PYTHONPATH')))
		self._module_event_map = {}

		#  The signal watcher.  This uses a self-pipe to cause the select event loop to
		#  wake on child-death.  This allows signals to be permanently set in restartable
		#  mode instead for havong to continually change their settings.
		#
		self._watch_child, self._wakeup = os.pipe()
		for fd in [self._watch_child, self._wakeup]:
			fl = fcntl.fcntl(fd, fcntl.F_GETFL)
			fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

	def _sig_handler(self, sig, frame):
		log = self._params.get('log', self._discard)
		if sig == signal.SIGCHLD:
			log.debug("Received SIGCHLD")
			try:
				os.write(self._wakeup, '*'.encode('utf-8'))
			except Exception as e:
				log.error("Write to self-pipe failed -- %s", str(e))
			return

		if sig in set([signal.SIGHUP, signal.SIGINT, signal.SIGTERM]):
			log.info("Stopping all unadoptable tasks on %s", utils.signame(sig))
			now = time.time()
			self._exiting = now
			if sig == signal.SIGHUP:
				self._resetting = now
			elif self._resetting:
				log.warn("Terminating signal arrived while resetting, coercing to exit")
				self._resetting = None
			self.stop_all()
		else:
			log.info("Relaying %s to all registered tasks", utils.signame(sig))
			self.signal_all(sig)
		if sig in self._signal_prior and type(self._signal_prior[sig]) == type(self._sig_handler):
			log.info("Chaining to prior signal handler %s", str(self._signal_prior[sig]))
			try:
				self._signal_prior[sig](sig, frame)
			except Exception as e:
				log.error("Exception from chained handler %s -- %s",
								str(self._signal_prior[sig]), str(e))
			else:
				log.info("Prior signal handler %s returned", str(self._signal_prior[sig]))

	def schedule_exit(self, now=None):
		if not now:
			now = time.time()
		self._exiting = now
		self._do_stop_all = True
		self.next_timeout()

	def schedule_reset(self, now=None):
		if not now:
			now = time.time()
		self._resetting = now
		self.schedule_exit(now)

	def is_exiting(self):
		return self._exiting is not None

	def is_resetting(self):
		return (self._exiting is not None and self._resetting is not None)

	def next_timeout(self, timeout = def_short_cycle):
		prev_timeout = self._timeout
		if self._timeout > timeout:
			self._timeout = timeout
		return prev_timeout

	def _set_handler(self, sig, ignore=False):
		prior = signal.getsignal(sig)
		if ignore and prior == signal.SIG_IGN:
			return
		signal.signal(sig, legion_create_handler(self))
		self._signal_prior[sig] = prior

		#  Mark all signals as restartable as signal-triggered operations
		#  happen either via a select on a self-pipe or by flags and rapid
		#  polling.
		#
		signal.siginterrupt(sig, False)

	def _fmt_set(self, val):
		if val is None:
			return 'None'
		elif not val:
			return '()'
		else:
			return '(' + ', '.join(val) + ')'
	def _context_build(self, pending=False):
		"""
		Create a context dict from standard legion configuration.

		The context is constructed in a standard way and is passed to str.format() on configuration.
		The context consists of the entire os.environ, the config 'defines', and a set
		of pre-defined values which have a common prefix from 'context_prefix'.

		This is similar to the task conext but without the task-specific entries.
	"""
		log = self._params.get('log', self._discard)
		log.debug("called with pending=%s", pending)
		if pending:
			conf = self._config_pending
		else:
			conf = self._config_running
		if not conf:
			log.warning("No config available") 
			conf = {}

		#  Build context used to format process args.
		#
		context = {
			context_prefix+'host': self.host,
			context_prefix+'fqdn': self.fqdn
		}

		#  Add the environment to the context
		#
		context.update(os.environ)

		if conf:
			self._context_defines(context, conf)
			self._context_defaults(context, conf)
		else:
			log.warning("No legion config available for defines") 
		return context

	def _get_http_services(self, http_list):
		"""
		Returns a list of httpd.HttpService instances which describe the HTTP
		services that should be started.

		The is built from the settings.http section of the configuration.
		The first element of that section is adjusted according to parameters
		which have been passed into the legion.  If settings.http is empty or
		missing but parameters are present, an httpd.HttpService instance will
		built using just the parameters and the returned list will contain
		just that entry.
	"""
		log = self._params.get('log', self._discard)
		listen_param = self._params.get('http')
		services = []
		if len(http_list) > 0:
			for service in http_list:
				s = httpd.HttpService()
				for att in ['listen', 'allow_control', 'certfile', 'timeout']:
					val = service.get(att)
					if val is not None:
						setattr(s, att,  _fmt_context(self._get(val), self._context))
				services.append(s)
		elif listen_param is not None:
			services.append(httpd.HttpService())
		if services:
			if listen_param is not None:
				log.debug("Service 0 listen from args: %s", listen_param)
				services[0].listen = listen_param
			val = self._params.get('control')
			if val is not None:
				log.debug("Service 0 control from args: %s", val)
				services[0].allow_control = val
			val = self._params.get('certfile')
			if val is not None:
				log.debug("Service 0 certfile from args: %s", val)
				services[0].certfile = val
		return services

	def _manage_http_servers(self):
		"""
		Compares the running services with the current settings configuration
		and adjusts the running services to match it if different.

		The services are identified only by their postion in the server list,
		so a change than only involves a position move will cause a shuffle
		in multiple services.  They don't change often so this isn't much
		of a problem.

		The method attempts to create all services.  If any service
		creation fails, the slot is set to None, the error is logged and
		a self._http_retry is set to when another attempt should be made.
		The method should be called whenever self._http_retry has expired.
		The presumption is that the error was transient (already in use, etc)
		and a retry might bring the service up.
	"""
		log = self._params.get('log', self._discard)

		if not self._config_running:
			raise Exception('Attempt to create HTTP services before config loaded')
		conf = self._config_running
		need = self._get_http_services(conf['settings']['http']
						if 'settings' in conf and 'http' in conf['settings'] else [])

		#  If the service count has changed, close all servers and rebuild from scratch.
		#
		if len(self._http_servers) != len(need):
			log.info("HTTP services count changed from %d to %d, reconfiguring all services",
						len(self._http_servers), len(need))
			pos = 0
			for server in self._http_servers:
				if server:
					if self._pset:
						try: self._pset.unregister(server)
						except: pass
					try: server.close()
					except: pass
					log.debug("Slot %d service closed", pos)
				pos += 1
			self._http_servers = []

		self._http_retry = None
		for pos in range(len(need)):
			if len(self._http_servers) > pos:
				if self._http_servers[pos]:
					if need[pos].cmp(self._http_servers[pos]._http_service):
						log.debug("No change in service slot %d: %s", pos, str(need[pos]))
						continue
					else:
						log.debug("Slot %d service changing from %s",
									pos, str(self._http_servers[pos]._http_service))
						if self._pset:
							try: self._pset.unregister(self._http_servers[pos])
							except: pass
						try: self._http_servers[pos].close()
						except: pass
						self._http_servers[pos] = None
				else:
					log.debug("No existing service in slot %d", pos)
			else:
				log.debug("Increasing services list for slot %d", pos)
				self._http_servers.append(None)

			#  At this point the service slot exists and is empty.  We'll attempt to fill it.
			try:
				server = httpd.server(need[pos], log=log)

				#  Add our own attribute to retain the service information
				#
				server._http_service = need[pos]

				manage.http(self, server, log=log)
				status.http(self, server, log=log)
				if self._pset:
					self._pset.register(server, poll.POLLIN)
				self._http_servers[pos] = server
				log.info("Slot %d service is now %s", pos, str(server._http_service))
			except Exception as e:
				log.error("Failed to create server slot %d on %s -- %s", pos, str(need[pos]), str(e))
				if not self._http_retry:
					self._http_retry = time.time() + service_retry_limit

	def _load_roles(self):
		"""
		Load the roles, one per line, from the roles file.  This is
		called at startup and whenever the roles file changes.

		Note that it is not strictly an error for the roles file to
		be missing but a warning is logged in case that was not
		intended.

		Returns True if there was a change in roles, False otherwise.
		On any change, the config should be reapplied except this is
		typically skipped at startup as the first apply() will not
		yet have happened.
	"""
		log = self._params.get('log', self._discard)

		new_role_set = None
		if self._roles_file:
			try:
				with open(self._roles_file, 'r') as f:
					new_role_set = set()
					for line in f:
						line = line.strip()
						if line and not re.match(r'^\s*#', line):
							new_role_set.add(line)
			except Exception as e:
				log.warning("Open failed on roles file '%s' -- %s", self._roles_file, str(e))
		if self._role_set == new_role_set:
			log.info("Roles file check gave no changes from current set '%s'", self._fmt_set(new_role_set))
			return False
		elif self._role_set is None:
			log.info("Roles set to: %s", self._fmt_set(new_role_set))
		else:
			log.info("Roles changing from '%s' to '%s'", self._fmt_set(self._role_set), self._fmt_set(new_role_set))
		self._prev_role_set = self._role_set
		self._role_set = new_role_set
		return True

	def set_roles_file(self, path):
		"""
		Load all roles from the roles file, and watch for future role
		changes.  When the roles file changes, it will be read and the
		current configuration re-applied so that any role-induced
		changes are processed.

		Once loaded, the roles are presented as a set.  If there is
		no role file, the role set is None and role processing is
		inhibited (all tasks are in scope).  If the file exists but
		is empty, then the role set is the empty set, and only tasks
		with no role list will be in scope.  Otherwise the contents
		is parsed as a set of roles, one per line.
	"""
		log = self._params.get('log', self._discard)
		if path != self._roles_file:
			if self._roles_file:
				log.info("Roles file changed from '%s' to '%s'", self._config_file, path)
				self.file_del(self, paths=[self._roles_file])
			else:
				log.info("Roles file set to '%s'", path)
			self._roles_file = path
			self.file_add(event_target(self, 'legion_config', log=log), path)
		return self._load_roles()

	def get_roles_file(self):
		return self._roles_file

	def get_roles(self, previous=False):
		if previous:
			return self._prev_role_set
		else:
			return self._role_set

	def _load_config(self):
		"""

		Load the config which must contain YAML text.  This is called
		at startup and whenever it changes.

		Returns True if there was a change in config, False otherwise.
		On any change, the config should be reapplied.
	"""
		log = self._params.get('log', self._discard)

		new_config = None
		if self._config_file:
			try:
				with open(self._config_file, 'r') as f:
					new_config = yaml.safe_load(f)
				if 'tasks' not in new_config:
					raise Exception("File '%s' does not contain a valid config" % (self._config_file,))
			except Exception as e:
				log.error("Load of config from '%s' failed -- %s", self._config_file, str(e))
				return False
		else:
			log.error("Invalid config file")
			return False

		self._config_running = new_config

		for name in self._tasknames:
			if name not in new_config['tasks']:
				self._tasknames[name][0].terminate()
		for name in new_config['tasks']:
			if name in self._tasknames:
				t = self._tasknames[name][0]
			else:
				t = task(name, self, **self._params)
			t.set_config(new_config['tasks'][name])
		self._apply()
		return True

	def set_config_file(self, path):
		"""
		Set the config file.  The contents must be valid YAML and there
		must be a top-level element 'tasks'.  The listed tasks will be
		started according to their configuration, and the file will
		be watched for future changes.  The changes will be activated
		by appropriate changes to the running tasks.
	"""
		log = self._params.get('log', self._discard)
		if path != self._config_file:
			if self._config_file:
				log.info("Config file changed from '%s' to '%s'", self._config_file, path)
				self.file_del(self, paths=[self._config_file])
			else:
				log.info("Config file set to '%s'", path)
			self._config_file = path
			self.file_add(event_target(self, 'legion_config', log=log), path)
		return self._load_config()

	def set_own_module(self, path):
		"""
		This is provided so the calling process can arrange for processing
		to be stopped and a LegionReset exception raised when any part of
		the program's own module tree changes.
	"""
		log = self._params.get('log', self._discard)
		self._name = path
		self.module_add(event_target(self, 'legion_reset', key=path, log=log), path)

	def get_config_file(self):
		return self._config_file

	def stop_all(self):
		for name, tinfo in self._tasknames.items():
			tinfo[0].stop()
			
	def task_add(self, t, periodic=None):
		"""
		Register a task in this legion.  "periodic" should be None, or
		a callback function which will be called periodically when the
		legion is otherwise idle.
	"""
		name = t.get_name()
		if name in self._tasknames:
			raise TaskError(name, 'Task already exists with %d daemon%s active' %
							(len(self._tasknames), ses(len(self._tasknames))))
		self._tasknames[name] = (t, periodic)
		self._tasks.add(t)

	def task_del(self, t):
		"""
		Remove a task in this legion.
		If the task has active processes, an attempt is made to
		stop them before the task is deleted.
	"""
		name = t._name
		if name in self._tasknames:
			del self._tasknames[name]
		self._tasks.discard(t)
		self._tasks_scoped.discard(t)
		try:
			t.stop()
		except:
			log = self._params.get('log', self._discard)
			log.error("Failed to stop processes for task '%s' -- %s",
							name, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
		for pid in t.get_pids():
			self.proc_del(pid)

	def task_get(self, taskname):
		if taskname in self._tasknames:
			return self._tasknames[taskname][0]
		else:
			return None

	def task_list(self, pending=True):
		"""
		Return the list of scoped tasks (ie tasks that have
		appropriate roles set) in correct execution order.

		The result is a list of task objects.
	"""
		log = self._params.get('log', self._discard)
		tasks = [t for t in self._tasks if t.participant()]
		requires = {}
		for t in tasks:
			requires[t] = t.get_requires(pending=pending)
		done = set()
		start_order = []
		cycle = 0
		while len(tasks) > len(start_order):
			cycle += 1
			changed = False
			for t in tasks:
				if t._name in done:
					continue
				needs = 0
				for req in requires[t]:
					if req._name in done:
						needs += 1
				if needs == len(requires[t]):
					changed = True
					start_order.append(t)
					done.add(t._name)
					log.debug("Found '%s' in scope", t._name)
			if not changed:
				log.error("Cycle %d failed after %s", cycle, str([t._name for t in set(tasks).difference(done)]))
				raise TaskError(None, "At cycle %d, startup order conflict, processed %s, remaining %s" %
						(cycle, str(done), str([t._name for t in set(tasks).difference(done)])))
		log.debug("Cycle %d gave %s", cycle, str([t._name for t in start_order]))
		return start_order

	def proc_add(self, ev):
		"""
		Associate a process with the specfied task.  The event is fired
		when the process exits, with details as the exit status.
	"""
		self._procs[ev.get_key()] = ev

	def proc_del(self, pid):
		"""
		Disassociate a process from the legion.  Note that is is almost
		always called by the task -- it doesn't attempt to stop the actual
		process so a direct call is almost always wrong.
	"""
		if pid in self._procs:
			del self._procs[pid]
		else:
			log = self._params.get('log', self._discard)
			log.warning("Process %d missing from proc list during deletion", pid)

	def module_add(self, ev, path=None):
		"""
		Register for python module change events.  If there is a module change, the
		task will be notified with a call t.event(action).
	"""
		log = self._params.get('log', self._discard)
		key = ev.get_key()
		if key is None:
			raise TaskError(name, "Attempt to register python module event with no key available")
		log.debug("Adding path '%s' for task '%s', action %s", str(path), str(ev.get_name()), ev._handler_name)
		self._watch_modules.add(key, command_path=path)
		self._module_event_map[key] = ev

	def module_del(self, key):
		"""
		Deregister from python module change events.
	"""
		if key in self._module_event_map:
			del self._module_event_map[key]
		if key in self._watch_modules.names:
			self._watch_modules.remove(key)

	def file_add(self, ev, paths):
		"""
		Register for file change events.  If there is a change to the file, all
		registered tasks will be notified with a call t.event(action).

		Note that as multiple tasks might register an event on the same
		path, each path is mapped to a dict of tasks pointing at actions.
		A task can only register a single action with each path.
	"""
		log = self._params.get('log', self._discard)
		if not isinstance(paths, list):
			paths = [paths]
		for path in paths:
			if path not in self._file_event_map:
				self._watch_files.add(path)
				self._file_event_map[path] = {}
			self._file_event_map[path][ev.get_key()] = ev
		log.debug("Added event key '%s', action '%s' to path%s: %s",
					str(ev.get_key()), ev._handler_name, ses(len(paths)), str(paths))

	def file_del(self, key, paths=None):
		"""
		Deregister a task for file event changes.  If paths is None, all
		paths assoicated with the task will be deregistered.
	"""
		if paths is None:
			paths = []
			for path in self._file_event_map:
				if key in self._file_event_map[path]:
					paths.append(path)
		elif not isinstance(paths, list):
			paths = [paths]
		for path in paths:
			if key in self._file_event_map[path]:
				del self._file_event_map[path][key]
			if path in self._file_event_map and not self._file_event_map[path]:
				self._watch_files.remove(path)
				del self._file_event_map[path]

	def _reap(self):
		"""
		Reap all processes that have exited.  We try to reap bursts of
		processes so that groups that cluster will tend to restart in the
		configured order.
	"""
		log = self._params.get('log', self._discard)
		try:
			cnt = len(os.read(self._watch_child, 102400))
			log.debug("%d byte%s read from self-pipe", cnt, ses(cnt))
		except OSError as e:
			if e.errno != errno.EAGAIN:
				log.error("Self-pipe read failed -- %s", str(e))
		except Exception as e:
			log.error("Self-pipe read failed -- %s", str(e))
		reaped = False
		while True:
			try:
				(pid, status) = os.waitpid(-1, os.WNOHANG)
			except OSError as e:
				if e.errno == errno.ECHILD:
					log.debug("No children to wait for")
					pid = 0
				else:
					raise e
			if pid > 0:
				reaped = True
				if pid in self._procs:
					log.debug("Pid %d exited, firing event", pid)
					self._procs[pid].handle(status)
					self.proc_del(pid)
				else:
					log.error("Unknown pid %d %s, ignoring", pid, statusfmt(status))
				continue
			else:
				return reaped

	def _apply(self):
		log = self._params.get('log', self._discard)
		self._context = self._context_build()

		self._manage_http_servers()

		target_tasks = self.task_list()
		for t in set(self._tasks_scoped):
			if t not in target_tasks:
				log.info("Removing task '%s' from scope", t.get_name())
				self._tasks_scoped.discard(t)
				t.stop()
		for t in target_tasks:
			if t not in self._tasks_scoped:
				log.info("Adding task '%s' to scope", t.get_name())
				self._tasks_scoped.add(t)
			t.apply()

	def manage(self):
		log = self._params.get('log', self._discard)
		timeout_short_cycle = self._params.get('short_cycle', def_short_cycle)
		timeout_long_cycle = self._params.get('long_cycle', def_long_cycle)

		self._set_handler(signal.SIGHUP)
		self._set_handler(signal.SIGINT, ignore=True)
		self._set_handler(signal.SIGCHLD)
		self._set_handler(signal.SIGTERM)
		self._apply()

		last_timeout = None
		last_idle_run = time.time()
		exit_report = 0
		self._pset = poll.poll()
		log.info("File event polling via %s from %s available",
						self._pset.get_mode_name(), self._pset.get_available_mode_names())
		self._pset.register(self._watch_child, poll.POLLIN)
		self._pset.register(self._watch_modules, poll.POLLIN)
		self._pset.register(self._watch_files, poll.POLLIN)

		for server in self._http_servers:
			if server:
				self._pset.register(server, poll.POLLIN)

		try:
			while True:
				now = time.time()
				if self._do_stop_all:
					self._do_stop_all = False
					self.stop_all()

				if self._exiting:
					if self._exiting + sigterm_limit < time.time():
						log.warning("Limit waiting for all tasks to exit was exceeded")
						break
					still_running = 0
					for t in self._tasks_scoped:
						still_running += len(t.get_pids())
					if still_running == 0:
						log.info("All tasks have stopped")
						break
					if exit_report + 1 < now:
						log.warning("Still waiting for %d process%s",
									still_running, ses(still_running, 'es'))
						exit_report = now
					self.next_timeout()
				if self.expires:
					if self.expires < now:
						if self._exiting:
							log.debug("Legion expiration reached %s ago, still exiting",
											deltafmt(now - self.expires))
						else:
							log.warning("Legion expiration reached %s ago",
											deltafmt(now - self.expires))
							self._exiting = now
						self.stop_all()
					else:
						log.debug("expires in %s", deltafmt(self.expires - now))

				if last_timeout != self._timeout:
					log.debug("select() timeout is now %s", deltafmt(self._timeout))
					last_timeout = self._timeout
				try:
					evlist = self._pset.poll(self._timeout*1000)
				except OSError as e:
					if e.errno != errno.EINTR:
						raise e
					else:
						log.debug("Ignoring %s(%s) during poll", e.__class__.__name__, str(e))

				self._timeout = timeout_long_cycle

				idle_starving = (last_idle_run + idle_starvation < now)
				if idle_starving:
					log.warning("Idle starvation detected, last run was %s ago", deltafmt(now - last_idle_run))
				if idle_starving or not evlist:
					log.debug("idle")
					last_idle_run = now

					if self._reap():
						self.next_timeout()

					if self._http_retry and self._http_retry < now:
						self._manage_http_servers()

					#  Manage tasks.  The tasks themselves figure out what might need to
					#  happen.
					#
					for t in set(self._tasks_scoped):
						if t.manage():
							self.next_timeout()

					if self._reload_config:
						try:
							log.info("Reloading config for change from %s ago",
									deltafmt(time.time() - self._reload_config))
							self._load_roles()
							self._load_config()
							self._reload_config = None
						except Exception as e:

							log.error("Config load sequence failed -- %s", str(e), exc_info=True)

					#  Housekeeping
					#
					self._watch_files.scan()
					self._watch_modules.scan()

				else:
					for item, mask in evlist:
						if item in self._http_servers:
							item.handle_request()
							continue
						if item == self._watch_child:
							if self._reap():
								self.next_timeout()
							continue

						log.debug("Activity: %s", str(item))

						#  This may need work.  For now, all selectable events
						#  give back objects that have a 'get' method, and it
						#  is possible to choose an action based on the shape
						#  of the value returned.
						#
						if not callable(getattr(item, 'get')):
							log.error("Selected %s object has no 'get' method", type(item).__name__)
							continue
						for tgt in item.get():
							if isinstance(tgt, tuple):
								name = tgt[0]
								cmd = tgt[1]
								paths = tgt[2]
								if len(paths) > 2:
									desc = str(len(paths))+' files'
								else:
									desc = ','.join(paths)
								log.info("Handling module %s change for task '%s'", desc, name)
								if name not in self._module_event_map:
									log.error("Ignoring unknown python module '%s' in event",
													name)
									continue
								self._module_event_map[name].handle(name)
							else:
								path = tgt
								if path not in self._file_event_map:
									log.error("Ignoring unknown file path %s from event",
													repr(path))
									continue
								log.info("file_change event for '%s'", path)
								for key, ev in self._file_event_map[path].items():
									log.debug("dispatching '%s' event", key)
									ev.handle(path)
		except Exception as e:
			log.error("unexpected error -- %s", str(e), exc_info=True)
			raise e
		finally:
			#  If we reach here and _exiting is not set then something bad
			#  happened.  Make an attempt to shut everything down before
			#  leaving.
			#
			if not self._exiting:
				log.warning("Unexpected exit -- attempting to stop all tasks")
				try:
					self.stop_all()
				except Exception as ee:
					log.error("Failsafe attempt to stop tasks failed -- %s", str(ee))
			for server in self._http_servers:
				if server:
					try: self._pset.unregister(server)
					except: pass
					try: server.server.close()
					except: pass
			self._http_servers = []
			#  Reset all signal handlers to their entry states
			log.debug("reseting signals")
			for sig, state in self._signal_prior.items():
				signal.signal(sig, state)
		if self._resetting:
			raise LegionReset()

class ProcessState(object):
	"""
	Record the process state for each task.  Tasks will
	have one or more processes associated with them, recorded
	in task._proc_state, a list ProcessState instances.
	The list is maintained with active processes recorded
	in range(count) of the task._proc_state list.
"""
	instance = None		#  This should always match the list position in _proc_state
	pid = None		#  Process ID of the process in this slot
	exit_code = None	#  Exit code from this slot's last process exit if any
	started = None		#  When this slot's process was last started
	exited = None		#  When this slot's process last exited
	next_sig = None		#  When to send an escalated signal to this process
	pending_sig = None	#  The signal to send if next_sig doesn't expire

class task(Context):
	"""
Manage daemon tasks.

A task represents one or more processes that are configured, started, and
stopped in exactly the same manner and at the same time.  Normally, a task
manages a single daemon but the approach provides for those cases where
application functions can be routed to multiple worker daemons.

Each task has a configuration (config_pending) and a running state (config_running).
The pending config can be updated at will.  The running config should be
regarded as read-only.

At some point, the apply() method is called and any necessary changes will
be made to the associated processes that at needed to match the pending config.
This will typically involve restarting processes.  Once apply() has completed,
the pending config becomes the running config.

Task instances can't reasonably be created independently from a legion, which
is needed to:

  -	Direct events like process termination to the correct
	daemon_spawn instance for restart.
  -	Detect file change events in watched files and trigger
	appropriate daemon_spawn actions (like restarting the
	processes when the executable changes).

So, each instance must register child PIDs, files to watch, etc with the
legion instance.

Params are:
	log	- a logging object.  If not specified, log messages
		  will be discrded
"""

	def __init__(self, name, task_legion, **params):
		if not isinstance(task_legion, legion):
			raise TaskError(name, "Specified legion is not an instance of the class 'legion'")
		self._legion = task_legion
		if not name:
			raise TaskError(name, "No name specified")
		self._name = str(name)
		self._params = dict(params)
		self._discard = logging.getLogger(__name__)
		self._discard.addHandler(logging.NullHandler())
		self._config_running = None
		self._config_pending = None
		self._proc_state = []
		self._last_status = None

		#  Caches the executable path once it is looked up with get_path()
		#
		self._path = None

		self._reset_state()

		self._last_message = 0

		self._context = None

		#  Register with legion
		self._legion.task_add(self, periodic=self._task_periodic)

	def close(self):
		log = self._params.get('log', self._discard)
		if self._legion:
			try:
				self._event_deregister()
			except Exception as e:
				log.warning("Task '%s' event deregister failed -- %s",
							self._name, str(e), exc_info=log.isEnabledFor(logging.INFO))
			try:
				self._legion.task_del(self)
			except Exception as e:
				log.warning("Task '%s' legion delete -- %s",
							self._name, str(e), exc_info=log.isEnabledFor(logging.INFO))
		else:
			log.warning("Task '%s' has no associated legion -- close skipped", self._name)

	def _reset_state(self):
		"""
		State flags.  These hold the time of the change in the particular state, or
		None if there has been no such state change yet.

		starting      - Indicates the task is in the process of starting.  This flag
				inhibits further startup attempts.
		started       - Indicates the task has been fully started.  As long as this
				is not a "once" task, other tasks that require this task may
				now start.
		stopping      - Indicates the task has commenced stopping.  It is set immediately
				for "once" tasks (they are effectively stopping as soon as they
				start), and for other tasks when the task's stop() method has been
				called.  The stop() method is called when the legion receives a
				signal to shutdown, and during legion configuration changes where it
				is determined that the process characteristics might have changed
				(command line, environment, etc).
		terminated    - Indicates the task default stop mechanism has been triggered.  Tasks
				that are "stopping" but not "terminated" are generally "once" tasks.
				This also softens the log message when the process actually exits.
				Unexpected process exits will be flagged with a warning message
				instead of the usual info message.
		killed        - Indicates the task default stop mechanism has not terminated all
				processes in the task, and the mechanism has been escalated to kill.
		stopped       - Indicates that all processes in the task have terminated and the
				task is now completely stopped.  Only valid if "starting" is set.
		dnr           - Indicates that this task is scheduled for destruction.  Once all
				processes have stopped, it should delete itself.
		limit         - Time after which this task should be stopped.
	"""
		self._starting = None
		self._started = None
		self._suspended = None
		self._stopping = None
		self._terminated = None
		self._killed = None
		self._stopped = None
		self._dnr = None
		self._limit = None

	def get_name(self):
		return self._name

	def _context_build(self, pending=False):
		"""
		Create a context dict from standard task configuration.

		The context is constructed in a standard way and is passed to str.format() on configuration.
		The context consists of the entire os.environ, the config 'defines', and a set
		of pre-defined values which have a common prefix from 'context_prefix'.
	"""
		log = self._params.get('log', self._discard)
		log.debug("called with pending=%s", pending)
		if pending:
			conf = self._config_pending
		else:
			conf = self._config_running
		if not conf:
			log.warning("No config available") 
			conf = {}

		#  Initially create the context as a copy of the environment.
		#
		context = os.environ.copy()

		#  Merge in the built-in items.  It is important that these
		#  will override any values from the environment as they will
		#  have come from a parent instance of "taskforce".
		#
		context.update(
			{
				context_prefix+'instance': None,
				context_prefix+'pid': None,
				context_prefix+'name': self._name,
				context_prefix+'ppid': os.getpid(),
				context_prefix+'host': self._legion.host,
				context_prefix+'fqdn': self._legion.fqdn
			}
		)

		#  Add certain config values to the context
		for tag in ['user', 'group', 'pidfile', 'cwd']:
			if tag in conf:
				context[context_prefix+tag] = self._get(conf[tag], context=context)

		if self._legion._config_running:
			self._context_defines(context, self._legion._config_running)
		else:
			log.warning("No legion config available for defines") 
		self._context_defines(context, conf)

		self._context_defaults(context, conf)
		if self._legion._config_running:
			self._context_defaults(context, self._legion._config_running)
		else:
			log.warning("No legion config available for defaults") 

		return context

	def get_path(self):
		if self._path is not None:
			return self._path
		log = self._params.get('log', self._discard)
		if 'commands' in self._config_running and 'start' in self._config_running['commands']:
			name = _fmt_context(self._config_running['commands']['start'], self._context)
			if isinstance(name, list):
				name = name[0]
			if os.path.basename(name) != name:
				log.debug("Task '%s' path '%s' (direct from 'start' command)", self._name, name)
				return name
			log.debug("Task '%s' using '%s' from 'start' command for path lookup", self._name, name)
		else:
			name = self._name
			if os.path.basename(name) != name:
				log.debug("Task '%s' path '%s' (direct from task name)", self._name, name)
				return name
			log.debug("Task '%s' using task name for path lookup", self._name, name)
		path_list = self._params.get('path', os.environ['PATH']).split(os.pathsep)
		for dir in path_list:
			path = os.path.join(dir, name)
			try:
				if os.access(path, os.R_OK|os.X_OK):
					self._path = path
					break
			except:
				continue
		if self._path is None:
			raise TaskError(self._name, "Could not determine full path for task executable")
		log.debug("Task '%s' using '%s' from path lookup of '%s'", self._name, self._path, name)
		return self._path

	def get_pids(self):
		return [i.pid for i in self._proc_state if i.pid is not None]

	def get_config(self, pending=False):
		log = self._params.get('log', self._discard)
		log.debug("%s '%s' config", 'pending' if pending else 'running', self._name)
		if pending:
			return self._config_pending
		else:
			return self._config_running

	def get_requires(self, pending=False):
		log = self._params.get('log', self._discard)
		context = self._context_build(pending=pending)
		conf = self.get_config(pending=pending)
		req = self._get_list(conf.get('requires'), context=context)
		requires = []
		for item in req:
			r = _fmt_context(item, context)
			if r is None:
				raise TaskError(self._name, 'Task "requires" element "%s" is invalid' % (item,))
			if r in self._legion._tasknames:
				requires.append(self._legion._tasknames[r][0])
			else:
				raise TaskError(self._name, "Task requires separate task '%s' that does not exist" % (r,))
		if requires:
			log.debug("%s '%s' requires: %s",
				'Pending' if pending else 'Running', self._name, ', '.join([t._name for t in requires]))
		return requires

	def set_config(self, config):
		log = self._params.get('log', self._discard)
		log.debug("for '%s'", self._name)
		self._config_pending = config.copy()

	def participant(self):
		"""
		True if the tasks roles meet the legion's constraints,
		False otherwise.
	"""
		log = self._params.get('log', self._discard)
		context = self._context_build(pending=True)
		conf = self._config_pending

		if conf.get('control') == 'off':
			log.debug("Excluding task '%s' -- control is off", self._name)
			return False

		#  If role-set is None (but not the empty set)
		#  then role processing is inhibited.
		#
		active_roles = self._legion.get_roles()
		if active_roles is None:
			log.debug("Including task '%s' -- role processing is inhibited", self._name)
			return True

		#  If roles are present, at least one has to match the role-set.
		#  If none are present, the task is always included.
		#
		roles = self._get_list(conf.get('roles'), context=context)

		#  If a task has no roles listed, then it particpates
		#  in all roles:
		#
		if not roles:
			log.debug("Including task '%s' -- no explicit roles", self._name)
			return True

		for role in roles:
			if role in active_roles:
				log.debug("Including task '%s' -- has role '%s'", self._name, role)
				return True
		log.debug("Excluding task '%s' -- no role matches %s", self._name, str(active_roles))
		return False

	def _make_event_target(self, event, control):
		log = self._params.get('log', self._discard)
		handler = None
		arg = None
		for h in ['command', 'signal']:
			val = self._get(event.get(h))
			if val:
				if control in self._legion.once_controls and h == 'command' and val == 'stop':
					log.warning("Ignoring '%s' %s event for %s task", val, h, control)
					return None
				handler = h
				arg = val
				break
		if not handler:
			raise TaskError(self._name, "Event type '%s' has no handler defined" % (str(event.get('type')),))
		return event_target(self, handler, arg=arg, key=self._name, log=log)

	def _event_register(self, control):
		"""
		Do all necessary event registration with the legion for
		events listed in the pending config.  The default event
		action is to stop the task.
	"""
		log = self._params.get('log', self._discard)
		if 'events' not in self._config_running:
			log.debug("No events present for task '%s'", self._name)
			return
		for event in self._config_running['events']:
			ev_type = self._get(event.get('type'))
			if not ev_type:
				log.error("Ignoring event in task '%s' with no type", self._name)
				continue
			ev = self._make_event_target(event, control)
			if ev is None:
				continue
			log.debug("Adding event type '%s' for task '%s'", ev_type, self._name)
			if ev_type == 'self':
				self._legion.file_add(ev, self.get_path())
			elif ev_type == 'python':
				self._legion.module_add(ev, path=self.get_path())
			elif ev_type == 'file_change':
				path = self._get_list(event.get('path'))
				if path:
					self._legion.file_add(ev, _fmt_context(path, self._context))
				else:
					log.error("Ignoring %s event in task '%s' with no path", ev_type, self._name)
			elif ev_type in ['stop', 'restart']:
				log.debug("No task '%s' registration action for '%s' event", self._name, ev_type)
			else:
				log.error("Ignoring unknown event type '%s' in task '%s'", ev_type, self._name)
			
	def _event_deregister(self):
		"""
		Deregister all legion events associated with this task
		(or possibly those listed in the current config, but it
		would be better to base deregistration on the task name).
	"""
		log = self._params.get('log', self._discard)
		if 'events' not in self._config_running:
			log.debug("No events present for task '%s'", self._name)
			return
		for event in self._config_running['events']:
			ev_type = self._get(event.get('type'))
			if ev_type == 'python':
				self._legion.module_del(self._name)
			elif ev_type == 'self':
				self._legion.file_del(self._name)
			elif ev_type == 'file_change':
				self._legion.file_del(self._name)

	def _command_change(self):
		"""
		Returns True if the difference between the current and
		pending configs represents a change to the command.
		That comes down to these cases:
			-  No current config (startup case)
			-  No pending config (task deleted)
			-  Command changed (restart needed)
			-  Environment changed (restart needed)
	"""
		log = self._params.get('log', self._discard)
		if self._config_running is None:
			log.debug("Task '%s' change - no previous config", self._name)
			return True
		for elem in set(list(self._config_running) + list(self._config_pending)):
			#  Ignore these elements as they don't affect the operation of a process
			#  that is already running
			#
			if elem in ['control', 'pidfile', 'onexit', 'requires', 'start_delay']:
				continue
			if self._config_running.get(elem) != self._config_pending.get(elem):
				log.debug("Task '%s' change - '%s' text change", self._name, elem)
				return True
		new_context = self._context_build(pending=True)
		if self._context != new_context:
			if log.isEnabledFor(logging.DEBUG):
				log.debug("Task '%s' change - context change", self._name)
				for tag in set(list(self._context) + list(new_context)):
					o = self._context.get(tag)
					n = new_context.get(tag)
					if o != n:
						log.debug("    %s: %s -> %s", tag, str(o), str(n))
			return True
		log.debug("No changes in task '%s'", self._name)
		return False

	def _task_periodic(self):
		"""
		This is a callback that is registered to be called periodically
		from the legion.  The legion chooses when it might be called,
		typically when it is otherwise idle.
	"""
		log = self._params.get('log', self._discard)
		log.debug("periodic")
		self.manage()

	def _signal(self, sig, pid=None):
		"""
		Send a signal to one or all pids associated with this task.  Never fails, but logs
		signalling faults as warnings.
	"""
		log = self._params.get('log', self._discard)
		if pid is None:
			pids = self.get_pids()
		else:
			pids = [pid]
		for pid in pids:
			try:
				os.kill(pid, sig)
				log.debug("Signalled '%s' pid %d with %s", self._name, pid, utils.signame(sig))
			except Exception as e:
				log.warning("Failed to signal '%s' pid %d with %s -- %s",
									self._name, pid, utils.signame(sig), str(e))

	def onexit(self):
		"""
		Runs any "onexit" functions present in the config.  This will
		normally be called from the proc_exit event handler after all
		processes in a task have stopped.

		Currently the following "onexit" types are supported:

		  'start':	Set the specified task to be started.  It
				normally would not make sense for a task to set
				itself to run again (that's handled by the "control"
				element).  This handles the case where a task
				needs a "once" task to be rerun whenever it exits.
				For that reason, 'start' may only be issued against
				a "once" task.
	"""
		log = self._params.get('log', self._discard)
		conf = self._config_running
		if 'onexit' not in conf:
			log.debug("Task %s has no 'onexit' processing", self._name)
			return
		if self._legion.is_exiting():
			log.debug("Skipping task %s 'onexit' processing because legion is exiting", self._name)
			return
		item = 0
		for op in conf['onexit']:
			item += 1
			if 'type' not in op:
				log.error("Task %s 'onexit' item %d has no 'type'", self._name, item)
				continue
			op_type = self._get(op.get('type'))
			if op_type == 'start':
				if 'task' not in op:
					log.error("Task %s 'onexit' item %d type '%s' has no 'task'", self._name, item, op_type)
					continue
				taskname = self._get(op.get('task'))
				if taskname not in self._legion._tasknames:
					log.error("Task %s 'onexit' item %d type '%s' task '%s' does not exist",
										self._name, item, op_type, taskname)
					continue
				task = None
				for t in self._legion.task_list(pending=False):
					if taskname == t._name:
						task = t
				if not task:
					log.error("Task %s 'onexit' item %d type '%s' task '%s' exists but is out of scope",
										self._name, item, op_type, taskname)
					continue
				if task._config_running.get('control') not in self._legion.once_controls:
					log.error("Task %s 'onexit' item %d type '%s' task '%s' may only start 'once' tasks",
										self._name, item, op_type, taskname)
					continue
				log.info("Task '%s' marked to restart by task '%s'", taskname, self._name)
				task._reset_state()
			else:
				log.error("Unknown type '%s' for task %s 'onexit' item %d", op_type, self._name, item)
				continue

	def _shrink(self, needed, running):
		"""
		Shrink the process pool from the number currently running to
		the needed number.  The processes will be sent a SIGTERM at first
		and if that doesn't clear the process, a SIGKILL.  Errors will
		be logged but otherwise ignored.
	"""
		log = self._params.get('log', self._discard)
		log.info("%d process%s running, reducing to %d process%s", running, ses(running, 'es'), needed, ses(needed, 'es'))
		now = time.time()
		signalled = 0
		for proc in self._proc_state[needed:]:
			if proc.pid is None:
				continue
			if proc.pending_sig is None:
				proc.pending_sig = signal.SIGTERM
			if proc.next_sig is None or proc.next_sig < now:
				self._signal(proc.pending_sig, pid=proc.pid)
				signalled += 1
				proc.pending_sig = signal.SIGKILL
				proc.next_sig = now + sigkill_escalation
			else:
				log.debug("Process instance %d (pid %d) for task '%s' exit pending",
						proc.instance, proc.pid, self._name)
		log.info("%d process%s signalled", signalled, ses(signalled, 'es'))

	def _mark_started(self):
		"""
		Set the state information for a task once it has completely started.
		In particular, the time limit is applied as of this time (ie after
		and start delay has been taking.
	"""
		log = self._params.get('log', self._discard)

		now = time.time()
		self._started = now

		limit = self._config_running.get('time_limit')
		try:
			limit = float(_fmt_context(self._get(limit, default='0'), self._context))
			if limit > 0:
				log.debug("Applying task '%s' time limit of %s", self._name, deltafmt(limit))
				self._limit = now + limit
		except Exception as e:
			log.warn("Task '%s' time_limit value '%s' invalid -- %s",
				self._name, limit, str(e), exc_info=log.isEnabledFor(logging.DEBUG))

	def _start(self):
		"""
		Start a task, which may involve starting zero or more processes.

		This is indicated as an internal method because tasks are really
		only ever marked as startable by the configuration.  Any task
		that should be running and is not will be started during regular
		manage() calls.  A task set to run only once will be started only
		if the _stopped attribute is None.

		If a task requires another task, it won't be started until the
		required task has started, except if the required task has 'once'
		control, then it won't be started until the 'once' task has
		stopped.

		Currently, processes are started via direct fork/exec, with
		stdin/stdout/stderr all redirected from /dev/null.  In future,
		will probably add options to redirect stdout/stderr to syslog
		or files.

		Note that processes are intentionally not detached or put in
		separate process groups or terminal groups.  The presumption is
		that "async" and "adopt" tasks will handle this themselves, and
		we need "wait" tasks to not be detached.

		Returns True to request a shorter period before the next call,
		False if nothing special is needed.
	"""
		log = self._params.get('log', self._discard)
		if self._stopping:
			log.debug("%s task is stopping", self._name)
			return True
		now = time.time()
		conf = self._config_running
		control = self._get(conf.get('control'))
		once = (control in self._legion.once_controls)

		#  Tasks with "event" control are immediately marked stopped as if they
		#  ran at start.  This is the only difference between "event" and "once"
		#  controls.
		#
		if control == 'event' and not self._stopped:
			self._stopped = now
		if self._stopped:
			if self._dnr:
				log.info("Task '%s' stopped and will now be deleted", self._name)
				self.close()
				return False
			elif once:
				log.debug("'%s' task %s exited %s ago", control, self._name, deltafmt(time.time() - self._stopped))
				return False
			else:
				log.debug("Restarting %s, task was stopped %s ago",
							self._name, deltafmt(time.time() - self._stopped))
				self._reset_state()

		start_delay = self._get(conf.get('start_delay'))
		if start_delay:
			try:
				start_delay = int(start_delay)
			except Exception as e:
				log.error("Task '%s' has invalid start_delay '%s'", self._name, start_delay)
				start_delay = 0
		else:
			start_delay = 0
		if self._starting and not self._started:
			if now > self._starting + start_delay:
				log.info("%s task marked started after %s", self._name, deltafmt(now - self._starting))
				self._mark_started()
				return False
			log.debug("%s task has been starting for %s of %s",
					self._name, deltafmt(now - self._starting), deltafmt(start_delay))
			return True

		#  Check the required state to ensure dependencies have been started.  In the case of
		#  'once' controls, the dependency must have already stopped, otherwise it must have
		#  started.
		#
		if self._started and control != 'suspend':
			log.debug("Task '%s' already started, skipping requires-check", self._name)
		else:
			for req in self.get_requires():
				if req._config_running.get('control') == 'once':
					if not req._stopped:
						if self._last_message + repetition_limit < time.time():
							log.info("Task '%s' is waiting on '%s' to complete", self._name, req._name)
							self._last_message = now
						return True
				else:
					if not req._started:
						if self._last_message + repetition_limit < time.time():
							log.info("Task '%s' is waiting on '%s' to start", self._name, req._name)
							self._last_message = now
						return True

		self._last_message = 0
		if once:
			#  "once" processes are immediately marked as stopping.
			#
			self._stopping = now

		try:
			start_command = None
			if 'commands' in conf:
				start_command = self._get_list(conf['commands'].get('start'))
			if not start_command:
				raise TaskError(self._name, "No 'start' command in task configuration")
			if not isinstance(start_command, list):
				start_command = list(start_command)

			if control != 'suspend':
				needed = self._get(conf.get('count'), default=1)
				running = len(self.get_pids())
				if needed < running:
					self._shrink(needed, running)
					return False
				elif needed == running:
					log.debug("all %d needed process%s running", running, ses(running, 'es'))
					return False

			self._starting = now
			if not start_delay:
				self._mark_started()

			if control == 'suspend':
				if not self._suspended:
					log.debug("%s just moved to %s", self._name, repr(control))
					running = len(self.get_pids())
					if running > 0:
						log.debug("%s now %s, stopping running processes", self._name, repr(control))
						self._shrink(0, running)
					else:
						log.debug("%s is %s control, skipping process startup", self._name, repr(control))
						self._suspended = now
				return False
			else:
				if self._suspended:
					log.debug("%s just moved to %s", self._name, repr(control))
				self._suspended = None

			log.debug("Found %d running, %d needed, starting %d", running, needed, needed-running)
			started = 0
			for instance in range(needed):
				if instance < len(self._proc_state):
					proc = self._proc_state[instance]
					if proc.pid is not None:
						log.debug("%s instance %d already started", self._name, instance)
						continue
					if proc.started is None:
						proc.started = now
					last_start_delta = now - proc.started
					if last_start_delta < 0:
						#  This can happen when the system clock is manually set.  As one
						#  of the goals here is to restart ntpd when it dies due to exceeding
						#  the panic threshold (1000 seconds), go ahead and mark the time
						#  as now so the task restart will only be delayed slightly longer
						#  than normal.
						#
						log.warning("Time flowed backwards, resetting %s instance %d start time",
								self._name, instance)
						proc.started = now
						continue
					if last_start_delta < reexec_delay:
						log.debug("%s instance %d restart skipped, last attempt %s ago",
								self._name, instance, deltafmt(last_start_delta))
						continue
				else:
					log.debug("%s growing instance %d", self._name, instance)
					self._proc_state.append(ProcessState())
					proc = self._proc_state[instance]

				pid = _exec_process(start_command, self._context, instance=instance, log=log)
				log.debug("Forked pid %d for '%s', %d of %d now running",
							pid, self._name, len(self.get_pids()), needed)
				self._legion.proc_add(event_target(self, 'proc_exit', key=pid, log=log))
				proc.pid = pid
				proc.started = now
				started += 1

			log.info("Task %s: %d process%s scheduled to start%s",
					self._name, started, ses(started, 'es'),
					(' with time limit %s' % (deltafmt(self._limit - now),)) if self._limit else '')
		except Exception as e:
			log.error("Failed to start task '%s' -- %s", self._name, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
		return False

	def stop(self, task_is_resetting=False):
		"""
		Stop a task.  This stops all processes for the task.  The approach
		is to mark the task as "stopping" , send a SIGTERM to each process,
		and schedule a SIGKILL for some time later.

		If the legion or task is resetting and a "restart" event is in scope,
		that event will be fired rather than sending the SIGTERM.  Otherwise,
		if a "stop" event is in scope, that event will be fired.  In
		either case, the SIGKILL escalation will still occur so the
		recipient needs to process the event and exit promptly.

		Returns True to request a shorter period before the next call,
		False if nothing special is needed.
	"""
		log = self._params.get('log', self._discard)

		if self._stopped:
			log.debug("'%s' is already stopped", self._name)
			return False
		now = time.time()
		running = len(self.get_pids())
		if self._stopping and running == 0:
			log.debug("All '%s' processes are now stopped", self._name)
			self._reset_state()
			self._stopped = now
			return False
		if self._config_running:
			control = self._config_running.get('control')
		else:
			control = None
		if self._terminated:
			#  These are tasks that have been explicitly terminated but have not yet stopped
			#
			if self._killed:
				log.warning("%d '%s' process%s still running %s after SIGKILL escalation",
							running, self._name, ses(running, 'es'), deltafmt(now - self._killed))
			elif self._terminated + sigkill_escalation < now:
				log.warning("Excalating to SIGKILL with %d '%s' process%s still running",
							running, self._name, ses(running, 'es'))
				self._signal(signal.SIGKILL)
				self._killed = now
			else:
				log.debug("%d '%s' process%s still running %s after being terminated",
					running, self._name, ses(running, 'es'), deltafmt(now - self._terminated))
			return True
		if self._limit and now > self._limit:
			#  These are tasks that have a time limit set and it has expired.
			#  This case falls through to the stop code.
			log.info("Stopping task '%s', time limit exceeded %s ago", self._name, deltafmt(now - self._limit))
		elif self._stopping and not self._legion.is_exiting():
			#  These are tasks that are expected to stop soon but have not been explicitly
			#  terminated.  These are typically tasks with 'once' or 'event' controls.
			#  Unless there is a time limit set, they are allowed to run indefinitely
			#
			log.debug("%d '%s' '%s' process%s still running %s",
					running, self._name, control, ses(running, 'es'), deltafmt(now - self._stopping))
			return False

		if not self._stopping:
			self._stopping = now
		self._terminated = now
		restart_target = None
		stop_target = None
		resetting = self._legion.is_resetting() or task_is_resetting
		if self._config_running:
			for event in self._config_running.get('events', []):
				ev_type = self._get(event.get('type'))
				if resetting and ev_type == 'restart':
					restart_target = self._make_event_target(event, control)
				elif ev_type == 'stop':
					stop_target = self._make_event_target(event, control)
		if restart_target:
			log.debug("Restart event on %d '%s' process%s", running, self._name, ses(running, 'es'))
			restart_target.handle()
		elif stop_target:
			log.debug("Stop event on %d '%s' process%s", running, self._name, ses(running, 'es'))
			stop_target.handle()
		else:
			log.debug("Stopping %d '%s' process%s with SIGTERM", running, self._name, ses(running, 'es'))
			self._signal(signal.SIGTERM)
		return True

	def terminate(self):
		"""
		Called when an existing task is removed from the configuration.
		This sets a Do Not Resuscitate flag and then initiates a stop
		sequence.  Once all processes have stopped, the task will delete
		itself.
	"""
		log = self._params.get('log', self._discard)
		self._dnr = time.time()
		self.stop()
		log.info("Task '%s' marked for death", self._name)

	def apply(self):
		"""
		Make the pending config become the running config for this task
		by triggering any necessary changes in the running task.

		Returns True to request a shorter period before the next call,
		False if nothing special is needed.
	"""
		log = self._params.get('log', self._discard)
		if not self._config_pending:
			raise TaskError(self._name, "No configuration available to apply")

		control = self._config_pending.get('control')
		if not control:
			control = 'wait'

		log.debug("for '%s', control '%s'", self._name, control)
		if self._command_change() and len(self.get_pids()) > 0:
			self._event_deregister()
			self.stop(task_is_resetting=True)

		self._config_running = self._config_pending
		self._context = self._context_build()

		if control in self._legion.run_controls:
			self._event_register(control)
		return self.manage()

	def manage(self):
		"""
		Manage the task to handle restarts, reconfiguration, etc.

		Returns True to request a shorter period before the next call,
		False if nothing special is needed.
	"""
		log = self._params.get('log', self._discard)
		if self._stopping:
			log.debug("Task '%s', stopping, retrying stop()", self._name)
			return self.stop()
		now = time.time()
		if self._started and self._limit:
			if now > self._limit:
				log.debug("Task '%s', time limit exceeded by %s, stopping", self._name, deltafmt(now - self._limit))
				return self.stop()
			else:
				log.debug("Task '%s', time limit remaining %s", self._name, deltafmt(self._limit - now))
		if self._legion.is_exiting():
			log.debug("Not managing '%s', legion is exiting", self._name)
			return False
		log.debug("managing '%s'", self._name)
		return self._start()
