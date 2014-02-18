# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

from . import entities
from . import exceptions
from . import plays


class Conductor:
    """The Maestro; the Conductor.

    The conductor is in charge of parsing and analyzing the environment
    description and carrying out the orchestration plays to act on the services
    and containers described in the environment.
    """

    def __init__(self, config):
        self._config = config

        # Create container ships.
        self._ships = dict(
            (k, entities.Ship(
                k, v['ip'],
                docker_port=v.get('docker_port',
                                  entities.Ship.DEFAULT_DOCKER_PORT),
                timeout=v.get('timeout')))
            for k, v in self._config['ships'].iteritems())

        # Register defined private Docker registries authentications
        self._registries = self._config.get('registries', {})
        for name, registry in self._registries.iteritems():
            if 'username' not in registry or 'password' not in registry:
                raise exceptions.OrchestrationException(
                    'Incomplete registry auth data for {}!'.format(name))

        # Build all the entities.
        self._services = {}
        self._containers = {}

        for kind, service in self._config['services'].iteritems():
            self._services[kind] = entities.Service(kind, service['image'],
                                                    service.get('env', {}))

            for name, instance in service['instances'].iteritems():
                self._containers[name] = \
                    entities.Container(name,
                                       self._ships[instance['ship']],
                                       self._services[kind],
                                       instance,
                                       self._config['name'])

        # Resolve dependencies between services.
        for kind, service in self._config['services'].iteritems():
            for dependency in service.get('requires', []):
                self._services[kind].add_dependency(self._services[dependency])
                self._services[dependency].add_dependent(self._services[kind])

        # Provide link environment variables to each container of each service.
        for service in self._services.itervalues():
            for container in service.containers:
                # Containers always know about their peers in the same service.
                container.env.update(service.get_link_variables(True))
                # Containers also get links from the service's dependencies.
                for dependency in service.requires:
                    container.env.update(dependency.get_link_variables())

    @property
    def services(self):
        """Returns the names of all the services defined in the environment."""
        return self._services.keys()

    @property
    def containers(self):
        """Returns the names of all the containers defined in the
        environment."""
        return self._containers.keys()

    def get_service(self, name):
        """Returns a service, by name."""
        return self._services[name]

    def get_container(self, name):
        """Returns a container, by name."""
        return self._containers[name]

    def _order_dependencies(self, pending=[], ordered=[], forward=True):
        """Order the given set of containers into an order respecting the
        service dependencies in the given direction.

        The list of containers to order should be passed in the pending
        parameter. The ordered list will be returned by the function (the
        ordered parameter is for internal recursion use only).

        The direction of the dependencies controls whether the ordering should
        be constructed for startup (dependencies first) or shutdown (dependents
        first).
        """
        wait = []
        for container in pending:
            deps = self._gather_dependencies([container], forward)
            if deps and not deps.issubset(set(ordered + [container])):
                wait.append(container)
            else:
                ordered.append(container)

        # If wait and pending are not empty and have the same length, it means
        # we were not able to order any container from the pending list (they
        # all went to the wait list). This means the dependency tree cannot be
        # resolved and an error should be raised.
        if wait and pending and len(wait) == len(pending):
            raise exceptions.DependencyException(
                'Cannot resolve dependencies for containers {}!'.format(
                    map(lambda x: x.name, wait)))

        # As long as 'wait' has elements, keep recursing to resolve
        # dependencies. Otherwise, returned the ordered list, which should now
        # be final.
        return wait and self._order_dependencies(wait, ordered, forward) \
            or ordered

    def _gather_dependencies(self, containers, forward=True):
        """Transitively gather all containers from the dependencies or
        dependents (depending on the value of the forward parameter) services
        that the services the given containers are members of."""
        result = set(containers or self._containers.values())
        for container in result:
            deps = container.service.requires if forward \
                else container.service.needed_for
            deps = reduce(lambda x, y: x.union(y),
                          map(lambda s: s.containers, deps),
                          set([]))
            result = result.union(deps)
        return result

    def _to_containers(self, things):
        """Transform a list of "things", container names or service names, to
        an expended list of Container objects."""
        def parse_thing(s):
            if s in self._containers:
                return [self._containers[s]]
            elif s in self._services:
                return self._services[s].containers
            raise exceptions.OrchestrationException(
                '{} is neither a service nor a container!'.format(s))
        return reduce(lambda x, y: x+y, map(parse_thing, things), [])

    def _ordered_containers(self, things, forward=True):
        """Return the ordered list of containers from the list of names passed
        to it (either container names or service names).

        Args:
            things (list<string>):
            forward (boolean): controls the direction of the dependency tree.
        """
        return self._order_dependencies(
            sorted(self._gather_dependencies(self._to_containers(things),
                                             forward)),
            forward=forward)

    def status(self, things=[], only=False, **kwargs):
        """Display the status of the given services and containers, but only
        looking at the container's state, not the application availability.

        Args:
            things (set<string>): The things to show the status of.
            only (boolean): Whether to only show the status of the specified
                things, or their dependencies as well.
        """
        containers = self._ordered_containers(things) \
            if not only else self._to_containers(things)
        plays.Status(containers).run()

    def fullstatus(self, things=[], only=False, **kwargs):
        """Display the status of the given services and containers, pinging for
        application availability (slower).

        Args:
            things (set<string>): The things to show the status of.
            only (boolean): Whether to only show the status of the specified
                things, or their dependencies as well.
        """
        containers = self._ordered_containers(things) \
            if not only else self._to_containers(things)
        plays.FullStatus(containers).run()

    def start(self, things=[], refresh_images=False, only=False, **kwargs):
        """Start the given container(s) and services(s). Dependencies of the
        requested containers and services are started first.

        Args:
            things (set<string>): The list of things to start.
            refresh_images (boolean): Whether to force an image pull for each
                container or not.
            only (boolean): Whether to act on only the specified things, or
                their dependencies as well.
        """
        containers = self._ordered_containers(things) \
            if not only else self._to_containers(things)
        plays.Start(containers, self._registries, refresh_images).run()

    def stop(self, things=[], only=False, **kwargs):
        """Stop the given container(s) and service(s).

        This one is a bit more tricky because we don't want to look at the
        dependencies of the containers and services we want to stop, but at
        which services depend on the containers and services we want to stop.
        Unless of course the only parameter is set to True.

        Args:
            things (set<string>): The list of things to stop.
            only (boolean): Whether to act on only the specified things, or
                their dependencies as well.
        """
        containers = self._ordered_containers(things, False) \
            if not only else self._to_containers(things)
        plays.Stop(containers).run()

    def clean(self, **kwargs):
        raise NotImplementedError('Not yet implemented!')

    def logs(self, things=[], **kwargs):
        """Display the logs of the given container."""
        containers = self._to_containers(things)
        if len(containers) != 1:
            raise exceptions.ParameterException(
                'Logs can only be shown for a single container!')

        container = containers[0]

        o = plays.OutputFormatter()
        o.pending('Inspecting container status...')
        status = container.status()
        if not status:
            return

        try:
            stream = status['State']['Running'] and kwargs.get('follow')
            if stream:
                o.pending(
                    'Now streaming logs for {}. New output will appear below.'
                    .format(container.name))
                logs = container.ship.backend.attach(container.id, stream=True)
                for line in logs:
                    print(line.rstrip())
            else:
                o.pending(
                    'Requesting logs for {}. This may take a while...'
                    .format(container.name))
                logs = container.ship.backend.logs(container.id).split('\n')
                logs = logs[-int(kwargs.get('n', len(logs))):]
                print('\n'.join(logs))
        except:
            pass
