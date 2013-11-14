#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import argparse
import docker
import errno
import logging
import re
import socket
import sys
import time
import yaml

import scores

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

    def __init__(self, name, ip, docker_port=DEFAULT_DOCKER_PORT):
        """Instantiate a new ship.

        Args:
            name (string): the name of the ship.
            ip (string): the IP address of resolvable host name of the host.
            docker_port (int): the port the Docker daemon listens on.
        """
        Entity.__init__(self, name)
        self._ip = ip
        self._docker_port = docker_port

        self._backend = docker.Client(
               base_url='http://%s:%d' % (self._ip, docker_port),
               version="1.6",
               timeout=5)

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
        return 'ship(%s@%s:%d)' % (self.name, self._ip, self._docker_port)


class Service(Entity):
    """A Service is a collection of Containers running on one or more Ships
    that constitutes a logical grouping of containers that make up an
    infrastructure service.
    
    Services may depend on each other. This dependency tree is honored when
    services need to be started.
    """

    def __init__(self, name, image):
        """Instantiate a new named service/component of the platform using a
        given Docker image.

        By default, a service has no dependencies. Dependencies are resolved
        and added once all Service objects have been instantiated.

        Args:
            name (string): the name of this service.
            image (string): the name of the Docker image the instances of this
            service should use.
        """
        Entity.__init__(self, name)
        self._image = image
        self._requires = set([])
        self._containers = {}

    def __repr__(self):
        return '<service:%s>' % self.name

    @property
    def image(self):
        return self._image

    def get_image_details(self):
        """Return a dictionary detailing the image used by this service, with
        its repository name and the requested tag (defaulting to latest if not
        specified)."""
        p = self._image.split(':')
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
    def containers(self):
        """Return an ordered list of instance containers for this service, by
        instance name."""
        return map(lambda c: self._containers[c], sorted(self._containers.keys()))

    def add_dependency(self, service):
        """Declare that this service depends on the passed service."""
        self._requires.add(service)

    def register_container(self, container):
        """Register a new instance container as part of this service."""
        self._containers[container.name] = container

    def get_link_variables(self):
        """Return the dictionary of all link variables from each container of
        this service."""
        return dict(reduce(lambda x, y: x+y,
            map(lambda c: c.get_link_variables().items(), self._containers.values())))

    def ping(self, retries=1):
        """Check if this service is running, that is if all of its containers
        are up and running."""
        for container in self._containers.itervalues():
            if not container.ping(retries):
                return False
        return True

class Container(Entity):
    """A Container represents an instance of a particular service that will be
    executed inside a Docker container on its target ship/host."""

    def __init__(self, name, ship, service, config):
        """Create a new Container object.

        Args:
            name (string): the instance name (should be unique).
            ship (Ship): the Ship object representing the host this container
                is expected to be executed on.
            service (Service): the Service this container is an instance of.
            config (dict): the YAML-parsed dictionary containing this
                instance's configuration (ports, environment, volumes, etc.)
        """
        Entity.__init__(self, name)
        self._ship = ship
        self._service = service

        # Register this instance container as being part of its parent service.
        self._service.register_container(self)

        # Parse the port specs.
        def parse_ports(ports):
            result = {}
            for name, spec in ports.iteritems():
                parts = map(int, str(spec).split(':'))
                assert len(parts) <= 2, \
                    ('Invalid port spec %s for port %s of %s:%s!' %
                        (spec, name, service.name, self.name))
                result[name] = {'exposed': len(parts) > 1 and parts[1] or parts[0],
                                'external': parts[0]}
            return result

        self.ports = parse_ports(config.get('ports', {}))

        # Get environment variables.
        self.env = config.get('env', {})

        # If no volume source is specified, we assume it's the same path as the
        # destination inside the container.
        self.volumes = dict((src or dst, dst)
            for dst, src in config.get('volumes', {}).iteritems())

        # Seed the container name and host address as part of the container's
        # environment.
        self.env['CONTAINER_NAME'] = self.name
        self.env['CONTAINER_HOST_ADDRESS'] = self.ship.ip

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

    def status(self):
        """Retrieve the details about this container from the Docker daemon, or
        None if the container doesn't exist."""
        try:
            return self.ship.backend.inspect_container(self.name)
        except docker.client.APIError:
            return None

    def get_link_variables(self):
        """Build and return a dictionary of environment variables providing
        linking information to this container.

        Variables are named '<service_name>_<container_name>_{HOST,PORTS}'.
        """
        basename = re.sub(r'[^\w]', '_', '%s_%s' % (self.service.name, self.name)).upper()
        links = {'%s_HOST' % basename: self.ship.ip}
        links.update(dict(('%s_%s_PORT' % (basename, name.upper()), spec['exposed'])
            for name, spec in self.ports.iteritems()))
        return links

    def ping(self, retries=3):
        """Check whether this container is alive or not. If the container
        doesn't expose any ports, assume it is running. If the container
        exposes multiple ports, as soon as one port is active the application
        inside the container is considered to be up and running.
        
        Args:
            retries (int): number of attempts (timeout is 1 second).
        """
        if not self.ports:
            return True

        def ping_port(ip, port):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect((ip, port))
                s.close()
                return True
            except:
                return False

        while retries > 0:
            pings = filter(None,
                map(lambda port: ping_port(self.ship.ip, port['external']),
                       self.ports.itervalues()))
            if pings: return True
            retries -= 1
            if retries: time.sleep(1)

        # If we reach this point, the application is not running.
        return False


    def __repr__(self):
        return 'container(%s/%s on %s)' % (self.service, self.name, self.ship)

