taskforce
=========
[![Version](https://pypip.in/version/taskforce/badge.svg)![Status](https://pypip.in/status/taskforce/badge.svg)![Downloads](https://pypip.in/download/taskforce/badge.svg)](https://pypi.python.org/pypi/taskforce/)[![Build](https://travis-ci.org/akfullfo/taskforce.svg?branch=master)](https://travis-ci.org/akfullfo/taskforce)

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](http://doctoc.herokuapp.com/)*

- [Introduction](#introduction)
- [Installation](#installation)
- [Taskforce Roles](#taskforce-roles)
- [Included Modules](#included-modules)
- [Task Context](#task-context)
- [Values and Lists](#values-and-lists)
- [Configuration File](#configuration-file)
  - [Top-level Keys](#top-level-keys)
  - [`defaults` and `defines`](#defaults-and-defines)
  - [The `tasks` tag](#the-tasks-tag)
  - [The `tasks.commands` tag](#the-taskscommands-tag)
  - [The `tasks.events` tag](#the-tasksevents-tag)
- [Example](#example)
- [Application](#application)
- [ToDo](#todo)
- [License](#license)
- [Acknowledgement](#acknowledgement)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


### Introduction ###
Taskforce starts and restarts daemon processes.  It will detect executable and/or module changes and automatically restart the
affected processes.  This supports python 2.7 and python 3 on Unix derivatives.

Commands to be run are defined in a configuration file in YAML format.  Let's go straight to a quick example:

```
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

The `ntpd` task configuration uses a couple of extra features.  First, it defines a tag for the configuration file name.  This is convenient for when the element is used in multiple places.  It also adds two events.  The first fires if the executable file changes, and the second fires if the configuration file changes.  The event type _self_ is shorthand for the equivalent _file_change_ event.  In both cases, the event will cause the task to be stopped.  As both tasks have the _wait_ `control`, they will then be restarted.

### Installation ###
The easiest way to install taskforce is with "pip" as:

    sudo pip install taskforce

This will install [taskforce](https://github.com/akfullfo/taskforce) from [PyPI](https://pypi.python.org/) and if necessary, install [PyYAML](http://pyyaml.org/).  On linux systems, it will also attempt to install [`inotifyx`](https://launchpad.net/inotifyx/).  `inotifyx` is optional but if available, taskforce will use *inotify(2)* to improve performance.  Installing `inotifyx` requires python-dev which can be installed (Debian-style) with:

    sudo apt-get install python-dev

or (Redhat Style) with:

    sudo yum install python-devel

If python-dev is not available, `inotifyx` will be skipped.  taskforce will still function but with higher overhead and latency.  If you install python-dev after installing taskforce, you can reinstall to get full *inotify(2)* functionality with:

    sudo pip install --upgrade --force taskforce

The `inotifyx` modules is neither needed nor useful on \*BSD or Mac OSX which both use *select.kqueue()*.

### Taskforce Roles ###

Roles are stored in a file, one name per line, on a taskforce host.  Each task in the configuration can be labelled with a list of roles.  The task will then only be started if one of the roles matches a role from the role file.

Roles provide a way of managing task allocation across different hosts while using a single distributed taskforce configuration file.  For example, a production service might consist of multple hosts with some running web front-ends, some running application services, and some running database backends.  These individual deployments could be labelled "web", "app", and "db".  Those names are then the *roles* and a role file on each host is used to indicate the roles that host is configured to handle.

The approach allows for flexible configuration:

Within | Roles | Deployment
-------|-------|------------
Large production system| web | Several hosts dedicated to the web role with other hosts handling other roles
Small production system| web<br>app | Two hosts handle web and app roles with other hosts handing the db roles
Sanity test system| web<br>app<br>db | A single host handles all roles.  It runs all regular sanity tests in an environment while exactly following standard production upgrade procedures.

The approach allows hosts to be configured in exactly the same way except for the roles file.  In addition, because the role file is continuously monitored for changes, a role file update will cause an automatic migration from one configuration to another, starting an stopping tasks as needed to meet the new scope.

### Included Modules ###
**task.py** holds the primary class `legion` which is the entry point into task management.  An effectively internal class `task` manages each task after it is defined by the configurtion.  There are also some classes and methods present for event handling and process execution.

**watch_files.py** handles triggering events to the event select loop when a file changes.

**watch_modules.py** handles triggering events to the event select loop when any of the modules of a python application change.  It uses *taskforce.watch_files* to detect the changes and *modulefinder* to identify the important modules used by an application.

**utils.py** holds support methods and classes

### Task Context ###
Each task is started based on a context.  The context is a key/value map that is intitalized to the Unix environment present
when the `legion.manage()` method is called.  The context is updated based on configuration file [`defaults` and `defines`](#defaults-and-defines) keys and specific internally generated values.  These are:

Key | Decription
:---|:----------
<a name="Task_name"></a>`Task_name`| The task name based on the configuration `tasks` key.
<a name="Task_pid"></a>`Task_pid`| The process ID of the task process
<a name="Task_ppid"></a>`Task_ppid`| The process ID of the application running the legion.
<a name="Task_pidfile"></a>`Task_pidfile`| The pidfile if specified in the configuration.
<a name="Task_cwd"></a>`Task_cwd`| The task current-working-directory if specified in the configuration.
<a name="Task_instance"></a>`Task_instance`| The instance number of the task process.  The value goes from 0 up to (but excluding) the number of processes configured for the task.  It will be 0 in the most common case where only one process is configured.  It is effectively a process slot number, so if a process exits, it will be restarted with the same instance number.
<a name="Task_user"></a>`Task_user`| The task user if specified in the configuration
<a name="Task_uid"></a>`Task_uid`| The numeric user id of the process.
<a name="Task_group"></a>`Task_group`| The task group if specified in the configuration
<a name="Task_gid"></a>`Task_gid`| The numeric group id of the process.
<a name="Task_host"></a>`Task_host`| The name of the host running the taskforce application.
<a name="Task_fqdn"></a>`Task_fqdn`| The fully qualified domain name of the host running the taskforce application.

When taskforce starts a process, the entire context is exported as the process's Unix environment.  In addition, the context is used to perform tagged substitutions in configuration file values.  Substitution tags are surrounded by braces. For example, a specification like:

    "path": "{PGDATA}/postgresql.conf"

would cause the value of PGDATA from the context to be substituted for the "{PGDATA}" string.  The value would have been loaded
into the context from the Unix environment or from a "defines" map.

### Values and Lists ###
Keys in the configuration file have values which may be scalar (strings and numbers) or lists (normally arrays of strings). For example, commands are defines using a list consisting of the command name and its arguments.

A special construct is supported for keys that take scalar or list values to give better control of the value based on the task
context.  This is particularly useful for command lists as it allows commands to be changed in fairly complex ways depending on
the Unix environment and the roles that are in scope.  This is done by allowing a map to be used where a scalar value might
appear.  Here is an example using a `start` command list:

<pre>
"tasks": {
    "db_server": {
        "pidfile": "/var/run/{<a href="#Task_name">Task_name</a>}.pid",
        "commands": {
            "start": [ "{Task_name}", {"VERBOSE": "-v"}, "-p", "{Task_pidfile}" ]
        }
    }
}
</pre>
In this example, the value after the command name in the start command is a map.  Each key in the map will be evaluated: if it
is present in the context then the key's value will included.  If the key is not present in the context, the value will be
skipped.  So for this case if VERBOSE was defined in the context, this would be run:
```
db_server -v -p /var/run/db_server.pid
```
If VERBOSE was not defined, this would be run:
```
db_server -p /var/run/db_server.pid
```

If a value is included, then it will be scanned recursively.  The conditional value could be a list, and the list could have
elements that are maps with more conditional values.  Here is a more complex example:
<pre>
"tasks": {
    "db_server": {
        "pidfile": "/var/run/{<a href="#Task_name">Task_name</a>}.pid",
        "commands": {
            "start": [
                "{Task_name}",
                    {"DEBUG": [
                        "-d", "{DEBUG}",
                        {"LOGFILE": ["-l": "{LOGFILE}"]}
                    ]},
                    "-p", "{Task_pidfile}"
            ]
        }
    }
}
</pre>

In this example, if DEBUG is defined as "2", the command would look like:
```
db_server -d 2 -p /var/run/db_server.pid
```
If LOGFILE is also defined as "/tmp/db_server.out", the command would be:
```
db_server -d 2 -l /tmp/db_server.out -p /var/run/db_server.pid
```
If DEBUG was not defined, neithe the -d or -l flags will be emitted even if LOGFILE is defined because that processing is
conditional on DEBUG being defined.

### Configuration File ###
taskforce configuration is traditionally done using YAML flow style which is effectlively JSON with comments and better error messages for format errors.  It is loaded using `yaml.safe_load()` so there should be no reason you can't use YAML block style if you prefer.

Like the roles file, the configuration file is continuously monitored and configuration changes will be reflect immediately by stopping, starting, or restarting tasks to match the new state.

The configuration consists of a key/value map at the top-level, where the values are further maps.  The term "map" here is the same as "associative array" or "dictionary".  The rest of this section describes the configuration keys in detail.

#### Top-level Keys ####
Key | Type | Decription
:---|------|:----------
<a name="defines"></a>`defines`| map | The associated map is added to the base context used when building commands and other parameter substitions.
<a name="role_defines"></a>`role_defines` | map | Maps individual roles to a key/value map.  The map is added to the context only if this role if in scope.
<a name="defaults"></a>`defaults`| map | Similar to `defines`, but entries are only added when no matching entry is present in the context.
<a name="role_defaults"></a>`role_defaults` | map | Similar to `role_defines`, but entries are only added when no matching entry is present in the context.
`tasks` | map | Normally this is largest top-level key as its value is a map of all task names with their definitions (see below).

#### `defaults` and `defines` ####
The top-level and task-level maps `defaults` and `defines` as well as `role_defaults` and `role_defines` are used to manipulate the [task context](#task-context).  The context becomes the Unix environment of the processes taskforce starts, so these maps also manipulate the process environment.

The order in which these maps are interpretted governs which entry will be used when building the context.  The interpretation order for *defines* is:

1. The top-level `defines`.
1. The top-level `role_defines` for any role that is in scope.
1. The task `defines`.
1. The task `role_defines` for any role that is in scope.

This gives the task *defines* precedence over the top-level *defines*.

The interpretation order for *defaults* is:

1. The task `role_defaults` for any role that is in scope.
1. The task `defaults`.
1. The top-level `role_defaults` for any role that is in scope.
1. The top-level `defaults`.

This is the opposite order to *defines* but results in the same precedence because the first matching *defaults* entry prevents further entries from being applied.

If more then one `role_defaults` or `role_defines` map is in scope because there are multiple active roles, and the maps contain the same key, it is indeterminate which value will be used.  It is best to avoid using the same key in cases where multiple roles may be in scope.

#### The `tasks` tag ####

Each key in the <a name="tasks"></a>`tasks` map describes a single task.  A task is made up of one or more processes which run concurrently with exactly the same configuration.

Key | Type | Decription
:---|------|:----------
`commands`| map | A map of commands used to start and manage a task.  See [`tasks.commands`](#the-taskscommands-tag).
<a name="control"></a>`control`| string | Describes how taskforce manages this task.<br>**once** indicates the task should be run when `legion.manage()` is first executed but the task will not be restarted.<br>**wait** indicates task processes once started  will be waited on as with *wait(2)* and will be restarted whenever a process exits to maintain the required process count.<p>Two additional controls are planned:<br>**nowait** handles processes that will always run in the background and uses probes to detect when a restart is needed.<br>**adopt** is similar to **nowait** but the process is not stopped when taskforce shuts down and is not restarted if found running when taskforce starts.<p>If not specified, **wait** is assumed.
<a name="count"></a>`count`| integer | An integer specifying the number of processes to be started for this task.  If not specified, one process will be started.  Each process will have exactly the same configuration except that the context items [`Task_pid`](#Task_pid) and [`Task_instance`](#Task_instance) will be specific to each process, and any context items derived from these values will be different.  This is particularly useful when defining the pidfile and procname values.
<a name="cwd"></a>`cwd`| string | Specifies the current directory for the process being run.
`defaults`| map | Similar to the top-level [`defaults`](#defaults) but applies only to this task.
`defines`| map | Similar to the top-level [`defines`](#defines) but applies only to this task.
`events`| map | Maps event types to their disposition as commands or signals.  See [`tasks.events`](#the-tasksevents-tag).
<a name="group"></a>`group`| string or integer | Specifies the group name or gid for the task.  An error occurs if the value is invalid or if taskforce does not have enough privilege to change the group.
<a name="pidfile"></a>`pidfile`| string | Registers the file where the process will write its PID.  This does nothing to cause the process to write the file, but the context item [`Task_pidfile`](#Task_pidfile) is available for use in the *start* command.  The value is used by taskforce to identify an orphaned task from a prior run so it can be restarted (**wait** and **nowait** controls) or adopted (**adopt** control).  In the case of **nowait** and **adopt** controls, it is also used to implement the default management commands *check* and *stop*.  Note that the **nowait** and **adopt** controls are not yet supported.
<a name="procname"></a>`procname`| string | The value is used when the *start* command is run as the `argv[0]` program name.  A common use when the `count` value is greater than 1 is to specify `'procname':` '{[`Task_name`](#Task_name)}-{[`Task_instance`](#Task_instance)}' which makes each instance of the task distinct in *ps(1)* output.
<a name="onexit"></a>`onexit`| map | Causes the specified operation to be performed after all processes in this task have exited following a *stop* command.  The only supported `onexit` operation is `'type': 'start'` which causes the named task to be started.  It normally would not make sense for a task to set itself to run again (that's handled by the *control* element).  This handles the case where a task needs a *once* task to be rerun whenever it exits.  For that reason, `'type': 'start' may only be issued against a *once* task.
<a name="requires"></a>`requires`| list | A list of task names that must have run before this task will be started.  *once* tasks are considered to have run only after they have exited.  Other controls (*wait*, *nowait*, *adopt*) are considered run as soon as any `start_delay` period has completed after the task has started.
`role_defaults`| map | Similar to the top-level [`role_defaults`](#role_defaults) but applies only to this task.
`role_defines`| map | Similar to the top-level [`role_defines`](#role_defines) but applies only to this task.
<a name="roles"></a>`roles`| list | A list of roles in which this task participates.  If none of the roles listed is active for this taskforce instance, the task will not be considered in scope and so will not be started.  If the `roles` item is not present, the task will always be in scope.
<a name="start_delay"></a>`start_delay`| number | A delay in seconds before other tasks that `requires` this task will be started.
<a name="user"></a>`user`| string or integer | Specifies the user name or uid for the task.  An error occurs if the value is invalid or if taskforce does not have enough privilege to change the user.

#### The `tasks.commands` tag ####
<a name="commands"></a>`commands` is a map of commands use to manage a task.  It is the only required `tasks` tag, and the only required command is the `start` command.  The command name is mapped to a list of command arguments, the first list element being the program to execute.  All list elements are formatted with the task context, so a command list can be very general, for example:
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

The `stop` command can be defined to override the built-in command stop function.  The built-in function issues a SIGTERM to the known process ID for each of the task's processes and escalates that to SIGKILL if the process does not exit within 5 seconds.  Explicitly defining a `stop` command overrides this behavior.  Care should be taken to ensure that a replacement `stop` command is rigorous in ensuring the process will have exited once the replacement command completes.

The `check` command can be defined to override built-in process checking.  The built-in function uses a zero signal to test for
the existence of the task's process IDs.  The replacement `check` command must exit 0 if the task's process is running normally
and non-zero if it should be restarted.  The `check` command (built-in or not) is only used with **nowait** and **adopt**
tasks (not currently supported).

In addition to these commands, other arbitrary commands can be defined which are run as the result of events (see below).

#### The `tasks.events` tag ####
<a name="events"></a>`events` is a list indicating the disposition of various event types.  For example, this configuration:
```
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

In this case, the *file_change* event will trigger when the configuration file is changed.  That will cause the *reconfig* command from the `commands` list to run.  That resolves to this command:
```
db_server_ctl -p /var/run/db_server.pid reload
```
Presumably this would cause the *db_server* process to reread its configuration.

If the *self* event is triggered, the *stop* command will be run.  Because no *stop* command has been explicitly defined, the built-in command will run, causing *db_server* to stop.  Once stopped, normal *wait* control takes over to immediately restart the task.

The following event types are supported:

Type | Decription
:----|:----------
<a name="file_change"></a>`file_change`| Performs the specified action if any of the files in the `path` list change.
<a name="python"></a>`python`| Performs the specified action if the python script run by this task changes, including any modules found via the PYTHONPATH enviroment variable.  Assigning this event to a task that does not use a python script will generate an error.
<a name="restart"></a>`restart`| Performs the action if the task is being restarted (stopped with the expectation it will be immediately restarted).  The action must cause the task to stop, but the task may choose to take special action on the assumption that it will be immediately restarted.  If the task does not exit within 5 seconds, the action will escalate to SIGKILL as with the built-in `stop` command.
<a name="self"></a>`self`| Performs the specified action if the file holding the task executable changes.

The following event actions are supported:

Action | Decription
:------|:----------
<a name="command"></a>`command`| Runs the command named which may be an explicit command from the `commands` tag or a built-in command.
<a name="signal"></a>`signal`| Sends the signal named.  Signal names can be written 'HUP', 'SIGHUP', 1, '1', etc.

### Example ###
Below is a more complete configuration example.  This is included in the Github source distribution as a working example that runs simulatations of the various tasks to avoid interfering with normal system processes.  The simulated programs mostly just sleep.  To run the example, download and unpack the code from githib then run:

```
cd .../taskforce/examples
./run frontend
```
This runs the example using the "frontend" role.  You can change the role to "backend" or use both roles to observe role behavior.  Use `./run -h` for more options.

The example itself is documented with comments so that it can be read separately in the source distribution.  Contol elements in the example are linked to the relevant discussion in this document.

<!-- CONFIG "example.conf" START linked by anchor_conf.  Keep comment to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN anchor_conf TO UPDATE -->
<pre>
{
    '<a href="#defaults">defaults</a>': {
        #  These defaults are applied globally to the context used when running all tasks.
        #  The values will only be used if they are not present in the environment or
        #  in the task-specified configurations.
        #
        #  The PATH value here will be used if no PATH was set in the environment when
        #  "taskforce" was started.  If security or other concerns justify mandate a
        #  specific PATH, the value can be set in the '<a href="#defines">defines</a>' section.  It can also
        #  be overriden for each task.
        #
        "PATH": "/usr/bin:/usr/sbin:/bin:/usr/local/bin:/usr/local/sbin",

        #  The EXAMPLES_BASE is a hook to allow the example script "run" to specify
        #  the base directory to be used.  In this example, if EXAMPLES_BASE is not
        #  set in the environment, "taskforce" will run from the root directory.
        #
        "EXAMPLES_BASE": "",
    },
    '<a href="#defines">defines</a>': {
        #  These defines are also global.  They will override environment values
        #  if present but will be overridden by task-specific defines.
        #
        "piddir": "{EXAMPLES_BASE}/var/run",
        "ntpd_conf": "/etc/ntp.conf",
        "confdir": "/usr/local/etc",
        "wsurl": "wss://localhost:9000/"
    },
    '<a href="#tasks">tasks</a>': {
        "timeset": {
            #  This task is run once when "taskforce" first starts.  It simulates
            #  running the base time setting operation of "ntpd" which is similar
            #  to using "ntpdate" but does not require a separate time service
            #  configuration.
            #
            '<a href="#control">control</a>': "once",

            #  The "commands" section defines one or more lists which are used
            #  to run commands.  Each task must have at least one command, the
            #  "start" command.  Refere to the "commands" description for other
            #  possible commands.
            #
            '<a href="#commands">commands</a>': { "start": ["ntpd", "-c", "{ntpd_conf}", "-n", "-g", "-q"] },
        },
        "ntpd": {
            #  The "ntpd" task is started when the "timeset" command has completed,
            #  indicated by the "requires" list.  The "wait" control indicates the
            #  command will be restarted if it exists.
            #
            '<a href="#control">control</a>': "wait",
            '<a href="#requires">requires</a>': [ "timeset" ],

            #  "pidfile" will be used internally by "taskforce" in the future (see
            #  description).  It also sets the "Task_pidfile" context value so the
            #  value will remain consistent between "taskforce" and the task.
            #
            '<a href="#pidfile">pidfile</a>': "{piddir}/{<a href="#Task_name">Task_name</a>}.pid",
            '<a href="#defines">defines</a>': {
                "keys": "/etc/ntp/ntp.keys",
                "drift": "/var/db/ntpd.drift"
            },

            #  This "start" command includes a more complex list expression (see
            #  'Values and Lists'), allowing the "run" script to cause the task to
            #  exit after a random interval (via the "-x" flag).  Using this option
            #  means the example will demonstrate task startup interaction (see the
            #  "onexit" element below).
            #
            '<a href="#commands">commands</a>': {
                "start": [
                    "{<a href="#Task_name">Task_name</a>}",
                        "-c", "{ntpd_conf}",
                        "-p", "{<a href="#Task_pidfile">Task_pidfile</a>}",
                        "-f", "{drift}",
                        "-n",
                        {"MINSLEEP": [
                            "--min-sleep", "{MINSLEEP}", {
                                "SLEEPRANGE": ["--sleep-range", "{SLEEPRANGE}"]
                            }
                        ]}
                ]
            },
            #  This event causes "ntpd" to restart if either the configuration
            #  file or the ntpd keys files change.  A "self" event has not been
            #  included so "ntpd" would not restart if the executable was updated,
            #  probably because such updates tend to coincide with a broad O/S
            #  upgrade that requires a server-reboot.
            #
            '<a href="#events">events</a>': [
                { "type": "file_change", "path": [ "{ntpd_conf}", "{keys}" ],
                  "command": "stop" }
            ],

            #  The "onexit" setting causes the "timeset" task to be rerun if ever the "ntpd"
            #  task exits.  "ntpd" will then re-wait for the "timeset" task to complete.
            #
            #  This interaction is actually a real-world case for ntpd.  If the system
            #  time gets wildly off, ntpd will panic and exit.  If ntpd is then just blindly
            #  restarted, it will continue to exit.  By triggering "timeset" after each
            #  exit, the time can be resynchronized before "ntpd" is restarted.
            #
            '<a href="#onexit">onexit</a>': [
                { "type": "start", "task": "timeset" }
            ]
        },
        "haproxy": {
            #  This task has '<a href="#roles">roles</a>' specified.  That means the task will only
            #  be started if the "frontend" role is present in the roles file.
            #
            #  Roles allow a single configuration file to be used for multiple
            #  deployment styles, given a global view of an entire system.
            #  That ensures that changes to configurations for tasks that are
            #  common to multiple roles are consisent across the deployment.
            #  However, it is perfectly reasonable to use a separate configuration
            #  for each host type if the global view is not needed or becomes
            #  cumbersome.
            #
            '<a href="#control">control</a>': "wait",
            '<a href="#roles">roles</a>': [ "frontend" ],
            '<a href="#requires">requires</a>': [ "ntpd" ],

            #  The '<a href="#start_delay">start_delay</a>' here means that other tasks that require this
            #  task will not be started for at least 1 second after this task
            #  starts.
            #
            '<a href="#start_delay">start_delay</a>': 1,
            '<a href="#defines">defines</a>': { "conf": "{confdir}/haproxy.conf" },
            '<a href="#commands">commands</a>': {
                "start": [ "{<a href="#Task_name">Task_name</a>}", "-f", "{conf}" ]
            },
            '<a href="#events">events</a>': [
                #  Here, a "self" event is used so the task will be restarted if
                #  the "haproxy" executable is updated.  That choice might be made
                #  if there is an expectation that "haproxy" will be updated frequently
                #  possibly because it includes locally supported modifications.
                #
                { "type": "self", "command": "stop" },
                { "type": "file_change", "path": [ "{conf}" ], "command": "stop" }
            ]
        },
        "httpd": {
            #  The "httpd" task is set to run if either or both "frontend"
            #  and "backend" roles are active.  With only these two roles
            #  in use, this is the equivalent of specifying no '<a href="#roles">roles</a>'.
            #  The advantage of enumerating them is that if an additional
            #  role is added, the task would not automatically be started
            #  for that role.  In the case of the "ntpd" task there is
            #  an expectation that this would be run on a server regardless
            #  of that server's role.
            #
            '<a href="#control">control</a>': "wait",
            '<a href="#roles">roles</a>': [ "frontend", "backend" ],
            '<a href="#requires">requires</a>': [ "ntpd" ],
            '<a href="#start_delay">start_delay</a>': 1,
            '<a href="#defines">defines</a>': {
                "conf": "{confdir}/httpd-inside.conf"
            },

            #  The '<a href="#role_defines">role_defines</a>' value here sets the configuration
            #  according to what role is active.  The default is
            #  to use the "inside" configuration which would possibly
            #  cover web-based administrative operations.
            #
            #  If the "frontend" role is active, this value will
            #  be overridden and the outside-facing web application
            #  would be used.
            #
            #  If both roles are active, the "frontend" role will
            #  trump the "backend" role.
            #
            '<a href="#role_defines">role_defines</a>': {
                "frontend": { "conf": "{confdir}/httpd-outside.conf" },
            },
            '<a href="#pidfile">pidfile</a>': "{piddir}/{<a href="#Task_name">Task_name</a>}.pid",
            '<a href="#commands">commands</a>': {
                "start": [ "{<a href="#Task_name">Task_name</a>}", "-f", "{conf}" ]
            },
            '<a href="#events">events</a>': [
                { "type": "self", "command": "stop" },
                { "type": "file_change",
                    "path": [
                        "{conf}",
                        "{confdir}/httpd-ssl.conf",
                        "/var/apache/conf/server.crt"
                    ],
                    "command": "stop" }
            ]
        },
        "ws_server": {
            #  The "ws_server" task is set to only start once the "httpd"
            #  task has started.
            #
            '<a href="#control">control</a>': "wait",
            '<a href="#roles">roles</a>': [ "frontend" ],
            '<a href="#requires">requires</a>': [ "httpd" ],

            #  This is set up to start 4 instances of this process.
            #
            '<a href="#count">count</a>': 4,

            #  Using the {<a href="#Task_instance">Task_instance</a>} value ensures that the pidfile is
            #  unique for each process, and will be a consistent set of names
            #  across multiple taskforce executions.
            #
            '<a href="#pidfile">pidfile</a>': "{piddir}/{<a href="#Task_name">Task_name</a>}-{<a href="#Task_instance">Task_instance</a>}.pid",
            '<a href="#commands">commands</a>': {
                "start": [ "{<a href="#Task_name">Task_name</a>}", "-l", "{wsurl}", "-p", "{<a href="#Task_pidfile">Task_pidfile</a>}" ]
            },
            '<a href="#events">events</a>': [
                #  The "python" event type requires that the task be written in
                #  Python.  The task is then examined and will be restarted in
                #  any of the non-system modules change.  This is useful because
                #  python applications tend to be implemented as a wrapper script
                #  that implements most of its functions via classes and modules.
                #  The python event type ensures that long-running python applications
                #  are always running the latest modules.
                #
                { "type": "python", "command": "stop" }
            ]
        },
        "db_server": {
            #  The "db_server" task is set to only run if the
            #  "backend" role is active.
            #
            '<a href="#control">control</a>': "wait",
            '<a href="#roles">roles</a>': [ "backend" ],
            '<a href="#requires">requires</a>': [ "httpd" ],
            '<a href="#defines">defines</a>': { "conf": "{confdir}/db.conf" },
            '<a href="#pidfile">pidfile</a>': "{piddir}/{<a href="#Task_name">Task_name</a>}.pid",
            '<a href="#commands">commands</a>': {
                "start": [ "{<a href="#Task_name">Task_name</a>}", "-c", "{conf}", "-n", "-p", "{<a href="#Task_pidfile">Task_pidfile</a>}" ]
            },
            '<a href="#events">events</a>': [
                { "type": "self", "command": "stop" },

                #  The "file_change" event will fire if the db_server configuration
                #  file changes.  In this case, the action is to signal the db_server
                #  process with SIGHUP, which presumably will cause it to reread
                #  its configuration.
                #
                { "type": "file_change", "path": [ "{conf}" ], "signal": "HUP" }
            ]
        },
    }
}
</pre>
<!-- CONFIG "example.conf" END linked by anchor_conf.  Keep comment to allow auto update -->

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
* Support the **nowait** and **adopt** controls
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
