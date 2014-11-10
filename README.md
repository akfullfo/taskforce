taskforce
=========

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](http://doctoc.herokuapp.com/)*

- [Introduction](#introduction)
- [Installation](#installation)
- [Roles](#roles)
- [Included Modules](#included-modules)
- [Task Context](#task-context)
- [Configuration File](#configuration-file)
  - [Top-level Keys](#top-level-keys)
  - [The `tasks` tag](#the-tasks-tag)
- [Application](#application)
- [ToDo](#todo)
- [License](#license)
- [Acknowledgement](#acknowledgement)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


### Introduction ###
Taskforce starts and restarts daemon processes.  It will detect executable and/or module changes and automatically restart the affected processes.  Initially this supports python 2.7 on Unix derivatives.

Commands to be run are defined in a configuration file in YAML format.  Let's go straight to a quick example:

```YAML
{
    "tasks": {
        "sshd": {
            "control": "wait",
            "commands": { "start": [ "/usr/sbin/sshd", "-D" ] }
        },
        "ntpd": {
            "control": "wait",
            "requires": "sshd",
            "defines": { "conf": "/etc/ntp.conf" },
            "commands": { "start": [ "/usr/sbin/ntpd", "-c", "{conf}", "-n"] },
            "events": [
                { "type": "self", "command": "stop" },
                { "type": "file_change", "path": "{conf}", "command": "stop" }
            ]
        }
    }
}
```
In this example, `taskforce` starts `sshd` and then starts `ntpd`.  `taskforce` is set to wait on both programs and both programs are started so that they will not detach themselves.  If either program exits, it will be restarted.

`ntpd` is run with a couple of extra features.  First, it defines a tag for the configuration file name.  This is convenient for when the element is used in multiple places.  It also adds two events.  The first fires if the executable file changes, and the second fires if the configuration file changes.  The event type _self_ is shorthand for the equivalent _file_change_ event.  In both cases, the event will cause the task to be stopped.  As both tasks have the _wait_ `control`, they will then be restarted.

### Installation ###
The easiest way to install taskforce is with "pip" as:

    sudo pip install taskforce

This will install [`taskforce`](https://github.com/akfullfo/taskforce) from [PyPI](https://pypi.python.org/) and if necessary, install [`PyYAML`](http://pyyaml.org/).  On linux systems, it will also attempt to install [`inotifyx`](https://launchpad.net/inotifyx/).  `inotifyx` is optional but if available, `taskforce` will use *inotify(2)* to improve performance.  Installing `inotifyx` requires python-dev which can be installed (Debian-style) with:

    sudo apt-get install python-dev

or (Redhat Style) with:

    sudo yum install python-devel

If python-dev is not available, `inotifyx` will be skipped.  `taskforce` will still function but with higher overhead and latency.  If you install python-dev after installing `taskforce`, you can reinstall to get full *inotify(2)* functionality with:

    sudo pip install --upgrade --force taskforce

`inotifyx` is neither needed nor useful on \*BSD or Mac OSX which both use *select.kqueue()*.

### Roles ###

Roles are stored in a file, one name per line, on a `taskforce` host.  Each task in the configuration can be labelled with a list of roles.  The task will then only be started if one of the roles matches a role from the role file.

Roles provide a way of managing task allocation across different hosts while using a single distributed `taskforce` configuration file.  For example, a production service might consist of multple hosts with some running web front-ends, some running application services, and some running database backends.  These individual deployments could be labelled "web", "app", and "db".  Those names are then the *roles* and a role file on each host is used to indicate the roles that host is configured to handle.

The approach allows for flexible configuration:

Within | Roles | Deployment
-------|-------|------------
Large production system| web | Several hosts dedicated to the web role with other hosts handling other roles
Small production system| web<br>app | Two hosts handle web and app roles with other hosts handing the db roles
Sanity test system| web<br>app<br>db | A single host handles all roles.  It runs all regular sanity tests in an environment while exactly following standard production upgrade procedures.

The approach allows hosts to be configured in exactly the same way except for the roles file.  In addition, because the role file is continuously monitor for changes, a role file update will cause an automatic migration from one configuration to another, starting an stopping tasks as needed to meet the new scope.

### Included Modules ###
**task.py** holds the primary class `legion` which is the entry point into task management.  An effectively internal class `task` manages each task after it is defined by the configurtion.  There are also some classes and methods present for event handling and process execution.

**watch_files.py** handles triggering events to the event select loop when a file changes.

**watch_modules.py** handles triggering events to the event select loop when any of the modules of a python application change.  It uses *taskforce.watch_files* to detect the changes and *modulefinder* to identify the important modules used by an application.

**utils.py** holds support methods and classes

### Task Context ###
Each task is started based on a context.  The context is a key/value map that is intitalized to the Unix environment present when the `legion.manage()` method is called.  The context is updated based on configuration file `defines` keys (see below) and specific internally generated values.  These are:

Key | Decription
:---|:----------
`Task_name`| The task name based on the configuration `tasks` key.
`Task_pid`| The process ID of the task process
`Task_ppid`| The process ID of the application running the legion.
`Task_pidfile`| The pidfile if specified in the configuration.
`Task_cwd`| The task current working directory if specified in the configuration.
`Task_instance`| The instance number of the task process.  The value goes from 0 up to (but excluding) the number of processes configured for the task.  It will be 0 in the most common case where only one process is configured.  It is effectively a process slot number, so if a process exits, it will be restarted with the same instance number.
`Task_user`| The task user if specified in the configuration
`Task_uid`| The numeric user id of the process.
`Task_group`| The task group if specified in the configuration
`Task_gid`| The numeric group id of the process.
`Task_host`| The name of the host running the taskforce application.
`Task_fqdn`| The fully qualified domain name of the host running the taskforce application.

When `taskforce` starts a process, the entire context is exported as the process environment.  In addition, the context is used to perform tagged substitutions in configuration file values.  Substitution tags are surrounded by braces. For example, a specification like:

    "path": "{PGDATA}/postgresql.conf"

would cause the value of PGDATA from the context to be substituted for the "{PGDATA}" string.  The value would have been loaded
into the context from the Unix environment or from a "defines" map.

### Configuration File ###
`taskforce` configuration is traditionally done using YAML flow style which is effectlively JSON with comments and better error messages for format errors.  It is loaded using `yaml.safe_load()` so there should be no reason you can't use YAML block style if you prefer.

Like the roles file, the configuration file is continuously monitored and configuration changes will be reflect immediately by stopping, starting, or restarting tasks to match the new state.

The configuration consists of key/value map at the top-level, where the values are further maps.  The term "map" here means the same thing as associative array or dictionary.  The rest of this section describes the configuration keys in detail.

#### Top-level Keys ####
Key | Decription
:---|:----------
`defines`| The associated map is added to the base context used when building commands and other parameter substitions.
`role_defines` | Maps individual roles a key/value map.  The map is added to the context if this role if in scope.
`tasks` | Normally this is largest top-level key as its value is a map of all task names with their definitions (see below).

#### The `tasks` tag ####

Each key in the `tasks` map describes a single task.  A task is made up of one or more processes which have exactly the same configuration.

### Application ###
Also included is **bin/taskforce** which provides an operational harness for running a taskforce legion.  It also serves as an example of how the `taskforce.task.legion()` class should be called.

Here is the help message:
```

usage: taskforce [-h] [-v] [-q] [-e] [-b] [-p PIDFILE] [-f CONFIG_FILE]
                 [-r ROLES_FILE] [-C] [-R] [-S]

Manage tasks and process pools

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Verbose logging for debugging
  -q, --quiet           Quiet logging, warnings and errors only
  -e, --log-stderr      Log to stderr instead of syslog
  -b, --background      Run in the background
  -p PIDFILE, --pidfile PIDFILE
                        Pidfile path, default /var/run/taskforce.pid, "-"
                        means none
  -f CONFIG_FILE, --config-file CONFIG_FILE
                        Configuration. File will be watched for changes.
                        Default /usr/local/etc/taskforce.conf
  -r ROLES_FILE, --roles-file ROLES_FILE
                        File to load roles from. File will be watched for
                        changes. Default is selected from:
                        /var/local/etc/tf_roles.conf,
                        /usr/local/etc/tf_roles.conf
  -C, --check-config    Check the config and exit
  -R, --reset           Cause the background taskforce to reset. All
                        unadoptable tasks will be stopped and the program will
                        restart itself.
  -S, --stop            Cause the background taskforce to exit. All
                        unadoptable tasks will be stopped.
```
### ToDo ###
* Extend support for python 3
* Add a control path
* Add status access
* Support logging or other capture of task output
* Add external events (snmp traps, nagios via NSCA)

### License ###
<center>
Copyright &copy; 2014 Andrew Fullford
</center>

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the License for the specific language governing permissions and limitations under the License.

### Acknowledgement ###
This package is based on work done by Andrew Fullford at Netsocket, Inc.  On October 16, 2014, Netsocket allowed this code to be publicly released under the Apache License.
