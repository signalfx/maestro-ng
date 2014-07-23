# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

import functools
import threading
import sys

from . import tasks
from .. import exceptions
from .. import termoutput
from ..termoutput import green, red


class BaseOrchestrationPlay:
    """Base class for orchestration plays.

    Orchestration plays automatically parallelize the orchestration action
    while respecting the dependencies between the containers and the dependency
    order direction.
    """

    HEADER_FMT = '{:>3s}  {:<20s} {:<20s} {:<20s} ' + \
                 tasks.CONTAINER_STATUS_FMT + ' ' + tasks.TASK_RESULT_FMT
    HEADERS = ['  #', 'INSTANCE', 'SERVICE', 'SHIP', 'CONTAINER', 'STATUS']

    LINE_FMT = ('{:>3d}. \033[;1m{:<20.20s}\033[;0m {:<20.20s} {:<20.20s}'
                if sys.stdout.isatty() else
                '{:>3d}. {:<20.20s} {:<20.20s} {:<20.20s}')

    def __init__(self, containers=[], forward=True, ignore_dependencies=False,
                 concurrency=None):
        self._containers = containers
        self._forward = forward
        self._ignore_dependencies = ignore_dependencies
        self._concurrency = threading.Semaphore(concurrency or len(containers))

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
                task.o.commit(self._error)
                return

            try:
                self._concurrency.acquire(blocking=True)
                task.run()
                self._concurrency.release()
                self._done.add(task.container)
            except Exception as e:
                self._error = e
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
                self._error = exceptions.MaestroException('Manual abort')
            except Exception as e:
                self._error = e
            finally:
                self._cv.acquire()
                self._cv.notifyAll()
                self._cv.release()
        self._om.end()

        # Display and raise any error that occurred
        if self._error:
            raise self._error

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
                    o.commit(green(tasks.CONTAINER_STATUS_FMT
                                   .format(container.id[:7])))
                else:
                    o.commit(red(tasks.CONTAINER_STATUS_FMT
                                 .format('down')))

                o.pending('checking service...')
                running = status and status['State']['Running']
                if running:
                    o.commit(green(tasks.TASK_RESULT_FMT.format('up')))
                else:
                    o.commit(red(tasks.TASK_RESULT_FMT.format('down')))

                for name, port in container.ports.items():
                    o.commit('\n')
                    o = termoutput.OutputFormatter(prefix='     >>')
                    o.pending('{:>9.9s}:{:s}'.format(port['external'][1],
                                                     name))
                    ping = container.ping_port(name)
                    if ping:
                        o.commit(green('{:>9.9s}'.format(port['external'][1])))
                    else:
                        o.commit(red('{:>9.9s}'.format(port['external'][1])))
                    o.commit(':{}'.format(name))
            except Exception:
                o.commit(tasks.CONTAINER_STATUS_FMT.format('-'))
                o.commit(red('host down'))
            o.commit('\n')


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
                 ignore_dependencies=True, concurrency=None):
        BaseOrchestrationPlay.__init__(
            self, containers, ignore_dependencies=ignore_dependencies,
            concurrency=concurrency)

        self._registries = registries
        self._refresh_images = refresh_images

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.StartTask(o, container, self._registries,
                                          self._refresh_images))


class Stop(BaseOrchestrationPlay):
    """A Maestro orchestration play that will stop the containers of the
    requested services. The list of containers should be provided reversed so
    that dependent services are stopped first."""

    def __init__(self, containers=[], ignore_dependencies=True,
                 concurrency=None):
        BaseOrchestrationPlay.__init__(
            self, containers, forward=False,
            ignore_dependencies=ignore_dependencies,
            concurrency=concurrency)

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

    def __init__(self, containers=[], concurrency=None):
        BaseOrchestrationPlay.__init__(
            self, containers, ignore_dependencies=False,
            concurrency=concurrency)

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.RemoveTask(o, container))


class Restart(BaseOrchestrationPlay):
    """A Maestro orchestration play that restarts containers.

    By setting an appropriate concurrency level one can achieve "rolling
    restart" type orchestration."""

    def __init__(self, containers=[], registries={}, refresh_images=False,
                 ignore_dependencies=True, concurrency=None, step_delay=0,
                 stop_start_delay=0):
        BaseOrchestrationPlay.__init__(
            self, containers, forward=False,
            ignore_dependencies=ignore_dependencies,
            concurrency=concurrency)

        self._registries = registries
        self._refresh_images = refresh_images
        self._step_delay = step_delay
        self._stop_start_delay = stop_start_delay

    def _run(self):
        for order, container in enumerate(self._containers):
            o = self._om.get_formatter(order, prefix=(
                BaseOrchestrationPlay.LINE_FMT.format(
                    order + 1, container.name, container.service.name,
                    container.ship.address)))
            self.register(tasks.RestartTask(
                o, container, self._registries, self._refresh_images,
                self._step_delay if order > 0 else 0, self._stop_start_delay))
