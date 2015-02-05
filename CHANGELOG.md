Changelog
=========

0.3.4 (2015-02-04)
------------------

- Simple unreleased version string that pypi_push can fix. [Andrew
  Fullford]

- Changed mind, .gitchangelog.rc should be checked in.  currently is the
  exact sample for gitchangelog. [Andrew Fullford]

- Ignore .gitchangelog.rc. [Andrew Fullford]

0.3.3 (2015-02-02)
------------------

- Release 0.3.3. [Andrew Fullford]

- Merge branch 'master' of github.com:akfullfo/taskforce. [Andrew
  Fullford]

- Moved http service startup to config round.  service changes now noted
  in config.  service failures now retried. [Andrew Fullford]

- Shrank the SSLContext msg. [Andrew Fullford]

- Added cmp() method to HttpService class. [Andrew Fullford]

0.3.2 (2015-01-31)
------------------

- Release 0.3.2. [Andrew Fullford]

0.3.1 (2015-01-31)
------------------

- Release 0.3.1. [Andrew Fullford]

- Merge branch 'master' of github.com:akfullfo/taskforce. [Andrew
  Fullford]

- Expose a sample taskforce management service. [Andrew Fullford]

- Release 0.3.0. [Andrew Fullford]

- Include remote address in logging. [Andrew Fullford]

- Doc on status and management interface. [Andrew Fullford]

- Re-doctoc. [Andrew Fullford]

- Started on http docs, fixed example line width. [Andrew Fullford]

- Added /magae/count and /manage/reload paths. [Andrew Fullford]

- Support new proccess status class, added process info for exited,
  exit_pending. [Andrew Fullford]

- Added /magae/count and /manage/reload paths. [Andrew Fullford]

- Added a convenience function truthy() to test posted value for
  true/false strings. [Andrew Fullford]

- Add config dump to status interface. [Andrew Fullford]

- Include iso8601 time stamps in status. [Andrew Fullford]

- Service 0 override now honored without any listen change. [Andrew
  Fullford]

- Work around the way setuptools injects elements in front of where
  PYTHONPATH ends up. [Andrew Fullford]

- Add flag to override certfile. [Andrew Fullford]

- Magic : as interpreter apparently no longer supported in freebsd10.
  [Andrew Fullford]

- Fixed #8, don't let Task_xxx values from a parent affect the context
  in the child. [Andrew Fullford]

- Allow override of logging program name. [Andrew Fullford]

- Add flag to use syslog. [Andrew Fullford]

- Turn off testing for pypy. [Andrew Fullford]

- Turn on testing for pypy. [Andrew Fullford]

- Add settings config section, with http section to allow multiple HTTP
  services to be active. [Andrew Fullford]

- Moved sslcert file into examples tree.  added mockup of http settings
  to config. [Andrew Fullford]

- Provide http status service. [Andrew Fullford]

- Statusfmt() not using "exited ok" [Andrew Fullford]

- Bad merge_query() call. [Andrew Fullford]

- Reorg merge_query to provide a get_query() [Andrew Fullford]

- Handle case where legion might not have started. [Andrew Fullford]

- Enable stop and reset via http.  add flag to enable controls via http,
  status only otherwise. [Andrew Fullford]

- Adjusted execute mode. [Andrew Fullford]

- Use new http client routines. [Andrew Fullford]

- Env holds ssl cert path. [Andrew Fullford]

- Implements a client-side interface to the http service.  This will be
  used by bin/taskforce and is available to use by user-developed
  management programs. [Andrew Fullford]

- Allow for different default port when ssl is used. [Andrew Fullford]

- Added support for SSL with the HTTP service. [Andrew Fullford]

- Added support for unix domain sockets.  entry point to httpd module is
  now a function that returns the appropriate stream server instance.
  [Andrew Fullford]

- Drop osx.  need to figure out about python support. [Andrew Fullford]

