#!/usr/bin/env python

import re
from setuptools import setup

version_file = 'taskforce/__init__.py'
readme_file = 'README.md'
version = ''
with open(version_file, 'rt') as f:
	m = re.search(r'''__version__\s*=\s*["'](\d+(\.\d+)+)["']''', f.read())
	if m:
		version = m.group(1)
if not re.match(r'^\d+(\.\d+)+$', version):
	raise Exception("Invalid version '%s' found in version file '%s'" % (version, version_file))

setup_parms = {
	'name': "taskforce",
	'version': version,
	'description': """Taskforce starts and restarts daemon processes.
It will detect executable and/or module changes and automatically restart the affected processes.""",
	'author': "Andrew Fullford",
	'author_email': "git042013@fullford.com",
	'maintainer': "Andrew Fullford",
	'maintainer_email': "pypi102014@fullford.com",
	'url': "https://github.com/akfullfo/taskforce",
	'download_url': "https://github.com/akfullfo/taskforce/tarball/" + version,
	'license': "Apache License, Version 2.0",
	'include_package_data': True,

	'packages': ['taskforce'],
	'scripts': ['bin/taskforce'],
	'install_requires': ['yaml>=3.09'],
}
try:
	with open(readme_file, 'rt') as f:
		setup_parms['long_description'] = f.read()
except:
	pass

setup(**setup_parms)
