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

Installation
------------

Maestro provides `setuptools`-style installation. Running this will do
the trick:

```
$ python setup.py install
```

Depending on your setup, you might need to change the permissions of
Python's `dist-packages` or `site-packages` directories so that your
user can access this newly installed Python module. For example, on
MacOS, it would look something like:

```
$ sudo chmod -R a+rX /Library/Python/2.7/site-packages/
```

If you don't want to install Maestro system-wide, you can just leave it
as-is in its Git repository clone. You'll just need to add the path to
the repository to your `PYTHONPATH` environment variable.


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

Finally, Maestro makes the choice of using one-to-one port mappings from
the container to the host. This _may_ change in the future, but for now
this simplifies things:

* it means Maestro doesn't have to do a lot of introspection on the
  containers to figure out which external port Docker assigned them;
* it makes it a bit easier for troubleshooting as port numbers are the
  same inside and outside the containers;
* some services (Cassandra is one example) assume that all their nodes
  use the same port(s).

One of the downsides of this approach is that if you run multiple
instances of the same service on the same host, you need to manually
make sure they don't use the same ports, through their configuration.


Finally, Maestro uses _named_ ports, where each port your configure for
each service instance is named. This name is the name used by the
instance container to find out how it should be configured and on which
port(s) it needs to listen, but it's also the name used for each port
exposed through environment variables to other containers. This way, a
dependent service can know the address of a remote service, and the
specific port number of a desired endpoint. For example, service
depending on ZooKeeper would be looking for its `client` port.

How Maestro orchestrates and service auto-configuration
-------------------------------------------------------


Usage
=====

Once installed, Maestro is available both as a library through the
`maestro` package and as an executable. Note that if you didn't install
Maestro system-wide, you can still run it with the same commands as long
as your `PYTHONPATH` contains the path to your `maestro-ng` repository
clone. To run Maestro, simply execute the main Python package:

```
$ python -m maestro -h
usage: maestro.py [-h] [-f [FILE]] [-v]
                  [{status,start,stop,clean}] [services [services ...]]

Docker container orchestrator

positional arguments:
  {status,start,stop,clean}
                        Orchestration command to execute
  services              Service(s) to affect

optional arguments:
  -h, --help            show this help message and exit
  -f [FILE], --file [FILE]
                        Read environment description from FILE (use -
for
                        stdin)
  -v, --verbose         Be verbose
```

By default, Maestro will read the environment description from the
standard input so if you run Maestro without arguments it will appear to
not do anything and just be "stuck". You can also use the `-f` flag to
specify the path to the environment file. The two following commands are
identical:

```
$ python -m maestro < demo.yaml
$ python -m maestro -f demo.yaml
```

The first positional argument is a command you want Maestro to execute.
The available commands are `status`, `start`, `stop` and `clean`. They
should all be self-explanatory. Service dependency is always honored for
all commands. Note that if services don't have any dependencies (or have
the same dependencies), their start order might not always be the same.

You can also pass one or more service names on which to execute the
command, to restrict the action of the command to just these services.
Note that Maestro will do its best to examine the state of the system
and not perform any action unless it's really necessary.

Finally, if started without any command and service names, Maestro will
default to the `status` command, showing the state of the environment.

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
