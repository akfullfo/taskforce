
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
		self.examples_dir = os.path.realpath("examples")
		self.working_dir = self.examples_dir
		self.examples_bin = os.path.join(self.examples_dir, "bin")
		self.config_file = os.path.join(self.examples_dir, "example.conf")
		self.roles_file = os.path.join(self.temp_dir, 'test.roles')
		self.test_roles = ['frontend', 'backend']
		if not os.path.isdir(self.temp_dir):
			os.mkdir(self.temp_dir, 0777)

	def __del__(self):
		if os.path.isdir(self.temp_dir):
			os.rmdir(self.temp_dir)

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

class taskforce(object):
	"""
	Start a taskforce process via subproccess().  taskforce is started with
	logging to stderr and stdout and stderr collected.  The log level can
	be set witht the 'verbose' param (default True means debug level).
	The follow() method can be used to read the log output in a non-blocking manner.

	The process will be destroyed when the object is removed, or when the
	close() method is called.
"""
	@classmethod
	def command_line(self, e, *args, **params):
		cmd = [
			os.path.join(e.bin_dir, 'taskforce'),
			'--log-stderr',
			'--config-file', e.config_file,
			'--roles-file', e.roles_file
		]
		if 'verbose' not in params or params.get('verbose'):
			cmd.append('--verbose')
		if args:
			cmd.extend(args)
		return cmd

	def __init__(self, e, *args, **params):
		cmd = self.command_line(e, *args, **params)
		with open('/dev/null', 'r') as dev_null:
			self.proc = subprocess.Popen(cmd,
					bufsize=1,
					stdin=dev_null,
					stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT,
					close_fds=True,
					cwd=e.working_dir,
					universal_newlines=True)
		fl = fcntl.fcntl(self.proc.stdout.fileno(), fcntl.F_GETFL)
		fcntl.fcntl(self.proc.stdout.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)
		self.log = params.get('log')

	def __del__(self):
		self.close(warn=False)

	def close(self, warn=True):
		if self.proc is None:
			if self.log and warn: self.log.warning("taskforce() has already been closed")
			return
		if self.proc.returncode is not None:
			if self.log: self.log.info("taskforce() has already exited 0x%x", self.proc.returncode)
			return
		self.proc.terminate()
		start = time.time()
		for i in range(50):
			if self.proc.poll() is not None:
				if self.log: self.log.info("taskforce() successfully terminated after %.1fs", time.time()-start)
				break
			time.sleep(0.1)
		if self.proc.returncode is None:
			if self.log: self.log.info("taskforce() did not terminate, killing")
			self.proc.kill()
			self.proc.wait()
			if self.log: self.log.info("taskforce() killed after %.1fs", time.time()-start)
		ret = self.proc.returncode
		self.proc = None
		return ret

	def follow(self):
		if self.proc is None:
			raise Exception("Attempt to follow() a closed process")
		try:
			return self.proc.stdout.readline().rstrip()
		except Exception as e:
			if e[0] == errno.EAGAIN:
				return None
			raise e
		if self.proc.poll() is not None: return ''

	def search(self, regex, limit=30, iolimit=10, log=None):
		"""
		Search for the regular expression which must be
		created with re.compile().  Returns True if found,
		False if not found within the time limits, and None
		if the process exits before the search is successful.
	"""
		start = time.time()
		proc_limit = start + limit
		line_limit = start + iolimit
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
			if regex.search(l):
				if log: log.debug("support.search() found in: %s", l)
				return True
			if log: log.debug("support.search() no match: %s", l)
			line_limit = now + iolimit
		if log: log.debug("support.search() search timeout")
		return False

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
		with open('/dev/null', 'r') as dev_null:
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
		if proc.poll() is None:
			raise Exception("Command '%s' still running after output consumed", (' '.join(cmd),))
		for p in self.processes.values():
			if p.ppid in self.processes:
				p.parent = self.processes[p.ppid]
				p.parent.children.append(p)
			elif p.ppid != 0:
				raise Exception("Process %d has non-existant parent %d" % (pid, p.ppid))

if __name__ == "__main__":
	procs = proctree()
	seen = {}

	def pump(p, level):
		if p.pid in seen:
			return
		seen[p.pid] = True
		print ''.rjust(level, ' '), p.pid, p.name, p.time
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
	print 'Process name with the most instances -', long_name+':',
	for p in sorted(procs.names[long_name], key=lambda p: p.pid):
		print p.pid,
	print
