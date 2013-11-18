# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import docker
import logging
import sys

class BaseScore:
    def __cond_label(self, cond, t, f): return cond and t or f
    def _color(self, cond): return self.__cond_label(cond, 32, 31)
    def _up(self, cond): return self.__cond_label(cond, 'up', 'down')

    def run(self):
        raise NotImplementedError

class OutputFormatter:
    def __init__(self, prefix):
        self._committed = prefix

    def commit(self, s=None):
        self._committed = '{} {}'.format(self._committed, s)
        print '{}\033[K\r'.format(self._committed),
        sys.stdout.flush()

    def pending(self, s):
        print '{} {}\033[K\r'.format(self._committed, s),
        sys.stdout.flush()

    def end(self):
        print
        sys.stdout.flush()

class Status(BaseScore):
    """The Status score is a Maestro orchestration play that displays the
    status of the given services."""

    def run(self, containers):
        print '{:>3s}  {:<20s} {:<15s} {:<25s} {:<15s} {:<10s}'.format(
            '  #', 'COMPONENT', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(containers, 1):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20s}\033[;0m {:<15s} {:<25s}'.format(
                order, container.name, container.service.name, container.ship.ip[:25]))

            try:
                o.pending('checking container...')
                status = container.status()
                o.commit('\033[{:d};1m{:<15s}\033[;0m'.format(
                    self._color(status and status['State']['Running']),
                    (status and status['State']['Running'] and container.id[:7] or 'down')))

                o.pending('checking service...')
                ping = container.ping(1)
                o.commit('\033[{:d};1m{:<10s}\033[;0m'.format(
                    self._color(ping), self._up(ping)))
            except Exception, e:
                o.commit('\033[31;1m{:<15s} {:<10s}\033[;0m'.format('host down', 'down'))
            o.end()


class Start(BaseScore):
    """The Start score is a Maestro orchestration play that will execute the
    start sequence of the requested services, starting each container for each
    instance of the services, in the given start order, waiting for each
    container's application to become available before moving to the next
    one."""

    def run(self, containers):
        print '{:>3s}  {:<20s} {:<15s} {:<25s} {:<15s} {:<10s}'.format(
            '  #', 'COMPONENT', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(containers, 1):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20s}\033[;0m {:<15s} {:<25s}'.format(
                order, container.name, container.service.name, container.ship.ip[:25]))
            error = None
            try:
                result = self._start_container(o, container)
                o.commit('\033[{:d};1m{:<10s}\033[;0m'.format(
                    self._color(ping), result and 'up' or 'failed to start!'))
                o.end()

                if not result:
                    sys.stderr.write(container.ship.backend.logs(container.id))
                    # Halt the sequence if a container failed to start.
                    return
            except docker.client.APIError, e:
                o.commit('\033[31;1mfail!\033[;0m')
                o.end()
                sys.stderr.write(e)

    def _start_container(self, o, container):
        o.pending('checking service...')
        if container.ping(retries=2):
            o.commit('\033[34;0m{:<15s} {:<10s}\033[;0m'.format(
                container.id[:7], 'already up'))
            return True

        # Otherwise we need to start it.
        if container.id:
            o.pending('removing old container {}...'.format(container.id[:7]))
            container.ship.backend.remove_container(container.id)

        o.pending('pulling image {}...'.format(container.service.image))
        container.ship.backend.pull(**container.service.get_image_details())

        o.pending('creating container...')
        c = container.ship.backend.create_container(
            image=container.service.image,
            hostname=container.name,
            name=container.name,
            environment=container.env,
            ports=dict([('%d/tcp' % port['exposed'], {})
                for port in container.ports.itervalues()]))

        container.status(refresh=True)
        o.commit('\033[32;1m{:<15s}\033[;0m'.format(container.id[:7]))

        o.pending('starting container...')
        container.ship.backend.start(c,
            binds=container.volumes,
            port_bindings=dict([('%d/tcp' % port['exposed'],
                    [{'HostIp': '0.0.0.0', 'HostPort': str(port['external'])}])
                for port in container.ports.itervalues()]),
            create_local_bind_dirs=True)

        # Wait up to 30 seconds for the container to be up before
        # moving to the next one.
        o.pending('waiting for service...')
        return container.ping(retries=30)

class Stop(BaseScore):
    """The Stop score is a Maestro orchestration play that will stop and remove
    the containers of the requested services, in the inverse dependency
    order."""

    def run(self, containers):
        print '{:>3s}  {:<20s} {:<15s} {:<25s} {:<15s} {:<10s}'.format(
            '  #', 'COMPONENT', 'SERVICE', 'SHIP', 'CONTAINER', 'RESULT')

        for order, container in enumerate(containers):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20s}\033[;0m {:<15s} {:<25s}'.format(
                len(containers) - order, container.name,
                container.service.name, container.ship.ip[:25]))

            o.pending('checking container...')
            try:
                if not container.status():
                    o.commit('{:<15s} {:<10s}'.format('n/a', 'already down'))
                    o.end()
                    continue
            except:
                o.commit('\033[31;1m{:<15s} {:<10s}\033[;0m'.format('host down', 'down'))
                o.end()
                continue

            o.commit('{:<15s}'.format(container.id[:7]))

            try:
                o.pending('stopping service...')
                container.ship.backend.stop(container.id)
                o.pending('removing container...')
                container.ship.backend.remove_container(container.id)
                o.commit('\033[32;1mstopped\033[;0m')
            except:
                o.commit('\033[31;1mfail!\033[;0m')

            o.end()
