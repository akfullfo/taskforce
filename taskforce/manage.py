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

import sys, os

"""
Implement management interfaces.  Currently supports http,
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

		self._httpd.register_post(r'/manage/control', self.post)

	def post(self, path, postmap):
		postmap = self._httpd.merge_query(path, postmap)
		results = {}
		change_detected = False
		error_detected = False
		for taskname in postmap:
			task = self._legion.task_get(taskname)
			control = postmap[taskname][0]
			if not task:
				results[taskname] = 'not found'
				error_detected = True
			elif control not in self._legion.all_controls:
				results[taskname] = "bad control '%s'" % (control,)
				error_detected = True
			elif not task._config_pending or 'control' not in task._config_pending:
				results[taskname] = "no pending config"
				error_detected = True
			elif not task._config_running or 'control' not in task._config_running:
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
