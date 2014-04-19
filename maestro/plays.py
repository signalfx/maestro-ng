# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

import collections
import json
import sys
import time

from . import exceptions


# Some utility functions for output.
def color(cond):
    """Returns 32 (green) or 31 (red) depending on the validity of the given
    condition."""
    return cond and 32 or 31


def up(cond):
    """Returns 'up' or 'down' depending on the validity of the given
    condition."""
    return cond and 'up' or 'down'


class BaseOrchestrationPlay:
    """Base class for orchestration plays, holds the ordered list containers to
    act on."""

    def __init__(self, containers=[]):
        self._containers = containers

    def run(self):
        raise NotImplementedError


class OutputFormatter:
    """Output formatter for nice, progressive terminal output.

    Manages the output of a progressively updated terminal line, with "in
    progress" labels and a "committed" base label.
    """
    def __init__(self, prefix=None):
        self._committed = prefix

    def commit(self, s=None):
        if self._committed and s:
            self._committed = '{} {}'.format(self._committed, s)
        elif not self._committed and s:
            self._committed = s
        print('{}\033[K\r'.format(self._committed), end='')
        sys.stdout.flush()

    def pending(self, s):
        if self._committed and s:
            print('{} {}\033[K\r'.format(self._committed, s), end='')
        elif not self._committed and s:
            print('{}\033[K\r'.format(s), end='')
        sys.stdout.flush()

    def end(self):
        print('')
        sys.stdout.flush()


class FullStatus(BaseOrchestrationPlay):
    """A Maestro orchestration play that displays the status of the given
    services and/or instance containers."""

    def __init__(self, containers=[]):
        BaseOrchestrationPlay.__init__(self, containers)

    def run(self):
        print('{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS'))

        for order, container in enumerate(self._containers, 1):
            o = OutputFormatter(
                ('{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
                 '{:<20.20s}').format(order,
                                      container.name,
                                      container.service.name,
                                      container.ship.name))

            try:
                o.pending('checking container...')
                status = container.status()
                o.commit('\033[{:d};1m{:<15s}\033[;0m'.format(
                    color(status and status['State']['Running']),
                    (status and status['State']['Running']
                        and container.id[:7] or 'down')))

                o.pending('checking service...')
                running = status and status['State']['Running']
                o.commit('\033[{:d};1m{:<4.4s}\033[;0m'.format(color(running),
                                                               up(running)))

                for name, port in container.ports.iteritems():
                    o.end()
                    o = OutputFormatter('     >>')
                    o.pending('{:>9.9s}:{:s}'.format(port['external'][1],
                                                     name))
                    ping = container.ping_port(name)
                    o.commit('\033[{:d};1m{:>9.9s}\033[;0m:{:s}'.format(
                        color(ping), port['external'][1], name))
            except Exception:
                o.commit('\033[31;1m{:<15s} {:<10s}\033[;0m'.format(
                    'host down', 'down'))
            o.end()


class Status(BaseOrchestrationPlay):
    """A less advanced, but faster status display orchestration play that only
    looks at the presence and status of the containers. Status information is
    bulk-polled from each ship's Docker daemon."""

    def __init__(self, containers=[]):
        BaseOrchestrationPlay.__init__(self, containers)

    def run(self):
        status = {}
        o = OutputFormatter()
        for ship in set([container.ship for container in self._containers]):
            o.pending('Gathering container information from {} ({})...'.format(
                ship.name, ship.ip))
            try:
                status.update(dict((c['Names'][0][1:], c)
                              for c in ship.backend.containers()))
            except:
                pass

        o.commit('{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER'))
        o.end()

        for order, container in enumerate(self._containers, 1):
            o = OutputFormatter(
                ('{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
                 '{:<20.20s}').format(order,
                                      container.name,
                                      container.service.name,
                                      container.ship.name))

            s = status.get(container.name)
            if s and s['Status'].startswith('Up'):
                cid = s.get('ID', s.get('Id', None))
                o.commit('\033[32;1m{}\033[;0m'.format(cid[:7]))
            else:
                o.commit('\033[31;1mdown\033[;0m')
            o.end()


