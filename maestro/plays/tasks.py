# Copyright (C) 2013-2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

import collections
import json
import time
try:
    import urlparse
except ImportError:
    # Try for Python3
    from urllib import parse as urlparse

from docker import auth
from .. import audit
from .. import exceptions
from ..termoutput import green, blue, red, time_ago


CONTAINER_STATUS_FMT = '{:<25s} '
TASK_RESULT_FMT = '{:<10s}'


class Task:
    """Base class for tasks acting on containers."""

    def __init__(self, action, o, container):
        """Initialize the base task parameters.

        Args:
            o (termoutput.OutputFormatter): the output formatter used for task
                output.
            container (entities.Container): the container the task operates on.
        """
        self.action = action
        self.o = o
        self.container = container

    def _wait_for_status(self, cond, retries=10):
        """Wait for the container's status to comply to the given condition."""
        while retries >= 0:
            if cond():
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
            cond (lambda): a function that should return True if the container
                reaches the desired lifecycle state.
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

    def run(self, auditor=None):
        if auditor:
            auditor.action(action=self.action, level=audit.DEBUG,
                           what=self.container)

        try:
            self._run()
            if auditor:
                auditor.success(action=self.action, level=audit.DEBUG,
                                what=self.container)
        except Exception as e:
            if auditor:
                auditor.error(action=self.action, what=self.container,
                              message=e)
            exceptions.raise_with_tb()

    def _run(self):
        raise NotImplementedError


class StatusTask(Task):
    """Check for and display a container's status."""

    def __init__(self, o, container):
        Task.__init__(self, 'status', o, container)

    def _run(self):
        self.o.reset()
        self.o.pending('checking...')

        try:
            if self.container.is_running():
                self.o.commit(green(CONTAINER_STATUS_FMT.format(
                    self.container.shortid_and_tag)))
                self.o.commit(green('running{}'.format(
                    time_ago(self.container.started_at))))
            else:
                self.o.commit(CONTAINER_STATUS_FMT.format(
                    self.container.shortid_and_tag))
                self.o.commit(red('down{}'.format(
                    time_ago(self.container.finished_at))))
        except Exception:
            self.o.commit(CONTAINER_STATUS_FMT.format('-'))
            self.o.commit(red(TASK_RESULT_FMT.format('host down')))
            return


class StartTask(Task):
    """Start a container, refreshing the image if requested.

    If reuse is True, the container will not be removed and re-created
    if it exists."""

    def __init__(self, o, container, registries={}, refresh=False,
                 reuse=False):
        Task.__init__(self, 'start', o, container)
        self._registries = registries
        self._refresh = refresh
        self._reuse = reuse

    def _run(self):
        self.o.reset()
        error = None
        try:
            # TODO: None is used to indicate that no action was performed
            # because the container and its application were already
            # running. This makes the following code not very nice and this
            # could be improved.
            result = self._create_and_start_container()
            if result is None:
                self.o.commit(blue('up{}'.format(
                    time_ago(self.container.started_at))))
            elif result:
                self.o.commit(green('started'))
            else:
                self.o.commit(red('container did not start!'))
        except Exception:
            self.o.commit(red('error starting container!'))
            raise

        if result is False:
            log = self.container.ship.backend.logs(self.container.id)
            error = (
                'Halting start sequence because {} failed to start!\n{}'
            ).format(self.container, log)
            raise exceptions.ContainerOrchestrationException(
                self.container, error.strip())

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
        if self.container.is_running():
            self.o.commit(blue(CONTAINER_STATUS_FMT.format(
                self.container.shortid_and_tag)))
            # We use None as a special marker showing the container and the
            # application were already running.
            return None

        if not self._check_for_state('pre-start', self.container.is_down):
            raise Exception('failed pre-start lifecycle checks')

        # Otherwise we need to start it.
        if (not self._reuse) or (not self.container.status()):
            CleanTask(self.o, self.container, standalone=False).run()

            # Check if the image is available, or if we need to pull it down.
            image = self.container.get_image_details()
            if self._refresh or \
                not list(filter(
                        lambda i: self.container.image in (i['RepoTags'] or []),
                        self.container.ship.backend.images(image['repository']))):
                PullTask(self.o, self.container, self._registries,
                         standalone=False).run()

            # Create and start the container.
            ports = self.container.ports \
                and list(map(lambda p: tuple(p['exposed'].split('/')),
                             self.container.ports.values())) \
                or None

            self.o.pending('creating container from {}...'.format(
                self.container.short_image))
            self.container.ship.backend.create_container(
                image=self.container.image,
                name=self.container.name,
                hostname=self.container.hostname,
                environment=self.container.env,
                volumes=list(self.container.get_volumes()),
                cpu_shares=self.container.cpu_shares,
                host_config=self.container.host_config,
                ports=ports,
                detach=True,
                working_dir=self.container.workdir,
                command=self.container.command)

        self.o.pending('waiting for container...')
        if not self._wait_for_status(
                lambda: self.container.status(refresh=True)):
            raise exceptions.ContainerOrchestrationException(
                self.container,
                'Container status could not be obtained after creation!')
        self.o.commit(green(CONTAINER_STATUS_FMT.format(
            self.container.shortid_and_tag)))

        ports = collections.defaultdict(list) if self.container.ports else None
        if ports is not None:
            for port in self.container.ports.values():
                ports[port['exposed']].append(
                    (port['external'][0], port['external'][1].split('/')[0]))

        self.o.pending('starting container {}...'
                       .format(self.container.id[:7]))
        self.container.ship.backend.start(
            self.container.id)

        # Waiting one second and checking container state again to make sure
        # initialization didn't fail.
        self.o.pending('waiting for initialization...')

        if not self._wait_for_status(self.container.is_running):
            raise exceptions.ContainerOrchestrationException(
                self.container,
                'Container status could not be obtained after start!')

        # Wait up for the container's application to come online.
        self.o.pending('waiting for service...')
        return self._check_for_state('running', self.container.is_running)


