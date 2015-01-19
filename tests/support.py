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

import os, time, subprocess, fcntl, errno, logging, re

class env(object):
	"""
	Set up some generally useful parameters and manage the creation
	and destruction of the temp working dir.
"""
	def __init__(self, base='.'):
		self.base_dir = os.path.realpath(base)
		self.bin_dir = os.path.join(self.base_dir, "bin")
		self.test_dir = os.path.join(self.base_dir, "tests")
		self.temp_dir = os.path.join(self.test_dir, "tmp")
		self.examples_dir =  os.path.join(self.base_dir, "examples")
		self.examples_run = os.path.join(self.examples_dir, 'var', 'run')
		self.working_dir = self.examples_dir
		self.examples_bin = os.path.join(self.examples_dir, "bin")
		self.config_file = os.path.join(self.examples_dir, "example.conf")
		self.roles_file = os.path.join(self.temp_dir, 'test.roles')
		self.test_roles = ['frontend', 'backend']
		if not os.path.isdir(self.examples_run):
			os.makedirs(self.examples_run)
		if not os.path.isdir(self.temp_dir):
			os.makedirs(self.temp_dir)

	def __del__(self):
		try: os.rmdir(self.temp_dir)
		except: pass

def logger():
	if logger.log:
		return logger.log
	handler = logging.StreamHandler()
	handler.setFormatter(logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s"))
	logger.log = logging.getLogger(__name__)
	logger.log.addHandler(handler)
	log_level = None

	#  This cuts the logging noise in the travis output.
	#  Set NOSE_LOG_LEVEL in .travis.yml
	#
	if 'NOSE_LOG_LEVEL' in os.environ:
		try:
			log_level = getattr(logging, os.environ['NOSE_LOG_LEVEL'].upper())
		except:
			pass
		if log_level is None:
			try:
				log_level = int(os.environ['NOSE_LOG_LEVEL'])
			except:
				pass
	if log_level is None:
		log_level = logging.INFO
	logger.log.setLevel(log_level)
	return logger.log
logger.log = None

def find_open_fds():
	cnt = 0
	fds = []
	for fd in range(1024):
		try:
			os.fstat(fd)
			fds.append(fd)
		except:
			pass
	return fds

def known_fds(fwatch, log=None, exclude=set()):
	"""
	Build text describing the open file descriptors associated
	with a watch_files object.  This attempts to include all
	files expected to be open, and if possible reports infomation
	about any unknown fds.  You can set an exclude-set for fds
	you know are ok.  Unknown reporting will only work on Linux
	as it depends on the structure of the /proc file system.
"""
	fds_open = find_open_fds()
	fds_info = {}
	for fd in fds_open:
		try:
			fds_info[fd] = os.readlink('/proc/self/fd/'+str(fd))
		except Exception as e:
			if log: log.debug("Could not read fd %d info, probably not Linux -- %s", fd, str(e))
	fds_known = fwatch.fds_open.copy()
	fds_known[fwatch.fileno()] = '*control*'
	if 0 not in fds_known: fds_known[0] = '*stdin*'
	if 1 not in fds_known: fds_known[1] = '*stdout*'
	if 2 not in fds_known: fds_known[2] = '*stderr*'
	mode = fwatch.get_mode()
	if mode == 0:
		if fwatch._poll_send not in fds_known: fds_known[fwatch._poll_send] = '*poll_write*'

	for fd in fds_open:
		if fd not in fds_known and fd in fds_info:
			if fds_info[fd].endswith('/urandom') or fds_info[fd].endswith('/random'):
				fds_known[fd] = '*randev*'
			elif fd not in exclude:
				if log: log.info("Unknown fd %d: %s", fd, fds_info[fd])

	text = '%d fds: ' % (len(fds_known),)
	for fd in sorted(fds_known):
		text += ' %d<%s>' % (fd, fds_known[fd])
	return text

class python_subprocess(object):
	"""
	Start a python process via subproccess().  It is started with logging to stderr
	and stdout and stderr collected.  The log level can be set witht the 'verbose'
	param (default True means debug level).  The follow() method can be used to
	read the log output in a non-blocking manner.

	The version of python can be specified with the 'python' param.  The default is
	to attempt to find the executable used to run the current process and use that.

	The process will be destroyed when the object is removed, or when the
	close() method is called.
"""
	python_exec = None

	@classmethod
	def command_line(self, e, args, **params):
		if 'exe' not in params:
			raise Exception("No 'exe' params, maybe the superclass was called directly")
		if 'python' in params:
			python = params['python']
		elif self.python_exec:
			python = self.python_exec
		else:
			procs = proctree()
			mypid = os.getpid()
			if mypid in procs.processes:
				myproc = procs.processes[mypid]
				cmd = myproc.command.split(' ')[0].rstrip(':')
				if cmd.find('python') >= 0:
					if cmd.startswith('/'):
						self.python_exec = cmd
					else:
						self.python_exec = os.path.basename(cmd)
				else:
					#  python not mentioned in the command, punt
					self.python_exec = 'python'
			else:
				#  Hmm, that's weird, we'll punt
				self.python_exec = 'python'
			python = self.python_exec
		cmd = [
			python,
			params['exe'],
			'--log-stderr'
		]
		if 'verbose' not in params or params.get('verbose'):
			cmd.append('--verbose')
		if args:
			cmd.extend(args)
		return cmd

	def __init__(self, e, args, **params):
		self.log = params.get('log')
		cmd = self.command_line(e, args, **params)
		with open(os.devnull, 'r') as dev_null:
			self.proc = subprocess.Popen(cmd,
					bufsize=1,
					stdin=dev_null,
					stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT,
					close_fds=True,
					cwd=e.working_dir,
					universal_newlines=True)
		self.pid = self.proc.pid
		fl = fcntl.fcntl(self.proc.stdout.fileno(), fcntl.F_GETFL)
		fcntl.fcntl(self.proc.stdout.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)

	def __del__(self):
		self.close(warn=False)

	def close(self, warn=True):
		if self.proc is None:
			if self.log and warn: self.log.warning("'%s' has already been closed", self.__class__.__name__)
			return
		ret = self.proc.poll()
		if ret is not None:
			if self.log: self.log.info("%s() has already exited %d", self.__class__.__name__, ret)
			return ret
		self.proc.terminate()
		start = time.time()
		for i in range(50):
			ret = self.proc.poll()
			if ret is not None:
				if self.log: self.log.info("%s() terminated %d after %.1fs",
									self.__class__.__name__, ret, time.time()-start)
				break
			time.sleep(0.1)
		if self.proc.returncode is None:
			if self.log: self.log.info("%s() did not terminate, killing", self.__class__.__name__)
			self.proc.kill()
			self.proc.wait()
			ret = self.proc.returncode
			if self.log: self.log.info("%s() killed after %.1fs", self.__class__.__name__, time.time()-start)
		self.proc = None
		return ret

	def follow(self):
		if self.proc is None:
			raise Exception("Attempt to follow() a closed process")
		try:
			ret = self.proc.stdout.readline()
			if ret == '':
				#  In python 3, readline() returns empty when the underlying fd has been
				#  set to O_NONBLOCK.  In python 2 this throws an EAGAIN exception.
				#  The python 2 behavior is actually more useful because we can distiguish
				#  EOF and nothing-available, but this code takes account of both.
				#  It is no big deal because a real EOF will only happen when the process
				#  exits, and this code detects that as well.
				#
				ecode = self.proc.poll()
				if ecode is not None:
					if self.log: self.log.debug("support.follow(): proc exited %d", ecode)
					return ret
				else:
					return None
			else:
				return ret
		except Exception as e:
			ecode = None
			try: ecode = e.errno
			except: pass
			if ecode is None:
				try: ecode = e[0]
				except: pass
			if ecode == errno.EAGAIN:
				return None
			raise e

	def search(self, regex_list, limit=60, iolimit=20, log=None):
		"""
		Search for the regular expression which must be
		created with re.compile().  Returns True if found,
		False if not found within the time limits, and None
		if the process exits before the search is successful.
	"""
		start = time.time()
		proc_limit = start + limit
		line_limit = start + iolimit
		if not type(regex_list) is list:
			regex_list = [regex_list]
		need_regex = {}
		for regex in regex_list:
			need_regex[regex] = re.compile(regex)
		while time.time() < proc_limit:
			now = time.time()
			l = self.follow()
			if l is None:
				if now > line_limit:
					if log: log.debug("support.search() I/O timeout")
					return False
				time.sleep(0.01)
				continue
			if l == '':
				if log: log.debug("support.search() EOF")
				return None
			l = l.rstrip()
			found = False
			for regex in list(need_regex):
				if need_regex[regex].search(l):
					if log: log.debug("support.search(%s) found in: %s", regex, l)
					found = True
					del need_regex[regex]
					break
			if not found and log: log.debug("support.search() no match: %s", l)
			if len(need_regex) == 0:
				return True
			line_limit = now + iolimit
		if log: log.debug("support.search() search timeout")
		return False

class taskforce(python_subprocess):
	"""
	Start a taskforce subprocess
"""
	@classmethod
	def command_line(self, e, args, **params):
		params = params.copy()
		args = list(args)
		params['exe'] = os.path.join(e.bin_dir, 'taskforce')
		args.extend(['--config-file', e.config_file, '--roles-file', e.roles_file])
		return super(taskforce, self).command_line(e, args, **params)

	def __init__(self, e, args, **params):
		params = params.copy()
		args = list(args)
		params['exe'] = os.path.join(e.bin_dir, 'taskforce')
		args.extend(['--config-file', e.config_file, '--roles-file', e.roles_file])
		super(taskforce, self).__init__(e, args, **params)

class watch_files(python_subprocess):
	"""
	Start a watch_files subprocess
"""
	@classmethod
	def command_line(self, e, args, **params):
		params = params.copy()
		params['exe'] = os.path.join(e.test_dir, 'scripts', 'watch_files')
		return super(watch_files, self).command_line(e, args, **params)

	def __init__(self, e, args, **params):
		params = params.copy()
		params['exe'] = os.path.join(e.test_dir, 'scripts', 'watch_files')
		super(watch_files, self).__init__(e, args, **params)

class proctree(object):
	"""
	Builds an object with the current process information based on
	running ps(1).  The resulting attributes are:

		processes	- dict of PIDs referencing process objects
		names		- dict of process names referencing a list of
				  process objects
	
	See the process class (below) for what is in a process object.
"""
	class process(object):
		"""

		Used to hold per-process details, which attributes taken from
		the ps(1) output, passed in as a list of ps(1) data elements
		and the header, passed in as a list of header elements.

		The attributes present in the object are listed in
		"direct_attributes" and "derived_attributes" with their
		descriptions.  If an attribute is not available on a given
		system, its value will be None.

			pid		- process ID (int)
			ppid		- parent process ID (int)
			parent		- parent for this process (process object)
			children	- list of children (process object list, possibly empty)
			command		- command line which may be truncated by ps command (text)
			name		- basename of the first word of the CMD field (text)
			uid		- user ID of process (int)
			flags		- system dependent process flags (int)
			cpu		- cpu running the process (int)
			priority	- process priority (int)
			nice		- process "nice" value (int)
			size		- process size (float bytes)
			rss		- resident size (float bytes)
			wchan		- system dependent wait channel (text)
			state		- system dependent process state (text)
			tty		- full path of controlling tty (text)
			time		- total CPU time (float seconds)

		Because the parent of a process doesn't necessarily exist
		when the object is instantiated, it is a proctree() responsibility
		to set up the parent and children.
	"""
		direct_attributes = {
			'command': 'command line which may be truncated by ps command (text)',
			'cpu': 'cpu running the process (int)',
			'flags': 'system dependent process flags (int)',
			'nice': 'process "nice" value (int)',
			'pid': 'process ID (int)',
			'ppid': 'parent process ID (int)',
			'priority': 'process priority (int)',
			'rss': 'resident size (int kilobytes)',
			'size': 'process size (int kilobytes)',
			'state': 'system dependent process state (text)',
			'time': 'total CPU time (float seconds)',
			'tty': 'full path of controlling tty (text)',
			'uid': 'user ID of process (int)',
			'wchan': 'system dependent wait channel (text)',
		}
		derived_attributes = {
			'name': 'basename of the first word of the CMD field (text)',
			'parent': 'parent for this process (process object)',
			'children': 'list of children (process object list, possibly empty)',
		}
		int_attributes = frozenset(['cpu', 'flags', 'nice', 'pid', 'ppid', 'priority', 'rss', 'size', 'uid'])
		header_map = {
			'CMD': 'command',
			'COMMAND': 'command',
			'CPU': 'cpu',
			'F': 'flags',
			'NI': 'nice',
			'PID': 'pid',
			'PPID': 'ppid',
			'PRI': 'priority',
			'RSS': 'rss',
			'S': 'state',
			'STAT': 'state',
			'SZ': 'size',
			'TIME': 'time',
			'TT': 'tty',
			'TTY': 'tty',
			'UID': 'uid',
			'VSZ': 'size',
			'MWCHAN': 'wchan',
			'WCHAN': 'wchan'
		}
		def __init__(self, header, data):
			for att in self.direct_attributes:
				setattr(self, att, None)
			for att in self.derived_attributes:
				setattr(self, att, None)
			for h in header:
				if h not in self.header_map:
					raise Exception("Header '%s' from ps(1) output has no mapping" % (h,))
				elif len(data) == 0:
					raise Exception("Ran out of data before all headers consumed")
				elif self.header_map[h]:
					att = self.header_map[h]
					if att == 'command':
						setattr(self, att, ' '.join(data))
						if data[0].find('/') == 0:
							self.name = os.path.basename(data[0])
						else:
							self.name = data[0]
						break
					elif att == 'time':
						setattr(self, att, self.canon_time(data[0]))
					elif att in self.int_attributes:
						try:
							setattr(self, att, int(data[0]))
						except:
							pass
					else:
						setattr(self, att, data[0])
				data.pop(0)

		def canon_time(self, data):
			"""
			This converts strings line mm:ss.sss or hh:mm:ss.sss
			to float seconds.  It will blow up if ps(1) reports
			days but none seem to.  Actually none seem to go
			beyond minutes.
		"""
			scale = 1
			seconds = 0
			for elem in reversed(data.split(':')):
				seconds += float(elem) * scale
				scale *= 60
			return seconds

	def __init__(self):
		bust = re.compile(r'\s+')
		cmd = ['ps', 'waxl']
		with open(os.devnull, 'r') as dev_null:
			proc = subprocess.Popen(cmd,
					stdin=dev_null,
					stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT,
					close_fds=True,
					universal_newlines=True)
		header_line = proc.stdout.readline().strip()
		header = bust.split(header_line)
		self.processes = {}
		self.names = {}
		while True:
			line = proc.stdout.readline().strip()
			if not line:
				break
			p = self.process(header, bust.split(line))
			self.processes[p.pid] = p
			if p.name in self.names:
				self.names[p.name].append(p)
			else:
				self.names[p.name] = [p]
			p.children = []
		limit = time.time() + 1
		while time.time() < limit:
			if proc.poll() is not None:
				break
			time.sleep(0.05)
		if proc.poll() is None:
			raise Exception("Command '%s' still running after output consumed", (' '.join(cmd),))
		for p in self.processes.values():
			if p.ppid in self.processes:
				p.parent = self.processes[p.ppid]
				p.parent.children.append(p)
			elif p.ppid != 0:
				raise Exception("Process %d has non-existant parent %d" % (pid, p.ppid))

def listeners(log=None):
	"""
	Builds a dict indexed by port for the current TCP listeners based on
	running netstat(1).  A dict value will be a list of (protocol, address)
	tuples where protocol will be either 'tcp4' or 'tcp6' and address will
	the listen address.  For wildcard listeners, this will be either
	('tcp4', '0.0.0.0') or ('tcp6', '::').
"""
	cmd = ['netstat', '-an']
	with open(os.devnull, 'r') as dev_null:
		proc = subprocess.Popen(cmd,
				stdin=dev_null,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				close_fds=True,
				universal_newlines=True)
	choose = re.compile(r'\bLISTEN$')
	portsep = re.compile(r'^(.*)[:\.](\d+)$')
	ports = {}

	#  Build a dict of sets of tuples.
	#
	while True:
		line = proc.stdout.readline().strip()
		if not line:
			break
		if not choose.search(line):
			continue
		f = line.split()
		if len(f) != 6:
			if log: log.warning("Ignoring unexpected '%s' LISTEN line: %s", ' '.join(cmd), line)
			continue
		protocol = f[0]
		if protocol == 'tcp':
			protocol = 'tcp4'
		netaddr = f[3]
		m = portsep.match(netaddr)
		if m:
			addr = m.group(1)
			port = m.group(2)
		else:
			if log: log.warning("Ignoring unexpected '%s' listen address in line: %s", ' '.join(cmd), line)
			continue
		if addr == '*':
			if protocol == 'tcp6':
				addr = '::'
			else:
				addr = '0.0.0.0'
		try:
			port = int(port)
		except Exception as e:
			if log: log.warning("Ignoring '%s' non-integer port in line: %s", ' '.join(cmd), line)
			continue
		if port not in ports:
			ports[port] = set()
		if protocol == 'tcp46':
			ports[port].add(('tcp4', addr))
			ports[port].add(('tcp6', addr))
		else:
			ports[port].add((protocol, addr))

	#  Now convert the sets of tuples into lists of tuples ordered by
	#  (protocol, address)
	#
	def tup_order(key):
		p, a = key
		if a.find(':') >= 0:
			f = list(reversed(a.split(':')))
			r = []
			for i in range(8):
				e = 0
				if f:
					e = f.pop()
					if e:
						try:
							e = int(e, 16)
						except Exception as e:
							if log: log.warning("Error canonicalizing '%s'", a)
					else:
						e = 0
				r.append('%05d' % (e,))
			r = ':'.join(reversed(r))
		else:
			f = a.split('.')
			r = []
			for e in f:
				try:
					e = int(e)
				except Exception as e:
					if log: log.warning("Error canonicalizing '%s'", a)
					e = 0
				r.append('%03d' % (e,))
			r = '.'.join(reversed(r))
		return p + '-' + r

	for port in ports:
		ports[port] = sorted(list(ports[port]), key=tup_order)
	return ports

if __name__ == "__main__":

	import sys, pprint, logging

	log = logger()
	l = listeners(log=log)
	pprint.pprint(l, indent=4)

	e = env(base='.')
	print("Command line: %s" % (taskforce.command_line(e),))
	print("Command line: %s" % (taskforce.command_line(e),))

	procs = proctree()
	seen = {}

	def pump(p, level):
		if p.pid in seen:
			return
		seen[p.pid] = True
		print("%*d %s %.1f" % (level*2+6, p.pid, p.name, p.time))
		for c in sorted(p.children, key=lambda p: p.pid):
			pump(c, level+1)
		
	# Print the process tree
	#
	for pid in sorted(procs.processes.keys()):
		pump(procs.processes[pid], 0)

	# Print the process with the most instances
	#
	max_kids = 0
	for name in procs.names:
		cnt = len(procs.names[name])
		if cnt > max_kids:
			long_name = name
			max_kids = cnt
	pids = ''
	for p in sorted(procs.names[long_name], key=lambda p: p.pid):
		pids += ' ' + str(p.pid)
	print('Process name with the most instances - %s%s' % (long_name+':', pids))
