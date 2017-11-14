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

import sys, platform, time, json
from . import httpd
from . import utils
from .__init__ import __version__ as taskforce_version

"""
Implement status interfaces.  Currently supports http,
but other transports are plausible.  It is expected that
each transport will be implemented as a separate class
in this module so the classes can share module functions.
"""

class http(object):
    """
    Sets up a handler to allow limited task control via http.

    The interface currently allows the 'control' setting
    of a previously established task to be changed.

    The change will persist until another control operation
    is performed, or the configuration file is changed
    which causes a normal reconfiguration.

    These are the standard options for the class methods:

          fmt       -  Placeholder for other content formatting (eg XML).
                   Currently only "json" is supported.
          indent    -  Indent to make formatted output more human-readable.
                   Default is no indent which removes unnecessary padding.

    Standard options are supported in the format routines.
"""
    def __init__(self, legion, httpd, **params):
        self._log = params.get('log')
        if not self._log:                                                                       # pragma: no cover
            self._log = logging.getLogger(__name__)
            self._log.addHandler(logging.NullHandler())

        self._legion = legion
        self._httpd = httpd

        self._httpd.register_get(r'/status/version', self.version)
        self._httpd.register_post(r'/status/version', self.version)
        self._httpd.register_get(r'/status/tasks', self.tasks)
        self._httpd.register_post(r'/status/tasks', self.tasks)
        self._httpd.register_get(r'/status/config', self.config)
        self._httpd.register_post(r'/status/config', self.config)

        self._formatters = {}
        for attr in dir(self):
            if attr.startswith('_format_'):
                func = getattr(self, attr)
                if callable(func):
                    name = attr.replace('_format_', '', 1)
                    self._formatters[name] = func

    def _format_json(self, ans, q):
        """
        Generate a json response string.
    """
        params = {}
        try: params['indent'] = int(q.get('indent')[0])
        except: pass

        return json.dumps(ans, **params)+'\n'

    def _format(self, ans, q):
        """
        Returns the response tuple according to the selected format.
        A format is available if the method "_format_xxx" is callable.
        The default format is json.
    """
        if 'fmt' in q:
            fmt = q['fmt'][0]
        else:
            fmt = 'json'

        fmt = fmt.lower()

        if fmt in self._formatters:
            return (200, self._formatters[fmt](ans, q), 'application/json')
        else:
            return (415,
                'Invalid fmt request "%s", supported formats are: %s\n'%
                    (fmt, ' '.join(self._formatters.keys()),),
                'text/plain')

    def version(self, path, postmap=None, **params):
        """
        Return the taskforce version.

        Supports standard options.
    """
        q = httpd.merge_query(path, postmap)

        ans = {
            'taskforce': taskforce_version,
            'python': '.'.join(str(x) for x in sys.version_info[:3]),
        }
        ans['platform'] = {
            'system': platform.system(),
        }

        #  Add in some extra details if this is a control path.
        #  These might give away too many details on a public
        #  path.
        #
        if self._httpd.allow_control:
            ans['platform']['platform'] = platform.platform()
            ans['platform']['release'] = platform.release()

        return self._format(ans, q)

    def config(self, path, postmap=None, **params):
        """
        Return the running configuration which almost always matches the
        configuration in the config file.  During a reconfiguration, it may
        be transitioning to the new state, in which case it will be different
        to the pending config.  Neither the running or pending configurations
        necessarily match the operational state, either because a task has
        exited and not yet restarted, or because a task control has been
        changed via the management interface.

        Supports standard options.
    """

        q = httpd.merge_query(path, postmap)

        ans = self._legion._config_running
        if not ans: ans = {}

        return self._format(ans, q)

    def tasks(self, path, postmap=None, **params):
        """
        Return the task status.  This delves into the operating structures
        and picks out information about tasks that is useful for status
        monitoring.

        For each task, the response includes:

          control   - The active task control value, whoich may have been
                  changed via the management interface.
          count     - The number of processes configured to run for the
                  task.  This does not necessarily correspond to the
                  process list below if tasks are failing or the
                  control is set to "off".
          processes - A list of the running processes for the task.
                  Each entry may contain:
                    pid     - The process ID of the process currently
                              running in this slot.  If "pid" is not
                          present, no process is running in the
                          slot.
                    started - The ISO8601 date stamp when the
                              process started.
                    started_t   - The Unix time_t of when the process
                              started.
                    status  - The exit code for the last time this
                              process exited.
                    exit    - The status translated for human
                              consumption.

        Not that the status and exit values are not cleared if the process
        has successfully restarted.

        Supports standard options.
    """
        q = httpd.merge_query(path, postmap)

        ans = {}
        for name, tinfo in self._legion._tasknames.items():
            t = tinfo[0]
            info = {}
            conf = t.get_config()
            if conf:
                info['control'] = t._get(conf.get('control'))
                info['count'] = t._get(conf.get('count'), default=1)
                info['processes'] = []
                for p in t._proc_state:
                    if p is None: continue
                    proc = {}
                    if p.pid is not None:
                        proc['pid'] = p.pid
                    if p.exit_code is not None:
                        proc['status'] = p.exit_code
                        proc['exit'] = utils.statusfmt(p.exit_code)
                    if p.started is not None:
                        proc['started_t'] = p.started
                        proc['started'] = utils.time2iso(p.started)
                    if p.exited is not None:
                        proc['exited_t'] = p.exited
                        proc['exited'] = utils.time2iso(p.exited)
                    if p.pending_sig is not None:                                               # pragma: no cover
                        proc['exit_pending'] = True
                    info['processes'].append(proc)
            ans[name] = info

        return self._format(ans, q)
