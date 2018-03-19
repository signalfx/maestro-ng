# Copyright (C) 2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Docker container orchestration utility.

import os
import re
import requests
import shlex
import socket
import subprocess
import time

from . import exceptions


class BaseLifecycleHelper:
    """Base class for lifecycle helpers."""

    def test(self, container=None):
        """State helpers must implement this method to perform the state test.
        The method must return True if the test succeeds, False otherwise."""
        raise NotImplementedError


class RetryingLifecycleHelper(BaseLifecycleHelper):

    DEFAULT_MAX_ATTEMPTS = 180

    def __init__(self, attempts, delay=1):
        self.attempts = int(attempts or
                            RetryingLifecycleHelper.DEFAULT_MAX_ATTEMPTS)
        self.delay = int(delay)

    def test(self, container=None):
        retries = self.attempts
        while retries > 0:
            if self._test(container):
                return True
            retries -= 1
            if retries > 0:
                time.sleep(self.delay)
        return False

    def _test(self, container=None):
        raise NotImplementedError


class TCPPortPinger(RetryingLifecycleHelper):
    """
    Lifecycle state helper that "pings" a particular TCP port.
    """

    def __init__(self, host, port, attempts):
        """Create a new TCP port pinger for the given host and port. The given
        number of attempts will be made, until the port is open or we give
        up."""
        RetryingLifecycleHelper.__init__(self, attempts)
        self.host = host
        self.port = int(port)

    def __repr__(self):
        return 'PortPing(tcp://{}:{}, {} attempts)'.format(
            self.host, self.port, self.attempts)

    def _test(self, container=None):
        try:
            s = socket.create_connection((self.host, self.port), 1)
            s.close()
            return True
        except Exception:
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

        return TCPPortPinger(container.ship.ip, int(parts[0]),
                             attempts=config.get('max_wait'))


class ScriptExecutor(RetryingLifecycleHelper):
    """
    Lifecycle state helper that executes a script and uses the exit code as the
    success value.
    """

    def __init__(self, command, env, attempts):
        RetryingLifecycleHelper.__init__(self, attempts)
        self.command = shlex.split(command)
        self.container_env = env

    def __repr__(self):
        return 'ScriptExec({}, {} attempts)'.format(self.command,
                                                    self.attempts)

    def _create_env(self):
        env = dict((k, v) for k, v in os.environ.items())
        env.update(self.container_env)
        return dict((str(k), str(v)) for k, v in env.items())

    def _test(self, container=None):
        return subprocess.call(self.command, env=self._create_env()) == 0

    @staticmethod
    def from_config(container, config):
        return ScriptExecutor(config['command'], container.env,
                              attempts=config.get('attempts'))


class RemoteScriptExecutor(RetryingLifecycleHelper):
    """
    Lifecycle state helper that executes a script in side of 'Remote
    Container' and uses the exit code as the success value.
    """

    def __init__(self, command, env, attempts):
        RetryingLifecycleHelper.__init__(self, attempts)
        self.command = shlex.split(command)
        self.container_env = env

    def __repr__(self):
        return 'RemoteScriptExector({}, {} attempts)'.format(self.command,
                                                             self.attempts)

    def _test(self, container):
        """ Execute a script in side of remote container """
        client = container.ship.backend
        exec_instance = client.exec_create(container.name, self.command)
        client.exec_start(exec_instance)
        while client.exec_inspect(exec_instance)['ExitCode'] is None:
            time.sleep(1)
        return client.exec_inspect(exec_instance)['ExitCode'] == 0

    @staticmethod
    def from_config(container, config):
        return RemoteScriptExecutor(config['command'], container.env,
                                    attempts=config.get('attempts'))


class Sleep(BaseLifecycleHelper):
    """
    Lifecycle state helper that simply sleeps for a given amount of time (in
    seconds).
    """

    def __init__(self, wait):
        self.wait = wait

    def __repr__(self):
        return 'Sleep({}s)'.format(self.wait)

    def test(self, container=None):
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
            except Exception:
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

    def test(self, container=None):
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
            except Exception:
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
            except Exception:
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
        'rexec': RemoteScriptExecutor,
        'sleep': Sleep,
        'http': HttpRequestLifecycle
    }

    @staticmethod
    def from_config(container, config):
        return (LifecycleHelperFactory.HELPERS[config['type']]
                .from_config(container, config))