class StopTask(Task):
    """Stop a container."""

    def __init__(self, o, container):
        Task.__init__(self, 'stop', o, container)

    def _run(self):
        self.o.reset()
        self.o.pending('checking container...')
        try:
            if not self.container.is_running():
                self.o.commit(CONTAINER_STATUS_FMT.format(
                    self.container.shortid_and_tag))
                self.o.commit(blue(TASK_RESULT_FMT.format('down')))
                return
        except Exception:
            self.o.commit(CONTAINER_STATUS_FMT.format('-'))
            self.o.commit(red(TASK_RESULT_FMT.format('host down')))
            return

        self.o.commit(green(CONTAINER_STATUS_FMT.format(
            self.container.shortid_and_tag)))

        try:
            if not self._check_for_state(
                    'pre-stop', self.container.is_running):
                raise Exception('failed pre-stop lifecycle checks')

            self.o.pending('stopping service...')
            self.container.ship.backend.stop(
                self.container.id, timeout=self.container.stop_timeout)

            if not self._check_for_state('stopped', self.container.is_down):
                raise Exception('failed stopped lifecycle checks')
            self.o.commit(green(TASK_RESULT_FMT.format('stopped')))
        except Exception as e:
            # Stop failures are non-fatal, usually it's just the container
            # taking more time to stop than the timeout allows.
            self.o.commit(red('failed: {}'.format(e)))


class RestartTask(Task):
    """Task that restarts a container."""

    def __init__(self, o, container, registries={}, refresh=False,
                 step_delay=0, stop_start_delay=0, reuse=False,
                 only_if_changed=False):
        Task.__init__(self, 'restart', o, container)
        self._registries = registries
        self._refresh = refresh
        self._step_delay = step_delay
        self._stop_start_delay = stop_start_delay
        self._reuse = reuse
        self._only_if_changed = only_if_changed

    def _run(self):
        self.o.reset()

        if self._refresh:
            PullTask(self.o, self.container, self._registries,
                     standalone=False).run()

        if self._only_if_changed:
            if self.container.is_running():
                self.o.pending('checking image...')
                images = self.container.ship.get_image_ids()
                if images.get(self.container.image) == \
                        self.container.status()['Image']:
                    self.o.commit(CONTAINER_STATUS_FMT.format(
                        self.container.shortid_and_tag))
                    self.o.commit(blue('up to date'))
                    return

        if self._step_delay:
            self.o.pending('waiting {}s before restart...'
                           .format(self._step_delay))
            time.sleep(self._step_delay)

        StopTask(self.o, self.container).run()

        self.o.reset()
        if self._stop_start_delay:
            self.o.pending('waiting {}s before starting...'
                           .format(self._stop_start_delay))
            time.sleep(self._stop_start_delay)

        StartTask(self.o, self.container, self._registries,
                  False, self._reuse).run()


