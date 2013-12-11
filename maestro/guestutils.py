#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
# Utility functions for service start scripts that help work with Maestro
# orchestration.

import docker
import os
import re

import entities

class MaestroEnvironmentError(Exception):
    pass

def get_environment_name():
    """Return the name of the environment the container calling this in a part
    of."""
    return os.environ.get('MAESTRO_ENVIRONMENT_NAME', 'local')

def get_service_name():
    """Returns the service name of the container calling it."""
    name = os.environ.get('SERVICE_NAME', '')
    if not name:
        raise MaestroEnvironmentError, 'Service name was not defined'
    return name

def get_container_name():
    """Returns the name of the container calling it."""
    name = os.environ.get('CONTAINER_NAME', '')
    if not name:
        raise MaestroEnvironmentError, 'Container name was not defined'
    return name

def get_container_host_address():
    """Return the publicly-addressable IP address of the host of the
    container."""
    address = os.environ.get('CONTAINER_HOST_ADDRESS', '')
    if not address:
        raise MaestroEnvironmentError, 'Container host address was not defined'
    return address

def get_container_internal_address():
    """Return the internal, private IP address assigned to the container."""
    ship = entities.Ship('host', get_container_host_address())
    return str(ship.backend.inspect_container(get_container_name())['NetworkSettings']['IPAddress'])

def get_port(name, default=None):
    """Return the port number for the given port, or the given default if not
    found."""
    return get_specific_port(
        get_service_name(), get_container_name(),
        name, default)

def get_specific_host(service, container):
    """Return the hostname/address of a specific container/instance of the
    given service."""
    return os.environ['{}_{}_HOST'.format(_to_env_var_name(service),
                                          _to_env_var_name(container))]

def get_specific_port(service, container, port, default=None):
    """Return the port number of a specific port of a specific container from a
    given service."""
    return int(os.environ.get(
        '{}_{}_{}_PORT'.format(_to_env_var_name(service),
                               _to_env_var_name(container),
                               _to_env_var_name(port)).upper(),
        default))

def get_node_list(service, ports=[], minimum=1):
    """Build a list of nodes for the given service from the environment,
    eventually adding the ports from the list of port names. The resulting
    entries will be of the form 'host[:port1[:port2]]' and sorted by container
    name."""
    nodes = []

    for container in _get_service_instance_names(service):
        node = get_specific_host(service, container)
        for port in ports:
            node = '{}:{}'.format(node, get_specific_port(service, container, port))
        nodes.append(node)

    if len(nodes) < minimum:
        raise MaestroEnvironmentError, \
            'No or not enough {} nodes configured'.format(service)
    return nodes

def _to_env_var_name(s):
    """Transliterate a service or container name into the form used for
    environment variable names."""
    return re.sub(r'[^\w]', '_', s).upper()

def _get_service_instance_names(service):
    """Return the list of container/instance names for the given service."""
    def extract_name(var):
        m = re.match(r'^{}_(\w+)_HOST$'.format(_to_env_var_name(service)), var)
        return m and m.group(1) or None
    return filter(None, map(extract_name, sorted(os.environ.keys())))
