# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

import collections
import json
import threading
import time
import sys

from . import exceptions
from . import termoutput


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
    """Base class for orchestration plays.

    Orchestration plays automatically parallelize the orchestration action
    while respecting the dependencies between the containers and the dependency
    order direction.
    """

    def __init__(self, containers=[], forward=True):
        self._containers = containers
        self._forward = forward

        self._dependencies = dict((c.name, self._gather_dependencies(c))
                                  for c in containers)
        self._om = termoutput.OutputManager(len(containers))
        self._threads = set([])
        self._done = set([])
        self._error = None
        self._cv = threading.Condition()

    def start(self):
        """Start the orchestration play."""
        self._om.start()

    def register(self, target, container, o):
        """Register an orchestration action for a given container.

        The action is automatically wrapped into a layer that limits the
        concurrency to enforce the dependency order of the orchestration play.
        The action is only performed once the action has been performed for all
        the dependencies (or dependents, depending on the forward parameter).

        Args:
            target (callable): the bound function that performs the action.
            container (entities.Container): the container it acts on.
            o (termoutput.OutputFormatter): the output formatter to use for
                displaying status.
        """
        def act(target, container, o):
            o.pending('waiting...')

            # Wait until we can be released (or if an error occurred for
            # another container).
            self._cv.acquire()
            while not self._satisfied(container) and not self._error:
                self._cv.wait(1)
            self._cv.release()

            # Abort if needed
            if self._error:
                o.commit('\033[31;1maborted!\033[;0m')
                return

            try:
                target(container, o)
                self._done.add(container)
            except Exception as e:
                self._error = e
            finally:
                self._cv.acquire()
                self._cv.notifyAll()
                self._cv.release()

        t = threading.Thread(target=act, args=(target, container, o))
        t.start()
        self._threads.add(t)

    def end(self):
        """End the orchestration play by waiting for all the action threads to
        complete."""
        for t in self._threads:
            try:
                while t.isAlive():
                    t.join(1)
            except KeyboardInterrupt:
                self._error = 'Manual abort.'
                self._cv.acquire()
                self._cv.notifyAll()
                self._cv.release()
        self._om.end()

        # Display any error that occurred
        if self._error:
            sys.stderr.write('{}\n'.format(self._error))

    def run(self):
        raise NotImplementedError

    def _gather_dependencies(self, container):
        """Transitively gather all containers from the dependencies or
        dependent (depending on the value of the forward parameter) services
        of the service the given container is a member of. This set is limited
        to the containers involved in the orchestration play."""
        containers = set(self._containers)
        result = set([container])

        for container in result:
            deps = container.service.requires if self._forward \
                else container.service.needed_for
            deps = reduce(lambda x, y: x.union(y),
                          map(lambda s: s.containers, deps),
                          set([]))
            result = result.union(deps.intersection(containers))

        result.remove(container)
        return result

    def _satisfied(self, container):
        """Returns True if all the dependencies of a given container have been
        satisfied by what's been executed so far."""
        missing = self._dependencies[container.name].difference(self._done)
        return len(missing) == 0


class FullStatus(BaseOrchestrationPlay):
    """A Maestro orchestration play that displays the status of the given
    services and/or instance containers."""

    def __init__(self, containers=[]):
        BaseOrchestrationPlay.__init__(self, containers)

    def run(self):
        print('{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS'))

        for order, container in enumerate(self._containers, 1):
            o = termoutput.OutputFormatter(prefix=(
                '{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
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
                    o.commit('\n')
                    o = termoutput.OutputFormatter(prefix='     >>')
                    o.pending('{:>9.9s}:{:s}'.format(port['external'][1],
                                                     name))
                    ping = container.ping_port(name)
                    o.commit('\033[{:d};1m{:>9.9s}\033[;0m:{:s}'.format(
                        color(ping), port['external'][1], name))
            except Exception:
                o.commit('\033[31;1m{:<15s} {:<10s}\033[;0m'.format(
                    'host down', 'down'))
            o.commit('\n')


class Status(BaseOrchestrationPlay):
    """A less advanced, but faster status display orchestration play that only
    looks at the presence and status of the containers. Status information is
    bulk-polled from each ship's Docker daemon."""

    def __init__(self, containers=[]):
        BaseOrchestrationPlay.__init__(self, containers)

    def run(self):
        print('{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER'))

        self.start()
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                '{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
                '{:<20.20s}').format(order + 1,
                                     container.name,
                                     container.service.name,
                                     container.ship.name))
            self.register(self._get_container_status, container, o)
        self.end()

    def _get_container_status(self, container, o):
        o.pending('checking...')
        s = container.status(refresh=True)
        if s and s['State']['Running']:
            cid = container.id
            o.commit('\033[32;1m{}\033[;0m'.format(cid[:7]))
        else:
            o.commit('\033[31;1mdown\033[;0m')


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

        self.start()
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                '{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
                '{:<20.20s}').format(order + 1,
                                     container.name,
                                     container.service.name,
                                     container.ship.name))
            self.register(self._start_container, container, o)
        self.end()

    def _start_container(self, container, o):
        error = None
        try:
            # TODO: None is used to indicate that no action was performed
            # because the container and its application were already
            # running. This makes the following code not very nice and this
            # could be improved.
            result = self._create_and_start_container(container, o)
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

    def _create_and_start_container(self, container, o):
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
            detach=True,
            command=container.cmd)

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
        BaseOrchestrationPlay.__init__(self, containers, forward=False)

    def run(self):
        print('{:>3s}  {:<20s} {:<15s} {:<20s} {:<15s} {:<10s}'.format(
            '  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS'))

        self.start()
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                '{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<15.15s} ' +
                '{:<20.20s}').format(len(self._containers) - order,
                                     container.name,
                                     container.service.name,
                                     container.ship.name))
            self.register(self._stop_container, container, o)
        self.end()

    def _stop_container(self, container, o):
        o.pending('checking container...')
        try:
            status = container.status(refresh=True)
            if not status or not status['State']['Running']:
                o.commit('{:<15s} {:<10s}'.format('n/a', 'already down'))
                return
        except:
            o.commit('\033[31;1m{:<15s} {:<10s}\033[;0m'.format(
                'host down', 'down'))
            return

        o.commit('{:<15s}'.format(container.id[:7]))

        try:
            o.pending('stopping service...')
            container.ship.backend.stop(container.id,
                                        timeout=container.stop_timeout)
            container.check_for_state('stopped')
            o.commit('\033[32;1mstopped\033[;0m')
        except:
            # Stop failures are non-fatal, usually it's just the container
            # taking more time to stop than the timeout allows.
            o.commit('\033[31;1mfail!\033[;0m')