- Another fix to host/port parsing.  this time for sure. [Andrew
  Fullford]

- Fix bug parsing http listen address.  change so exceptions during
  startup cause immediate exit. [Andrew Fullford]

- Enable task control management via http.  currently allows changing
  the "control" element which basically allows a task to be stopped or
  restarted. [Andrew Fullford]

- Task.py. [Andrew Fullford]

  enable task control management via http.  currently allows changing the "control" element which basically allows a task to be stopped or restarted


- Add code to response tuple.  add convenience function to merge uri
  query and body params. [Andrew Fullford]

- Allow_reuse_address was actually ok the way it was.  not sure why
  Travis CI is seeing address-already-in-use errors.  Try explicit del.
  [Andrew Fullford]

- Different way to set allow_reuse_address. [Andrew Fullford]

- Added POST test. [Andrew Fullford]

- Added GET test. [Andrew Fullford]

- New httpd test. [Andrew Fullford]

- Added listeners() to return all ports listened upon. [Andrew Fullford]

- Cosmetic -- removed #! line. [Andrew Fullford]

- Add http service to event loop. [Andrew Fullford]

- Add in http service startup. [Andrew Fullford]

- Add -w to offer up web service.  no implementation yet. [Andrew
  Fullford]

- Include a POST example. [Andrew Fullford]

- Added more complex test. fixed bug in content-length determination.
  [Andrew Fullford]

- Initial outline of a poll() compatible internal http service. [Andrew
  Fullford]

0.2.1 (2015-01-15)
------------------

- Release 0.2.1. [Andrew Fullford]

- Added count to example. [Andrew Fullford]

- Add -V (--version) flag. [Andrew Fullford]

- Fixed #7.  Return to using rename to update roles file.  Workaround
  added to taskforce.watch_files() handles case where file system does
  not file IN_DELETE_SELF or IN_MODE_SELF events on a file rename.
  Specific case is with simfs used with OpenVZ (containers), which
  happens to be used by Travis-CI. [Andrew Fullford]

- #7. Test simfs inotify work-around. [Andrew Fullford]

- #7. Attempt to manually catch rename events by recording inode number.
  These missing rename events appear to be related to this Travis CI
  issue, wherein the OpenVZ simfs filesystem isn't sending inotify file
  move/delete events: travis-ci/travis-ci#2342. [Andrew Fullford]

- Stop context formatting when an error occurs and use the last good
  value. [Andrew Fullford]

- Change exit codes to seventies because taskforce uses codes in the
  eighties. [Andrew Fullford]

- #7. force polling with inotifyx.  successfully reproduced the problem,
  but only on travis-ci. [Andrew Fullford]

- Add variable polling rate so test goes quicker with polling mode.
  [Andrew Fullford]

- Needed debug for test support. [Andrew Fullford]

- Need longeer timeout for polling mode. [Andrew Fullford]

- Generalize subprocess runner, add watch_files rename test. [Andrew
  Fullford]

- Add dummy -e flag. [Andrew Fullford]

- New script to test watch_files. [Andrew Fullford]

- Merge branch 'master' of github.com:akfullfo/taskforce. [Andrew
  Fullford]

- Increase log level. [Andrew Fullford]

- Revert to overwrite for roles file. [Andrew Fullford]

- Increase timeouts.  why do these fail on travis and not locally?
  [Andrew Fullford]

- Fix for FreeBSD which throws ":" after perfectly good program names in
  the ps(1) output. [Andrew Fullford]

- Taskforce.search() allows a list, all must be matched.  Use this to
  get better stability in tests. [Andrew Fullford]

- Enable subproc count assertions. [Andrew Fullford]

- Enabled error file count assertion. [Andrew Fullford]

- Create examples/var/run if needed.  it won't be there unless ./run has
  been executed. [Andrew Fullford]

- Include code to capture error files from procsim. [Andrew Fullford]

- Comment out stability test, not ready for prime time. [Andrew
  Fullford]

