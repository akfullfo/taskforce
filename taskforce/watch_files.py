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

import sys, os, time, errno, select, logging
from . import utils
from .utils import ses
from .utils import get_caller as my

#  These values are used internally to select watch mode.
#
WF_POLLING = 0
WF_KQUEUE = 1
WF_INOTIFYX = 2

wf_inotifyx_available = False
try:
	import inotifyx
	if callable(inotifyx.init):
		wf_inotifyx_available = True
except:
	pass

class watch(object):
	"""
	Sets up an instance that can be included in a select/poll set.  The
	descriptor will become readable whenever registered files change.

	Because the class has a fileno() method, the class instance can generally
	be used directly with select/poll.

	The intent of this interface is to insulate the caller from the
	system-dependent implementations of Unix file system event notification
	(kevent on *BSD/MacOS, inotify on Linux).  The interface also supports
	a polling mode which is much less efficient, but probably better than
	nothing.

	At the moment, inotify is not supported, so Linux systems will operate
	in polling mode.

	Apart from simplifying the use of select.kqueue calls, the intent is to
	mask changes that might be needed if linux inotify needs to be supported.
	Because of this, the interface avoids providing features that would be
	hard to implement in one or other interface.

	All open file descriptors are automatically closed when the instance
	is removed.

	The following params can be set when the class is initialized and
	overridden in methods where appropriate.

	  timeout       -  Aggregation timeout.  Because file change events
			   tend to arrive in bursts, setting an aggregation
			   timeout limits the number of calls and cuts
			   duplication of changes on a single file.  The
			   effect is that the method will keep retrieving
			   events until none arrive within the timeout period.
			   That means the get() method will block for at least
			   the timeout period, so the timeout should be small
			   (perhaps 0.1 seconds).  The default is 0 which
			   means the get() method will return immediately.

			   Note that even with a zero timeout, get() may still
			   return multiple events if multiple changes are
			   pending when it is called.

	  limit         -  Limit the number of change events that will
			   collected due to the aggregation timeout.  The
			   default is None (no limit).  The value is ignored
			   if a timeout is not set.  Note that the limit may
			   be exceeded if the last event read returns more
			   than one event.

	  commit        -  If False, skip rebuilding watch list after each
			   add() or remove().  The caller should then call
			   commit() directly to commit changes.

	  missing       -  If True, a file does not need to pre-exist
			   when add() is called.  In addition, a file added
			   with this flag set can disappear and reappear which
			   will cause an event each time.  With the flag False
			   which is the default, add() and get() will raise
			   exceptions if the file is initially missing or is
			   removed or renamed, and the file will cease being
			   watched until add() is called again.

	  polling	-  Force the interface into polling mode.  Only available
			   when instantiating the class.  Polling mode has no
			   practical advantage over file system events so this
			   param really exists for testing polling mode.

	  log		-  A logging instance.
"""
	def __init__(self, polling=False, **params):
		self._params = params

		self._mode_map = dict((val, nam) for nam, val in globals().items() if nam.startswith('WF_'))

		#  Set up the access mode.  If select.kqueue() is callable, WF_KQUEUE
		#  mode will be used, otherwise polling will be used.  The get_mode()
		#  method supplies read-only access to th attribute.  The value is not
		#  settable after the class is instantiated.
		#
		if polling:
			self._mode = WF_POLLING
		elif wf_inotifyx_available:
			self._mode = WF_INOTIFYX
		elif 'kqueue' in dir(select) and callable(select.kqueue):
			self._mode = WF_KQUEUE
		else:
			self._mode = WF_POLLING

		#  Holds all paths that have been added, whether actually being watched or not.
		self.paths = {}

		#  Holds paths that have been opened and are being watched
		#
		self.paths_open = {}

		#  Holds paths where "missing" was True and the path could not be opened.
		#
		self.paths_pending = {}

		#  Associates all open file descriptors and the opened path
		#
		self.fds_open = {}

		#  Provided to caller to observe the last set of changes.  The
		#  value of the dict is the time the change was noted.
		#
		self.last_changes = {}

		self._discard = logging.getLogger(__name__)
		self._discard.addHandler(logging.NullHandler())
		self.unprocessed_event = None

		if self._mode == WF_KQUEUE:
			#  Immediately create a kernel event queue so that an immediate
			#  call to fileno() will return the correct controlling fd.
			#
			self._kq = select.kqueue()
		elif self._mode == WF_INOTIFYX:
			#  Immediately create an inotifyx channel identified by a
			#  file descriptor.
			#
			self._inx_fd = inotifyx.init()

			#  This is the standard mask used for watches.  It is setup
			#  to only trigger events when somethingn changes.
			#
			self._inx_mask = inotifyx.IN_ALL_EVENTS & ~(inotifyx.IN_ACCESS | inotifyx.IN_CLOSE | inotifyx.IN_OPEN)

			# Record inode of watched paths to work around simfs bug 
			#
			self._inx_inode = {}
		elif self._mode == WF_POLLING:
			self._self_pipe()

			self._poll_stat = {}

			#  Holds paths that were removed or renamed until get() is
			#  called.
			#
			self._poll_pending = {}

	def __del__(self):
		self.close()

	def close(self):
		close_fds = True
		if self._mode == WF_KQUEUE and self._kq:
			#  The is actually auto-closed, so this bit is not
			#  strictly needed.
			#
			try: self._kq.close()
			except: pass
			self._kq = None
		elif self._mode == WF_INOTIFYX:
			#  As we are storing inotify watch-descriptors rather
			#  than file descriptors in fds_open, skip closing them.
			#  They are automatically cleared when _inx_fd is closed
			#
			close_fds = False
			try: os.close(self._inx_fd)
			except: pass
			self._inx_fd = None
		elif self._mode == WF_POLLING:
			for fd in [self._poll_fd, self._poll_send]:
				try: os.close(fd)
				except: pass

		#  However, these are not automatically closed, so we
		#  definitely need the destructor here.
		#
		if close_fds:
			for fd in list(self.fds_open):
				try: os.close(fd)
				except: pass
				del self.fds_open[fd]

	def fileno(self):
		if self._mode == WF_KQUEUE:
			return self._kq.fileno()
		elif self._mode == WF_INOTIFYX:
			return self._inx_fd
		else:
			return self._poll_fd

	def get_mode(self):
		return self._mode

	def get_mode_name(self, mode=None):
		if mode is None:
			mode = self._mode
		if mode in self._mode_map:
			return self._mode_map[mode]
		else:
			return "Mode" + str(mode)

	def _getparam(self, tag, default = None, **params):
		val = params.get(tag)
		if val is None:
			val = self._params.get(tag)
		if val is None:
			val = default
		return val

	def _close(self, fd):
		"""
		Close the descriptor used for a path regardless
		of mode.
	"""
		if self._mode == WF_INOTIFYX:
			try: inotifyx.rm_watch(self._inx_fd, fd)
			except: pass
		else:
			try: os.close(fd)
			except: pass

	def _self_pipe(self):
		"""
		This sets up a self-pipe so we can hand back an fd to the caller
		allowing the object to manage event triggers.  The ends of the pipe are
		set non-blocking so it doesn't really matter if a bunch of events fill
		the pipe buffer.
	"""
		import fcntl

		self._poll_fd, self._poll_send = os.pipe()
		for fd in [self._poll_fd, self._poll_send]:
			fl = fcntl.fcntl(fd, fcntl.F_GETFL)
			fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

	def _disappeared(self, fd, path, **params):
		"""
		Called when an open path is no longer acessible.  This will either
		move the path to pending (if the 'missing' param is set for the
		file), or fire an exception.
	"""
		log = self._getparam('log', self._discard, **params)

		log.debug("%s Path '%s' removed or renamed, handling removal", my(self), path)
		self._close(fd)
		if self._mode == WF_POLLING and fd in self._poll_stat:
			del self._poll_stat[fd]
		if self._mode == WF_INOTIFYX and path in self._inx_inode:
			del self._inx_inode[path]
		del self.fds_open[fd]
		del self.paths_open[path]
		if self.paths[path]:
			try:
				if self._add_file(path, **params):
					log.debug("%s Path '%s' immediately reappeared, pending transition skipped", my(self), path)
					return
			except Exception as e:
				log.debug("%s Path '%s' reappearance check failed -- %s", my(self), path, str(e))
			log.debug("%s Path '%s' marked as pending", my(self), path)
			self.paths_pending[path] = True
		else:
			del self.paths[path]
			raise Exception("Path '%s' has been removed or renamed" % (path,))

	def _poll_get_stat(self, fd, path):
		"""
		Check the status of an open path.  Note that we have to use stat() rather
		than fstat() because we want to detect file removes and renames.
	"""
		try:
			st = os.stat(path)
			fstate = (st.st_mode, st.st_nlink, st.st_uid, st.st_gid, st.st_size, st.st_mtime)
		except Exception as e:
			log = self._getparam('log', self._discard)
			log.debug("%s stat failed on %s -- %s", my(self), path, str(e))
			self._poll_pending[path] = time.time()
			self._disappeared(fd, path)
			fstate = None
		return fstate

	def _poll_trigger(self):
		"""
		Trigger activity for the caller by writting a NUL to the self-pipe.
	"""
		try:
			os.write(self._poll_send, '\0'.encode('utf-8'))
		except Exception as e:
			log = self._getparam('log', self._discard)
			log.debug("%s Ignoring self-pipe write error -- %s", my(self), str(e))

	def _clean_failed_fds(self, fdlist):
		for fd in fdlist:
			if fd in self.fds_open:
				path = self.fds_open[fd]
				del self.fds_open[fd]
				if self._mode == WF_INOTIFYX and path in self._inx_inode:
					del self._inx_inode[path]
				if path in self.paths_open:
					del self.paths_open[path]
			self._close(fd)

	def _trigger(self, fd, **params):
		"""
		We need events to fire on appearance because the code
		doesn't see the file until after it has been created.

		In WF_KQUEUE mode, this simulates triggering an event by firing
		a oneshot timer event to fire immediately (0 msecs).  Because
		this uses the file descriptor as the timer identity and get() doesn't
		care what filter actually fired the event, the outside world sees
		this as a file change.

		In WF_INOTIFYX mode, this triggers an event by setting IN_OPEN on
		the inotify watch, opening the file in read-only mode, closing it,
		and removing the IN_OPEN setting.  The file is not discovered unless
		it can be opened so this is reliable.

		In WF_POLLING mode, this resets our knowledge of the stat
		info, and then triggers file activity to wake up the caller.
	"""
		log = self._getparam('log', self._discard, **params)
		if self._mode == WF_KQUEUE:
			try:
				ev = select.kevent(fd, filter=select.KQ_FILTER_TIMER,
							flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR | select.KQ_EV_ONESHOT, data=0)
				self._kq.control([ev], 0, 0)
				log.debug("%s Added timer event following pending file promotion", my(self))
			except Exception as e:
				log.error("%s Failed to add timer event following pending file promotion -- %s", my(self), str(e))
		elif self._mode == WF_INOTIFYX:
			if fd in self.fds_open:
				try:
					path = self.fds_open[fd]
					nfd = inotifyx.add_watch(self._inx_fd, path, self._inx_mask|inotifyx.IN_OPEN)
					if nfd != fd:
						raise Exception("Assertion failed: IN_OPEN add_watch() set gave new wd")
					tfd = os.open(path, os.O_RDONLY)
					try: os.close(tfd)
					except: pass
					nfd = inotifyx.add_watch(self._inx_fd, path, self._inx_mask)
					if nfd != fd:
						raise Exception("Assertion failed: IN_OPEN add_watch() clear gave new wd")
				except Exception as e:
					log.error("%s Failed to trigger event via os.open() following pending file promotion -- %s",
											my(self), str(e))
			else:
				log.error("%s Pending file promotion of unknown wd %d failed", my(self), fd)
		elif self._mode == WF_POLLING:
			self._poll_stat[fd] = ()
			self._poll_trigger()

	def _add_file(self, path, **params):
		"""
		Attempt to add a file to the system monitoring mechanism.
	"""
		log = self._getparam('log', self._discard, **params)
		fd = None
		try:
			fd = os.open(path, os.O_RDONLY)
		except Exception as e:
			if not self.paths[path]:
				log.error("%s open failed on watched path '%s' -- %s",
								my(self), path, str(e), exc_info=log.isEnabledFor(logging.DEBUG))
				raise e
			elif path in self.paths_pending:
				log.debug("%s path '%s' is still pending -- %s", my(self), path, str(e))
			else:
				self.paths_pending[path] = True
				log.debug("%s added '%s' to pending list after open failure -- %s",
							my(self), path, str(e))
			return False
		if self._mode == WF_KQUEUE:
			log.debug("%s path %s opened as fd %d", my(self), path, fd)
			try:
				ev = select.kevent(fd,
					filter=select.KQ_FILTER_VNODE,
					flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
					fflags=select.KQ_NOTE_WRITE | select.KQ_NOTE_ATTRIB | select.KQ_NOTE_LINK |
								select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME)
				self._kq.control([ev], 0, 0)
			except Exception as e:
				log.error("%s kevent failed on watched path '%s' -- %s", my(self), path, str(e))
				try: os.close(fd)
				except: pass
				raise e

		elif self._mode == WF_INOTIFYX:
			#  inotify doesn't need the target paths open, so now it is known to be
			#  accessible, close the actual fd and use the watch-descriptor as the fd.
			#
			#  However, due to an apparent simfs bug where inotify does not fire either
			#  IN_DELETE_SELF or IN_MOVE_SELF, we need to record the inode so that we
			#  can detect deletes and renames internally.  simfs is used in containers.
			#
			try:
				s = os.fstat(fd)
				self._inx_inode[path] = s.st_ino
			except Exception as e:
				log.error("%s fstat(%d) failed on open path '%s' -- %s", my(self), fd, path, str(e))
				try: os.close(fd)
				except: pass
				raise e
			try: os.close(fd)
			except: pass
			try:
				fd = inotifyx.add_watch(self._inx_fd, path, self._inx_mask)
				log.debug("%s path %s watched with wd %d", my(self), path, fd)
			except Exception as e:
				log.error("%s inotify failed on watched path '%s' -- %s", my(self), path, str(e))
				raise e

		elif self._mode == WF_POLLING:
			log.debug("%s path %s opened as fd %d", my(self), path, fd)
			fstate = self._poll_get_stat(fd, path)
			if fstate:
				self._poll_stat[fd] = fstate

		self.paths_open[path] = fd
		self.fds_open[fd] = path
		return True

	def commit(self, **params):
		"""
		Rebuild kevent operations by removing open files that no longer need to
		be watched, and adding new files if they are not currently being watched.

		This is done by comparing self.paths to self.paths_open.
	"""
		log = self._getparam('log', self._discard, **params)

		#  Find all the modules that no longer need watching
		#
		removed = 0
		added = 0
		for path in list(self.paths_open):
			if path not in self.paths:
				fd = self.paths_open[path]
				if self._mode == WF_KQUEUE:
					#  kevent automatically deletes the event when the fd is closed
					try:
						os.close(fd)
					except Exception as e:
						log.warning("%s close failed on watched file '%s' -- %s", my(self), path, str(e))
				elif self._mode == WF_INOTIFYX:
					try:
						inotifyx.rm_watch(self._inx_fd, fd)
					except Exception as e:
						log.warning("%s remove failed on watched file '%s' -- %s", my(self), path, str(e))
					if path in self._inx_inode:
						del self._inx_inode[path]
				elif self._mode == WF_POLLING:
					if fd in self._poll_stat:
						del self._poll_stat[fd]
					else:
						log.warning("%s fd watched path '%s' missing from _poll_stat map", my(self), path)
					try:
						os.close(fd)
					except Exception as e:
						log.warning("%s close failed on watched file '%s' -- %s", my(self), path, str(e))
				if fd in self.fds_open:
					del self.fds_open[fd]
				else:
					log.warning("%s fd watched path '%s' missing from fd map", my(self), path)
				del self.paths_open[path]
				log.debug("%s Removed watch for path '%s'", my(self), path)
				removed += 1

		#  Find all the paths that are new and should be watched
		#
		fdlist = []
		failed = []
		last_exc = None
		log.debug("%s %d watched path%s", my(self), len(self.paths), ses(len(self.paths)))
		for path in list(self.paths):
			if path not in self.paths_open:
				try:
					if not self._add_file(path, **params):
						continue
				except Exception as e:
					last_exc = e
					failed.append(path)
					continue
				fdlist.append(self.paths_open[path])

				if path in self.paths_pending:
					log.debug("%s pending path '%s' has now appeared", my(self), path)
					del self.paths_pending[path]
					self._trigger(self.paths_open[path], **params)

				added += 1
				log.debug("%s Added watch for path '%s' with ident %d", my(self), path, self.paths_open[path])
		if failed:
			self._clean_failed_fds(fdlist)
			raise Exception("Failed to set watch on %s -- %s" % (str(failed), str(last_exc)))
		log.debug("%s %d added, %d removed", my(self), added, removed)

	def get(self, **params):
		"""
		Return a list of watched paths that where affected by recent
		changes, following a successful poll() return for the controlling
		file descriptor.

		If param "timeout" is greater than 0, the event queue will be read
		multiple times and reads continue until a timeout occurs.

		With a timeout active, if param "limit" is greater than 0,
		event reads will stop when the number of changes exceeds the
		limit.  This guarantees that the time the method will block
		will never be greater than timeout*limit seconds.

		Note that with a timeout active, multiple changes to a
		single path will only be reported once.
	"""
		log = self._getparam('log', self._discard, **params)

		self.last_changes = {}

		timeout = self._getparam('timeout', 0, **params)
		if not timeout or timeout < 0:
			timeout = 0
		limit = self._getparam('limit', None, **params)
		if not limit or limit < 0:
			limit = None

		max_events = limit if limit else 10000
		if self.unprocessed_event:
			log.debug("%s Will handle unprocessed event", my(self))

		if self._mode == WF_KQUEUE:
			evagg = {}
			while True:
				try:
					evlist = self._kq.control(None, max_events, timeout)
				except OSError as e:
					if e.errno == errno.EINTR:
						break
					raise e
				if not evlist:
					break

				log.debug("%s kq.control() returned %d event%s", my(self), len(evlist), ses(len(evlist)))
				for ev in evlist:
					if ev.ident in self.fds_open:
						path = self.fds_open[ev.ident]
						if path in evagg:
							evagg[path].fflags |= ev.fflags
						else:
							evagg[path] = ev
				if limit and len(evagg) >= limit:
					break
			for path, ev in evagg.items():
				if ev.fflags & (select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME):
					self._disappeared(ev.ident, path, **params)
				self.last_changes[path] = time.time()
				log.debug("%s Change on '%s'", my(self), path)

		elif self._mode == WF_INOTIFYX:
			evagg = {}
			while True:
				try:
					evlist = inotifyx.get_events(self._inx_fd, timeout)
				except IOError as e:
					if e.errno == errno.EINTR:
						break
					raise e
				if not evlist:
					break

				log.debug("%s inotifyx.get_events() returned %d event%s", my(self), len(evlist), ses(len(evlist)))

				for ev in evlist:
					if ev.wd in self.fds_open:
						path = self.fds_open[ev.wd]
						if path in evagg:
							evagg[path].mask |= ev.mask
						else:
							evagg[path] = ev
					elif ev.mask & inotifyx.IN_IGNORED:
						log.debug("%s skipping IN_IGNORED event on unknown wd %d", my(self), ev.wd)
					else:
						log.warning("%s attempt to handle unknown inotify event wd %d", my(self), ev.wd)
				if limit and len(evagg) >= limit:
					break
			for path, ev in evagg.items():
				log.debug("%s Change on '%s' -- %s", my(self), path, ev.get_mask_description())
				if ev.mask & (inotifyx.IN_DELETE_SELF | inotifyx.IN_MOVE_SELF):
					self._disappeared(ev.wd, path, **params)
				elif ev.mask & inotifyx.IN_ATTRIB:
					file_move_del = False
					try:
						s = os.stat(path)
						if s.st_ino != self.xxx[path]:
							file_move_del = True
							log.info("%s 'simfs' (used with containers) bug detected -- '%s' moved",
													my(self), path)
					except Exception as e:
						file_move_del = True
						log.info("%s 'simfs' (used with containers) bug detected -- '%s' removed",
													my(self), path)
					if file_move_del:
						self._disappeared(ev.wd, path, **params)
				self.last_changes[path] = time.time()

		elif self._mode == WF_POLLING:
			#  Consume any pending data from the self-pipe.  Read
			#  until EOF.  The fd is already non-blocking so this
			#  terminates on zero read or any error.
			#
			cnt = 0
			while True:
				try:
					data = os.read(self._poll_fd, 1024)
					if data == '':
						break
					cnt += len(data)
				except OSError as e:
					if e.errno != errno.EAGAIN:
						log.warning("%s Ignoring self-pipe read failure -- %s", my(self), str(e))
					break
				except Exception as e:
					log.warning("%s Ignoring self-pipe read failure -- %s", my(self), str(e))
					break
			log.debug("%s Self-pipe read consumed %d byte%s", my(self), cnt, ses(cnt))
			now = time.time()
			for path in self._poll_pending:
				self.last_changes[path] = self._poll_pending[path]
			self._poll_pending = {}
			for fd in list(self._poll_stat):
				path = self.fds_open[fd]
				fstate = self._poll_get_stat(fd, path)
				if fstate is None:
					self.last_changes[path] = now
				elif self._poll_stat[fd] != fstate:
					self._poll_stat[fd] = fstate
					self.last_changes[path] = now
					log.debug("%s Change on '%s'", my(self), path)
		else:
			raise Exception("Unsupported polling mode " + self.get_mode_name())
		paths = list(self.last_changes)
		paths.sort()
		log.debug("%s Change was to %d path%s", my(self), len(paths), ses(len(paths)))
		return paths

	def add(self, paths, **params):
		"""
		Add a path (or list of paths) to the list of paths being
		watched.  The 'missing' setting for a file can also be
		changed by re-adding the file.
	"""
		log = self._getparam('log', self._discard, **params)
		missing = self._getparam('missing', True, **params)
		commit = self._getparam('commit', True, **params)

		if type(paths) is not list:
			paths = [paths]

		rebuild = False
		for path in paths:
			if path in self.paths:
				if self.paths[path] == missing:
					log.info("%s Ignoring attempt to add existing path '%s'", my(self), path)
				else:
					log.debug("%s Changing missing state from %s to %s on existing path '%s'",
							my(self), str(self.paths[path]), str(missing), path)
					self.paths[path] = missing
			else:
				log.debug("%s Adding path '%s'", my(self), path)
				self.paths[path] = missing
				rebuild = True
		if commit and rebuild:
			self.commit(**params)

	def remove(self, paths, **params):
		"""
		Delete paths from the watched list.
	"""
		log = self._getparam('log', self._discard, **params)
		commit = self._getparam('commit', True, **params)

		if type(paths) is not list:
			paths = [paths]

		rebuild = False
		for path in paths:
			if path in self.paths_pending:
				del self.paths_pending[path]
			if path in self.paths:
				del self.paths[path]
				rebuild = True
			else:
				log.error("%s Attempt to remove '%s' which was never added", my(self), path)
				raise Exception("Path '%s' has never been added" % (path,))
		if commit and rebuild:
			self.commit(**params)

	def scan(self, **params):
		"""
		This method should be called periodically if files were added
		with "missing=False".  It will check for the appearance of missing
		files and ensure an event will be triggered for any that appear.

		It also needs to be called if the instance could be in WF_POLLING
		mode as file system changes will only be detected in WF_POLLING
		mode when scan() is called.

		The method should be called frequently (perhaps every 1-5 seconds)
		as part of idle processing in a select/poll loop.

		The approach is intended to support file appearance and disappearance
		using kqueue/kevent on BSD while retaining the ability in the
		future to transparently support inotify on Linux without any code
		or efficiency impact on callers.

		For WF_KQUEUE and WF_INOTIFYX mode, processing consists of determining
		that a pending path is now accessible, and then calling commit() to
		make the necessary adjustments.  This will be efficient as long as the
		list of pending paths is small.

		At some point this should be optimized by watching the directory of
		a pending target (assuming it exists).	If the directory changes to
		indicate the pending path might have appeared, then the next get()
		call should perform a scan().

		For WF_POLLING mode, the entire list of open files is also scanned
		looking for significant differences in the os.fstat info.

		If/when inotify is supported here, it is expected that the scan()
		method would be a no-op.
	"""
		log = self._getparam('log', self._discard, **params)
		pending = len(self.paths_pending)
		log.debug("%s Checking %d pending path%s", my(self), pending, ses(pending))
		for path in self.paths_pending:
			if os.path.exists(path):
				log.debug("%s pending path %s now accessible, triggering commit()", my(self), path)
				self.commit(**params)
				return
		if self._mode == WF_POLLING:
			log.debug("%s Checking %d open path%s", my(self), len(self._poll_stat), ses(len(self._poll_stat)))
			for fd in list(self._poll_stat):
				fstate = self._poll_get_stat(fd, self.fds_open[fd])
				if fstate is None or self._poll_stat[fd] != fstate:
					self._poll_trigger()
					break
