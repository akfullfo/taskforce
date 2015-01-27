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

import time, json
from . import httpd
from . import utils

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
"""
	def __init__(self, legion, httpd, log=None):
		if log:
			self._log = log
		else:
			self._log = logging.getLogger(__name__)
			self._log.addHandler(logging.NullHandler())
		self._legion = legion
		self._httpd = httpd

		self._httpd.register_get(r'/status/tasks', self.status)
		self._httpd.register_post(r'/status/tasks', self.status)

	def status(self, path, postmap=None):
		q = httpd.merge_query(path, postmap)
		if 'fmt' in q:
			fmt = q['fmt']
		else:
			fmt = 'json'
		ans = {}
		for name, tinfo in self._legion._tasknames.items():
			t = tinfo[0]
			info = {}
			conf = t.get_config()
			if conf:
				info['control'] = t._get(conf.get('control'))
				info['count'] = t._get(conf.get('count'), default=1)
				info['processes'] = []
				for instance in range(len(t._pids)):
					proc = {}
					if t._pids[instance] is not None:
						proc['pid'] = t._pids[instance]
					if t._status[instance] is not None:
						proc['status'] = t._status[instance]
						proc['exit'] = utils.statusfmt(t._status[instance])
					if t._proc_start[instance] is not None:
						proc['started_t'] = t._proc_start[instance]
						proc['started'] = utils.time2iso(t._proc_start[instance])
					info['processes'].append(proc)
			ans[name] = info

		if fmt == 'json':
			return (200, json.dumps(ans, indent=4)+'\n', 'application/json')
		else:
			return (415, 'Invalid "fmt" request, supported formats are: json\n', 'text/plain')
