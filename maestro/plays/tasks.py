# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

import collections
import json
import time

from .. import exceptions
from ..termoutput import green, blue, red


TASK_RESULT_HEADER_FMT = '{:<15s} {:10s}'


class Task:
    """Base class for tasks acting on containers."""

    def __init__(self, o, container):
        """Initialize the base task parameters.

        Args:
            o (termoutput.OutputFormatter): the output formatter used for task
                output.
            container (entities.Container): the container the task operates on.
        """
        self.o = o
        self.container = container

    @property
    def cid(self):
        return self.container.id[:7] if self.container.id else '-'

    def _wait_for_status(self, cond, retries=10):
        """Wait for the container's status to comply to the given condition."""
        while retries >= 0:
            status = self.container.status(refresh=True)
            if cond(status):
                return True
            retries -= 1
            if retries >= 0:
                time.sleep(0.5)
        return False

    def _check_for_state(self, state, cond):
        """Wait for the container to reach the given lifecycle state by executing
        the corresponding, configured lifecycle checks, taking into account the
        container state (through _wait_for_status) while the checks wait for
        the target status to be reached.

        Args:
            state (string): the target lifecycle state.
            cond (lambda): a lambda function that takes in the container's
                status (from inspection) and returns True if it conforms to the
                target desired lifecycle state.
        """
        checks = self.container.start_lifecycle_checks(state)
        if not checks:
            return self._wait_for_status(cond)

        # Wait for all checks to complete
        while not checks.ready():
            checks.wait(1)
            if not self._wait_for_status(cond, retries=1):
                return False

        # Check results
        for check in checks.get():
            if not check:
                return False

        return True

    def run(self):
        raise NotImplementedError


class StatusTask(Task):
    """Check for and display a container's status."""

    def __init__(self, o, container):
        Task.__init__(self, o, container)

    def run(self):
        self.o.pending('checking...')
        try:
            s = self.container.status(refresh=True)
            if s and s['State']['Running']:
                self.o.commit(green(TASK_RESULT_HEADER_FMT
                                    .format(self.cid, 'running')))
            else:
                self.o.commit(TASK_RESULT_HEADER_FMT
                              .format(self.cid, red('down')))
        except:
            self.o.commit(red('host down'))


class StopTask(Task):
    """Stop a container."""

    def __init__(self, o, container):
        Task.__init__(self, o, container)

    def run(self):
        self.o.pending('checking container...')
        try:
            status = self.container.status(refresh=True)
            if not status or not status['State']['Running']:
                self.o.commit(TASK_RESULT_HEADER_FMT
                              .format(self.cid, blue('down')))
                return
        except:
            self.o.commit(TASK_RESULT_HEADER_FMT
                          .format('-', red('host down')))
            return

        self.o.commit(green('{:<15s}'.format(self.cid)))

        try:
            self.o.pending('stopping service...')
            self.container.ship.backend.stop(
                self.container.id, timeout=self.container.stop_timeout)

            if not self._check_for_state('stopped',
                                         lambda x: not x or
                                         (x and not x['State']['Running'])):
                raise Exception('failed stopped lifecycle checks')
            self.o.commit(green('stopped'))
        except Exception as e:
            # Stop failures are non-fatal, usually it's just the container
            # taking more time to stop than the timeout allows.
            self.o.commit(red('failed: {}'.format(e)))