class LoginTask(Task):
    """Log in with the registry hosting the image a container is based on.

    Extracts the registry name from the image needed for the container, and if
    authentication data is provided for that registry, login to it so a
    subsequent pull operation can be performed.
    """

    def __init__(self, o, container, registries={}):
        Task.__init__(self, 'login', o, container)
        self._registries = registries

    def _run(self):
        registry = LoginTask.registry_for_container(self.container,
                                                    self._registries)
        if not registry:
            # No registry found, or no registry login needed.
            return

        if not registry.get('username'):
            registry_auth_config = auth.load_config().\
                get(urlparse.urlparse(registry['registry']).netloc)
            registry['username'] = registry_auth_config.get('username') \
                if registry_auth_config else None

        if not registry.get('username'):
            # Still no username found; bail out.
            return

        self.o.reset()
        self.o.pending('logging in to {}...'.format(registry['registry']))
        try:
            self.container.ship.backend.login(**registry)
        except Exception as e:
            raise exceptions.ContainerOrchestrationException(
                self.container,
                'Login to {} as {} failed: {}'
                .format(registry['registry'], registry['username'], e))

    @staticmethod
    def registry_for_container(container, registries={}):
        image = container.get_image_details()
        if image['repository'].find('/') <= 0:
            return None

        registry, repo_name = image['repository'].split('/', 1)
        if registry not in registries:
            # If the registry defined name doesn't match, try to find a
            # matching registry by registry FQDN.
            for name, info in registries.items():
                fqdn = urlparse.urlparse(info['registry']).netloc
                if registry == fqdn or registry == fqdn.split(':')[0]:
                    registry = name
                    break

        return registries.get(registry)


class PullTask(Task):
    """Pull (download) the image a container is based on."""

    def __init__(self, o, container, registries={}, standalone=True):
        Task.__init__(self, 'pull', o, container)
        self._registries = registries
        self._standalone = standalone
        self._progress = {}

    def _run(self):
        self.o.reset()

        # First, attempt to login if we can/need to.
        LoginTask(self.o, self.container, self._registries).run()

        self.o.pending('pulling image {}...'
                       .format(self.container.short_image))

        registry = LoginTask.registry_for_container(self.container,
                                                    self._registries)
        insecure = (urlparse.urlparse(registry['registry']).scheme == 'http'
                    if registry else False)
        image = self.container.get_image_details()

        # Pull the image (this may be a no-op, but that's fine).
        for dlstatus in self.container.ship.backend.pull(
                stream=True, insecure_registry=insecure, **image):
            if dlstatus:
                percentage = self._update_pull_progress(dlstatus)
                self.o.pending('... {:.1f}%'.format(percentage))

        if self._standalone:
            self.o.commit(CONTAINER_STATUS_FMT.format(''))
            self.o.commit(green(TASK_RESULT_FMT.format('done')))

    def _update_pull_progress(self, last):
        """Update an image pull progress map with latest download progress
        information for one of the image layers, and return the average of the
        download progress of all layers as an indication of the overall
        progress of the pull."""
        last = json.loads(last.decode('utf-8'))
        if 'error' in last:
            raise exceptions.ContainerOrchestrationException(
                self.container,
                'Pull of image {} failed: {}'.format(
                    self.container.image,
                    last['errorDetail']['message'].encode('utf-8')))

        try:
            self._progress[last['id']] = (
                100 if last['status'] == 'Download complete' else
                (100.0 * last['progressDetail']['current'] /
                 last['progressDetail']['total']))
        except Exception:
            pass

        total = 0
        if len(self._progress):
            for downloaded in self._progress.values():
                total += downloaded
            total /= len(self._progress)
        return total


class CleanTask(Task):
    """Remove a container from Docker if it exists."""

    def __init__(self, o, container, standalone=True):
        Task.__init__(self, 'clean', o, container)
        self._standalone = standalone

    def _run(self):
        self.o.reset()
        status = self.container.status()
        if not status:
            if self._standalone:
                self.o.commit(CONTAINER_STATUS_FMT.format('-'))
                self.o.commit(blue(TASK_RESULT_FMT.format('absent')))
            return

        if status['State']['Running']:
            self.o.commit(CONTAINER_STATUS_FMT.format(
                self.container.shortid_and_tag))
            self.o.commit(red(TASK_RESULT_FMT.format('skipped')))
            return

        self.o.pending('removing container {}...'.format(
            self.container.shortid))
        self.container.ship.backend.remove_container(self.container.id, v=True)

        if self._standalone:
            self.o.commit(CONTAINER_STATUS_FMT.format(
                self.container.shortid))
            self.o.commit(green(TASK_RESULT_FMT.format('removed')))
