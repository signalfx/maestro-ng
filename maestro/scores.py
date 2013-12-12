# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import docker
import json
import sys
import time

import exceptions

# Some utility functions for output.
def cond_label(cond, t, f):
    return t if cond else f
def color(cond):
    return cond_label(cond, 32, 31)
def up(cond):
    return cond_label(cond, 'up', 'down')

class BaseScore:
    def __init__(self, containers=[]):
        self._containers = containers
    def run(self):
        raise NotImplementedError

class OutputFormatter:
    """Output formatter for nice, progressive terminal output.

    Manages the output of a progressively updated terminal line, with "in
    progress" labels and a "committed" base label.
    """
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
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(self._containers, 1):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20.20s}\033[;0m {:<15.15s} {:<20.20s}'.format(
                order, container.name, container.service.name, container.ship.ip))

            try:
                o.pending('checking container...')
                status = container.status()
                o.commit('\033[{:d};1m{:<15s}\033[;0m'.format(
                    color(status and status['State']['Running']),
                    (status and status['State']['Running'] and container.id[:7] or 'down')))

                o.pending('checking service...')
                ping = status and status['State']['Running'] and container.ping(1)
                o.commit('\033[{:d};1m{:<10s}\033[;0m'.format(color(ping), up(ping)))
            except Exception, e:
                print e
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
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(self._containers, 1):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20.20s}\033[;0m {:<15.15s} {:<20.20s}'.format(
                order, container.name, container.service.name, container.ship.ip))

            error = None
            try:
                # TODO: None is used to indicate that no action was performed
                # because the container and its application were already
                # running. This makes the following code not very nice and this
                # could be improved.
                result = self._start_container(o, container)
                o.commit('\033[{:d};1m{:<10s}\033[;0m'.format(
                    color(result is not False),
                    result is None and 'up' or \
                        result and 'started' or 'service did not start!'))
                if result is False:
                    error = container.ship.backend.logs(container.id)
            except docker.client.APIError, e:
                o.commit('\033[31;1mfailed to start container!\033[;0m')
                error = e

            o.end()

            # Halt the sequence if a container failed to start.
            if error:
                raise exceptions.OrchestrationException, \
                    ('Halting start sequence because {} failed to start!\n{}'
                        .format(container, error))

    def _update_pull_progress(self, progress, last):
        """Update an image pull progress map with latest download progress
        information for one of the image layers, and return the average of the
        download progress of all layers as an indication of the overall
        progress of the pull."""
        try:
            last = json.loads(last)
            progress[last['id']] = last['status'] == 'Download complete' \
                and 100 \
                or 100.0 * last['progressDetail']['current'] / last['progressDetail']['total']
        except:
            pass

        return reduce(lambda x, y: x+y, progress.values()) / len(progress) \
                if progress else 0

    def _wait_for_status(self, container, cond, retries=10):
        while retries >= 0:
            status = container.status(refresh=True)
            if cond(status):
                return True
            time.sleep(0.5)
            retries -= 1
        return False

    def _start_container(self, o, container):
        """Start the given container.

        If the container and its application are already running, no action is
        performed and the function returns None to indicate that. Otherwise, a
        new container must be created and started. To achieve this, any
        existing container of the same name is first removed. Then, if
        necessary or if requested, the container image is pulled from its
        registry. Finally, the container is created and started, configured as
        necessary. We then wait for the application to start and return True or
        False depending on whether the start was successful."""
        o.pending('checking service...')
        if container.ping(retries=2):
            o.commit('\033[34;0m{:<15s}\033[;0m'.format(container.id[:7]))
            # We use None as a special marker showing the container and the
            # application were already running.
            return None

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
            progress = {}
            for dlstatus in container.ship.backend.pull(stream=True, **image):
                o.pending('... {:.1f}%'.format(
                    self._update_pull_progress(progress, dlstatus)))

        # Create and start the container.
        o.pending('creating container...')
        container.ship.backend.create_container(
            image=container.service.image,
            hostname=container.name,
            name=container.name,
            environment=container.env,
            ports=dict([('%d/tcp' % port['exposed'], {})
                for port in container.ports.itervalues()]))

        o.pending('waiting for container creation...')
        if not self._wait_for_status(container, lambda x: x):
            return False
        o.commit('\033[32;1m{:<15s}\033[;0m'.format(container.id[:7]))

        o.pending('starting container...')
        container.ship.backend.start(container.id,
            binds=container.volumes,
            port_bindings=dict([('%d/tcp' % port['exposed'],
                    [{'HostIp': '0.0.0.0', 'HostPort': str(port['external'])}])
                for port in container.ports.itervalues()]),
            create_local_bind_dirs=True)

        # Waiting one second and checking container state again to make sure
        # initialization didn't fail.
        o.pending('waiting for container initialization...')
        if not self._wait_for_status(container, lambda x: x and x['State']['Running']):
            return False

        # Wait up for the container's application to come online.
        o.pending('waiting for service...')
        return container.ping(retries=60)

class Stop(BaseScore):
    """The Stop score is a Maestro orchestration play that will stop and remove
    the containers of the requested services, in the inverse dependency
    order."""

    def __init__(self, containers=[]):
        BaseScore.__init__(self, containers)

    def run(self):
        print '{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS')

        for order, container in enumerate(self._containers):
            o = OutputFormatter(
                '{:>3d}. \033[37;1m{:<20.20s}\033[;0m {:<15.15s} {:<20.20s}'.format(
                len(self._containers) - order, container.name,
                container.service.name, container.ship.ip))

            o.pending('checking container...')
            try:
                status = container.status(refresh=True)
                if not status or not status['State']['Running']:
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
