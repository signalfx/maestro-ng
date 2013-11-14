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

class Status(BaseScore):
    """The Status score is a Maestro orchestration play that displays the
    status of the given services."""

    def run(self, services):
        print 'ORDER %13s %-20s %-25s %-15s %-10s' % \
                ('COMPONENT', 'INSTANCE', 'SHIP', 'CONTAINER', 'SERVICE')
        for order, service in enumerate(services, 1):
            for inst, container in enumerate(service.containers, 1):
                if inst == 1:
                    print '\033[;1m%2d: %15s\033[;0m' % (order, service.name),
                else:
                    print ' ' * 19,
                self._show_container_status(container)

    def _show_container_status(self, container):
        print '\033[37;1m%-20s\033[;0m' % container.name,
        print '%-25s' % container.ship.ip[:25],

        status = None
        try:
            status = container.status()
            print '\033[%d;1m%-15s\033[;0m' % \
                    (self._color(status and status['State']['Running']),
                     status and status['State']['Running'] \
                             and '%s' % container.id[:7] or 'down'),
        except:
            print '\033[31;1m%-15s\033[;0m' % 'host down',

        if not status or not status['State']['Running']:
            print 'n/a'
            return

        ping = container.ping(1)
        print '\033[%d;1m%-10s\033[;0m' % (self._color(ping), self._up(ping))

class Start(BaseScore):
    """The Start score is a Maestro orchestration play that will execute the
    start sequence of the requested services, starting each container for each
    instance of the services, in the given start order, waiting for each
    container's application to become available before moving to the next
    one."""

    def run(self, services):
        print 'ORDER %13s %-20s %-25s %-15s %-10s' % \
                ('COMPONENT', 'INSTANCE', 'SHIP', 'CONTAINER', 'SERVICE')
        for order, service in enumerate(services, 1):
            for inst, container in enumerate(service.containers, 1):
                if inst == 1:
                    print '\033[;1m%2d: %15s\033[;0m' % (order, service.name),
                else:
                    print ' ' * 19,

                try:
                    if not self._start_container(container):
                        # Halt the sequence if a container failed to start.
                        logging.error('Container for instance %s of service %s '
                            'failed to start. Halting sequence!',
                            container.name, service.name)
                        sys.stderr.write(container.ship.backend.logs(container.id))
                        return
                except docker.client.APIError, e:
                    print '\033[31;1mfail!\033[;0m'
                    logging.error(e)
                    return

    def _start_container(self, container):
        print '\033[37;1m%-20s\033[;0m' % container.name,
        print '%-25s' % container.ship.ip[:25],
        sys.stdout.flush()

        if container.ping(retries=2):
            print '%-15s already running' % container.id[:7]
            return True

        print '..',
        sys.stdout.flush()

        if container.id:
            logging.debug('Removing old container %s (id: %7s)',
                    container.name, container.id)
            container.ship.backend.remove_container(container.id)

        logging.debug('Pulling service image %s...', container.service.image)
        container.ship.backend.pull(**container.service.get_image_details())

        print '..',
        sys.stdout.flush()

        logging.debug('Creating container for instance %s of service %s...',
                container.name, container.service.name)
        c = container.ship.backend.create_container(
                image=container.service.image,
                hostname=container.name,
                name=container.name,
                environment=container.env,
                ports=dict([('%d/tcp' % port['exposed'], {})
                    for port in container.ports.itervalues()]))

        print '\033[32;1m%-11s\033[;0m' % container.id[:7],

        logging.debug('Starting container %s for instance %s...',
                container.id[:7], container.name)
        container.ship.backend.start(c,
                binds=container.volumes,
                port_bindings=dict([('%d/tcp' % port['exposed'],
                        [{'HostIp': '0.0.0.0', 'HostPort': str(port['external'])}])
                    for port in container.ports.itervalues()]),
                create_local_bind_dirs=True)

        print '...',
        sys.stdout.flush()

        # Wait up to 30 seconds for the container to be up before
        # moving to the next one.
        ping = container.ping(retries=30)
        print '\033[%d;1m%s\033[;0m' % (self._color(ping), self._up(ping))
        return ping

class Stop(BaseScore):
    """The Stop score is a Maestro orchestration play that will stop and remove
    the containers of the requested services, in the inverse dependency
    order."""

    def run(self, services):
        print 'ORDER %13s %-20s %-25s %-15s %-10s' % \
                ('COMPONENT', 'INSTANCE', 'SHIP', 'CONTAINER', 'RESULT')
        for order, service in enumerate(services[::-1], 1):
            for inst, container in enumerate(service.containers, 1):
                if inst == 1:
                    print '\033[;1m%2d: %15s\033[;0m' % (order, service.name),
                else:
                    print ' ' * 19,

                self._stop_container(container)

    def _stop_container(self, container):
        print '\033[37;1m%-20s\033[;0m' % container.name,
        print '%-25s' % container.ship.ip[:25],
        sys.stdout.flush()

        if not container.ping(retries=2):
            print '%-15s already down' % 'n/a'
            return True

        print '%-15s ..' % container.id[:7],
        sys.stdout.flush()

        try:
            container.ship.backend.stop(container.id)
            container.ship.backend.remove_container(container.id)
            print '\033[32;1mstopped\033[;0m'
            return True
        except:
            print '\033[31;1mfail!\033[;0m'
            return False