class Conductor:

    def __init__(self, config):
        self._config = config
        self._ships = dict(
            (k, Ship(k, v['ip'], v.get('docker_port', Ship.DEFAULT_DOCKER_PORT)))
                for k, v in self._config['ships'].iteritems())

        self._services = {}
        self._containers = {}

        logging.debug('Analyzing environment definition...')
        for kind, service in self._config['services'].iteritems():
            self._services[kind] = Service(kind, service['image'])

            for name, instance in service['instances'].iteritems():
                self._containers[name] = Container(name,
                        self._ships[instance['ship']],
                        self._services[kind], instance)

        # Resolve dependencies between services.
        logging.debug('Resolving service dependencies...')
        for kind, service in self._config['services'].iteritems():
            for dependency in service.get('requires', []):
                self._services[kind].add_dependency(self._services[dependency])

        # Provide link environment variables to each container of each service.
        for service in self._services.itervalues():
            for container in service.containers:
                # Containers always know about their peers in the same service.
                container.env.update(service.get_link_variables())
                # Containers also get links from the service's dependencies.
                for dependency in service.requires:
                    container.env.update(dependency.get_link_variables())

    def _service_order(self, pending=[], ordered=[]):
        """Calculate the service start order based on each service's
        dependencies.

        Services are initially all into the pending list and moved to the
        ordered list iff they have no dependency or all their dependencies have
        been met, that is are already into the ordered list.
        """
        wait = []
        for service in pending:
            if service.requires and not service.requires.issubset(set(ordered + [service])):
                wait.append(service)
            else:
                ordered.append(service)

        if len(wait) == len(pending):
            raise Exception, \
                'Cannot resolve dependencies in environment for services %s!' % wait
        return wait and self._service_order(wait, ordered) or ordered

    def _gather_dependencies(self, services):
        """Returns the extended set of services with dependencies for the
        requested services."""
        result = set(services)
        for service in services:
            result = result.union(service.requires)
        return result

    def _ordered_dependencies(self, services):
        return self._service_order(self._gather_dependencies(
            map(lambda n: self._services[n], services or self._services.keys())))

    def status(self, services):
        scores.Status().run(self._ordered_dependencies(services))

    def start(self, services):
        scores.Start().run(self._ordered_dependencies(services))
 
    def stop(self, services):
        scores.Stop().run(self._ordered_dependencies(services))

    def clean(self, services):
        raise NotImplementedError, 'Not yet implemented!'

def main():
    parser = argparse.ArgumentParser(description='Docker container orchestrator')
    parser.add_argument('command', nargs='?',
                        choices=['status', 'start', 'stop', 'clean'],
                        default='status',
                        help='Orchestration command to execute')
    parser.add_argument('services', nargs='*',
                        help='Service(s) to affect')
    parser.add_argument('-f', '--file', nargs='?', default='-', metavar='FILE',
                        help='Read environment description from FILE (use - for stdin)')
    parser.add_argument('-v', '--verbose', action='store_const',
                        const=logging.DEBUG, default=logging.INFO,
                        help='Be verbose')
    args = parser.parse_args()

    stream = args.file == '-' and sys.stdin or open(args.file)
    config = yaml.load(stream)
    stream.close()

    logging.basicConfig(stream=sys.stdout, level=args.verbose,
            format='%(message)s')

    # Shutup urllib3, wherever it comes from.
    logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARN)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARN)

    c = Conductor(config)
    getattr(c, args.command)(set(args.services))

if __name__ == '__main__':
    main()