- Merge branch 'master' of github.com:akfullfo/taskforce. [Andrew
  Fullford]

- Need to track down a bug in ntpd simulation before process count
  assertions can be enabled. [Andrew Fullford]

- Record failure when in test mode (ie NOSE_LOG_LEVEL is set) [Andrew
  Fullford]

- Up logging level. [Andrew Fullford]

- Up logging level. [Andrew Fullford]

- Validate that taskforce has started the correct number of processes.
  [Andrew Fullford]

- Allow up to 1 second for the ps process to exit after output is
  consumed. [Andrew Fullford]

- Added example of a "count" param. [Andrew Fullford]

- Record the subprocess pid for callers. [Andrew Fullford]

- Removed python3 from the todo list because it might, or might not, be
  done. [Andrew Fullford]

0.2.0 (2015-01-09)
------------------

- Release 0.2.0. [Andrew Fullford]

- Move status to beta now python 3 seems to work. [Andrew Fullford]

- #6.  declare preliminary support for python 3.  it passes regression,
  anyway. [Andrew Fullford]

- Skip installation attempt for inotifyx with python 3 -- it doesn't
  work. [Andrew Fullford]

- Enable testing of python 3.3 and 3.4. [Andrew Fullford]

- #6. handle difference between py2 and py3 reading from nonblocking fd.
  [Andrew Fullford]

- #6. removed __del__().  This class holds no resources and we can
  depend on the underlying object that do to clean up.  Otherwise there
  is a race in python3 between the task cleanup and thw watch_files
  cleanup. [Andrew Fullford]

- Use the python exec for subcommands that was used by the caller.
  [Andrew Fullford]

- Allow python executable to be specified as a param. [Andrew Fullford]

- Fix usage message. [Andrew Fullford]

- Remove debug levels. [Andrew Fullford]

- Fix for generalized EINTR catching. [Andrew Fullford]

- #6.  more changes from .keys() to list() for py3. [Andrew Fullford]

- Change log level to debug timeout. [Andrew Fullford]

- Try a little more.  travis is probably slower than my bxoes. [Andrew
  Fullford]

- Needs more lax iolimit when log level is warning or higher. [Andrew
  Fullford]

- #6: use list() instead of .keys() to ensure list is a snapshot in py2
  and py3. [Andrew Fullford]

- Remove main section.  use nosetests instead. [Andrew Fullford]

- #6: use list() instead of .keys() building set. [Andrew Fullford]

- #6.  Improved inline description of last change. [Andrew Fullford]

- #6.  Coercing EINTR errors to always appear as OSError is fairly
  convoluted when trying to handle py2 and py3.  py3 adds
  InterruptedError which is unknown in py2.  Anyway this should cover it
  and it hides the complexity from above. [Andrew Fullford]

- #6. Move known_fds() to support.  Force garbage collection is a couple
  of places.  python3 delays gc causing a race condition with nosetests
  test cleanup code on file descriptor closes. [Andrew Fullford]

- #6.  register previous change -- Use list() instead of .keys() to
  snapshot dict key list against python3 issue.  Also added ses() call.
  [Andrew Fullford]

- #5.  Use list() instead of .keys() to snapshot dict key list. [Andrew
  Fullford]

- Better tracking of fd use. [Andrew Fullford]

- Exposed object cleanup code as close() - needed in unit test when
  tracking fd use.  normally can rely on __del__ during object GC.
  [Andrew Fullford]

- Https://github.com/akfullfo/taskforce/issues/5 fixed.  fds now
  correctly closed in WF_POLLING mode. [Andrew Fullford]

- Fix syntax error from last. [Andrew Fullford]

- Python3 conversion - os.write needs bytes not str. [Andrew Fullford]

- Support for python3. [Andrew Fullford]

- Allow for both OSError and IOError in valid fd test. [Andrew Fullford]

