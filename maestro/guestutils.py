# Copyright (C) 2013-2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Utility functions for service start scripts that help work with Maestro
# orchestration.

import netifaces
import os
import re


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
        raise MaestroEnvironmentError('Service name was not defined')
    return name


def get_container_name():
    """Returns the name of the container calling it."""
    name = os.environ.get('CONTAINER_NAME', '')
    if not name:
        raise MaestroEnvironmentError('Container name was not defined')
    return name


def get_container_host_address():
    """Return the publicly-addressable IP address of the host of the
    container."""
    address = os.environ.get('CONTAINER_HOST_ADDRESS', '')
    if not address:
        raise MaestroEnvironmentError('Container host address was not defined')
    return address


def get_container_internal_address():
    """Return the internal, private IP address assigned to the container."""
    return netifaces.ifaddresses('eth0')[netifaces.AF_INET][0]['addr']


def get_port(name, default=None):
    """Return the exposed (internal) port number for the given port, or the
    given default if not found."""
    return get_specific_exposed_port(
        get_service_name(),
        get_container_name(),
        name, default)


def get_specific_host(service, container):
    """Return the hostname/address of a specific container/instance of the
    given service."""
    try:
        return os.environ['{}_{}_HOST'.format(_to_env_var_name(service),
                                              _to_env_var_name(container))]
    except Exception:
        raise MaestroEnvironmentError(
            'No host defined for container {} of service {}'
            .format(container, service))


def get_specific_exposed_port(service, container, port, default=None):
    """Return the exposed (internal) port number of a specific port of a
    specific container from a given service."""
    try:
        return int(os.environ.get(
            '{}_{}_{}_INTERNAL_PORT'.format(_to_env_var_name(service),
                                            _to_env_var_name(container),
                                            _to_env_var_name(port)).upper(),
            default))
    except Exception:
        raise MaestroEnvironmentError(
            'No internal port {} defined for container {} of service {}'
            .format(port, container, service))


def get_specific_port(service, container, port, default=None):
    """Return the external port number of a specific port of a specific
    container from a given service."""
    try:
        return int(os.environ.get(
            '{}_{}_{}_PORT'.format(_to_env_var_name(service),
                                   _to_env_var_name(container),
                                   _to_env_var_name(port)).upper(),
            default))
    except Exception:
        raise MaestroEnvironmentError(
            'No port {} defined for container {} of service {}'
            .format(port, container, service))


def get_node_list(service, ports=[], minimum=1):
    """Build a list of nodes for the given service from the environment,
    eventually adding the ports from the list of port names. The resulting
    entries will be of the form 'host[:port1[:port2]]' and sorted by container
    name."""
    nodes = []

    for container in _get_service_instance_names(service):
        node = get_specific_host(service, container)
        for port in ports:
            node = '{}:{}'.format(node,
                                  get_specific_port(service, container, port))
        nodes.append(node)

    if len(nodes) < minimum:
        raise MaestroEnvironmentError(
            'No or not enough {} nodes configured'.format(service))
    return nodes


def _to_env_var_name(s):
    """Transliterate a service or container name into the form used for
    environment variable names."""
    return re.sub(r'[^\w]', '_', s).upper()


def _get_service_instance_names(service):
    """Return the list of container/instance names for the given service."""
    key = '{}_INSTANCES'.format(_to_env_var_name(service))
    if key not in os.environ:
        return []
    return os.environ[key].split(',')
