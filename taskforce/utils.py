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

import sys, os, re, fcntl, atexit, time, random, signal, inspect, pipes, logging
from logging.handlers import SysLogHandler

def get_caller(*caller_class, **params):
    """
    This is obsolete and references are being removed
"""
    (frame, file, line, func, contextlist, index) = inspect.stack()[1]

    try: class_name = frame.f_locals["self"].__class__.__name__
    except: class_name = None

    if class_name:
        name = class_name + '.'
    elif caller_class != ():                                                                    # pragma: no cover
        name = inspect.getmodule(caller_class[0]).__name__ + '.'
    elif hasattr(inspect.getmodule(frame), '__name__'):
        name = inspect.getmodule(frame).__name__ + '.'
    else:                                                                                       # pragma: no cover
        name = ''

    if func == '__init__' and class_name:
        name = class_name + '()'
    elif name == '__main__.':                                                                   # pragma: no cover
        name = func + '()'
    else:
        name += func + '()'

    if 'persist_place' in params:
        get_caller._Persist_Place = params['persist_place']

    log = params.get('log', logging.getLogger())
    if get_caller._Persist_Place or params.get('place') or log.isEnabledFor(logging.DEBUG):
        name += ' [+{} {}]'.format(line, os.path.basename(file))
    return name
get_caller._Persist_Place = None

def version_sort_key(version, digits=6):
    """
    Produces a canonicalized version string for standard version strings
    in the dotted-numeric-label format.  Function appropriate for use as
    the key function of sort().

    The conversion removes a possible prefix and reformats each key element
    as a long string of digits with leading zeros.  The number of digits
    in each element can be changed with "digits".  The prefix is replaced
    before the result is returned.  Prefixes match the regex '^\w+[_-]'
    where the next character is a digit.

    Non-conforming input is returned with only those completely numeric
    elements reformatted.
"""
    m = re.match('^(\w+[_-])(\d.*)$', version)
    if m:
        prefix = m.group(1)
        version = m.group(2)
    else:
        prefix = ''
    key = []
    for elem in version.split('.'):
        try:
            num = int(elem)
            elem = ('%0'+str(digits)+'d') % num
        except:
            pass
        key.append(elem)
    return prefix + '.'.join(key)

def version_cmp(ver_a, ver_b):
    """
    Compares two version strings in the dotted-numeric-label format.

    Returns -1 if a < b, 0 if a == b, and +1 if a > b.

    Inputs may include a prefix string that matches '^\w+[_-]', but
    both strings must start with the same prefix.  If present, it
    is ignored for purposes of comparision.  If it does not match,
    straight lexicographical ordering is used for the entire string.

    If a is None, it is always considered less than b, even if b
    is also None.

    The function also accepts the case where both args are ints
    or can be converted to ints.
"""
    if ver_a is None and ver_b is None:
        return 0
    if ver_a is None:
        return -1
    elif ver_b is None:
        return 1
    try:
        a = int(ver_a)
        b = int(ver_b)
        if a < b: return -1
        elif a > b: return 1
        else: return 0
    except:
        pass
    m = re.match('^(\w+[_-])(\d.*)$', ver_a)
    if m:
        pref_a = m.group(1)
        a = m.group(2)
    else:
        pref_a = ''
        a = ver_a
    m = re.match('^(\w+[_-])(\d.*)$', ver_b)
    if m:
        pref_b = m.group(1)
        b = m.group(2)
    else:
        pref_b = ''
        b = ver_b
    if pref_a != pref_b:
        if ver_a < ver_b: return -1
        else: return 1
    a = a.split('.')
    b = b.split('.')

    restrip = re.compile(r'[^\d]+$')

    for i in range(0, max(len(a), len(b))):
        if i >= len(a): return -1
        if i >= len(b): return 1
        astr = restrip.sub('', a[i])
        if not astr: astr = '0'
        bstr = restrip.sub('', b[i])
        if not bstr: bstr = '0'
        try: aint = int(astr)
        except: return -1                                                                       # pragma: no cover
        try: bint = int(bstr)
        except: return -1                                                                       # pragma: no cover
        if aint < bint: return -1
        elif aint > bint: return 1
    return 0

