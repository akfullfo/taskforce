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

import time
from . import httpd

"""
Implement management interfaces.  Currently supports http,
but other transports are plausible.  It is expected that
each transport will be implemented as a separate class
in this module so the classes can share module functions.
"""

class http(object):
    """
    Sets up a handler to allow limited task control via http.

    The change will persist until another control operation
    is performed, or the configuration file is changed
    which causes a normal reconfiguration.
"""
    def __init__(self, legion, httpd, **params):
        self._log = params.get('log')
        if not self._log:                                                                       # pragma: no cover
            self._log = logging.getLogger(__name__)
            self._log.addHandler(logging.NullHandler())
        self._legion = legion
        self._httpd = httpd
        self._allow_control = self._httpd.allow_control

        self._httpd.register_post(r'/manage/', self.control)
        self._httpd.register_get(r'/manage/', self.control)

    def control(self, path, postmap=None, **params):
        if not self._allow_control:
            return (403, 'Control not permitted on this path\n', 'text/plain')
        if path.startswith('/manage/control'):
            postmap = httpd.merge_query(path, postmap)
            results = {}
            change_detected = False
            error_detected = False
            for taskname in postmap:
                control = postmap[taskname][0]
                task = self._legion.task_get(taskname)
                if not task:
                    results[taskname] = 'not found'
                    error_detected = True
                elif control not in self._legion.all_controls:
                    results[taskname] = "bad control '%s'" % (control,)
                    error_detected = True
                elif not task._config_pending or 'control' not in task._config_pending:         # pragma: no cover
                    results[taskname] = "no pending config"
                    error_detected = True
                elif not task._config_running or 'control' not in task._config_running:         # pragma: no cover
                    results[taskname] = "no running config"
                    error_detected = True
                elif task._config_running['control'] == control:
                    results[taskname] = "no change"
                else:
                    results[taskname] = "ok"
                    change_detected = True
            text = ''
            for taskname in sorted(results):
                text += "%s\t%s\n" % (taskname, results[taskname])
            if error_detected:
                return (404, text, 'text/plain')
            for taskname in postmap:
                self._legion.task_get(taskname)._config_pending['control'] = postmap[taskname][0]
            if change_detected:
                self._legion._apply()
                return (202, text, 'text/plain')
            else:
                return (200, text, 'text/plain')
        elif path.startswith('/manage/count'):
            postmap = httpd.merge_query(path, postmap)
            results = {}
            counts = {}
            change_detected = False
            error_detected = True
            for taskname in postmap:
                try:
                    count = int(postmap[taskname][0])
                except:
                    results[taskname] = 'bad count "%s"' % (postmap[taskname][0],)
                    continue
                task = self._legion.task_get(taskname)
                if not task:
                    results[taskname] = 'not found'
                elif count <= 0:
                    results[taskname] = "non-positive count '%s'" % (count,)
                elif not task._config_pending or 'count' not in task._config_pending:           # pragma: no cover
                    results[taskname] = "no pending config"
                    error_detected = True
                elif not task._config_running or 'count' not in task._config_running:           # pragma: no cover
                    results[taskname] = "no running config"
                    error_detected = True
                elif task._config_running.get('count') == count:
                    error_detected = False
                    results[taskname] = "no change"
                else:
                    error_detected = False
                    results[taskname] = "ok"
                    counts[taskname] = count
                    change_detected = True
            text = ''
            for taskname in sorted(results.keys()):
                text += "%s\t%s\n" % (taskname, results[taskname])
            if error_detected:
                return (404, text, 'text/plain')
            if change_detected:
                for taskname in postmap:
                    self._legion.task_get(taskname)._config_pending['count'] = counts[taskname]
                self._legion._apply()
                self._legion.next_timeout()
                return (202, text, 'text/plain')
            else:
                return (200, text, 'text/plain')
        elif path.startswith('/manage/reload'):
            self._legion._reload_config = time.time()
            return (202, 'Taskforce config reload initiated\n', 'text/plain')
        elif path.startswith('/manage/stop'):
            self._legion.schedule_exit()
            return (202, 'Taskforce exit initiated\n', 'text/plain')
        elif path.startswith('/manage/reset'):
            self._legion.schedule_reset()
            return (202, 'Taskforce reset initiated\n', 'text/plain')
        else:
            return (404, 'Unknown control path -- %s\n' % (path, ), 'text/plain')
