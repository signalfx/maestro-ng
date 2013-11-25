# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import docker
import logging
import sys
import time

class BaseScore:

    def __init__(self, containers=[]):
        self._containers = containers

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

    def __init__(self, containers=[]):
        BaseScore.__init__(self, containers)

    def run(self):
        print '{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'COMPONENT', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(self._containers, 1):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20.20s}\033[;0m {:<15.15s} {:<20.20s}'.format(
                order, container.name, container.service.name, container.ship.ip))

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

    def __init__(self, containers=[], refresh_images=False):
        BaseScore.__init__(self, containers)
        self._refresh_images = refresh_images

    def run(self):
        print '{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'COMPONENT', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(self._containers, 1):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20.20s}\033[;0m {:<15.15s} {:<20.20s}'.format(
                order, container.name, container.service.name, container.ship.ip))

            error = None
            try:
                result = self._start_container(o, container)
                o.commit('\033[{:d};1m{:<10s}\033[;0m'.format(
                    self._color(result), result and 'up' or 'service did not start!'))

                if not result:
                    error = container.ship.backend.logs(container.id)
            except docker.client.APIError, e:
                o.commit('\033[31;1mfailed to start container!\033[;0m')
                error = e

            o.end()

            # Halt the sequence if a container failed to start.
            if error:
                logging.error('%s/%s failed to start. Halting sequence.',
                    container.service.name, container.name)
                logging.error(error)
                return

    def _start_container(self, o, container):
        o.pending('checking service...')
        if container.ping(retries=2):
            o.commit('\033[34;0m{:<15s}\033[;0m'.format(container.id[:7]))
            return True

        # Otherwise we need to start it.
        if container.id:
            o.pending('removing old container {}...'.format(container.id[:7]))
            container.ship.backend.remove_container(container.id)

        # Check if the image is available, or if we need to pull it down.
        image = container.service.get_image_details()
        if self._refresh_images or \
                not filter(lambda i: i['Tag'] == image['tag'],
                           container.ship.backend.images(name=image['repository'])):
            o.pending('pulling image {}...'.format(container.service.image))
            container.ship.backend.pull(**image)

        # Create and start the container.
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

        # Waiting one second and checking container state again to make sure
        # initialization didn't fail.
        o.pending('waiting for container initialization...')
        time.sleep(1)
        status = container.status(refresh=True)
        if not status or not status['State']['Running']:
            return False

        # Wait up to 30 seconds for the container's application to come online.
        o.pending('waiting for service...')
        return container.ping(retries=30)

class Stop(BaseScore):
    """The Stop score is a Maestro orchestration play that will stop and remove
    the containers of the requested services, in the inverse dependency
    order."""

    def __init__(self, containers=[]):
        BaseScore.__init__(self, containers)

    def run(self):
        print '{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'COMPONENT', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(self._containers):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20.20s}\033[;0m {:<15.15s} {:<20.20s}'.format(
                len(self._containers) - order, container.name,
                container.service.name, container.ship.ip))

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
                o.commit('\033[32;1mstopped\033[;0m')
            except:
                o.commit('\033[31;1mfail!\033[;0m')

            o.end()
