#!/usr/bin/env python

import re, sys, os
from setuptools import setup

def has_pynotifyx():
    ok = False
    try:
        import pynotifyx
        ok = True
    except: pass
    return ok

def has_developer_tools():
    ok = False
    try:
        from distutils import sysconfig
        python_h = os.path.join(sysconfig.get_config_vars()['INCLUDEPY'], 'Python.h')
        if os.path.exists(python_h):
            ok = True
    except Exception as e:
        sys.stderr.write("Warning: Could not determine if python-dev is installed -- " + str(e) + "\n")
    return ok

def get_requires(namesonly = False):
    requires = ['PyYAML>=3.09']
    if sys.platform.startswith('linux'):
        if has_developer_tools():
            requires += ['pynotifyx>=0.3.7']
        elif not has_pynotifyx():
            sys.stderr.write("""
---------------------------------------------------------------------

WARNING: The linux implementation will use the "pynotifyx" bindings to
         inotify(7) if available.  On this system, "inotifyx" is not
         already present and the "python-dev" system is not loaded so
         "pynotifyx" can't be installed.  "taskforce" will still work,
         but with a slightly higher overhead and lower responsiveness.

         If you would like to gain full performance, install the
         "python-dev" package which is needed to install "pynotifyx",
         for example, using:

            sudo apt-get install python-dev
         or:
            sudo yum install python-devel

         Then rerun the the "taskforce" installation as:

            sudo pip install --upgrade --force taskforce

---------------------------------------------------------------------
""")
    return requires

version_file = 'taskforce/__init__.py'
readme_file = 'README'
version = ''
with open(version_file, 'rt') as f:
    m = re.search(r'''__version__\s*=\s*["'](\d+(\.\d+)+)["']''', f.read())
    if m:
        version = m.group(1)
if not re.match(r'^\d+(\.\d+)+$', version):
    raise Exception("Invalid version '%s' found in version file '%s'" % (version, version_file))

name = 'taskforce'

requires = get_requires()

setup_parms = {
    'name': name,
    'provides': [name],
    'version': version,
    'description': ("Taskforce starts and restarts daemon processes.  " +
                    "It will detect executable and/or module changes and automatically restart the affected processes."),
    'author': "Andrew Fullford",
    'author_email': "git042013@fullford.com",
    'maintainer': "Andrew Fullford",
    'maintainer_email': "pypi102014@fullford.com",
    'url': "https://github.com/akfullfo/taskforce",
    'download_url': "https://github.com/akfullfo/taskforce/tarball/" + version,
    'license': "Apache License, Version 2.0",
    'include_package_data': True,
    'platforms': ['Linux', 'BSD', 'Mac OS X'],
    'classifiers': [
        'Development Status :: 4 - Beta',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: POSIX :: BSD',
        'Operating System :: MacOS :: MacOS X',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Software Distribution',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities',
    ],
    'packages': [name],
    'scripts': [os.path.join('bin', name)],
    'requires': [re.sub(r'\W.*', '', item) for item in requires],
    'install_requires': requires,
}
try:
    with open(readme_file, 'rt') as f:
        setup_parms['long_description'] = f.read()
except:
    pass

setup(**setup_parms)
