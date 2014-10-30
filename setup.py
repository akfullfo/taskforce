#!/usr/bin/env python

from distutils.core import setup

setup(
	name = "taskforce",
	version = "0.0",
	description = """Taskforce starts and restarts daemon processes.
It will detect executable and/or module changes and automatically restart the affected processes.""",
	author = "Andrew Fullford",
	author_email = "git042013@fullford.com",
	maintainer = "Andrew Fullford",
	maintainer_email = "git042013@fullford.com",
	url = "https://github.com/akfullfo/taskforce",
	download_url = "https://github.com/akfullfo/taskforce/archive/master.zip",
	license = "Apache License, Version 2.0",

	packages = ['taskforce'],
	scripts = ['bin/taskforce'],
	requires = ['yaml'],
)
