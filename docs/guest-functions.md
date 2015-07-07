# Guest functions

To make use of the Maestro guest utils functions, you'll need to have
the Maestro package installed inside your container. You can easily
achieve this by adding the following to your Dockerfile (select the
version of Maestro that you need):

```Dockerfile
ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update && apt-get install python python-pip
RUN pip install maestro-ng
```

This will install the latest available version of Maestro. Feel free to
change that to any other version of Maestro you like or need by adding
`==<the_version_you_want>` to the end of the command-line.

Then, from your startup script (in Python), do:

```python
from maestro.guestutils import *
```

And you're ready to go!

Here's a summary of the functions available at your disposal that will
make your life much easier:

  - `get_environment_name()` returns the name of the environment as
    defined in the description file. Could be useful to namespace
    information inside ZooKeeper for example.
  - `get_service_name()` returns the friendly name of the service the
    container is a member of.
  - `get_container_name()` returns the friendly name of the container
    itself.
  - `get_container_host_address()` returns the IP address or hostname of
    the host of the container. Useful if your application needs to
    advertise itself to some service discovery system.
  - `get_container_internal_address()` returns the IP address assigned
    to the container itself by Docker (its private IP address).
  - `get_port(name, default)` will return the exposed (internal) port
    number of a given named port for the current container instance.
    This is useful to set configuration parameters for example.

Another very useful function is the `get_node_list` function. It takes
in a service name and an optional list of port names and returns the
list of IP addresses/hostname of the containers of that service. For
each port specified, in order, it will append `:<port number>` to each
host with the external port number. For example, if you want to return
the list of ZooKeeper endpoints with their client ports:

```python
get_node_list('zookeeper', ports=['client'])
# returns ['zk1.domain.com:2181', 'zk2.domain.com:2181']
```

Other functions you might need are:

  - `get_specific_host(service, container)`, which can be used to return
    the hostname or IP address of a specific container from a given
    service, and
  - `get_specific_port(service, container, port, default)`, to retrieve
    the external port number of a specific named port of a given
    container.
  - `get_specific_exposed_port(service, container, port, default)`, to
    retrieve the exposed (internal) port number of a specific named port
    of a given container.