class Start(BaseOrchestrationPlay):
    """A Maestro orchestration play that will execute the start sequence of the
    requested services, starting each container for each instance of the
    services, in the given start order, waiting for each container's
    application to become available before moving to the next one."""

    def __init__(self, containers=[], registries={}, refresh_images=False):
        BaseOrchestrationPlay.__init__(self, containers)
        self._registries = registries
        self._refresh_images = refresh_images

    def run(self):
        print('{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS'))

        for order, container in enumerate(self._containers, 1):
            o = OutputFormatter(
                ('{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
                 '{:<20.20s}').format(order,
                                      container.name,
                                      container.service.name,
                                      container.ship.name))

            error = None
            try:
                # TODO: None is used to indicate that no action was performed
                # because the container and its application were already
                # running. This makes the following code not very nice and this
                # could be improved.
                result = self._start_container(o, container)
                o.commit('\033[{:d};1m{:<10s}\033[;0m'.format(
                    color(result is not False),
                    result is None and 'up' or
                        (result and 'started' or
                            'service did not start!')))
                if result is False:
                    error = [
                        ('Halting start sequence because {} failed to start!'
                            .format(container)),
                        container.ship.backend.logs(container.id)]
                    raise exceptions.OrchestrationException('\n'.join(error))
            except Exception:
                o.commit('\033[31;1mfailed to start container!\033[;0m')
                raise
            finally:
                o.end()

    def _update_pull_progress(self, progress, last):
        """Update an image pull progress map with latest download progress
        information for one of the image layers, and return the average of the
        download progress of all layers as an indication of the overall
        progress of the pull."""
        try:
            last = json.loads(last)
            progress[last['id']] = last['status'] == 'Download complete' \
                and 100 \
                or (100.0 * last['progressDetail']['current'] /
                    last['progressDetail']['total'])
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

    def _login_to_registry(self, o, container):
        """Extract the registry name from the image needed for the container,
        and if authentication data is provided for that registry, login to it
        so a subsequent pull operation can be performed."""
        image = container.service.get_image_details()
        if image['repository'].find('/') <= 0:
            return

        registry, repo_name = image['repository'].split('/', 1)
        if registry not in self._registries:
            return

        o.pending('logging in to {}...'.format(registry))
        try:
            container.ship.backend.login(**self._registries[registry])
        except Exception as e:
            raise exceptions.OrchestrationException(
                'Login to {} failed: {}'.format(registry, e))

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
        status = container.status(refresh=True)

        if status and status['State']['Running']:
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
                not filter(lambda i: container.service.image in i['RepoTags'],
                           container.ship.backend.images(image['repository'])):
            # First, attempt to login if we can/need to.
            self._login_to_registry(o, container)
            o.pending('pulling image {}...'.format(container.service.image))
            progress = {}
            for dlstatus in container.ship.backend.pull(stream=True, **image):
                o.pending('... {:.1f}%'.format(
                    self._update_pull_progress(progress, dlstatus)))

        # Create and start the container.
        o.pending('creating container from {}...'.format(
            container.service.image))
        ports = container.ports \
            and map(lambda p: tuple(p['exposed'].split('/')),
                    container.ports.itervalues()) \
            or None
        container.ship.backend.create_container(
            image=container.service.image,
            hostname=container.name,
            name=container.name,
            environment=container.env,
            volumes=container.volumes.values(),
            mem_limit=container.mem_limit,
            cpu_shares=container.cpu_shares,
            ports=ports,
            detach=True)

        o.pending('waiting for container creation...')
        if not self._wait_for_status(container, lambda x: x):
            raise exceptions.OrchestrationException(
                'Container status could not be obtained after creation!')
        o.commit('\033[32;1m{:<15s}\033[;0m'.format(container.id[:7]))

        o.pending('starting container {}...'.format(container.id[:7]))
        ports = collections.defaultdict(list) if container.ports else None
        if ports is not None:
            for port in container.ports.values():
                ports[port['exposed']].append(
                    (port['external'][0], port['external'][1].split('/')[0]))
        container.ship.backend.start(container.id,
                                     binds=container.volumes,
                                     port_bindings=ports,
                                     privileged=container.privileged)

        # Waiting one second and checking container state again to make sure
        # initialization didn't fail.
        o.pending('waiting for container initialization...')
        if not self._wait_for_status(container,
                                     lambda x: x and x['State']['Running']):
            raise exceptions.OrchestrationException(
                'Container status could not be obtained after start!')

        # Wait up for the container's application to come online.
        o.pending('waiting for service...')
        return container.check_for_state('running') is not False


class Stop(BaseOrchestrationPlay):
    """A Maestro orchestration play that will stop and remove the containers of
    the requested services. The list of containers should be provided reversed
    so that dependent services are stopped first."""

    def __init__(self, containers=[]):
        BaseOrchestrationPlay.__init__(self, containers)

    def run(self):
        print('{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS'))

        for order, container in enumerate(self._containers):
            o = OutputFormatter(
                ('{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
                 '{:<20.20s}').format(len(self._containers) - order,
                                      container.name,
                                      container.service.name,
                                      container.ship.name))

            o.pending('checking container...')
            try:
                status = container.status(refresh=True)
                if not status or not status['State']['Running']:
                    o.commit('{:<15s} {:<10s}'.format('n/a', 'already down'))
                    o.end()
                    continue
            except:
                o.commit('\033[31;1m{:<15s} {:<10s}\033[;0m'.format(
                    'host down', 'down'))
                o.end()
                continue

            o.commit('{:<15s}'.format(container.id[:7]))

            try:
                o.pending('stopping service...')
                container.ship.backend.stop(container.id,
                                            timeout=container.stop_timeout)
                container.check_for_state('stopped')
                o.commit('\033[32;1mstopped\033[;0m')
            except:
                o.commit('\033[31;1mfail!\033[;0m')

            o.end()
