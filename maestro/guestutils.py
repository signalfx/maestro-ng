#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
# Utility functions for service start scripts that help work with Maestro
# orchestration.

import os
import re

class MaestroEnvironmentError(Exception):
    pass

def get_realm_name():
    """Return the name of the realm the container calling this is in."""
    return os.environ.get('DISCO_REALM', 'local')

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
    address = os.environ.get('CONTAINER_HOST_ADDRESS', '')
    if not address:
        raise MaestroEnvironmentError, 'Container host address was not defined'
    return address

def get_port(name, default=None):
    """Return the port number for the given port, or the given default if not
    found."""
    return _get_service_port(
        get_service_name(), get_container_name(),
        name, default)

def _to_env_var_name(s):
    """Transliterate a service or container name into the form used for
    environment variable names."""
    return re.sub(r'[^\w]', '_', s).upper()

def _get_service_port(service, container, port, default=None):
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
    entries will be of the form 'host[:port1[:port2]]'."""
    nodes = []

    regex = re.compile(r'^{}_(\w+)_HOST$'.format(_to_env_var_name(service)))

    for k, v in os.environ.iteritems():
        m = re.match(regex, k)
        if not m: continue
        node = v
        for port in ports:
            node = '{}:{}'.format(node, _get_service_port(service, m.group(1), port))
        nodes.append(node)

    if len(nodes) < minimum:
        raise MaestroEnvironmentError, \
            'No or not enough {} nodes configured'.format(service)
    return nodes