class StartTask(Task):
    """Start a container, refreshing the image if requested."""

    def __init__(self, o, container, registries={}, refresh=False):
        Task.__init__(self, o, container)
        self._registries = registries
        self._refresh = refresh

    def run(self):
        error = None
        try:
            # TODO: None is used to indicate that no action was performed
            # because the container and its application were already
            # running. This makes the following code not very nice and this
            # could be improved.
            result = self._create_and_start_container()
            self.o.commit(blue('up') if result is None else
                          (green('started') if result else
                          red('service did not start!')))
            if result is False:
                error = [
                    ('Halting start sequence because {} failed to start!'
                        .format(self.container)),
                    self.container.ship.backend.logs(self.container.id)]
                raise exceptions.OrchestrationException('\n'.join(error))
        except Exception:
            self.o.commit(red('failed to start container!'))
            raise

    def _create_and_start_container(self):
        """Start the container.

        If the container and its application are already running, no action is
        performed and the function returns None to indicate that. Otherwise, a
        new container must be created and started. To achieve this, any
        existing container of the same name is first removed. Then, if
        necessary or if requested, the container image is pulled from its
        registry. Finally, the container is created and started, configured as
        necessary. We then wait for the application to start and return True or
        False depending on whether the start was successful."""
        self.o.pending('checking service...')
        status = self.container.status(refresh=True)

        if status and status['State']['Running']:
            self.o.commit('\033[34;0m{:<15s}\033[;0m'.format(self.cid))
            # We use None as a special marker showing the container and the
            # application were already running.
            return None

        # Otherwise we need to start it.
        if self.container.id:
            self.o.pending('removing old container {}...'.format(self.cid))
            self.container.ship.backend.remove_container(self.container.id)

        # Check if the image is available, or if we need to pull it down.
        image = self.container.service.get_image_details()
        if self._refresh or \
                not filter(
                    lambda i: self.container.service.image in i['RepoTags'],
                    self.container.ship.backend.images(image['repository'])):
            # First, attempt to login if we can/need to.
            LoginTask(self.o, self.container, self._registries).run()
            PullTask(self.o, self.container).run()

        # Create and start the container.
        ports = self.container.ports \
            and map(lambda p: tuple(p['exposed'].split('/')),
                    self.container.ports.values()) \
            or None

        self.o.pending('creating container from {}...'.format(
            self.container.service.image))
        self.container.ship.backend.create_container(
            image=self.container.service.image,
            hostname=self.container.name,
            name=self.container.name,
            environment=self.container.env,
            volumes=self.container.volumes.values(),
            mem_limit=self.container.mem_limit,
            cpu_shares=self.container.cpu_shares,
            ports=ports,
            detach=True,
            command=self.container.command)

        self.o.pending('waiting for container creation...')
        if not self._wait_for_status(lambda x: x):
            raise exceptions.OrchestrationException(
                'Container status could not be obtained after creation!')
        self.o.commit(green('{:<15s}'.format(self.container.id[:7])))

        ports = collections.defaultdict(list) if self.container.ports else None
        if ports is not None:
            for port in self.container.ports.values():
                ports[port['exposed']].append(
                    (port['external'][0], port['external'][1].split('/')[0]))

        self.o.pending('starting container {}...'
                       .format(self.container.id[:7]))
        self.container.ship.backend.start(
            self.container.id,
            binds=self.container.volumes,
            port_bindings=ports,
            privileged=self.container.privileged)

        # Waiting one second and checking container state again to make sure
        # initialization didn't fail.
        self.o.pending('waiting for container initialization...')
        check_running = lambda x: x and x['State']['Running']
        if not self._wait_for_status(check_running):
            raise exceptions.OrchestrationException(
                'Container status could not be obtained after start!')

        # Wait up for the container's application to come online.
        self.o.pending('waiting for service...')
        return self._check_for_state('running', check_running)


class LoginTask(Task):
    """Log in with the registry hosting the image a container is based on.

    Extracts the registry name from the image needed for the container, and if
    authentication data is provided for that registry, login to it so a
    subsequent pull operation can be performed.
    """

    def __init__(self, o, container, registries={}):
        Task.__init__(self, o, container)
        self._registries = registries

    def run(self):
        image = self.container.service.get_image_details()
        if image['repository'].find('/') <= 0:
            return

        registry, repo_name = image['repository'].split('/', 1)
        if registry not in self._registries:
            return

        self.o.pending('logging in to {}...'.format(registry))
        try:
            self.container.ship.backend.login(**self._registries[registry])
        except Exception as e:
            raise exceptions.OrchestrationException(
                'Login to {} failed: {}'.format(registry, e))


class PullTask(Task):
    """Pull (download) the image a container is based on."""

    def __init__(self, o, container):
        Task.__init__(self, o, container)
        self._progress = {}

    def run(self):
        self.o.pending('pulling image {}...'
                       .format(self.container.service.image))
        image = self.container.service.get_image_details()
        for dlstatus in self.container.ship.backend.pull(stream=True, **image):
            percentage = self._update_pull_progress(dlstatus)
            self.o.pending('... {:.1f}%'.format(percentage))

    def _update_pull_progress(self, last):
        """Update an image pull progress map with latest download progress
        information for one of the image layers, and return the average of the
        download progress of all layers as an indication of the overall
        progress of the pull."""
        try:
            last = json.loads(last)
            self._progress[last['id']] = (
                100 if last['status'] == 'Download complete' else
                (100.0 * last['progressDetail']['current'] /
                 last['progressDetail']['total']))
        except:
            pass

        total = 0
        if len(self._progress):
            for downloaded in self._progress.values():
                total += downloaded
            total /= len(self._progress)
        return total