- Changes to support python3. [Andrew Fullford]

- Python3 conversion. [Andrew Fullford]

- Support for python3. [Andrew Fullford]

- Convert for python3. [Andrew Fullford]

- Fixed python3 change. [Andrew Fullford]

- Fixed child execution time report. [Andrew Fullford]

- Start of python3 support. [Andrew Fullford]

- Add flag to select python 2 or 3. [Andrew Fullford]

- Better environ control.  added test of role switching. [Andrew
  Fullford]

- Add some logging. [Andrew Fullford]

- Was not catching SIGTERM. made pidfile create error more obvious (exit
  code 85) [Andrew Fullford]

- Add poll() to ensure process wait. [Andrew Fullford]

- Add process tree scanning for testing that taskforce is running what
  it should be. [Andrew Fullford]

- Add search() for convenience. [Andrew Fullford]

- Add test of --sanity flag. [Andrew Fullford]

- Add config check test. [Andrew Fullford]

- Get ready to run task unit tests. [Andrew Fullford]

- Finalize watch_modules unit tests, handle log level names. [Andrew
  Fullford]

- Moved func to support. [Andrew Fullford]

- Get ready for watch_modules tests. [Andrew Fullford]

- Moved logging setup into support module. [Andrew Fullford]

- Use taskforce.poll module instead of select. [Andrew Fullford]

0.1.21 (2014-12-13)
-------------------

- Release 0.1.21. [Andrew Fullford]

- Fixed issue with missing not working.  actually it was, but
  missing=True is now the default. [Andrew Fullford]

- Assertion incorrect in inotifyx mode. [Andrew Fullford]

- Inotifyx mode was closing watch-descriptors as if they were file
  descriptors in the object destructor. [Andrew Fullford]

- New test, but needs update once a bug it found is fixed. [Andrew
  Fullford]

- Try out the osx test support. [Andrew Fullford]

- Removed some debugs. [Andrew Fullford]

- Tests for utils. [Andrew Fullford]

- Add travis-ci badge. [Andrew Fullford]

- Travis CI integration. [Andrew Fullford]

- Move testing to tests/test_poll.py for nosetests. [Andrew Fullford]

- Testing for poll module. [Andrew Fullford]

- Soften info on EINTR to debug. [Andrew Fullford]

- Full mapping of EINTR exception. [Andrew Fullford]

- Kqueue and poll actually raise OSError on interrupted system call.
  [Andrew Fullford]

- Switch to using generalized poll module instead of select.select()
  [Andrew Fullford]

- Translate OSError into IOError for EINTR to be consistent with
  select.poll() [Andrew Fullford]

- Translate select.error into IOError for EINTR to be consistent with
  select.poll() [Andrew Fullford]

- Implemented object/fd mapping. [Andrew Fullford]

- Doc and tests for object event return instead of fd.  implementation
  to come. [Andrew Fullford]

- Added support for kqueue. [Andrew Fullford]

- Added select.select() implementation. [Andrew Fullford]

- Added poll() implementation - basically just pass-thru. [Andrew
  Fullford]

- Baseline for generalized fd activity poll. [Andrew Fullford]

- More descriptive comments in example. [Andrew Fullford]

- Add todo - support nowait and adopt. [Andrew Fullford]

- Adjusted formatting so example fits in pre-box width. [Andrew
  Fullford]

- Added doc on value and list processing. [Andrew Fullford]

- Better signal handling. [Andrew Fullford]

- Updated example description. [Andrew Fullford]

- First test of example injection. [Andrew Fullford]

- Default/define refs. [Andrew Fullford]

- Preparing for long example in doc. [Andrew Fullford]

- Fixed wording.  two events but they apply to only one task. [Andrew
  Fullford]

0.1.20 (2014-11-30)
-------------------

- Release 0.1.20. [Andrew Fullford]

- Handle the death rattle inotify event when a wd is removed. [Andrew
  Fullford]

