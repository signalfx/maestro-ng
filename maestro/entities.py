# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import docker
import functools
import multiprocessing.dummy as multiprocessing
import re
import six

from . import exceptions
from . import lifecycle


class Entity:
    """Base class for named entities in the orchestrator."""
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        """Get the name of this entity."""
        return self._name

    def __repr__(self):
        return self._name


class Ship(Entity):
    """A Ship that can host and run Containers.

    Ships are hosts in the infrastructure. A Docker daemon is expected to be
    running on each ship, providing control over the containers that will be
    executed there.
    """

    DEFAULT_DOCKER_PORT = 4243
    DEFAULT_DOCKER_VERSION = '1.8'
    DEFAULT_DOCKER_TIMEOUT = 5

    def __init__(self, name, ip, docker_port=DEFAULT_DOCKER_PORT,
                 timeout=None, docker_endpoint=None):
        """Instantiate a new ship.

        Args:
            name (string): the name of the ship.
            ip (string): the IP address of resolvable host name of the host.
            docker_port (int): the port the Docker daemon listens on.
            docker_endpoint (url): endpoint to access the docker api
        """
        Entity.__init__(self, name)
        self._ip = ip
        self._docker_port = docker_port
        if docker_endpoint:
            self._backend_url = docker_endpoint
        else:
            self._backend_url = 'http://{:s}:{:d}'.format(ip, docker_port)
        self._backend = docker.Client(
            base_url=self._backend_url,
            version=Ship.DEFAULT_DOCKER_VERSION,
            timeout=timeout or Ship.DEFAULT_DOCKER_TIMEOUT)

    @property
    def ip(self):
        """Returns this host's IP address or hostname."""
        return self._ip

    @property
    def backend(self):
        """Returns the Docker client wrapper to talk to the Docker daemon on
        this host."""
        return self._backend

    @property
    def docker_endpoint(self):
        """Returns the Docker daemon endpoint location on that ship."""
        return 'tcp://%s:%d' % (self._ip, self._docker_port)

    def __repr__(self):
        return '<ship:%s [%s:%d]>' % (self.name, self._ip, self._docker_port)


class Service(Entity):
    """A Service is a collection of Containers running on one or more Ships
    that constitutes a logical grouping of containers that make up an
    infrastructure service.

    Services may depend on each other. This dependency tree is honored when
    services need to be started.
    """

    def __init__(self, name, image, env=None):
        """Instantiate a new named service/component of the platform using a
        given Docker image.

        By default, a service has no dependencies. Dependencies are resolved
        and added once all Service objects have been instantiated.

        Args:
            name (string): the name of this service.
            image (string): the name of the Docker image the instances of this
                service should use.
            env (dict): a dictionary of environment variables to use as the
                base environment for all instances of this service.
        """
        Entity.__init__(self, name)
        self._image = image
        self.env = env or {}
        self._requires = set([])
        self._needed_for = set([])
        self._containers = {}

    def __repr__(self):
        return '<service:%s [%d instances]>' % (self.name,
                                                len(self._containers))

    @property
    def image(self):
        """Return the full name and tag of the image used by instances of this
        service."""
        return self._image

    def get_image_details(self):
        """Return a dictionary detailing the image used by this service, with
        its repository name and the requested tag (defaulting to latest if not
        specified)."""
        p = self._image.rsplit(':', 1)
        return {'repository': p[0], 'tag': len(p) > 1 and p[1] or 'latest'}

    @property
    def requires(self):
        """Returns the full set of direct and indirect dependencies of this
        service."""
        dependencies = self._requires
        for dep in dependencies:
            dependencies = dependencies.union(dep.requires)
        return dependencies

    @property
    def needed_for(self):
        """Returns the full set of direct and indirect dependents (aka services
        that depend on this service)."""
        dependents = self._needed_for
        for dep in dependents:
            dependents = dependents.union(dep.needed_for)
        return dependents

    @property
    def containers(self):
        """Return an ordered list of instance containers for this service, by
        instance name."""
        return map(lambda c: self._containers[c],
                   sorted(self._containers.keys()))

    def add_dependency(self, service):
        """Declare that this service depends on the passed service."""
        self._requires.add(service)

    def add_dependent(self, service):
        """Declare that the passed service depends on this service."""
        self._needed_for.add(service)

    def register_container(self, container):
        """Register a new instance container as part of this service."""
        self._containers[container.name] = container

    def get_link_variables(self, add_internal=False):
        """Return the dictionary of all link variables from each container of
        this service."""
        return dict(functools.reduce(
            lambda x, y: x+y,
            map(lambda c: c.get_link_variables(add_internal).items(),
                self._containers.values())))