def ses(count, plural='s', singular=''):
    """
    ses is pronounced "esses".

    Return a string suffix that indicates a singular sense if
    the count is 1, and a plural sense otherwise.

    So, for example:
        log.info("%d item%s found", items, utils.ses(items))
    would log:
        "1 item found" if items was 1
    and:
        "0 items found" if items was 0

    And:
        log.info("%d famil%s found", 1, ses(1, singular='y', plural='ies'))
    or:
        log.info("%d famil%s found", 1, ses(1, 'ies', 'y'))
    would log:
        "1 family found" if items was 1
    and:
        "10 families found" if items was 10

    Note that the default covers pluralization for most English words and the positional
    override is ordered to handle most easily handfle other cases.

    This function officially has the highest comment:code ratio in our codebase.
"""
    return (singular if count == 1 else plural)

def deltafmt(delta, decimals = None):
    """
Returns a human readable representation of a time with the format:

    [[[Ih]Jm]K[.L]s

For example: 6h5m23s

If "decimals" is specified, the seconds will be output with that many decimal places.
If not, there will be two places for times less than 1 minute, one place for times
less than 10 minutes, and zero places otherwise
"""
    try:
        delta = float(delta)
    except:
        return '(bad delta: %s)' % (str(delta),)
    if delta < 60:
        if decimals is None:
            decimals = 2
        return ("{0:."+str(decimals)+"f}s").format(delta)
    mins = int(delta/60)
    secs = delta - mins*60
    if delta < 600:
        if decimals is None:
            decimals = 1
        return ("{0:d}m{1:."+str(decimals)+"f}s").format(mins, secs)
    if decimals is None:
        decimals = 0
    hours = int(mins/60)
    mins -= hours*60
    if delta < 3600:
        return "{0:d}m{1:.0f}s".format(mins, secs)
    else:
        return ("{0:d}h{1:d}m{2:."+str(decimals)+"f}s").format(hours, mins, secs)

def setproctitle(text):
    """
    This is a wrapper for setproctitle.setproctitle().  The call sets
    'text' as the new process title and returns the previous value.

    The module is commonly not installed.  If missing, nothing is changed,
    and the call returns None.

    The module is described here: https://pypi.python.org/pypi/setproctitle
"""
    try:
        import setproctitle
    except Exception as e:
        return None
    else:                                                                                       # pragma: no cover
        prev = setproctitle.getproctitle()
        setproctitle.setproctitle(text)
        return prev

def time2iso(unix_time, utc=False, terse=False, decimals=3):
    from math import pow
    from datetime import datetime
    if utc:
        tz_mins = 0
    else:
        tzdt = datetime.fromtimestamp(unix_time) - datetime.utcfromtimestamp(unix_time)
        tz_mins = int((tzdt.days * 24 * 3600 + tzdt.seconds)/60)
    if tz_mins == 0:
        if terse:
            tz = 'Z'
        else:
            tz = '+00:00'
    else:
        tz = "%+03d:%02d" % (tz_mins/60, tz_mins%60)
    if utc:
        tm = time.gmtime(unix_time)
    else:
        tm = time.localtime(unix_time)
    if decimals > 0:
        frac = '.' + "%0*.0f" % (decimals, (unix_time - int(unix_time)) * pow(10, decimals))
    else:
        frac = ''
    if terse:
        t = time.strftime("%Y%m%dT%H%M%S", tm) + frac + tz
    else:
        t = time.strftime("%Y-%m-%dT%H:%M:%S", tm) + frac + tz
    return t

def appname(path=None):
    """
Return a useful application name based on the program argument.
A special case maps 'mod_wsgi' to a more appropriate name so
web applications show up as our own.
"""
    if path is None:
        path = sys.argv[0]
    name = os.path.basename(os.path.splitext(path)[0])
    if name == 'mod_wsgi':
        name = 'nvn_web'                                                                        # pragma: no cover
    return name

def module_description(module__name__, module__doc__, module__file__):
    """
    Return formatted text that lists the module-level and class-level
    embedded documentation.  The function should be called exactly
    as:

        taskforce.utils.module_description(__name__, __doc__, __file__)

    The most common use for this function is to produce the help
    message for test code in a library module, which might look
    something like:

    if __name__ == "__main__":
        import ns_utils, argparse

        p = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                description=taskforce.utils.module_description(__name__, __doc__, __file__))
"""
    mod_name = os.path.splitext(os.path.basename(module__file__))[0]

    mod_desc = (lambda x: x + '\n' + '='*len(x) + '\n')('Module '+mod_name) if mod_name else ''
    for name, obj in inspect.getmembers(sys.modules[module__name__]):
        if inspect.isclass(obj) and '__doc__' in dir(obj) and obj.__doc__:
            mod_desc += '\n' + (lambda x: x + '\n' + '-'*len(x) + '\n')('Class '+name)
            mod_desc += obj.__doc__.lstrip()
    return mod_desc

