
Maestro guest functions
================================================================================

MaestroNG passes into your container's environment a lot of information
that you might need for your application to run: port numbers that you
have defined in your environment configuration file, addresses and ports
of your dependencies, etc. All these environment variables are defined
and documented in :doc:`orchestration`.

In order to make groking this environment information easier, MaestroNG
provides a Python module of "guest functions" that allow you to write
simple container init scripts in Python that act as the glue between
this information and your application's configuration before starting
the application itself.

A common use case, for example, is to get your ZooKeeper connection
string from this environment -- the rest you usually find in ZooKeeper
itself via service discovery.

Basic usage
--------------------------------------------------------------------------------

To make use of the Maestro guest utils functions, you'll need to have
the Maestro package installed inside your container. You can easily
achieve this by adding the following to your Dockerfile:

.. code-block:: Dockerfile

  ENV DEBIAN_FRONTEND noninteractive
  RUN apt-get update \
    && apt-get -y install python python-pip \
    && apt-get clean
  RUN pip install maestro-ng

Then, from your Python script, simply do:

.. code-block:: python

  from maestro.guestutils import *

And you're ready to go! Feel free to change the `import *` to the list
of specific functions you actually need in your script.

Reference
--------------------------------------------------------------------------------

Here's a summary of the functions available at your disposal that will
make your life much easier. All the examples given here are based on the
[Zookeeper+Kafka example environment](examples/zookeeper+kafka.yaml),
and assumed to be executed from within the `kafka-2` container.

get_environment_name()
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the name of the environment as defined in the description file.
Could be useful to namespace information inside ZooKeeper for example.

.. code-block:: python

  >> get_environment_name()
  'zk-kafka'

get_service_name()
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the name of the service the container is a member of.

.. code-block:: python

  >> get_service_name()
  'kafka'

get_container_name()
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the name of the container instance.

.. code-block:: python

  >> get_container_name()
  'kafka-2'

get_container_host_address()
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the IP address or hostname of the host of the container. Useful
if your application needs to advertise itself to some service discovery
system with its publicly reachable address. This would be `192.168.10.2`
in our example.

.. code-block:: python

  >> get_container_host_address()
  '192.168.10.2'

get_container_internal_address()
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the IP address assigned to the container itself by Docker (its
private IP address). This is normally the IP address Docker assigned to
the `eth0` interface inside the container and is usually in the
`172.18.42.0/24` subnet.

.. code-block:: python

  >> get_container_internal_address()
  # Might be different depending on the number of running containers on
  # that host.
  '172.18.42.1'

get_port(name, default=None)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the exposed internal port number of a given named port for the
current container. This is the port number your application uses
_inside_ the container. This is useful to automatically configure the
port your application should use directly from what you have specified
in your environment file.

If no default is provided and the port name does not exist, the function
will throw a `MaestroEnvironmentError` exception.

.. code-block:: python

  >> get_port('broker')
  9092

  >> get_port('unknown', 42)
  42

  >> get_port('unknown')
  # MaestroEnvironmentError gets raised

get_node_list(service, ports=[], minimum=1)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This function is one of the most useful of the set. It takes in a
service name and an optional list of port names and returns the list of
IP addresses/hostname of the containers of that service. For each port
specified, in order, it will append `:<port number>` to each host with
the external port number.

The `minimum` parameter allows for specifying a minimum number of hosts
to return, under which the function will throw a MaestroEnvironmentError
exception. This helps enforce the presence of at least N hosts of that
service you depend on in the environment.

Back to our example, you can return the list of ZooKeeper endpoints with
their client ports by calling:

.. code-block:: python

  >> get_node_list('zookeeper', ports=['client'])
  ['192.168.10.2:2181', '192.168.10.2:2182', '192.168.10.2:2183']

  >> get_node_list('zookeeper', ports=['client', 'peer'])
  ['192.168.10.2:2181:2888', '192.168.10.2:2182:2889', '192.168.10.2:2183:2890']

Note that Maestro provides information about all your declared
dependencies in your environment, but also the information about all the
instances of your service itself, so you can easily get a node list of
your peers:

.. code-block:: python

  >> get_node_list(get_service_name(), ports=['broker'])
  ['192.168.10.2:9092', '192.168.10.2:9093', '192.168.10.2:9094']

get_specific_host(service, container)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the hostname or IP address of a specific container from a given
service.

.. code-block:: python

  >> get_specific_host('zookeeper', 'zk-node-2')
  '192.168.10.2'

get_specific_port(service, container, port, default=None)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the external port number of a specific named port of a given
container. This is the externally reachable, routed port number for that
particular target.

.. code-block:: python

  >> get_specific_port('zookeeper', 'zk-node-2', 'client')
  2182

get_specific_exposed_port(service, container, port, default=None)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Returns the exposed internal port number of a specific named port of a
given container. This is rarely needed (but is used internally by
`get_port()`).

.. code-block:: python

  >> get_specific_exposed_port('zookeeper', 'zk-node-2', 'client')
  2181
