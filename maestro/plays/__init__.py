# Copyright (C) 2013-2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

import functools
import sys
import threading

from . import tasks
from .. import audit
from .. import exceptions
from .. import termoutput
from ..termoutput import columns, green, red, supports_color, time_ago


class BaseOrchestrationPlay:
    """Base class for orchestration plays.

    Orchestration plays automatically parallelize the orchestration action
    while respecting the dependencies between the containers and the dependency
    order direction.
    """

    # Data column sizes.
    # Instance name column is bounded between 20 and 40 characters. Ship name
    # column is bounded between 0 and 40 characters. We keep 60 columns for
    # pending and commited output in the last column.
    _COLUMNS = columns()
    _INST_CSIZE = min(40, max(20, (_COLUMNS - 60) / 3))
    _SHIP_CSIZE = min(40, max(0, _COLUMNS - _INST_CSIZE - 80))

    # Header line format and titles.
    HEADER_FMT = ('{{:>3s}}  {{:<{}.{}s}} {{:<20.20s}} {{:<{}.{}s}} '
                  .format(_INST_CSIZE, _INST_CSIZE,
                          _SHIP_CSIZE, _SHIP_CSIZE)) + \
        tasks.CONTAINER_STATUS_FMT + ' ' + tasks.TASK_RESULT_FMT
    HEADERS = ['  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS']

    # Output line format (to which the task output colmns are added).
    LINE_FMT = ('{{:>3d}}. {}{{:<{}.{}s}}{} {{:<20.20s}} {{:<{}.{}s}}'
                .format('\033[1m' if supports_color() else '',
                        _INST_CSIZE, _INST_CSIZE,
                        '\033[0m' if supports_color() else '',
                        _SHIP_CSIZE, _SHIP_CSIZE))

    def __init__(self, containers=[], forward=True, ignore_dependencies=False,
                 concurrency=None, auditor=None):
        self._containers = containers
        self._forward = forward
        self._ignore_dependencies = ignore_dependencies
        self._concurrency = threading.Semaphore(concurrency or len(containers))
        self._auditor = auditor
        self._play = self.__class__.__name__.lower()

        self._dependencies = dict(
            (c.name, self._gather_dependencies(c)) for c in containers)

        self._om = termoutput.OutputManager(len(containers))
        self._threads = set([])
        self._done = set([])
        self._error = None
        self._cv = threading.Condition()

    @property
    def containers(self):
        return self._containers

    def register(self, task):
        """Register an orchestration action for a given container.

        The action is automatically wrapped into a layer that limits the
        concurrency to enforce the dependency order of the orchestration play.
        The action is only performed once the action has been performed for all
        the dependencies (or dependents, depending on the forward parameter).

        Args:
            task (tasks.Task): the task to execute.
        """
        def act(task):
            task.o.pending('waiting...')

            # Wait until we can be released (or if an error occurred for
            # another container).
            self._cv.acquire()
            while not self._satisfied(task.container) and not self._error:
                self._cv.wait(1)
            self._cv.release()

            # Abort if needed
            if self._error:
                task.o.commit(red('aborted!'))
                return

            try:
                self._concurrency.acquire(blocking=True)
                task.run(auditor=self._auditor)
                self._concurrency.release()
                self._done.add(task.container)
            except Exception:
                task.o.commit(red('failed!'))
                self._error = sys.exc_info()
            finally:
                self._cv.acquire()
                self._cv.notifyAll()
                self._cv.release()

        t = threading.Thread(target=act, args=(tuple([task])))
        t.daemon = True
        t.start()
        self._threads.add(t)

    def _start(self):
        """Start the orchestration play."""
        if self._auditor:
            self._auditor.action(level=audit.INFO, action=self._play,
                                 what=self._containers)
        print(BaseOrchestrationPlay.HEADER_FMT
              .format(*BaseOrchestrationPlay.HEADERS))
        self._om.start()

    def _end(self):
        """End the orchestration play by waiting for all the action threads to
        complete."""
        for t in self._threads:
            try:
                while not self._error and t.isAlive():
                    t.join(1)
            except KeyboardInterrupt:
                self._error = (exceptions.MaestroException,
                               exceptions.MaestroException('Manual abort'),
                               None)
            except Exception:
                self._error = sys.exc_info()
            finally:
                self._cv.acquire()
                self._cv.notifyAll()
                self._cv.release()
        self._om.end()

        # Display and raise any error that occurred
        if self._error:
            if self._auditor:
                self._auditor.error(action=self._play, what=self._containers,
                                    message=str(self._error[1]))
            exceptions.raise_with_tb(self._error)
        else:
            if self._auditor:
                self._auditor.success(level=audit.INFO, action=self._play,
                                      what=self._containers)

    def _run(self):
        raise NotImplementedError

    def run(self):
        self._start()
        self._run()
        self._end()

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
            deps = functools.reduce(lambda x, y: x.union(y),
                                    [s.containers for s in deps],
                                    set([]))
            result = result.union(deps.intersection(containers))

        result.remove(container)
        return result

    def _satisfied(self, container):
        """Returns True if all the dependencies of a given container have been
        satisfied by what's been executed so far (or if it was explicitely
        requested to ignore dependencies)."""
        if self._ignore_dependencies:
            return True
        missing = self._dependencies[container.name].difference(self._done)
        return len(missing) == 0