sigmap = dict((signo, signam) for signam, signo in signal.__dict__.items()
                        if signam.startswith('SIG') and not signam.startswith('SIG_'))
def signame(sig):
    """
    Produce a symbolic signal name given a signal number.  This uses a
    cute scan of the signal module namespace to come up with the symbol
    mapping, so it should be accurate across different OSes.  The mapping
    suggestion came from stackoverflow, of course.
"""
    if sig in sigmap:
        return sigmap[sig]
    else:
        return 'SIG'+str(sig).lower()

def signum(signame):
    """
    Determine the signal from its name.  These forms are supported:

        signal object (needed for python >= 3.5)
        integer signal number
        text signal number
        SIGNAME (signal name in upper case)
        signame (signal name in lower case)
        NAME    (name without 'SIG' in upper case)
        name    (name without 'SIG' in lower case)

    In python 3.5 and above, "signal" is an object, so in addition
    to mapping signal numbers and stringified numbers, this also
    maps signal objects.
"""
    if signum.namemap is None:
        #  First time through, map evrything likely to its signal number
        #
        signum.namemap = {}
        for num, nam in sigmap.items():
            signum.namemap[num] = num
            signum.namemap[int(num)] = num
            signum.namemap[str(num)] = num
            signum.namemap[str(int(num))] = num
            signum.namemap[nam.upper()] = num
            signum.namemap[nam.lower()] = num
            abbr = nam.replace('SIG', '', 1)
            if abbr != nam:
                signum.namemap[abbr.upper()] = num
                signum.namemap[abbr.lower()] = num
    return signum.namemap.get(signame)
signum.namemap = None

def statusfmt(status):
    """
    Format an exit status as text.
"""
    if status == 0:
        msg = 'exited ok'
    elif os.WIFSIGNALED(status):
        msg = 'died on '+signame(os.WTERMSIG(status))
    elif os.WIFEXITED(status) and os.WEXITSTATUS(status) > 0:
        msg = 'exited '+str(os.WEXITSTATUS(status))
    else:
        msg = 'unknown exit code 0x%04x' % (status,)
    if os.WCOREDUMP(status):
        msg += ' (core dumped)'
    return msg

def sys_maxfd():
    """
    Returns the maximum file descriptor limit.  This is guaranteed to
    return a useful int value.
"""
    maxfd = None
    try:
        maxfd = int(resource.getrlimit(resource.RLIMIT_NOFILE)[0])
        if maxfd == resource.RLIM_INFINITY:                                                     # pragma: no cover
            maxfd = None
    except: pass
    if maxfd is None:
        maxfd = sys_maxfd.fallback_maxfd
    return maxfd
sys_maxfd.fallback_maxfd = 1000   # If param is 0 and the system lookup fails

def _pick_fd(obj, excludes):
    try:
        excludes[int(obj)] = True
        return
    except:
        pass
    try:
        excludes[obj.fileno()] = True
        return
    except:
        pass

def closeall(**params):
    """
    Close all file descriptors.  This turns out to be harder than you'd
    think.  For example, here is a discussion:

    http://stackoverflow.com/questions/899038/getting-the-highest-allocated-file-descriptor

    The default algorithm here is to close until "closeall.beyond_last_fd"
    close failures are registered.  The default value can be overriden.
    In some cases where a daemon handles a large number of connections,
    this approach may not be sufficient, so the "maxfd" param below
    alters the approach.

    Supported params are:

        exclude - Exclude the file descriptors in the int list provided
        beyond  - Override the closeall.beyond_last_fd value.
        maxfd   - If True, the system NOFILE value is used and closes
              will be attempted through this range.  If an int,
              the value will be used as a maximum.

    The method is intended to be safe against weird input and will never
    raise an exception.

    The method returns the highest fd closed or None if none were closed.
    It can be useful to log the highest fd because it can indicate a file
    descriptor leak in a parent process.
"""
    exclude_list = params.get('exclude')
    beyond = params.get('beyond')
    maxfd = params.get('maxfd')

    if maxfd:
        beyond = None
    elif not beyond:
        beyond = closeall.beyond_last_fd

    excludes = {}
    if exclude_list is not None:
        try:
            for s in exclude_list:
                _pick_fd(s, excludes)
        except:                                 # pragma: no cover
            _pick_fd(exclude_list, excludes)

    #  Find the largest excluded fd
    exlist = list(excludes)
    if len(exlist) > 0:
        exlist.sort(reverse=True)
        last_exc_fd = exlist[0]
    else:                                       # pragma: no cover
        last_exc_fd = None

    #  Find the maximum available fd

    if maxfd is True:
        maxfd = sys_maxfd()

    highest = -1
    fd = 0
    while True:
        if maxfd is None:
            if fd > highest + beyond:
                break
        elif fd > maxfd:
            break
        if not excludes.get(fd):
            try:
                os.close(fd)
                highest = fd
            except:
                pass
        fd += 1
    if highest == -1:
        return None
    else:
        return highest
