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

import sys, os, select, errno

PL_SELECT = 0
PL_POLL = 1
PL_KQUEUE = 2
#PL_EPOLL = 3   # Possible future implementation

POLLIN = 1
POLLPRI = 2
POLLOUT = 4
POLLERR = 8
POLLHUP = 16
POLLNVAL = 32

class Error(Exception):
    """
    This exception is raise for any internally detected problems.
    Using an Exception subclass allows the caller to detect internal
    exceptions as distinct from those raised by the underlying
    services.
"""
    pass

class poll(object):
    """
    Presents an interface consitent with select.poll() but uses
    select.kqueue(), select.poll() or select.select() depending on services
    availale from the O/S.

    The service is selected automatically and will typically be the best
    choice but it may be overridden with the set_mode() method which must
    be used before the first register() call.  get_available_modes() returns
    the modes possible on this O/S.

    There are a few differences to the select.poll() interface:

    1.  poll.Error exceptions are raised by this module to distinguish them from
        the underlying select.* object exceptions.  As a special case, the any
        exceptions for EINTR are reraised as OSError(errno=EINTR) so callers do
        not have to catch the multple inconsistent forms and the python2/python3
        variations.  Other than this case, no special attempt is made to make
        exceptions consistent across the underlying services.

    2.  The events that are available across all modes are POLLIN and POLLOUT.
        POLLPRI is not available with PL_KQUEUE so if you actually need this,
        you will probably have to force PL_SELECT mode.  PL_SELECT mode should
        be available on all systems.

    3.  select.poll() accepts integer file descriptors and objects with a fileno()
        method that returns an integer file descriptor.  However, the event that
        fires when an object is used for registration holds the file descriptor
        returned by the fileno() method rather than the object itself.  On the
        other hand, select.select() returns the object if that is what was used
        in the input lists.

        This module adopts the select behavior regardless of the underlying
        mode, as it is generally more useful.  I'm sure somebody will
        explain to me soon why that's not actually true.
"""
    def __init__(self):
        self._mode_map = dict((val, nam) for nam, val in globals().items() if nam.startswith('PL_'))
        self._poll_map = dict((val, nam) for nam, val in globals().items() if nam.startswith('POLL'))
        self._poll_keys = list(self._poll_map)
        self._poll_keys.sort()
        self._available_modes = set()
        self._has_registered = False
        self._fd_map = {}

        self._mode = None
        if 'kqueue' in select.__dict__ and callable(select.kqueue):                             # pragma: no cover
            if self._mode is None:
                self._mode = PL_KQUEUE
            self._available_modes.add(PL_KQUEUE)
        if 'poll' in select.__dict__ and callable(select.poll):
            if self._mode is None:
                self._mode = PL_POLL
            self._available_modes.add(PL_POLL)
        if 'select' in select.__dict__ and callable(select.select):
            if self._mode is None:                                                              # pragma: no cover
                self._mode = PL_SELECT
            self._available_modes.add(PL_SELECT)
        else:                                                                                   # pragma: no cover
            raise Error("System supports neither select.poll() nor select.select()")

    def __len__(self):
        return len(self._fd_map)

    def get_mode(self):
        return self._mode

    def set_mode(self, mode):
        if self._has_registered:
            raise Error("Mode can't be set once register() has been called")
        if mode in self._available_modes:
            old_mode = self._mode
            self._mode = mode
            return old_mode
        else:
            raise Error("Mode '%s' is not available" %
                    (self.get_mode_name(mode) if mode in self._mode_map else str(mode),))

    def get_mode_name(self, mode=None):
        if mode is None:
            mode = self._mode
        if mode in self._mode_map:
            return self._mode_map[mode]
        else:
            return "Mode" + str(mode)

    def get_available_modes(self):
        return self._available_modes

    def get_available_mode_names(self):
        names = []
        modes = list(self._mode_map)
        modes.sort()
        for mode in modes:
            if mode in self._available_modes:
                names.append(self.get_mode_name(mode))
        return names

    def get_event(self, evmask):
        s = ''
        for bit in self._poll_keys:
            if evmask & bit:
                if s:
                    s += ','
                s += self._poll_map[bit]
        return s

    def register(self, fo, eventmask=POLLIN|POLLOUT):
        fd = None
        try:
            #  This tests that the fd is an int type
            #  In python2, this will also coerce a long
            #  to an int.
            #
            fd = int(fo)
        except:
            pass
        if fd is None:
            if hasattr(fo, 'fileno') and callable(fo.fileno):
                fd = fo.fileno()
            else:
                raise Error("File object '%s' is neither 'int' nor object with fileno() method" % (str(fo),))
        if not isinstance(fd, int):
            raise Error("File object '%s' fileno() method did not return an 'int'" % (str(fo),))

        #  Trigger an exception if the fd in not an open file.
        #
        os.fstat(fd)

        if not self._has_registered:
            if self._mode == PL_KQUEUE:                                                         # pragma: no cover
                self._kq = select.kqueue()
            elif self._mode == PL_POLL:
                self._poll = select.poll()
            elif self._mode == PL_SELECT:
                self._rfos = set()
                self._wfos = set()
                self._xfos = set()
            self._has_registered = True
        if self._mode == PL_KQUEUE:                                                             # pragma: no cover
            if eventmask & POLLPRI:
                raise Error("POLLPRI is not supported in %s mode", self.get_mode_name(self._mode))
            self.unregister(fo)
            kl = []
            if eventmask & POLLIN:
                kl.append(select.kevent(fo, filter=select.KQ_FILTER_READ, flags=select.KQ_EV_ADD))
            if eventmask & POLLOUT:
                kl.append(select.kevent(fo, filter=select.KQ_FILTER_WRITE, flags=select.KQ_EV_ADD))
            self._fd_map[fd] = fo
            self._kq.control(kl, 0, 0)
        elif self._mode == PL_POLL:
            self._fd_map[fd] = fo
            return self._poll.register(fo, eventmask)
        elif self._mode == PL_SELECT:
            self.unregister(fo)
            self._fd_map[fd] = fo
            if eventmask & POLLIN:
                self._rfos.add(fo)
            if eventmask & POLLOUT:
                self._wfos.add(fo)
            if eventmask & POLLPRI:
                self._xfos.add(fo)

    def modify(self, fo, eventmask):
        if self._mode == PL_KQUEUE:
            self.register(fo, eventmask)
        elif self._mode == PL_POLL:
            return self._poll.modify(fo, eventmask)
        elif self._mode == PL_SELECT:
            self.register(fo, eventmask)

    def unregister(self, fo):
        fd = None
        try:
            fd = int(fo)
        except:
            pass
        if fd is None:
            if hasattr(fo, 'fileno') and callable(fo.fileno):
                fd = fo.fileno()
            else:
                raise Error("File object '%s' is neither 'int' nor object with fileno() method" % (str(fo),))
        if fd in self._fd_map:
            del self._fd_map[fd]
        if self._mode == PL_KQUEUE:                                                             # pragma: no cover
            ev = select.kevent(fo, filter=select.KQ_FILTER_READ, flags=select.KQ_EV_DELETE)
            try: self._kq.control([ev], 0, 0)
            except: pass
            ev = select.kevent(fo, filter=select.KQ_FILTER_WRITE, flags=select.KQ_EV_DELETE)
            try: self._kq.control([ev], 0, 0)
            except: pass
        elif self._mode == PL_POLL:
            return self._poll.unregister(fo)
        elif self._mode == PL_SELECT:
            self._rfos.discard(fo)
            self._wfos.discard(fo)
            self._xfos.discard(fo)

    def poll(self, timeout=None):
        if not self._has_registered:
            raise Error("poll() attempt before any objects have been registered")
        try:
            if self._mode == PL_KQUEUE:                                                         # pragma: no cover
                if timeout is not None:
                    timeout /= 1000.0
                evlist = []
                kelist = self._kq.control(None, 1024, timeout)
                if not kelist:
                    return evlist
                for ke in kelist:
                    fd = ke.ident
                    if fd not in self._fd_map:
                        raise Error("Unknown fd '%s' in kevent" % (str(fd),))
                    if ke.filter == select.KQ_FILTER_READ:
                        evlist.append((self._fd_map[fd], POLLIN))
                    elif ke.filter == select.KQ_FILTER_WRITE:
                        evlist.append((self._fd_map[fd], POLLOUT))
                    else:
                        raise Error("Unexpected filter 0x%x from kevent for fd %d" % (ke.filter, fd))
                return evlist
            elif self._mode == PL_POLL:
                evlist = []
                pllist = self._poll.poll(timeout)
                for pl in pllist:
                    (fd, mask) = pl
                    if fd not in self._fd_map:                                                  # pragma: no cover
                        raise Error("Unknown fd '%s' in select.poll()" % (str(fd),))
                    evlist.append((self._fd_map[fd], mask))
                return evlist
            elif self._mode == PL_SELECT:
                if timeout is not None:
                    timeout /= 1000.0
                rfos, wfos, xfos = select.select(self._rfos, self._wfos, self._xfos, timeout)

                #  select.select() already returns the registered object so no need
                #  to map through _fd_map.
                #
                evlist = []
                for fo in xfos:
                    evlist.append((fo, POLLPRI))
                for fo in rfos:
                    evlist.append((fo, POLLIN))
                for fo in wfos:
                    evlist.append((fo, POLLOUT))
                return evlist
        except Exception as e:
            ecode = None
            etext = None
            try:
                ecode = e.errno
                etext = e.strerror
            except:
                pass
            if ecode is None:
                try:
                    ecode = e[0]
                    etext = e[1]
                except:                                                                         # pragma: no cover
                    pass
            if ecode == errno.EINTR:
                raise OSError(ecode, etext)
            else:
                raise e                                                                         # pragma: no cover