class FullStatus(BaseOrchestrationPlay):
    """A Maestro orchestration play that displays the status of the given
    services and/or instance containers.

    This orchestration play does not make use of the concurrent play execution
    features.
    """

    def __init__(self, containers=[]):
        BaseOrchestrationPlay.__init__(self, containers)

    def _run(self):
        for order, container in enumerate(self._containers, 1):
            o = termoutput.OutputFormatter(prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order, container.name, container.service.name,
                    container.ship.address)))

            try:
                o.pending('checking container...')
                status = container.status()

                if status and status['State']['Running']:
                    o.commit(green(tasks.CONTAINER_STATUS_FMT.format(
                        container.shortid_and_tag)))
                    o.commit(green('running{}'.format(
                        time_ago(container.started_at))))
                else:
                    o.commit(red('down{}'.format(
                        time_ago(container.finished_at))))

                o.commit('\n')

                image_info = termoutput.OutputFormatter(prefix='     ')
                image_info.commit(container.image)
                if status:
                    image_info.commit(' ({})'.format(status['Image'][:7]))
                image_info.commit('\n')

                for name, port in container.ports.items():
                    o = termoutput.OutputFormatter(prefix='     >>')
                    o.commit('{:>15.15s}: {:>9.9s} is'
                             .format(name, port['external'][1]))
                    o.commit(green('up') if container.ping_port(name)
                             else red('down'))
                    o.commit('\n')
            except Exception:
                o.commit(tasks.CONTAINER_STATUS_FMT.format('-'))
                o.commit(red('host down'))


class Status(BaseOrchestrationPlay):
    """A less advanced, but faster (concurrent) status display orchestration
    play that only looks at the presence and status of the containers."""

    def __init__(self, containers=[], concurrency=None):
        BaseOrchestrationPlay.__init__(
            self, containers, ignore_dependencies=True,
            concurrency=concurrency)

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.StatusTask(o, container))


class Start(BaseOrchestrationPlay):
    """A Maestro orchestration play that will execute the start sequence of the
    requested services, starting each container for each instance of the
    services, in the given start order, waiting for each container's
    application to become available before moving to the next one."""

    def __init__(self, containers=[], registries={}, refresh_images=False,
                 ignore_dependencies=True, concurrency=None, reuse=False,
                 auditor=None):
        BaseOrchestrationPlay.__init__(
            self, containers, ignore_dependencies=ignore_dependencies,
            concurrency=concurrency, auditor=auditor)

        self._registries = registries
        self._refresh_images = refresh_images
        self._reuse = reuse

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.StartTask(o, container, self._registries,
                                          self._refresh_images, self._reuse))


class Pull(BaseOrchestrationPlay):
    """A Maestro orchestration play that will force an image pull to refresh
       images for the given services and containers."""

    def __init__(self, containers=[], registries={},
                 ignore_dependencies=True, concurrency=None, auditor=None):
        BaseOrchestrationPlay.__init__(
            self, containers, ignore_dependencies=ignore_dependencies,
            concurrency=concurrency, auditor=auditor)

        self._registries = registries

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.PullTask(o, container, self._registries))


class Stop(BaseOrchestrationPlay):
    """A Maestro orchestration play that will stop the containers of the
    requested services. The list of containers should be provided reversed so
    that dependent services are stopped first."""

    def __init__(self, containers=[], ignore_dependencies=True,
                 concurrency=None, auditor=None):
        BaseOrchestrationPlay.__init__(
            self, containers, forward=False,
            ignore_dependencies=ignore_dependencies,
            concurrency=concurrency, auditor=auditor)

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    len(self._containers) - order, container.name,
                    container.service.name, container.ship.address)))
            self.register(tasks.StopTask(o, container))


class Clean(BaseOrchestrationPlay):
    """A Maestro orchestration play that will remove stopped containers from
    Docker."""

    def __init__(self, containers=[], concurrency=None, auditor=None):
        BaseOrchestrationPlay.__init__(
            self, containers, ignore_dependencies=False,
            concurrency=concurrency, auditor=auditor)

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.CleanTask(o, container))


class Restart(BaseOrchestrationPlay):
    """A Maestro orchestration play that restarts containers.

    By setting an appropriate concurrency level one can achieve "rolling
    restart" type orchestration."""

    def __init__(self, containers=[], registries={}, refresh_images=False,
                 ignore_dependencies=True, concurrency=None, step_delay=0,
                 stop_start_delay=0, reuse=False, only_if_changed=False,
                 auditor=None):
        BaseOrchestrationPlay.__init__(
            self, containers, forward=False,
            ignore_dependencies=ignore_dependencies,
            concurrency=concurrency, auditor=auditor)

        self._registries = registries
        self._refresh_images = refresh_images
        self._step_delay = step_delay
        self._stop_start_delay = stop_start_delay
        self._reuse = reuse
        self._only_if_changed = only_if_changed

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.RestartTask(
                o, container, self._registries, self._refresh_images,
                self._step_delay if order > 0 else 0, self._stop_start_delay,
                self._reuse, self._only_if_changed))
