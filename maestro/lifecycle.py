# Copyright (C) 2014 SignalFuse, Inc.
#
# Docker container orchestration utility.

import socket
import time


class BaseLifecycleHelper:
    """Base class for lifecycle helpers."""
    def test(self):
        raise NotImplementedError


class TCPPortPinger(BaseLifecycleHelper):
    """
    Lifecycle state helper that "pings" a particular TCP port.
    """

    def __init__(self, host, port, attempts=1):
        """Create a new TCP port pinger for the given host and port. The given
        number of attempts will be made, until the port is open or we give
        up."""
        self._host = host
        self._port = int(port)
        self._attempts = int(attempts)

    def __repr__(self):
        return 'PortPing(tcp://{}:{}, {} attempts)'.format(
            self._host, self._port, self._attempts)

    def __ping_port(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((self._host, self._port))
            s.close()
            return True
        except Exception:
            return False

    def test(self):
        retries = self._attempts
        while retries > 0:
            if self.__ping_port():
                return True

            retries -= 1
            if retries > 0:
                time.sleep(1)
        return False
