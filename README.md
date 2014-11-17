taskforce
=========
[![Version](https://pypip.in/version/taskforce/badge.svg)![Status](https://pypip.in/status/taskforce/badge.svg)![Downloads](https://pypip.in/download/taskforce/badge.svg)](https://pypi.python.org/pypi/taskforce/)

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
  - [The `tasks.commands` tag](#the-taskscommands-tag)
  - [The `tasks.events` tag](#the-tasksevents-tag)
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

This will install [taskforce](https://github.com/akfullfo/taskforce) from [PyPI](https://pypi.python.org/) and if necessary, install [PyYAML](http://pyyaml.org/).  On linux systems, it will also attempt to install [`inotifyx`](https://launchpad.net/inotifyx/).  `inotifyx` is optional but if available, taskforce will use *inotify(2)* to improve performance.  Installing `inotifyx` requires python-dev which can be installed (Debian-style) with:

    sudo apt-get install python-dev

or (Redhat Style) with:

    sudo yum install python-devel

If python-dev is not available, `inotifyx` will be skipped.  taskforce will still function but with higher overhead and latency.  If you install python-dev after installing taskforce, you can reinstall to get full *inotify(2)* functionality with:

    sudo pip install --upgrade --force taskforce

`inotifyx` is neither needed nor useful on \*BSD or Mac OSX which both use *select.kqueue()*.

### Roles ###

Roles are stored in a file, one name per line, on a taskforce host.  Each task in the configuration can be labelled with a list of roles.  The task will then only be started if one of the roles matches a role from the role file.

Roles provide a way of managing task allocation across different hosts while using a single distributed taskforce configuration file.  For example, a production service might consist of multple hosts with some running web front-ends, some running application services, and some running database backends.  These individual deployments could be labelled "web", "app", and "db".  Those names are then the *roles* and a role file on each host is used to indicate the roles that host is configured to handle.

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
<a name="Task_name"></a>`Task_name`| The task name based on the configuration `tasks` key.
<a name="Task_pid"></a>`Task_pid`| The process ID of the task process
<a name="Task_ppid"></a>`Task_ppid`| The process ID of the application running the legion.
<a name="Task_pidfile"></a>`Task_pidfile`| The pidfile if specified in the configuration.
<a name="Task_cwd"></a>`Task_cwd`| The task current working directory if specified in the configuration.
<a name="Task_instance"></a>`Task_instance`| The instance number of the task process.  The value goes from 0 up to (but excluding) the number of processes configured for the task.  It will be 0 in the most common case where only one process is configured.  It is effectively a process slot number, so if a process exits, it will be restarted with the same instance number.
<a name="Task_user"></a>`Task_user`| The task user if specified in the configuration
<a name="Task_uid"></a>`Task_uid`| The numeric user id of the process.
<a name="Task_group"></a>`Task_group`| The task group if specified in the configuration
<a name="Task_gid"></a>`Task_gid`| The numeric group id of the process.
<a name="Task_host"></a>`Task_host`| The name of the host running the taskforce application.
<a name="Task_fqdn"></a>`Task_fqdn`| The fully qualified domain name of the host running the taskforce application.

When taskforce starts a process, the entire context is exported as the process environment.  In addition, the context is used to perform tagged substitutions in configuration file values.  Substitution tags are surrounded by braces. For example, a specification like:

    "path": "{PGDATA}/postgresql.conf"

would cause the value of PGDATA from the context to be substituted for the "{PGDATA}" string.  The value would have been loaded
into the context from the Unix environment or from a "defines" map.

### Configuration File ###
taskforce configuration is traditionally done using YAML flow style which is effectlively JSON with comments and better error messages for format errors.  It is loaded using `yaml.safe_load()` so there should be no reason you can't use YAML block style if you prefer.

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

Key | Decription
:---|:----------
`commands`| A map of commands used to start and manage a task.  See [`tasks.commands`](#the-taskscommands-tag).
`control`| Describes how taskforce manages this task.<br>**once** indicates the task should be run when `legion.manage()` is first executed.<br>**wait** indicates task processes will be waited on as with *wait(2)* and will be restarted whenever a process exits to maintain the required process count.<p>Two additional controls are planned:<br>**nowait** handles processes that do always run in the background and uses probes to detect when a restart is needed.<br>**adopt** is similar to **nowait** but the process is not stopped when taskforce shuts down and is not restarted if found running when taskforce starts.<p>If not specified, **wait** is assumed.
`count`| An integer specifying the number of processes to be started for this task.  If not specified, one process will be started.  Each process will have exactly the same configuration except that the context items [`Task_pid`](#Task_pid) and [`Task_instance`](#Task_instance) will be specific to each process, and any context items derived from these values will be different.  This is particularly useful when defining the pidfile and procname values.
`cwd`| Specifies the current directory for the process being run.
`defines`| Similar to the top-level `defines` but applies only to this task.
`events`| Maps event types to their disposition as commands or signals.  See [`tasks.events`](#the-tasksevents-tag).
`group`| Specifies the group name or gid for the task.  An error occurs if the value is invalid or if taskforce does not have enough privilege to change the group.
`pidfile`| Registers the file where the process will write its PID.  This does nothing to cause the process to write the file, but the context item [`Task_pidfile`](#Task_pidfile) is available for use in the *start* command.  The value is used by taskforce to identify an orphaned task from a prior run so it can be restarted (**wait** and **nowait** controls) or adopted (**adopt** control).  In the case of **nowait** and **adopt** controls, it is also used to implement the default management commands *check* and *stop*.  Note that the **nowait** and **adopt** controls are not yet supported.
`procname`| The value is used when the *start* command is run as the `argv[0]` program name.  A common use when the `count` value is greater than 1 is to specify `'procname':` '{[`Task_name`](#Task_name)}-{[`Task_instance`](#Task_instance)}' which makes each instance of the task distinct in *ps(1)* output.
`onexit`| Causes the specified operation to be performed after all processes in this task have exited following a *stop* command.  The only supported `onexit` operation is `'type': 'start'` which causes the named task to be started.  It normally would not make sense for a task to set itself to run again (that's handled by the *control* element).  This handles the case where a task needs a *once* task to be rerun whenever it exits.  For that reason, `'type': 'start' may only be issued against a *once* task.
`requires`| A list of task names that must have run before this task will be started.  *once* tasks are considered to have run only after they have exited.  Other controls (*wait*, *nowait*, *adopt*) are considered run as soon as any `start_delay` period has completed after the task has started.
`role_defines`| Similar to the top-level `role_defines` but applies only to this task.
`start_delay`| A delay in seconds before other tasks that `requires` this task will be started.
`user`| Specifies the user name or uid for the task.  An error occurs if the value is invalid or if taskforce does not have enough privilege to change the user.

#### The `tasks.commands` tag ####
`commands` is a map of commands use to manage a task.  It is the only required `tasks` tag, and the only required command is the `start` command.  The command name is mapped to a list of command arguments, the first list element being the program to execute.  All list elements are formatted with the task context, so a command list can be very general, for example:
<pre>
"tasks": {
    "db_server": {
        "pidfile": "/var/run/{<a href="#Task_name">Task_name</a>}.pid",
        "commands": {
            "start": [ "{Task_name}", "-p", "{Task_pidfile}" ]
        }
    }
}
</pre>
which would execute the command:
```
db_server -p /var/run/db_server.pid
```
In addition to the `start` command, there are two other standard commands.

The `stop` command can be defined to override the built-in command stop function.  The built-in function issues a SIGTERM to the known process ID for each of the tasks processes and escalates that to SIGKILL if the process does not exit within 5 seconds.  Explicitly defining a `stop` command overrides this behavior.  Care should be taken to ensure that a replacement `stop` command is rigorous in ensuring the process will have exited once the replacement command completes.

The `check` command can be defined to override built-in process checking.  The built-in function uses a zero signal to test for
the existence of the task's process IDs.  The replacement `check` command must exit 0 if the task's process is running normally
and non-zero if it should be restarted.  The `check` command (built-in or not) is only used with **nowait** and **adopt**
tasks (not currently supported).

In addition to these commands, other arbitrary commands can be defined which are run as the result of events (see below).

#### The `tasks.events` tag ####
`events` is a list indicating the disposition of various event types.  For example, this configuration:
```YAML
"tasks": {
    "db_server": {
        "defines": { "conf": "/etc/db_server.conf" },
        "pidfile": "/var/run/{Task_name}.pid",
        "commands": {
            "start": [ "{Task_name}", "-p", "{Task_pidfile}", "-f", "{conf}" ],
            "reconfig": [ "{Task_name}_ctl", "-p", "{Task_pidfile}", "reload" ]
        },
        "events": [
            { "type": "file_change", "path": [ "{conf}" ], "command": "reconfig" },
            { "type": "self", "command": "stop" }
        ]
    }
}
```
sets up two events.  The *file_change* event is triggered whenever a file in the *path* list changes.  The *self* event is triggered when the command executable file changes.  It is really just shorthand for the equivalent *file_change* event.

In this case, when the configuration file is changed, the command defined as *reconfig* will be run.  That resolves to this command:
```
db_server_ctl -p /var/run/db_server.pid reload
```
Presumably this would cause the *db_server* process to reread its configuration.

If the *self* event is triggered, the *stop* command will be run.  Because no *stop* command has been explicitly defined, the built-in command will run, causing *db_server* to stop.  Once stopped, normal *wait* control takes over to immediately restart the task.

The following event types are supported:

Type | Decription
:---|:----------
`file_change`| Performs the specified action if any of the files in the `path` list change.
`python`| Performs the specified action if the python script run by this task changes, including any modules found via the PYTHONPATH enviroment variable.  Assigning this event to a task that does not use a python script will generate an error.
`restart`| Performs the action if the task is being restarted (stopped with the expectation it will be immediately restarted).  The action must cause the task to stop, but the task may choose to take special action on the assumption that it will be immediately restarted.  If the task does not exit within 5 seconds, the action will escalate to SIGKILL as with the built-in `stop` command.
`self`| Performs the specified action if the file holding the task executable changes.

The following event actions are supported:

Action | Decription
:---|:----------
`command`| Runs the command named which may be an explicit command from the `commands` tag or a built-in command.
`signal`| Sends the signal named.  Signal names can be written 'HUP', 'SIGHUP', 1, '1', etc.

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