class Container(Entity):
    """A Container represents an instance of a particular service that will be
    executed inside a Docker container on its target ship/host."""

    def __init__(self, name, ship, service, config, env_name='local'):
        """Create a new Container object.

        Args:
            name (string): the instance name (should be unique).
            ship (Ship): the Ship object representing the host this container
                is expected to be executed on.
            service (Service): the Service this container is an instance of.
            config (dict): the YAML-parsed dictionary containing this
                instance's configuration (ports, environment, volumes, etc.)
            env_name (string): the name of the Maestro environment.
        """
        Entity.__init__(self, name)
        self._status = None  # The container's status, cached.
        self._ship = ship
        self._service = service

        # Register this instance container as being part of its parent service.
        self._service.register_container(self)

        # Parse the port specs.
        self.ports = self._parse_ports(config.get('ports', {}))

        # Get environment variables.
        self.env = dict(service.env)
        self.env.update(config.get('env', {}))

        def env_list_expand(elt):
            return type(elt) != list and elt \
                or ' '.join(map(env_list_expand, elt))

        for k, v in self.env.items():
            if type(v) == list:
                self.env[k] = env_list_expand(v)

        # If no volume source is specified, we assume it's the same path as the
        # destination inside the container.
        self.volumes = dict(
            (src or dst, dst) for dst, src in
            config.get('volumes', {}).items())

        # Should this container run with -privileged?
        self.privileged = config.get('privileged', False)

        # Stop timeout
        self.stop_timeout = config.get('stop_timeout', 10)

        # Get limits
        limits = config.get('limits', {})
        self.cpu_shares = limits.get('cpu')
        self.mem_limit = limits.get('memory')
        if isinstance(self.mem_limit, six.string_types):
            units = {'k': 1024,
                     'm': 1024*1024,
                     'g': 1024*1024*1024}
            suffix = self.mem_limit[-1].lower()
            if suffix in units.keys():
                self.mem_limit = int(self.mem_limit[:-1]) * units[suffix]
        # TODO: add swap limit support when it will be available in docker-py
        # self.swap_limit = limits.get('swap')

        # Seed the service name, container name and host address as part of the
        # container's environment.
        self.env['MAESTRO_ENVIRONMENT_NAME'] = env_name
        self.env['SERVICE_NAME'] = self.service.name
        self.env['CONTAINER_NAME'] = self.name
        self.env['CONTAINER_HOST_ADDRESS'] = self.ship.ip

        # With everything defined, build lifecycle state helpers as configured
        self._lifecycle = self._parse_lifecycle(config.get('lifecycle', {}))

    @property
    def ship(self):
        """Returns the Ship this container runs on."""
        return self._ship

    @property
    def service(self):
        """Returns the Service this container is an instance of."""
        return self._service

    @property
    def id(self):
        """Returns the ID of this container given by the Docker daemon, or None
        if the container doesn't exist."""
        status = self.status()
        return status and status['ID'] or None

    def status(self, refresh=False):
        """Retrieve the details about this container from the Docker daemon, or
        None if the container doesn't exist."""
        if refresh or not self._status:
            try:
                self._status = self.ship.backend.inspect_container(self.name)
            except docker.client.APIError:
                pass

        return self._status

    def get_link_variables(self, add_internal=False):
        """Build and return a dictionary of environment variables providing
        linking information to this container.

        Variables are named
        '<service_name>_<container_name>_{HOST,PORT,INTERNAL_PORT}'.
        """
        basename = re.sub(r'[^\w]',
                          '_',
                          '{}_{}'.format(self.service.name, self.name)).upper()

        port_number = lambda p: p.split('/')[0]

        links = {'{}_HOST'.format(basename): self.ship.ip}
        for name, spec in self.ports.items():
            links['{}_{}_PORT'.format(basename, name.upper())] = \
                port_number(spec['external'][1])
            if add_internal:
                links['{}_{}_INTERNAL_PORT'.format(basename, name.upper())] = \
                    port_number(spec['exposed'])
        return links

    def check_for_state(self, state):
        """Check if a particular lifecycle state has been reached by executing
        all its defined checks. If not checks are defined, it is assumed the
        state is reached immediately."""

        if state not in self._lifecycle:
            # Return None to indicate no checks were performed.
            return None

        pool = multiprocessing.Pool(len(self._lifecycle[state]))
        return reduce(lambda x, y: x and y,
                      pool.map(lambda check: check.test(),
                               self._lifecycle[state]))

    def ping_port(self, port):
        """Ping a single port, by its given name in the port mappings. Returns
        True if the port is opened and accepting connections, False
        otherwise."""
        parts = self.ports[port]['external'][1].split('/')
        if parts[1] == 'udp':
            return False

        return lifecycle.TCPPortPinger(self.ship.ip, int(parts[0])).test()

    def _parse_ports(self, ports):
        """Parse port mapping specifications for this container."""

        def validate_proto(port):
            parts = str(port).split('/')
            if len(parts) == 1:
                return '{:d}/tcp'.format(int(parts[0]))
            elif len(parts) == 2:
                try:
                    int(parts[0])
                    if parts[1] in ['tcp', 'udp']:
                        return port
                except ValueError:
                    pass
            raise exceptions.InvalidPortSpecException(
                ('Invalid port specification {}! ' +
                 'Expected format is <port> or <port>/{tcp,udp}.').format(
                    port))

        result = {}
        for name, spec in ports.items():
            # Single number, interpreted as being a TCP port number and to be
            # the same for the exposed port and external port bound on all
            # interfaces.
            if type(spec) == int:
                result[name] = {
                    'exposed': validate_proto(spec),
                    'external': ('0.0.0.0', validate_proto(spec)),
                }

            # Port spec is a string. This means either a protocol was specified
            # with /tcp or /udp, or that a mapping was provided, with each side
            # of the mapping optionally specifying the protocol.
            # External port is assumed to be bound on all interfaces as well.
            elif type(spec) == str:
                parts = list(map(validate_proto, spec.split(':')))
                if len(parts) == 1:
                    # If only one port number is provided, assumed external =
                    # exposed.
                    parts.append(parts[0])
                elif len(parts) > 2:
                    raise exceptions.InvalidPortSpecException(
                        ('Invalid port spec {} for port {} of {}! ' +
                         'Format should be "name: external:exposed".').format(
                            spec, name, self))

                if parts[0][-4:] != parts[1][-4:]:
                    raise exceptions.InvalidPortSpecException(
                        'Mismatched protocols between {} and {}!'.format(
                            parts[0], parts[1]))

                result[name] = {
                    'exposed': parts[0],
                    'external': ('0.0.0.0', parts[1]),
                }

            # Port spec is fully specified.
            elif type(spec) == dict and \
                    'exposed' in spec and 'external' in spec:
                spec['exposed'] = validate_proto(spec['exposed'])

                if type(spec['external']) != list:
                    spec['external'] = ('0.0.0.0', spec['external'])
                spec['external'] = (spec['external'][0],
                                    validate_proto(spec['external'][1]))

                result[name] = spec

            else:
                raise exceptions.InvalidPortSpecException(
                    'Invalid port spec {} for port {} of {}!'.format(
                        spec, name, self))

        return result

    def _parse_lifecycle(self, lifecycles):
        """Parse the lifecycle checks configured for this container and
        instantiate the corresponding check helpers, as configured."""
        return dict([
            (state, map(
                lambda c: (lifecycle.LifecycleHelperFactory
                           .from_config(self, c)),
                checks)) for state, checks in lifecycles.items()])

    def __repr__(self):
        return '<container:%s/%s [on %s]>' % \
            (self.name, self.service.name, self.ship.name)

    def __lt__(self, other):
        return self.name < other.name

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)
