# MaestroNG, an orchestrator of Docker-based deployments

Note: MaestroNG's documentation is in the process of being migrated to
ReadTheDocs. Individual, organized sections will be created
progressively, as they are restructured and taken out of this main
document (which used to be the project's README).

## Introduction

MaestroNG is an orchestrator of Docker-based, multi-hosts environments.
Working from a description of your environment, MaestroNG offers
service-level and container-level controls that rely on Maestro's
understanding of your declared service dependencies, and placement of
your containers in your fleet of hosts.

Maestro aims at being simple to use whether you are controlling a few
containers in a local virtual machine, or hundreds of containers spread
across as many hosts.

## Orchestration

The orchestration features of Maestro obviously rely on the
collaboration of the Docker containers that you are controlling with
Maestro. Maestro basically takes care of two things:

1. Controlling the start (and stop) order of services during environment
   bring up and tear down according to the defined dependencies between
   services.
1. Passing extra environment variables to each container to pass all the
   information it may need to operate in that environment, in particular
   information about its dependencies.

The most common way to integrate your application with Maestro is to
make your container's entrypoint a simple Python init script that acts
as the glue between Maestro, the information that it passes through the
container's environment, and your application. To make this easier to
write and put together, Maestro provides a set of [Guest
functions](guest-functions.md) that know how to grok this environment
information.

----

Let's first look at how environments and services are described, then
we'll discuss what information Maestro passes down to the containers
through their environment.

## Environment description

The environment is described using YAML. The format is still a bit in
flux but the base has been set and should remain fairly stable. It is
named and composed of three main mandatory sections: the _registries_
that define authentication credentials that might be needed to pull the
Docker images for the defined _services_ from their registries, the
_ships_, hosts that will execute the Docker containers, and the
_services_, which define what services make up the environment, the
dependencies between these services and the instances of each of these
services that need to run. Here's the outline:

```yaml
__maestro:
  schema: 2

name: demo
registries:
  # Auth credentials for each registry that needs them (see below)
ship_defaults:
  # defaults for some of the ship attributes (see below)
ships:
  # Ship definitions (see below)
services:
  # Service definitions (see below)
```

The first element, `__maestro`, is used to pass in some information to
Maestro that does not directly relate to your environment description,
but helps Maestro understand it. In particular, the `schema` version
is used to note what version of the YAML "schema" Maestro will be using
when parsing the environment description. This is used when backwards
incompatible changes are introduced by Maestro to provide an easier
upgrade path.

The _registries_ define each Docker registry Maestro might need to
pull images from and the authentication credentials needed to access them
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

The ship defaults allow you to specify certain ship attribute defaults,
like `timeout`, `docker_port`, or `ssh_timeout`.

```yaml
ship_defaults:
  timeout: 60
```

The _ships_ are simple to define. They are named (but that name doesn't
need to match their DNS resolvable host name), and need an `ip`
address/hostname. If the Docker daemon doesn't listen its default port
of 2375, the `docker_port` can be overriden.

If the address of the machine is not the one you want to use to interact
with the Docker daemon running there (for example via a private
network), you can override the Docker daemon endpoint address with the
`endpoint` parameter. If not specified, Maestro will simply use the
ship's `ip` parameter.

You can also use an SSH tunnel to secure the communication with the
target Docker daemon (especially if you don't want the Docker daemon to
listen on anything else than `localhost`, and rely on SSH key-based
authentication instead). Here again, if the `endpoint` parameter is
specified, it will be used as the target host for the SSH connection.

If the Docker daemon is listening on a unix domain socket in the local
filesystem, you can specify `socket_path` to connect to it directly.
This is useful when the Docker daemon is running locally.

```yaml
ships:
  vm1.ore1: {ip: c414.ore1.domain.com}
  vm2.ore2: {ip: c415.ore2.domain.com, docker_port: 4243}
  vm3.ore3:
    ip: c416.ore3.domain.com
    endpoint: c416.corp.domain.com
    docker_port: 4243
    ssh_tunnel:
      user: ops
      key: {{ env.HOME }}/.ssh/id_dsa
      port: 22 # That's the default
```

You can also connect to a Docker daemon secured by TLS.  Note that if
you want to use verification, you have to give the IP (or something that
is resolvable inside the container) as IP, and the name in the server
certificate as endpoint.

Not using verification works too (just don't mention `tls_verify` and
`tls_ca_cert`), but a warning from inside `urllib3` will make Maestro's
output unreadable.

In the example below, "docker1" is the CN in the server certificate.
All certificates and keys have been created as explained in
https://docs.docker.com/articles/https/

```yaml
ships:
    docker1:
        ip: 172.17.42.1
        endpoint: docker1
        tls: true
        tls_verify: true
        tls_ca_cert: ca.pem
        tls_key: key.pem
        tls_cert: cert.pem
```

Services are also named. Their name is used for commands that act on
specific services instead of the whole environment, and is also used in
dependency declarations. Each service must define the Docker image its
instances will be using via the `image` parameter, and of course a
description of each instance. It can also define environment variables
that will apply to all of that service's instances through the `env`
dictionary, dependencies through the `requires` and `wants_info` lists
(see below in _Defining dependencies_). It is also possible to exclude a
service from non-specific actions (when Maestro is executed without a
list of services or containers as arguments) by setting the `omit: true`
parameter on the service.

Each service instance must at least define the _ship_ its container will
be placed on (by name). Additionally, it may define:

  - `image`, to override the service-level image repository name, if
    needed (useful for canary deployments for example);
  - `ports`, a dictionary of port mappings, as a map of `<port name>:
    <port or port mapping spec>` (see below for port spec syntax);
  - `lifecycle`, for lifecycle state checks, which Maestro uses to
    confirm a service correctly started or stopped (see Lifecycle checks
    below);
  - `volumes`, for container volume mappings, as a map of
    `<source from host>: <destination in container>`. Each target can
    also be specified as a map `{target: <destination>, mode: <mode>}`,
    where `mode` is `ro` (read-only) or `rw` (read-write);
  - `container_volumes`, a path, or list of paths inside the container
    to be used as container-only volumes with no host bind-mount. This
    is mostly used for data-containers;
  - `volumes_from`, a container or list of containers running on the
    same _ship_ to get volumes from. This is useful to get the volumes
    of a data-container into an application container;
  - `env`, for environment variables, as a map of 
    `<variable name>: <value>` (variables defined at the instance
    level override variables defined at the service level);
  - `privileged`, a boolean specifying whether the container should run
    in privileged mode or not (defaults to `false`);
  - `cap_add`, Linux capabilities to add to the container (see the
    documentation for [docker run](https://docs.docker.com/reference/run/#runtime-privilege-linux-capabilities-and-lxc-configuration));
  - `cap_drop`, Linux capabilities to drop from the container;
  - `extra_hosts`, map a custom host to an IP for the container. Example: `<hostname>: <ip address>`;
  - `stop_timeout`, the number of seconds Docker will wait between
    sending `SIGTERM` and `SIGKILL` (defaults to 10);
  - `limits`:
    - `memory`, the memory limit of the container (in bytes, or with one
      of the `k`, `m` or `g` suffixes, also valid in uppercase);
    - `cpu`, the number of CPU shares (relative weight) allocated to the
      container;
    - `swap`, the swap limit of the container (in bytes, or with one
      of the `k`, `m` or `g` suffixes, also valid in uppercase);
  - `log_driver`, one of the supported log drivers, e.g. syslog or json-file.
  - `log_opt`, a set of key value pairs that provide additional logging parameters. E.g. the syslog-address to redirect syslog output to another address.
  - `command`, to specify or override the command executed by the
    container;
  - `net`, to specify the container's network mode (one of `bridge` --
    the default, `host`, `container:<name|id>` or `none` to disable
    networking altogether);
  - `restart`, to specify the restart policy (see Restart Policy below);
  - `dns`, to specify one (as a single IP address) or more DNS servers
    (as a list) to be declared inside the container.

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
          /data/zookeeper: /var/lib/zookeeper
        limits:
          memory: 1g
          cpu: 2
      zk-2:
        ship: vm2.ore1
        ports: {client: 2181, peer: 2888, leader_election: 3888}
        lifecycle:
          running: [{type: tcp, port: client}]
        volumes:
          /data/zookeeper: /var/lib/zookeeper
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
          /data/kafka: /var/lib/kafka
          /etc/locatime:
            target: /etc/localtime
            mode: ro
        env:
          BROKER_ID: 0
        stop_timeout: 2
        limits:
          memory: 5G
          swap: 200m
          cpu: 10
        dns: [ 8.8.8.8, 8.8.4.4 ]
        net: host
        restart:
          name: on-failure
          maximum_retry_count: 3
```

## Defining dependencies

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

Defining a dependency also makes Maestro inject environment variables
into the instances of these services that describe where the instances of
the services it depends on can be found (similarly to Docker links). See
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

## Port mapping syntax

Maestro supports several syntaxes for specifying port mappings. Unless
the syntax supports and/or specifies otherwise, Maestro will make the
following assumptions:

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

## Port mappings and named ports

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

## Volume bindings

Volume bindings are specified in a way similar to `docker-py` and
Docker's expected format, and the `mode` (read-only 'ro', or read-write
'rw') can be specified for each binding if needed. Volume bindings
default to being read-write.

```yaml
volumes:
  # This will be a read-write binding
  /on/the/host: /inside/the/container

  # This will be a read-only binding
  /also/on/the/host/:
    target: /inside/the/container/too
    mode: ro
```

Note that it is currently not possible to bind-mount the same host
location into two distinct places inside the container as this is not
supported by `docker-py` (it's a dictionary keyed on the host location).

Container-only volumes can be specified with the `container_volumes`
setting on each instance, as a path or list of paths:

```yaml
container_volumes:
  - /inside/the/container/1
  - /inside/the/container/2
```

Finally, you can get the volumes of one or more containers into a
container with the `volumes_from` feature of Docker, as long as the
containers run on the same ship:

```yaml
# other1 and other2 run on the same ship as this container
volumes_from: [ other1, other2 ]
```

## Lifecycle checks

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
value is reached (defaults to 300 seconds).

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

**HTTP Request** makes Maestro execute web requests to a target, once
per second until it succeeds or the `max_wait` value is reached
(defaults to 300 seconds).

Assuming your instance declares a `admin` named port that runs a
webserver, you can make Maestro wait up to 10 seconds for an HTTP
request to this port for the default path "/" to succeed by doing the
following:

```yaml
services:
  frontend:
    image: frontend
    ports: {admin: 8080}
    lifecycle:
      running:
        - {type: http, port: admin, max_wait: 10}
```

Options:

 - `port`, named port for an instance or explicit numbered port
 - `host`, IP or resolvable hostname (defaults to ship.ip)
 - `match_regex`, regular expression to test response against (defaults
   to checking for HTTP 200 response code)
 - `path`, path (including querystring) to use for request (defaults to
   /)
 - `scheme`, request scheme (defaults to http)
 - `method`, HTTP method (defaults to GET)
 - `max_wait`, max number of seconds to wait for a successful response
   (defaults to 300)
 - `requests_options`, additional dictionary of options passed directly
   to python's requests.request() method (e.g. verify=False to disable
   certificate validation)

**Script execution** makes Maestro execute the given command, using the
return code to denote the success or failure of the test (a return code
of zero indicates success, as per the Unix convention). The command is
executed a certain number of attempts (defaulting to 180), with a delay
between each attempt of 1 second. For example:

```yaml
type: exec
command: "python my_cool_script.py"
attempts: 30
```

The command's execution environment is extended with the same
environment that your running container would have, which means it
contains all the environment information about the container's
configuration, ports, dependencies, etc. You can then use Maestro guest
utility functions to easily grok that information from the environment
(in Python). See "How Maestro orchestrates and service
auto-configuration" and "Guest utils helper functions" below for more
information.

Note that the current working directory is never changed by Maestro
directly; paths to your scripts will be resolved from wherever you run
Maestro, not from where the environment YAML file lives.

## Restart policy

Since version 1.2 docker allows to define the restart policy of a
container when it stops. The available policies are:

  - `restart: no`, the default. The container is not restarted;
  - `restart: always`: the container is _always_ restarted, regardless
    of its exit code;
  - `restart: on-failure`: the container is restarted if it exits with a
    non-zero exit code.

You can also specify the number of maximum retries for restarting the
container before giving up:

```yaml
restart:
  name: on-failure
  retries: 3
```

Or as a single string (similar to Docker's command line option):

```yaml
restart: "on-failure:3"
```

## How Maestro orchestrates and service auto-configuration

The orchestration performed by Maestro is two-fold. The first part is
providing a way for each container to learn about the environment they
evolve into, to discover about their peers and/or the container
instances of other services in their environment. The second part is by
controlling the start/stop sequence of services and their containers,
taking service dependencies into account.

With inspiration from Docker's _links_ feature, Maestro utilizes
environment variables to pass information down to each container. Each
container is guaranteed to get the following environment variables:

* `DOCKER_IMAGE`: the full name of the image this container is started
  from.
* `DOCKER_TAG`: the tag of the image this container is started from.
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
* For each port declared by the dependent container, a
  `<SERVICE_NAME>_<CONTAINER_NAME>_<PORT_NAME>_PORT` environment
  variable, containing the external, addressable port number, is
  provided.

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

## Links

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

## Working with image registries

When Maestro needs to start a new container, it will do whatever it can
to make sure the image this container needs is available; the image full
name is specified at the service level.

Maestro will first check if the target Docker daemon reports the image
to be available. If the image is not available, or if the `-r` flag was
passed on the command-line (to force refresh the images), Maestro will
attempt to pull the image.

To do so, it will first analyze the name of the image and try to
identify a registry name (for example, in
`my-private-registry/my-image:tag`, the address of the registry is
`my-private-registry`) and look for a corresponding entry in the
`registries` section of the environment description file to look for
authentication credentials. Note that Maestro will also look at each
registry's address FQDN for a match as a fallback.

You can also put your credentials into `${HOME}/.dockercfg` in the
appropriate format expected by Docker and `docker-py`. Maestro, via the
`docker-py` library, will also be looking at the contents of this file
for credentials to registries you are already logged in against.

If credentials are found, Maestro will login to the registry before
attempting to pull the image.

## Passing extra environment variables

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

# Examples of Docker images with Maestro orchestration

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