- Improved function comment. [Andrew Fullford]

- Add timestamp (non-syslog) and log level to log output. [Andrew
  Fullford]

0.1.19 (2014-11-30)
-------------------

- Release 0.1.19. [Andrew Fullford]

- Catching wrong exception for EINTR. [Andrew Fullford]

- Remove google-site-verification meta tag. [Andrew Fullford]

0.1.18 (2014-11-30)
-------------------

- Release 0.1.18. [Andrew Fullford]

- Add google-site-verification meta tag. [Andrew Fullford]

- Wrong interpreter. [Andrew Fullford]

0.1.17 (2014-11-30)
-------------------

- Release 0.1.17. [Andrew Fullford]

0.1.16 (2014-11-30)
-------------------

- Release 0.1.16. [Andrew Fullford]

0.1.15 (2014-11-30)
-------------------

- Release 0.1.15. [Andrew Fullford]

- Use portable #! python header. [Andrew Fullford]

- Fixed bugs related to inotifyx watch removal. [Andrew Fullford]

0.1.14 (2014-11-29)
-------------------

- Release 0.1.14. [Andrew Fullford]

0.1.13 (2014-11-29)
-------------------

- Release 0.1.13. [Andrew Fullford]

- Exercise the MINSLEEP and SLEEPRANGE conditionals. [Andrew Fullford]

- Demonstrate new conditionals in values. [Andrew Fullford]

- Allow dicts and lists in config values to provide conditionals.
  [Andrew Fullford]

- Allow -v. [Andrew Fullford]

- Add -C flag, relayed to taskforce. [Andrew Fullford]

- Removed procpath, didn't make sense because you couldn't tell which
  command it applied to. [Andrew Fullford]

- Add macos to platform list. [Andrew Fullford]

0.1.12 (2014-11-21)
-------------------

- Release 0.1.12. [Andrew Fullford]

- Better wording. [Andrew Fullford]

- Better spacing. [Andrew Fullford]

- Added "defaults" and "role_defaults" [Andrew Fullford]

- First pass, more complex example. [Andrew Fullford]

- Added processing for 'defaults' and 'roles_defaults' [Andrew Fullford]

- Export EXAMPLES_BASE so samples can have a non-system work area.
  [Andrew Fullford]

- Fix similation flags and code. [Andrew Fullford]

- Add examples/var tree. [Andrew Fullford]

- Added web-socket server. [Andrew Fullford]

- Add flags for ntp behavior. [Andrew Fullford]

- Ignore file generated when example is run. [Andrew Fullford]

- Wording improvement. [Andrew Fullford]

- Parts for operating example. [Andrew Fullford]

- Link back to pypi. [Andrew Fullford]

- Add pypi badges. [Andrew Fullford]

- Test anchors in code-blocks. [Andrew Fullford]

- Test anchors. [Andrew Fullford]

- Test anchors. [Andrew Fullford]

- Test anchors. [Andrew Fullford]

- Test anchors. [Andrew Fullford]

- Fixed tabbing. [Andrew Fullford]

- Another format fix. [Andrew Fullford]

- Format fix. [Andrew Fullford]

- Filled out tasks.events tag. [Andrew Fullford]

- Filled out tasks.commands tag. [Andrew Fullford]

- Filled out next level of tags. [Andrew Fullford]

0.1.11 (2014-11-13)
-------------------

- Release 0.1.11. [Andrew Fullford]

- Only set IN_OPEN when triggering the event for the appearance of a
  pending file.  this cuts a bunch of events we don't want when python
  processes open module files. [Andrew Fullford]

0.1.10 (2014-11-12)
-------------------

- Release 0.1.10. [Andrew Fullford]

- Context change detection not isolated from per-process updates
  triggering continuous restart cycle on Linux. [Andrew Fullford]

- Added key descs. [Andrew Fullford]

- Use less emphasis. [Andrew Fullford]

