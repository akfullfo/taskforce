#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ________________________________________________________________________
#
#  Copyright (C) 2014 Andrew Fullford
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ________________________________________________________________________
#

import os, sys, logging, time, fcntl
import taskforce.poll
from taskforce.utils import deltafmt
import support
from support import get_caller as my

env = support.env(base='.')

#  Find possible polling modes
known_polling_modes = set(taskforce.poll.__dict__[mode] for mode in taskforce.poll.__dict__ if mode.startswith('PL_'))

class Test(object):

    @classmethod
    def setUpAll(self, mode=None):
        self.log = support.logger()
        self.log.info("%s started", self.__module__)
        self.poll_fd = None
        self.poll_send = None

    @classmethod
    def tearDownAll(self):
        self.log.info("%s ended", self.__module__)

    def self_pipe(self):
        """
        A self-pipe is a convenient way of exercising some polling
    """
        self.poll_fd, self.poll_send = os.pipe()
        for fd in [self.poll_fd, self.poll_send]:
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        self.log.info("%s poll_fd = %d, poll_send = %d", my(self), self.poll_fd, self.poll_send)
        return (self.poll_fd, self.poll_send)

    def close_pipe(self):
        if self.poll_fd is not None:
            try: os.close(self.poll_fd)
            except: pass
            self.poll_fd = None
        if self.poll_send is not None:
            try: os.close(self.poll_send)
            except: pass
            self.poll_send = None

    def dump_evlist(self, poll, tag, evlist):
        if evlist:
            self.log.info("%s Event list from %s ...", my(self), tag)
            for fd, ev in evlist:
                self.log.info("    %s on fd %s", poll.get_event(ev), str(fd))
        else:
            self.log.info("%s Event list from %s is empty", my(self), tag)

    def Test_A_mode(self):
        log_level = self.log.getEffectiveLevel()

        poll = taskforce.poll.poll()
        mode = poll.get_mode()
        allowed_modes = poll.get_available_modes()
        self.log.info("%s Default polling mode is '%s' of %s",
                        my(self), poll.get_mode_name(mode=mode), str(poll.get_available_mode_names()))

        #  get_mode_name() should always return a string
        #
        name = poll.get_mode_name(mode='junk')
        self.log.info("%s get_mode_name() response to invalid mode %s", my(self), name)
        assert type(name) is str

        #  Format multiple events
        #
        evtext = poll.get_event(taskforce.poll.POLLIN|taskforce.poll.POLLOUT)
        self.log.info("%s get_event() response to multiple events %s", my(self), evtext)
        assert type(name) is str

        #  Format bad events
        #
        evtext = poll.get_event(taskforce.poll.POLLIN|taskforce.poll.POLLOUT|0x800)
        self.log.info("%s get_event() response to multiple events %s", my(self), evtext)
        assert type(name) is str

        #  Invalid event input
        #
        try:
            #  Mask the log message as we expect a failure
            self.log.setLevel(logging.CRITICAL)
            poll.get_event(None)
            self.log.setLevel(log_level)
            expected_error_occurred = False
        except Exception as e:
            self.log.setLevel(log_level)
            self.log.info("%s Received expected invalid event error -- %s", my(self), str(e))
            expected_error_occurred = True
        assert expected_error_occurred

        #  Should always be able to force PL_SELECT
        poll.set_mode(taskforce.poll.PL_SELECT)
        assert poll.get_mode() == taskforce.poll.PL_SELECT

        #  Find a mode that is not available
        bad_mode = None
        for mode in known_polling_modes:
            if mode not in allowed_modes:
                bad_mode = mode
                break
        self.log.info("%s Determined unavailable mode as %s", my(self), poll.get_mode_name(mode=bad_mode))

        #  Check that we can't set mode to None
        #
        try:
            #  Mask the log message as we expect a failure
            self.log.setLevel(logging.CRITICAL)
            poll.set_mode(None)
            self.log.setLevel(log_level)
            expected_error_occurred = False
        except Exception as e:
            self.log.setLevel(log_level)
            self.log.info("%s Received expected error -- %s", my(self), str(e))
            expected_error_occurred = True
        assert expected_error_occurred

        #  Check that we can't set mode to an impossible value
        #
        try:
            #  Mask the log message as we expect a failure
            self.log.setLevel(logging.CRITICAL)
            poll.set_mode(-1)
            self.log.setLevel(log_level)
            expected_error_occurred = False
        except Exception as e:
            self.log.setLevel(log_level)
            self.log.info("%s Received expected error -- %s", my(self), str(e))
            expected_error_occurred = True
        assert expected_error_occurred

        #  Check that we can't set an unavailable mode
        #
        try:
            #  Mask the log message as we expect a failure
            self.log.setLevel(logging.CRITICAL)
            poll.set_mode(bad_mode)
            self.log.setLevel(log_level)
            expected_error_occurred = False
        except Exception as e:
            self.log.setLevel(log_level)
            self.log.info("%s Received expected error -- %s", my(self), str(e))
            expected_error_occurred = True
        assert expected_error_occurred

    def Test_B_register(self):
        log_level = self.log.getEffectiveLevel()
        poll = taskforce.poll.poll()
        currmode = poll.get_mode()
        self.log.info("%s Default polling mode is '%s' of %s",
                        my(self), poll.get_mode_name(mode=currmode), str(poll.get_available_mode_names()))

        #  Find a valid mode that is not the current mode
        #
        nextmode = None
        for mode in poll.get_available_modes():
            if mode != currmode:
                nextmode = mode
        self.log.info("%s Determined valid non-active mode as %s", my(self), poll.get_mode_name(mode=nextmode))

        poll_fd, poll_send = self.self_pipe()
        poll.register(poll_fd)

        #  Test that an attempt to change mode is rejected
        #
        try:
            #  Mask the log message as we expect a failure
            self.log.setLevel(logging.CRITICAL)
            poll.set_mode(nextmode)
            self.log.setLevel(log_level)
            expected_error_occurred = False
        except Exception as e:
            self.log.setLevel(log_level)
            self.log.info("%s Received expected error -- %s", my(self), str(e))
            expected_error_occurred = True
        assert expected_error_occurred

        #  Test that an attempt to register an invalid fd fails
        #
        inv_fd = 999

        #  Make sure it is invalid
        try: os.close(inv_fd)
        except: pass
        try:
            #  Mask the log message as we expect a failure
            self.log.setLevel(logging.CRITICAL)
            poll.register(inv_fd)
            self.log.setLevel(log_level)
            expected_error_occurred = False
        except Exception as e:
            self.log.setLevel(log_level)
            self.log.info("%s Received expected invalid fd error -- %s", my(self), str(e))
            expected_error_occurred = True
        assert expected_error_occurred

        #  Confirm new mode is same as previous
        poll = taskforce.poll.poll()
        mode = poll.get_mode()
        self.log.info("%s Default polling mode is '%s' and should be same as previous '%s'",
                        my(self), poll.get_mode_name(mode=mode), poll.get_mode_name(mode=currmode))

        #  Change to PL_SELECT and register
        poll.set_mode(taskforce.poll.PL_SELECT)
        assert poll.get_mode() == taskforce.poll.PL_SELECT
        poll.register(poll_fd)

        #  Check invalid unregister
        #
        try:
            #  Mask the log message as we expect a failure
            self.log.setLevel(logging.CRITICAL)
            poll.unregister(self)
            self.log.setLevel(log_level)
            expected_error_occurred = False
        except Exception as e:
            self.log.setLevel(log_level)
            self.log.info("%s Received expected error -- %s", my(self), str(e))
            expected_error_occurred = True
        assert expected_error_occurred

        #  Check valid unregister
        #
        poll.unregister(poll_fd)

        self.close_pipe()

    def Test_C_poll(self):
        log_level = self.log.getEffectiveLevel()

        poll_fd, poll_send = self.self_pipe()

        poll = taskforce.poll.poll()
        poll.register(poll_fd, taskforce.poll.POLLIN)

        #  Check active poll
        os.write(poll_send, '\0'.encode('utf-8'))
        evlist = poll.poll(timeout=30)
        self.dump_evlist(poll, 'active poll', evlist)
        assert evlist
        assert len(os.read(poll_fd, 10)) == 1

        #  Check timeout
        evlist = poll.poll(timeout=30)
        self.dump_evlist(poll, 'timeout poll', evlist)
        assert evlist == []

        #  Check timeout accuracy
        start = time.time()
        delay = 500
        evlist = poll.poll(timeout=500)
        self.dump_evlist(poll, 'timeout accuracy', evlist)
        assert evlist == []
        delta = abs(time.time() - start - delay/1000.0)
        self.log.info("%s poll timeout delta from wall clock %s", my(self), deltafmt(delta, decimals=6))
        assert delta < 0.1

        if poll.get_mode() == taskforce.poll.PL_SELECT:
            self.log.warning("%s Default mode is PL_SELECT so retest skipped", my(self))
        else:
            poll = taskforce.poll.poll()
            poll.set_mode(taskforce.poll.PL_SELECT)
            poll.register(poll_fd, taskforce.poll.POLLIN)

            #  Check active poll
            os.write(poll_send, '\0'.encode('utf-8'))
            evlist = poll.poll(timeout=30)
            self.dump_evlist(poll, 'select active poll', evlist)
            assert evlist
            assert len(os.read(poll_fd, 10)) == 1

            #  Check timeout
            evlist = poll.poll(timeout=30)
            self.dump_evlist(poll, 'select timeout poll', evlist)
            assert evlist == []

            #  Check timeout accuracy
            start = time.time()
            delay = 500
            evlist = poll.poll(timeout=500)
            self.dump_evlist(poll, 'select timeout accuracy', evlist)
            assert evlist == []
            delta = abs(time.time() - start - delay/1000.0)
            self.log.info("%s select poll timeout delta from wall clock %s", my(self), deltafmt(delta, decimals=6))
            assert delta < 0.1

        self.close_pipe()
