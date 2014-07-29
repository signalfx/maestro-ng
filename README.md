MaestroNG, an orchestrator of Docker-based deployments
======================================================

[![Build Status](https://travis-ci.org/signalfuse/maestro-ng.png)](https://travis-ci.org/signalfuse/maestro-ng)

The original [Maestro](http://github.com/toscanini/maestro) was developed
as a single-host orchestrator for Docker-based deployments. Given the
state of Docker at the time of its writing, it was a great first step
towards orchestration of deployments using Docker containers as the unit
of application distribution.

Docker having made significant advancements since then, deployments and
environments spanning across several hosts are becoming more and more
common and are in the need for some orchestration.

Based off ideas from the original Maestro and taking inspiration from
Docker's _links_ feature, MaestroNG makes the deployment and control of
complex, multi-host environments using Docker containers possible and
easy to use. Maestro of course supports declared dependencies between
services and makes sure to honor those during environment bring up.

What is Maestro?
----------------

MaestroNG is, for now, a command-line utility that allows for
automatically managing the orchestrated deployment and bring up of a set
of service instance containers that compose an environment on a set of
target host machines.

Each host machine is expected to run a Docker daemon. Maestro will then
contact the Docker daemon of each host in the environment to figure out
the status of the environment and what actions to take based on the
requested command.

Dependencies
------------

MaestroNG requires Docker 0.6.7 or newer on the hosts as it makes use of
the container naming feature and bug fixes in NAT port forwarding.

You'll also need the following Python modules, although these will be
automatically installed by `setuptools` if you follow the instructions
below.

* PyYAML (you may need to install this manually, e.g. `apt-get install python-yaml`)
* A recent [docker-py](http://github.com/dotcloud/docker-py)

Installation
------------

You can install Maestro via _Pip_:

```
$ pip install --user --upgrade git+git://github.com/signalfuse/maestro-ng
```

Orchestration
=============

The orchestration features of Maestro obviously rely on the
collaboration of the Docker containers that you are controlling with
Maestro. Maestro basically takes care of two things:

1. Controlling the start (and stop) order of services during environment
   bring up and tear down according to the defined dependencies between
   services.
1. Passing extra environment variables to each container to pass all the
   information it may need to operate in that environment, in particular
   information about its dependencies.

Let's first look at how environments and services are described, then
we'll discuss what information Maestro passes down to the containers
through their environment.

Environment description
-----------------------

The environment is described using YAML. The format is still a bit in
flux but the base has been set and should remain fairly stable. It is
named and composed of three main sections: the _registries_ that define
authentication credentials that might be needed to pull the Docker
images for the defined _services_ from their registries, the _ships_,
hosts that will execute the Docker containers, and the _services_, which
define what service make up the environment, the dependencies between
these services and the instances of each of these services that need to
run. Here's the outline:

```yaml
name: demo
registries:
  # Auth credentials for each registry that needs them (see below)
ships:
  # Ships definitions (see below)
services:
  # Services definition (see below)
```

The _registries_ define for each Docker registry Maestro might need to
pull images from the authentication credentials needed to access them
(see below _Working with image registries_). For each registry, the full
registry URL, a `username` and a `password` are required, and depending
on the registry the `email` might be as well. For example:

```yaml
registries:
  my-private-registry:
    registry: https://my-private-registry/v1/
    username: maestro
    password: secret
    email: maestro-robot@domain.com
```

The _ships_ are simple to define. They are named (but that name doesn't
need to match their DNS resolvable host name), and need an `ip`
address/hostname. If the Docker daemon doesn't listen its default port
of 2375, the `docker_port` can be overriden. You can also use an SSH
tunnel to secure the communication with the target Docker daemon
(especially if you don't want to Docker daemon to listen on anything
else than localhost, and rely on SSH key-based authentication instead).

```yaml
ships:
  vm1.ore1: {ip: c414.ore1.domain.com}
  vm2.ore2: {ip: c415.ore2.domain.com, docker_port: 4243}
  vm3.ore3:
    ip: c416.ore3.domain.com
    docker_port: 4243
    ssh_tunnel:
      user: ops
      key: {{ env.HOME }}/.ssh/id_dsa
      port: 22 # That's the default
```

Services are also named. Their name is used for commands that act on
specific services instead of the whole environment, and is also used in
dependency declarations. Each service must define the Docker image its
instances will be using, and of course a description of each instance.
It can also define environment variables that will apply to all
of that service's instances.

Each service instance must at least define the _ship_ its container will
be placed on (by name). Additionally, it may define:

  - `ports`, a dictionary of port mappings, as a map of `<port name>:
    <port or port mapping spec>` (see below for port spec syntax);
  - `lifecycle`, for lifecycle state checks, which Maestro uses to
    confirm a service correctly started or stopped (see Lifecycle checks
    below);
  - `volume`, for container volume mappings, as a map of `<destination
    in container>: <source from host>`;
  - `env`, for environment variables, as a map of `<variable name>:
    <value>` (variables defined at the instance level override variables
    defined at the service level);
  - `privileged`, a boolean specifying whether the container should run
    in privileged mode or not (defaults to `false`);
  - `stop_timeout`, the number of seconds Docker will wait between
    sending `SIGTERM` and `SIGKILL` (defaults to 10);
  - `limits`:
    - `memory`, the memory limit of the container (`k`, `m` and `g`
      limits accepted, also valid in uppercase);
    - `cpu`, the number of CPU shares (relative weight) allocated to the
      container;
  - `command`, to specify or override the command executed by the
    container.

```yaml
services:
  zookeeper:
    image: zookeeper:3.4.5
    instances:
      zk-1:
        ship: vm1.ore1
        ports: {client: 2181, peer: 2888, leader_election: 3888}
        lifecycle:
          running: [{type: tcp, port: client}]
        privileged: true
        volumes:
          /var/lib/zookeeper: /data/zookeeper
        limits:
          memory: 1g
          cpu: 2
      zk-2:
        ship: vm2.ore1
        ports: {client: 2181, peer: 2888, leader_election: 3888}
        lifecycle:
          running: [{type: tcp, port: client}]
        volumes:
          /var/lib/zookeeper: /data/zookeeper
        limits:
          memory: 1g
          cpu: 2
  kafka:
    image: kafka:latest
    requires: [ zookeeper ]
    instances:
      kafka-broker:
        ship: vm2.ore1
        ports: {broker: 9092}
        lifecycle:
          running: [{type: tcp, port: broker}]
        volumes:
          /var/lib/kafka: /data/kafka
        env:
          BROKER_ID: 0
        stop_timeout: 2
        limits:
          memory: 5G
          cpu: 10
```

Defining dependencies
---------------------

Services can depend on each other (circular dependencies are not
supported though). This dependency tree instructs Maestro to start and
stop the services in an order that will respect these dependencies.
Dependent services are started before services that depend on them, and
conversly leaves of the dependency tree are stopped before the services
they depend on so that at no point in time a service may run without its
dependencies -- unless this was forced by the user with the `-o` flag of
course.

Defining dependencies is done by giving a list of the dependent service
names in the service block:

```yaml
services:
  mysql:
    image: mysql
    instances:
      mysql-server-1: { ... }

  web:
    image: nginx
    requires: [ mysql ]
    instances:
      www-1: { ... }
```

Defining a dependency also makes Maestro inject into the instances of
the service environment variables that describe where the instances of
the service it depends on can be found (similarly to Docker links). See
"How Maestro orchestrates" below for more details on these variables.

It is also possible to define "soft" dependencies that do not impact the
start/stop orders but that still make Maestro inject these variables.
This can be useful if you know your application gracefully handles its
dependencies not being present at start time, through reconnects and
retries for examples. Defining soft dependencies is done via the
`wants_info` entry:

```yaml
services:
  mysql:
    image: mysql
    instances:
      mysql-server-1: { ... }

  web:
    image: nginx
    wants_info: [ mysql ]
    instances:
      www-1: { ... }
```

Port mapping syntax
-------------------

Maestro supports several syntaxes for specifying port mappings. Unless
the syntax supports and/or specifies it, Maestro will make the following
assumptions:

 * the exposed and external ports are the same (_exposed_ means the port
   bound to inside the container, _external_ means the port mapped by
   Docker on the host to the port inside the container);
 * the protocol is TCP (`/tcp`);
 * the external port is bound on all host interfaces using the `0.0.0.0`
   address.

The simplest form is a single numeric value, which maps the given TCP
port from the container to all interfaces of the host on that same port:

```yaml
# 25/tcp -> 0.0.0.0:25/tcp
ports: {smtp: 25}
```

If you want UDP, you can specify so:

```yaml
# 53/udp -> 0.0.0.0:53/udp
ports: {dns: 53/udp}
```

If you want a different external port, you can specify a mapping by
separating the two port numbers by a colon:

```yaml
# 25/tcp -> 0.0.0.0:2525/tcp
ports: {smtp: "25:2525"}
```

Similarly, specifying the protocol (they should match!):

```yaml
# 53/udp -> 0.0.0.0:5353/udp
ports: {dns: "53/udp:5353/udp"}
```

You can also use the dictionary form for any of these:

```yaml
ports:
  # 25/tcp -> 0.0.0.0:25/tcp
  smtp:
    exposed: 25
    external: 25

  # 53/udp -> 0.0.0.0:5353/udp
  dns:
    exposed: 53/udp
    external: 5353/udp
```

If you need to bind to a specific interface or IP address on the host,
you need to use the dictionary form:

```yaml
# 25/tcp -> 192.168.10.2:25/tcp
ports:
  smtp:
    exposed: 25
    external: [ 192.168.10.2, 25 ]


  # 53/udp -> 192.168.10.2:5353/udp
  dns:
    exposed: 53/udp
    external: [ 192.168.10.2, 5353/udp ]
```

Note that YAML supports references, which means you don't have to repeat
your _ship_'s IP address if you do something like this:

```yaml
ship:
  demo: {ip: &demoip 192.168.10.2, docker_port: 4243}

services:
  ...
    ports:
      smtp:
        exposed: 25/tcp
        external: [ *demoip, 25/tcp ]
```

Port mappings and named ports
-----------------------------

When services depend on each other, they most likely need to
communicate. If service B depends on service A, service B needs to be
configured with information on how to reach service A (its host and
port).

Even though Docker can provide inter-container networking, in a
multi-host environment this is not possible. Maestro also needs to keep
in mind that not all hosting and cloud providers provide advanced
networking features like multicast or bridged frames. This is why
Maestro makes the choice of always using the host's external IP address
and relies on traditional layer 3 communication between containers.

There is no performance hit from this, even when two containers on the
same host communicate, and it enables inter-host communication in a more
generic way regardless of where the two containers are located. Of
course, it is up to you to make sure that the hosts in your environment
can communicate with each other.

Note that even though Maestro allows for fully customizable port
mappings from the container to the host (see Port mapping syntax) above,
it is usually recommended to use the same port number inside and outside
the container. It makes it slightly easier for troubleshooting and some
services (Cassandra is one example) assume that all their nodes use the
same port(s), so the port they know about inside the container may need
to be the external port they use to connect to one of their peers.

One of the downsides of this approach is that if you run multiple
instances of the same service on the same host, you need to manually
make sure they don't use the same ports, through their configuration,
when that's possible.

Finally, Maestro uses _named_ ports, where each port your configure for
each service instance is named. This name is the name used by the
instance container to find out how it should be configured and on which
port(s) it needs to listen, but it's also the name used for each port
exposed through environment variables to other containers. This way, a
dependent service can know the address of a remote service, and the
specific port number of a desired endpoint. For example, service
depending on ZooKeeper would be looking for its `client` port.

Lifecycle checks
----------------

When controlling containers (your service instances), Maestro can
perform additional checks to confirm that the service reached the
desired lifecycle state, in addition to looking at the state of the
container itself. A common use-case for example is to check for a given
service port to become available to confirm that the application
correctly started and is accepting connections.

When starting containers, Maestro will execute all the lifecycle checks
for the `running` target state; all must pass for the instance to be
considered correctly up and running. Similarly, after stopping a
container, Maestro will execute all `stopped` target state checks.

Checks are defined via the `lifecycle` dictionary for each defined
instance. The following checks are available: TCP port pinging, and
script execution (using the return code). Keep in mind that if no
`running` lifecycle checks are defined, Maestro considers the service up
as soon as the container is up and will keep going with the
orchestration play immediately.

**TCP port pinging** makes Maestro attempt to connect to the configured
port (by name), once per second until it succeeds or the `max_wait`
value is reached (defaults to 60 seconds).

Assuming your instance declares a `client` named port, you can make
Maestro wait up to 10 seconds for this port to become available by doing
the following:

```yaml
services:
  zookeeper:
    image: zookeeper:3.4.5
    ports: {client: 2181}
    lifecycle:
      running:
        - {type: tcp, port: client, max_wait: 10}
```

**Script execution** makes Maestro execute the given command, using the
return code to denote the success or failure of the test (a return code
of zero indicates success, as per the Unix convention). For example:

```yaml
type: exec
command: "python my_cool_script.py"
```

How Maestro orchestrates and service auto-configuration
-------------------------------------------------------

The orchestration performed by Maestro is two-fold. The first part is
providing a way for each container to learn about the environment they
evolve into, to discover about their peers and/or the container
instances of other services in their environment. The second part is by
controlling the start/stop sequence of services and their containers,
taking service dependencies into account.

With inspiration from Docker's _links_ feature, Maestro utilizes
environment variables to pass information down to each container. Each
container is guaranteed to get the following environment variables:

* `SERVICE_NAME`: the friendly name of the service the container is an
  instance of. Note that it is possible to have multiple clusters of the
  same kind of application by giving them distinct friendly names.
* `CONTAINER_NAME`: the friendly name of the instance, which is also
  used as the name of the container itself. This will also be the
  visible hostname from inside the container.
* `CONTAINER_HOST_ADDRESS`: the external IP address of the host of the
  container. This can be used as the "advertised" address when services
  use dynamic service discovery techniques.

Then, for each container of each service that the container depends on,
a set of environment variables is added:

* `<SERVICE_NAME>_<CONTAINER_NAME>_HOST`: the external IP address of the
  host of the container, which is the address the application inside the
  container can be reached with accross the network.
* For each port declared by the dependent container:
  - `<SERVICE_NAME>_<CONTAINER_NAME>_<PORT_NAME>_PORT`, containing the
    external, addressable port number.

Each container of a service also gets these two variables for each
instance of that service so it knows about its peers. It also gets the
following variable for each port defined:

* `<SERVICE_NAME>_<CONTAINER_NAME>_<PORT_NAME>_INTERNAL_PORT`,
  containing the exposed (internal) port number that is, most likely,
  only reachable from inside the container and usually the port the
  application running in the container wants to bind to.

With all this information available in the container's environment, each
container can then easily know about its surroundings and the other
services it might need to talk to. It then becomes really easy to bridge
the gap between the information Maestro provides to the container via
its environment and the application you want to run inside the
container.

You could, of course, have your application directly read the
environment variables pushed in by Maestro. But that would tie your
application logic to Maestro, a specific orchestration system; you do
not want that. Instead, you can write a _startup script_ that will
inspect the environment and generate a configuration file for your
application (or pass in command-line flags).

To make this easier, Maestro provides a set of helper functions
available in its `maestro.guestutils` module. The recommended (or
easiest) way to build this startup script is to write it in Python, and
have the Maestro package installed in your container.

Links
-----

Maestro also supports defining links to link same-host containers
together via Docker's Links feature. Read more about [Docker
Links](http://docs.docker.io/en/latest/use/working_with_links_names/) to
learn more. Note that the format of the environment variables is not the
same as the ones Maestro inserts into the container's environment, so
software running inside the containers needs to deal with that on its
own.

Defining links is done through the instance-level `links` section, with
each link defined as a child in the format `name: alias`:

```yaml
services:
  myservice:
    image: ...
    instances:
      myservice-1:
        # ...
        links:
          mongodb01: db
```

Guest utils helper functions
----------------------------

To make use of the Maestro guest utils functions, you'll need to have
the Maestro package installed inside your container. You can easily
achieve this by adding the following to your Dockerfile (select the
version of Maestro that you need):

```
ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update
RUN apt-get -y install python python-pip git
RUN pip install git+git://github.com/signalfuse/maestro-ng
```

This will install the latest available version of Maestro. Feel free to
change that to any other version of Maestro you like or need.

Then, from your startup script (in Python), do:

```
from maestro.guestutils import *
```

And you're ready to go. Here's a summary of the functions available at
your disposal that will make your life much easier:

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
get_node_list('zookeeper', ports=['client']) -> ['c414.ore1.domain.com:2181', 'c415.ore1.domain.com:2181']
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

Working with image registries
-----------------------------

When Maestro needs to start a new container, it will do whatever it can
to make sure the image this container needs is available; the image full
name is specified at the service level.

Maestro will first check if the target Docker daemon reports the image
to be available. If the image is not available, or if the `-r` flag was
passed on the command-line (to force refresh the images), Maestro will
attempt to pull the image.

To do so, it will first analyze the name of the image and try to
identify a registry name (for example
`my-private-registry/my-image:tag`, the address of the registry is
`my-private-registry`) and look for a corresponding entry in the
`registries` section of the environment description file to look for
authentication credentials, if they are needed to access the images from
that registry.

If credentials are found, Maestro will login to the registry before
attempting to pull the image.

Passing extra environment variables
-----------------------------------

You can pass in or override arbitrary environment variables by providing
a dictionary of environment variables key/value pairs. This can be done
both at the service level and the container level; the latter taking
precedence:

```yaml
services:
  myservice:
    image: ...
    env:
      FOO: bar
    instance-1:
      ship: host
      env:
        FOO: overrides bar
        FOO_2: bar2
```

Additionally, Maestro will automatically expand all levels of YAML lists
in environment variable values. The following are equivalent:

```yaml
env:
  FOO: This is a test
  BAR: [ This, [ is, a ], test ]
```

This becomes useful when used in conjunction with YAML references to
build more complex environment variable values:

```yaml
_globals:
  DEFAULT_JVM_OPTS: &jvmopts [ '-Xms500m', '-Xmx2g', '-showversion', '-server' ]

...

env:
  JVM_OPTS: [ *jvmopts, '-XX:+UseConcMarkSweep' ]
```

Usage
=====

Once installed, Maestro is available both as a library through the
`maestro` package and as an executable. To run Maestro, simply execute
`maestro`. Note that if you didn't install Maestro system-wide, you can
still run it with the same commands as long as your `PYTHONPATH`
contains the path to your `maestro-ng` repository clone and using
`python -m maestro ...`.

```
$ maestro -h
usage: maestro [-h] [-f FILE] [-v]
               {status,start,stop,restart,logs,deptree} ...

Maestro, Docker container orchestrator.

positional arguments:
  {status,start,stop,restart,logs,deptree}
    status              display container status
    start               start services and containers
    stop                stop services and containers
    restart             restart services and containers
    logs                show logs from a container
    deptree             show the dependency tree
    complete            shell auto-completion helper

optional arguments:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  read environment description from FILE (use - for
                        stdin, defaults to ./maestro.yaml)
  -v, --version         show program version and exit
```

You can then get help on each individual command with:

```
$ maestro start -h
usage: maestro start [-h] [-c LIMIT] [-d] [-i] [-r] [thing [thing ...]]

Start services and containers

positional arguments:
  thing                 container(s) or service(s) to display

optional arguments:
  -h, --help            show this help message and exit
  -c LIMIT, --concurrency LIMIT
                        limit how many containers can be acted on at the same
                        time to LIMIT
  -d, --with-dependencies
                        include dependencies
  -i, --ignore-dependencies
                        ignore dependency order
  -r, --refresh-images  force refresh of container images from registry
```

By default, Maestro will read the environment description configuration
from the `maestro.yaml` file in the current directory. You can override
this with the `-f` flag to specify the path to the environment
configuration file. Additionally, you can use `-` to read the
configuration from `stdin`. The following commands are identical:

```
$ maestro status
$ maestro -f maestro.yaml status
$ maestro -f - status < maestro.yaml
```

The first positional argument is a command you want Maestro to execute.
The available commands are `status`, `start`, `stop`, `restart`, `logs`
and `deptree`. They should all be self-explanatory.

Most commands operate on one or more "things", which can be services or
instances, by name. When passing service names, Maestro will
automatically expand those to their corresponding list of instances. The
`logs` command is the only one that operates on strictly one container
instance.

Impact of defined dependencies on orchestration order
-----------------------------------------------------

One of the main features of Maestro is its understand of dependencies
between services. When Maestro carries out an orchestration action,
dependencies are always considered unless the `-i |
--ignore-dependencies` flag is passed.

**But Maestro will only respect the dependencies to other services and
containers that the current orchestration action includes.** If you want
Maestro to automatically include the dependencies of the services or
containers you want to act on in the orchestration that will be carried
out, you must pass the `-d | --with-dependencies` flag!

For example, assuming we have two services, ZooKeeper (`zookeeper`) and
Kafka (`kafka`). Kafka depends on ZooKeeper:

```
# Starts Kafka and only Kafka:
$ maestro start kafka

# Starts ZooKeeper, then Kafka:
$ maestro start -d kafka
# Which is equivalent to:
$ maestro start kafka zookeeper

# Starts ZooKeeper and Kafka at the same time (includes dependencies but
# ignores dependency order constraints):
$ maestro start -d -i kafka
```

Examples of Docker images with Maestro orchestration
====================================================

For examples of Docker images that are suitable for use with Maestro,
you can look at the following repositories:

- http://github.com/signalfuse/docker-cassandra  
  A Cassandra image. Nodes within the same cluster are automatically
  used as Gossip seed peers.

- http://github.com/signalfuse/docker-elasticsearch  
  ElasicSearch with ZooKeeper-based discovery instead of the
  multicast-based discovery, to work in cloud environments.

- http://github.com/signalfuse/docker-zookeeper  
  A ZooKeeper image, automatically creating a cluster with the other
  instances in the same environment.
