MaestroNG, an orchestrator of Docker-based deployments
======================================================

The original [Maestro](http://github.com/toscanini/mastro) was developed
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

*[See a demo](http://showterm.io/e20242d059958e09846ba)*

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

MaestroNG requires Docker 0.6.5 or newer on the hosts as it makes use of
the container naming feature.

You'll also need, to run Maestro:

* python-yaml
* A recent [docker-py](http://github.com/dotcloud/docker-py)

Orchestration
=============

Environment description
-----------------------

The environment is described using YAML. The format is still a bit in
flux but the base has been set and should remain fairly stable. It is
composed of two main sections: the _ships_, hosts that will execute the
Docker containers and the _services_, which define what service make up
the environment, the dependencies between these services and the
instances of each of these services that need to run.

The _ships_ are simple to define. They are named (but that name doesn't
need to match their DNS resolvable host name), and need an `ip`
address/hostname. If the Docker daemon doesn't listen its default port
of 4243, the `docker_port` can be overriden:

```yaml
ships:
  vm1.ore1:
    ip: c414.ore1.domain.com
  vm2.ore2:
    ip: c415.ore1.domain.com
    docker_port: 4244
  controller:
    ip: 42.42.42.1
```

Services are also named. Their name is used for commands that act on
specific services instead of the whole environment, and is also used in
dependency declarations. Each service must define the Docker image its
instances will be using, and of course a description of each instance.

Each service instance must at least define the _ship_ its container will
be placed on (by name). Additionally, it may define:

  - port mappings, as a map of `<port name>: <port or port mapping spec>`;
  - volume mappings, as a map of `<destination in container>: <source from host>`;
  - environment variables, as a map of `<variable name>: <value>`.

```yaml
services:
  zookeeper:
    image: zookeeper:3.4.5
    instances:
      zk:
        ship: vm1.ore1
        ports:
          client: 2181
        volumes:
          /var/lib/zookeeper: /data/zookeeper
  kafka:
    image: kafka:latest
    requires: [zookeeper]
    instances:
      kafka-broker:
        ship: vm2.ore1
        ports:
          broker: 9092
        volumes:
          /var/lib/kafka: /data/kafka
``` 

Port mappings and named ports
-----------------------------

How Maestro orchestrates and service auto-configuration
-------------------------------------------------------