- Fix links. [Andrew Fullford]

- Added installation instructions. [Andrew Fullford]

- Added details about task context. [Andrew Fullford]

- Updated TOC. [Andrew Fullford]

- Update README.md. [Andrew Fullford]

  Added top-level tag description

- Update README.md. [Andrew Fullford]

  Added roles description

- Test toc generation. [Andrew Fullford]

- Changes to allow conversion with "pandoc --from=markdown_github"
  [Andrew Fullford]

- Expose link to github.  Add MacOS support. [Andrew Fullford]

- Remove the short description from top so we don't see everything
  twice. [Andrew Fullford]

- Make sanity check noisier when inotifyx not installed on a linux
  system. [Andrew Fullford]

0.1.9 (2014-11-07)
------------------

- Release 0.1.9. [Andrew Fullford]

- Fixed README rst formatting. [Andrew Fullford]

0.1.8 (2014-11-07)
------------------

- Release 0.1.8. [Andrew Fullford]

- Added sanity test. easy way to be sure required and optional packages
  are present. [Andrew Fullford]

- Include inotifyx on linux iff python-dev is available.  added
  classifiers. [Andrew Fullford]

0.1.7 (2014-11-05)
------------------

- Release 0.1.7. [Andrew Fullford]

- Use simplified README for PyPI. [Andrew Fullford]

- Replace symlink with an abbreviated README. [Andrew Fullford]

- Add support for linux inotifyx.  uses polling if not present. [Andrew
  Fullford]

- Addition application doc. [Andrew Fullford]

- Try without long desc but with README. [Andrew Fullford]

- Better formatting when not processed as markdown. [Andrew Fullford]

0.1.6 (2014-11-02)
------------------

- New version 0.1.6. [Andrew Fullford]

- Fixed some problems with the conversion of bin/taskforce. [Andrew
  Fullford]

- Use README instead of README.md. [Andrew Fullford]

- Use symlink to keep setuptools and github happy about README. [Andrew
  Fullford]

0.1.5 (2014-11-02)
------------------

- Correct name for PyYAML. [Andrew Fullford]

0.1.4 (2014-11-02)
------------------

- Version 0.1.4. [Andrew Fullford]

- Made the readme optional. [Andrew Fullford]

- New version for setup. [Andrew Fullford]

- Setup changes. [Andrew Fullford]

- Setup changes. [Andrew Fullford]

0.1.2 (2014-10-31)
------------------

- Switch to setuptools.  added version file. [Andrew Fullford]

0.1.1 (2014-10-31)
------------------

- Release 0.1.1. [Andrew Fullford]

- Incorrect URL. [Andrew Fullford]

- Added MANIFEST. [Andrew Fullford]

- Point pypi at readme. [Andrew Fullford]

0.1 (2014-10-31)
----------------

- Typo. [Andrew Fullford]

- Fix download url. [Andrew Fullford]

- Typo. [Andrew Fullford]

- Dedicated maintainer email. [Andrew Fullford]

- Trying out pip install. [Andrew Fullford]

- More modules. [Andrew Fullford]

- Functional command to run a taskforce configuration.  can be used as
  an example of how to call the taskforce module or used directly.
  [Andrew Fullford]

- Completed conversion from external utilities. [Andrew Fullford]

- Fix copyright. [Andrew Fullford]

- Core code.  still needs work to satisfy imports. [Andrew Fullford]

- Fix hori rule. [Andrew Fullford]

- Added license text. [Andrew Fullford]

- Merge branch 'master' of github.com:akfullfo/taskforce. [Andrew
  Fullford]

- Added module descriptions. [Andrew Fullford]

- Added module descriptions. [Andrew Fullford]

- Modules to handle file and module change events. [Andrew Fullford]

- Added example. [Andrew Fullford]

- Update README.md. [Andrew Fullford]

- Update README.md. [Andrew Fullford]

- Initial commit. [Andrew Fullford]


