#!/usr/bin/env python

import re
from setuptools import setup

version_file = 'VERSION'
with open(version_file, 'rt') as f:
	version = f.readline().strip()

if not re.match(r'^\d+(\.\d+)+$', version):
	raise Exception("Invalid version '%s' found in version file '%s'" % (version, version_file))

setup(
	name = "taskforce",
	version = version,
	description = """Taskforce starts and restarts daemon processes.
It will detect executable and/or module changes and automatically restart the affected processes.""",
	author = "Andrew Fullford",
	author_email = "git042013@fullford.com",
	maintainer = "Andrew Fullford",
	maintainer_email = "pypi102014@fullford.com",
	url = "https://github.com/akfullfo/taskforce",
	download_url = "https://github.com/akfullfo/taskforce/tarball/" + version,
	license = "Apache License, Version 2.0",

	packages = ['taskforce'],
	scripts = ['bin/taskforce'],
	install_requires = ['yaml>=3.09'],
)
