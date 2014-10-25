taskforce
=========

### Introduction ###
Taskforce starts and restarts daemon processes.  It will detect executable and/or module changes and automatically restart the affected processes.

Initially this supports python 2.7 on Unix derivatives.  At the moment it has specific support for select.kqueue so operates efficiently on MacOS and *BSD.

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
In this example, `taskforce` starts `sshd` and then starts `ntpd`.  `taskforce` is set to wait on both programs and both
programs are started so that they will not detach themselves.  If either program exits, it will be restarted.

`ntpd` is run with a couple of extra features.  First, it defines a tag for the configuration file name.  This is convenient
for when the element is used in multiple places.  It also adds two events.  The first fires if the executable file changes, and
the second fires if the configuration file changes.  The event type _self_ is shorthand for the equivalent _file_change_ event.
In both cases, the event will cause the task to be stopped.  As both tasks have the _wait_ `control`, they will then be
restarted.

### Included Modules ###
*watch_files.py* handles triggering events to the event select loop when a file changes.

*watch_modules.py* handles triggering events to the event select loop when any of the modules of a python application change.
    It uses watch_files.py to detect the changes and *modulefinder* to identify the important modules used by an application.

### ToDo ###
* Add pyinotify support so it operates efficiently with Linux
* Extend support for python 3
* Add a control path
* Add status access
* Add external events (snmp traps, nagios via NSCA)