closeall.beyond_last_fd = 200     # Stop closeall() after this many failures

def format_cmd(args):
    """
    Format the arg list appropriate for display as a command line with
    individual arguments quoted appropriately.  This is intended for logging
    or display and not as input to a command interpreter (shell).
"""
    if args is None:
        return ''
    out = ''
    if not isinstance(args, list):
        args = [str(args)]
    for arg in args:
        if out != '':
            out += ' '
        out += pipes.quote(str(arg))
    return out

def daemonize(**params):
    """
This is a simple daemonization method.  It just does a double fork() and the
parent exits after closing a good clump of possibly open file descriptors.  The
child redirects stdin from /dev/null and sets a new process group and session.
If you need fancier, suggest you look at http://pypi.python.org/pypi/python-daemon/

Application logging setup needs to be delayed until after daemonize() is called.

Supported params:

    redir   - Redirect stdin, stdout, and stderr to /dev/null.  Default
          is True, use "redir=False" to leave std files unchanged.

    log     - logging function, default is no logging.  A logging function
          works best if you use stderr or a higher fd because these are
          closed last.  But note that all fds are closed or associated
          with /dev/null, so the log param is really only useful for
          debugging this function itself.  A caller needing logging
          should probably use syslog.

    plus params appropriate for taskforce.utils.closeall().
"""
    log = params.get('log')
    redir = params.get('redir', True)

    try:
        if os.fork() != 0:
            os._exit(0)
    except Exception as e:
        if log: log("First fork failed -- %s", e)
        return False
    try:
        os.setsid()
    except Exception as e:
        if log: log("Setsid() failed -- %s", e)

    try:
        if os.fork() != 0:
            os._exit(0)
    except Exception as e:
        if log: log("Second fork failed, pressing on -- %s", e)

    try:
        os.chdir('/')
    except Exception as e:
        if log: log("Chdir('/') failed -- %s", e)
    if redir:
        try: os.close(0)
        except Exception as e:
            if log: log("Stdin close failed -- %s", e)
        try:
            fd = os.open('/dev/null', os.O_RDONLY)
        except Exception as e:
            if log: log("Stdin open failed -- %s", e)
        if fd != 0:
            if log: log("Stdin open returned %d, should be 0", fd)
        try: os.close(1)
        except Exception as e:
            if log: log("Stdout close failed -- %s", e)
        try:
            fd = os.open('/dev/null', os.O_WRONLY)
        except Exception as e:
            if log: log("Stdout open failed -- %s", e)
        if fd != 1:
            if log: log("Stdout open returned %d, should be 1", fd)

    try:
        os.setpgrp()
    except Exception as e:
        if log: log("Setpgrp failed -- %s", e)

    if redir:
        try: os.close(2)
        except Exception as e:
            if log: log("Stderr close failed -- %s", e)
        try:
            fd = os.dup(1)
        except Exception as e:
            if log: log("Stderr dup failed -- %s", e)
        if fd != 2:
            if log: log("Stderr dup returned %d, should be 2", fd)
    if 'exclude' not in params:
        params['exclude'] = [0,1,2]
    closeall(**params)

