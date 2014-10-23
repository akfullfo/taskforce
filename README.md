taskforce
=========

Taskforce starts and restarts daemon processes.  It will detect executable and/or module changes and automatically restart the affected processes.

Initially this supports python 2.7 on Unix derivatives.  At the moment it has specific support for select.kqueue so operates efficiently on MacOS and *BSD.

ToDo
----
Add pyinotify support so it operates efficiently with Linux
Extend support for python 3
Add a control path
Add status access
Add external events (snmp traps, nagios via NSCA)
