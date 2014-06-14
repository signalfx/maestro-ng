# Copyright (C) 2014 SignalFuse, Inc.
#
# Docker container orchestration utility.

import socket
import subprocess
import time

from . import exceptions


class BaseLifecycleHelper:
    """Base class for lifecycle helpers."""

    def test(self):
        """State helpers must implement this method to perform the state test.
        The method must return True if the test succeeds, False otherwise."""
        raise NotImplementedError


class TCPPortPinger(BaseLifecycleHelper):
    """
    Lifecycle state helper that "pings" a particular TCP port.
    """

    DEFAULT_MAX_WAIT = 300

    def __init__(self, host, port, attempts=1):
        """Create a new TCP port pinger for the given host and port. The given
        number of attempts will be made, until the port is open or we give
        up."""
        self.host = host
        self.port = int(port)
        self.attempts = int(attempts)

    def __repr__(self):
        return 'PortPing(tcp://{}:{}, {} attempts)'.format(
            self.host, self.port, self.attempts)

    def __ping_port(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((self.host, self.port))
            s.close()
            return True
        except Exception:
            return False

    def test(self):
        retries = self.attempts
        while retries > 0:
            if self.__ping_port():
                return True

            retries -= 1
            if retries > 0:
                time.sleep(1)
        return False

    @staticmethod
    def from_config(container, config):
        if config['port'] not in container.ports:
            raise exceptions.InvalidLifecycleCheckConfigurationException(
                'Port {} is not defined by {}!'.format(
                    config['port'], container.name))

        parts = container.ports[config['port']]['external'][1].split('/')
        if parts[1] == 'udp':
            raise exceptions.InvalidLifecycleCheckConfigurationException(
                'Port {} is not TCP!'.format(config['port']))

        return TCPPortPinger(
            container.ship.ip, int(parts[0]),
            attempts=config.get('max_wait', TCPPortPinger.DEFAULT_MAX_WAIT))


class ScriptExecutor(BaseLifecycleHelper):
    """
    Lifecycle state helper that executes a script and uses the exit code as the
    success value.
    """

    def __init__(self, command):
        self.command = command

    def __repr__(self):
        return 'ScriptExec({})'.format(self.command)

    def test(self):
        return subprocess.call(self.command, shell=True) == 0

    @staticmethod
    def from_config(container, config):
        return ScriptExecutor(config['command'])


class Sleep(BaseLifecycleHelper):
    """
    Lifecycle state helper that simply sleeps for a given amount of time (in
    seconds).
    """

    def __init__(self, wait):
        self.wait = wait

    def __repr__(self):
        return 'Sleep({}s)'.format(self.wait)

    def test(self):
        while self.wait > 0:
            time.sleep(1)
            self.wait -= 1
        return not self.abort

    @staticmethod
    def from_config(container, config):
        return Sleep(config['wait'])


class LifecycleHelperFactory:

    HELPERS = {
        'tcp': TCPPortPinger,
        'exec': ScriptExecutor,
        'sleep': Sleep,
    }

    @staticmethod
    def from_config(container, config):
        return (LifecycleHelperFactory.HELPERS[config['type']]
                .from_config(container, config))