def log_filenos(log, cloexec=True):
    """
    Identify the filenos (unix file descriptors) of a logging object.
    This is most commonly used to avoid closing the log file descriptors
    after a fork so information can be logged before an exec().

    To prevent conficts and potential hangs, the default is to set the
    fcntl.FD_CLOEXEC close-on-exec flag for the file descriptors found.
    The can be inhibited with the 'cloexec' param.
"""
    filenos = []
    try:
        for handler in log.handlers:
            for name in dir(handler):
                attr = getattr(handler, name, None)
                if attr and hasattr(attr, 'fileno') and callable(attr.fileno):
                    filenos.append(attr.fileno())
        for fd in filenos:
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | fcntl.FD_CLOEXEC)
    except:
        pass
    return filenos

class PidClaimError(Exception):
    def __init__(self, message, pid = None, file = None):
        self.competing_pid = pid
        self.pidfile = file
        self.message = message
    def __str__(self):
        return str(self.message)

class pidclaim():
    active_pidfile = None
    temp_pidfile = None

    def __init__(self, pidfile = None, **params):
        """"
Claims a pidfile, ensuring that either there is no existing file or an existing
file does not contain the pid of a running process.  If no pidfile is passed, the
file "/var/run/program.pid" will be used.  "program" is based on the sys.argv[0]
value.  The directory when the file will be created must be writable by the
process.

If param 'noclean' is set, cleanup code will scheduled via atexit.register().
Instead the caller will have to arrange to either call pidclaim.clean() or
remove the pidfile independently.

If param 'pid' is set, this pid will be used in the lock.  This is useful
when a subprocess needs to claim a lock on behalf of its parent.
"""
        if pidfile is None:
            program = appname()
            pidfile = '/var/run/'+program+'.pid'

        if 'pid' in params:
            pid = int(params['pid'])
            if pid <= 1:
                raise PidClaimError("Invalid pid param '%s'" % (str(pid)))
        else:
            pid = os.getpid()

        self.active_pidfile = pidfile
        curpid = None

        pidfile_exists = False
        try:
            with open(self.active_pidfile, 'r') as f:
                curpid = f.read()
            pidfile_exists = True
            if curpid is not None:
                curpid = int(curpid.strip())
                ret = os.kill(curpid, 0)
                self.active_pidfile = None
        except Exception as e:
            #  We take any error to mean that the pidfile doesn't exist or it doesn't
            #  contain a valid pid.
            #
            pass

        #  There is an existing process flagged by clearing self.active_pidfile
        #  Give up and go home
        #
        if self.active_pidfile is None:
            raise PidClaimError("Existing '" + pidfile + "' process " + str(curpid) + " running", curpid, pidfile)

        #  If the pidfile exists, attempt to remove it -- we've already determined the
        #  referenced process is missing.
        #
        if pidfile_exists:
            try:
                os.unlink(self.active_pidfile)
            except:
                raise PidClaimError("Unable to remove existing '"+self.active_pidfile+
                            "' for zombie process", curpid, pidfile)
        self.temp_pidfile = self.active_pidfile + '.' + str(pid) + '.tmp'

        if os.path.exists(self.temp_pidfile):
            raise PidClaimError("Temp pidfile '"+self.temp_pidfile+"' already exists", curpid, pidfile)
        with open(self.temp_pidfile, 'w') as f:
            f.write(str(pid)+'\n')

        attempts = 0
        while True:
            attempts += 1
            try:
                os.symlink(self.temp_pidfile, self.active_pidfile)
                break
            except:
                if attempts > 3:
                    try: os.unlink(self.temp_pidfile)
                    except: pass
                    raise PidClaimError("Symlink of '"+self.temp_pidfile+"' failed after "
                                        +str(attempts)+" attempts", curpid, pidfile)
                time.sleep(0.2 * random.random())

        #  We have created a pidfile atomically, now clean up by renaming the symlink to be
        #  the pidfile
        #
        try:
            os.rename(self.temp_pidfile, self.active_pidfile)
            self.temp_pidfile = None
        except:
            try: os.unlink(self.temp_pidfile)
            except: pass
            raise PidClaimError("Symlink rename of '"+self.temp_pidfile+"' failed after "+str(attempts)+" attempts",
                                        curpid, pidfile)

        if 'noclean' not in params or not params['noclean']:
            atexit.register(self.clean)

    def clean(self):
        try:
            if self.active_pidfile is not None:
                os.unlink(self.active_pidfile)
                self.active_pidfile = None
            if self.temp_pidfile is not None:
                os.unlink(self.temp_pidfile)
                self.temp_pidfile = None
        except:
            pass
