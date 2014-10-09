# Copyright (C) 2014 SignalFuse, Inc.
#
# Docker container orchestration utility.

import socket
import subprocess
import time
import requests
import re

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
        return True

    @staticmethod
    def from_config(container, config):
        return Sleep(config['wait'])


class HttpRequestLifecycle(BaseLifecycleHelper):
    """
    Lifecycle request that makes a web request and checks for a given response
    """
    DEFAULT_MAX_WAIT = 300

    def __init__(self, host, port, match_regex=None, path='/', scheme='http',
                 method='get', max_wait=DEFAULT_MAX_WAIT, requests_options={}):
        self.host = host
        self.port = port

        self.match_regex = match_regex
        if self.match_regex:
            try:
                self.match_regex = re.compile(match_regex, re.DOTALL)
            except:
                raise exceptions.InvalidLifecycleCheckConfigurationException(
                    'Bad regex for {}: {}'.format(self.__class__.__name__,
                                                  match_regex)
                    )

        self.path = path
        if not self.path.startswith('/'):
            self.path = '/'+self.path
        self.scheme = scheme
        self.method = method.lower()
        self.max_wait = int(max_wait)

        # Extra options passed directly to the requests library
        self.requests_options = requests_options

    def test(self):
        start = time.time()
        end_by = start+self.max_wait

        url = '{}://{}:{}{}'.format(self.scheme, self.host, self.port,
                                    self.path)
        while time.time() < end_by:
            try:
                response = requests.request(self.method, url,
                                            **self.requests_options)
                if self._test_response(response):
                    return True
            except:
                pass

            time.sleep(1)
        return False

    def _test_response(self, response):
        if self.match_regex:
            if getattr(response, 'text', None) and \
               self.match_regex.search(response.text):
                return True
        else:
            if response.status_code == requests.codes.ok:
                return True
        return False

    @staticmethod
    def from_config(container, config):
        host = container.ship.ip
        if config.get('host'):
            host = config.get('host')
            del config['host']

        port = None
        if config['port'] not in container.ports:
            try:
                # accept a numbered port
                port = int(config['port'])
            except:
                raise exceptions.InvalidLifecycleCheckConfigurationException(
                    'Port {} is not defined by {}!'.format(
                        config['port'], container.name))

        if port is None:
            parts = container.ports[config['port']]['external'][1].split('/')
            if parts[1] == 'udp':
                raise exceptions.InvalidLifecycleCheckConfigurationException(
                    'Port {} is not TCP!'.format(config['port']))
            port = int(parts[0])

        opts = {}
        opts.update(**config)
        del opts['port']
        del opts['type']
        return HttpRequestLifecycle(host, port, **opts)


class LifecycleHelperFactory:

    HELPERS = {
        'tcp': TCPPortPinger,
        'exec': ScriptExecutor,
        'sleep': Sleep,
        'http': HttpRequestLifecycle
    }

    @staticmethod
    def from_config(container, config):
        return (LifecycleHelperFactory.HELPERS[config['type']]
                .from_config(container, config))
