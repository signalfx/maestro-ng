
.. _docker run: https://docs.docker.com/reference/run/#runtime-privilege-linux-capabilities-and-lxc-configuration

Environment description
================================================================================

The environment is described using YAML. The description of the environment
follows a specific, versioned *schema*. The default schema version, if not
specified, is version 1. The most recent version of the schema, described by
this documentation, is version 2. To declare what schema version to use for
your YAML environment description file, use the following header:

.. code-block:: yaml

  __maestro:
    schema: 2

Structure
--------------------------------------------------------------------------------

The environment is named, and composed of three main mandatory sections:
*registries*, *ships*, and *services*.

1. The *registries* section defines authentication credentials that Maestro can
   use to pull Docker images for your *services*. If you only pull public
   images, this section may remain empty.

2. The *ships* section describes hosts that will run the Docker containers.

3. The *services* section defines which services make up the environment, the
   dependencies between them, and instances of your services that you want to
   run.

Here's the outline:

.. code-block:: yaml

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

Metadata
--------------------------------------------------------------------------------

The ``__maestro`` section contains information that helps Maestro understand
your environment description. In particular, the ``schema`` version specifies
what version of the YAML "schema" Maestro should use when parsing the
environment description. This provides an easier upgrade path when Maestro
introduces backwards incompatible changes.

Registries
--------------------------------------------------------------------------------

The *registries* section defines the Docker registries that Maestro can pull
images from and the authentication credentials needed to access them (see
:doc:`registries`). For each registry, you must provide the full registry URL,
a ``username``, a ``password``, and possibly ``email``. For example:

.. code-block:: yaml

  registries:
    my-private-registry:
      registry: https://my-private-registry/v1/
      username: maestro
      password: secret
      email: maestro-robot@domain.com

Ship defaults
--------------------------------------------------------------------------------

The ship defaults sections specify certain ship attribute defaults,
like ``timeout``, ``docker_port``, ``api_version`` or ``ssh_timeout``.

.. code-block:: yaml

  ship_defaults:
    timeout: 60

Ships
--------------------------------------------------------------------------------

A *ship* is a host that runs your Docker containers. They have names (which
don't need to match their DNS resolvable host name) and IP addressses/hostnames
(``ip``). They may also define:

- ``api_version``: The API version of the Docker daemon. If you set it to ``auto``,
  the version is automatically retrieved from the Docker daemon and the latest
  available version is used.

- ``docker_port``: A custom port, used if the Docker daemon doesn't listen on the
  default port of 2375.

- ``endpoint``: The Docker daemon endpoint address. Override this if the address
  of the machine is not the one you want to use to interact with the Docker
  daemon running there (for example via a private network). Defaults to the
  ship's ``ip`` parameter.

- ``ssh_tunnel``: An SSH tunnel to secure the communication with the target
  Docker daemon (especially if you don't want the Docker daemon to listen on
  anything else than ``localhost``, and rely on SSH key-based authentication
  instead). Here again, if the ``endpoint`` parameter is specified, it will be
  used as the target host for the SSH connection.

- ``socket_path``: If the Docker daemon is listening on a unix domain socket in
  the local filesystem, you can specify ``socket_path`` to connect to it
  directly.  This is useful when the Docker daemon is running locally.


.. code-block:: yaml

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

You can also connect to a Docker daemon secured by TLS.  Note that if
you want to use verification, you have to give the IP (or something that
is resolvable inside the container) as IP, and the name in the server
certificate as endpoint.

Not using verification works too (just don't mention ``tls_verify`` and
``tls_ca_cert``), but a warning from inside ``urllib3`` will make Maestro's
output unreadable.

In the example below, "docker1" is the CN in the server certificate.
All certificates and keys have been created as explained in
https://docs.docker.com/articles/https/

.. code-block:: yaml

  ships:
      docker1:
          ip: 172.17.42.1
          endpoint: docker1
          tls: true
          tls_verify: true
          tls_ca_cert: ca.pem
          tls_key: key.pem
          tls_cert: cert.pem

Services
--------------------------------------------------------------------------------

Services have a name (used for commands that act on specific services instead
of the whole environment and in dependency declarations), a Docker image
(``image``), and a description of each instance of that service (under
``instances``). Services may also define:

- ``envfile``: Filename, or list of filenames, of Docker environment files that
  will apply to all of that service's instances. File names are relative to the
  Maestro environment YAML file's location;

- ``env``: Environment variables that will apply to all of that service's
  instances. ``env`` values take precedence over the contents of ``envfile``s;

- ``omit``: If ``true``, excludes the service from non-specific actions (when
  Maestro is executed without a list of services or containers as arguments);

- ``requires`` and ``wants_info``: Define hard and soft dependencies (see
  :doc:`dependencies`);

- ``lifecycle``: Service instances' lifecycle state checks, which Maestro uses
  to confirm a service instance correctly started or stopped (see
  :doc:`lifecycle_checks`);

- ``limits``: Set container limits at service scope. All service instances would
  inherit these limits;

- ``ports``: Set container ports at service scope. All service instances would
  inherit these ports;

Here's an example of a simple service with a single instance:

.. code-block:: yaml

  services:
    hello:
      image: ubuntu
      limits:
        memory: 10m
        cpu: 1
      ports:
        server: 4848
      envfile:
        - hello-base.env
        - hello-extras.env
      instances:
        hello1:
          ports:
            client: 4242
          command: "while true ; do echo 'Hello, world!' | nc -l 0.0.0.0 4242 ; done"


Service instances
--------------------------------------------------------------------------------

Each instance must, at minimum, define the *ship* its container will be placed
on (by name). Additionally, each instance may define:

- ``image``, to override the service-level image repository name, if needed
  (useful for canary deployments for example);

- ``ports``, a dictionary of port mappings, as a map of ``<port name>: <port or
  port mapping spec>`` (see :doc:`port_mapping` for port spec syntax);

- ``lifecycle``, for lifecycle state checks, which Maestro uses to confirm a
  service correctly started or stopped (see :doc:`lifecycle_checks`);

- ``volumes``, for container volume mappings, as a map of ``<source from host>:
  <destination in container>``. Each target can also be specified as a map
  ``{target: <destination>, mode: <mode>}``. ``mode`` defaults to ``rw`` for
  read-write, but can be any combination of comma-separated mode flags, like
  ``ro,Z`` or ``z,rw``;

- ``container_volumes``, a path, or list of paths inside the container to be
  used as container-only volumes with no host bind-mount. This is mostly used
  for data-containers;

- ``volumes_from``, a container or list of containers running on the same _ship_
  to get volumes from. This is useful to get the volumes of a data-container
  into an application container;

- ``envfile``: Filename, or list of filenames, of Docker environment files for
  this container. File names are relative to the Maestro environment YAML
  file's location;

- ``env``, for environment variables, as a map of ``<variable name>: <value>``
  (variables defined at the instance level override variables defined at the
  service level). ``env`` values take precedence over ``envfiles``s;

- ``privileged``, a boolean specifying whether the container should run in
  privileged mode or not (defaults to ``false``);

- ``read_only``, a boolean specifying whether the container root filesystem
  should be mount as read only or not.

- ``cap_add``, Linux capabilities to add to the container (see the documentation
  for `docker run`_;

- ``cap_drop``, Linux capabilities to drop from the container;

- ``extra_hosts``, a map of custom hostnames to IP addresses that will be added
  to the ``/etc/hosts`` for the container. Example: ``<hostname>: <ip address>``.
  You can also define extra hosts by reference to other *ships* defined in the
  Maestro environment with: ``<hostname>: {ship: <ship-name>}``. Note that the
  ship *must* be defined with an IP address (as opposed to a FQDN) for this to
  work in the containers' host file;

- ``stop_timeout``, the number of seconds Docker will wait between sending
  ``SIGTERM`` and ``SIGKILL`` (defaults to 10);

- ``limits``:

  - ``memory``, the memory limit of the container (in bytes, or with one of the
    ``k``, ``m`` or ``g`` suffixes, also valid in uppercase);

  - ``cpu``, the number of CPU shares (relative weight) allocated to the
    container;

  - ``swap``, the swap limit of the container (in bytes, or with one of the
    ``k``, ``m`` or ``g`` suffixes, also valid in uppercase);

- ``log_driver``, one of the supported log drivers, e.g. syslog or json-file;

- ``log_opt``, a set of key value pairs that provide additional logging
  parameters. E.g. the syslog-address to redirect syslog output to another
  address;

- ``command``, to specify or override the command executed by the container;

- ``net``, to specify the container's network mode (one of ``bridge`` -- the
  default, ``host``, ``container:<name|id>`` or ``none`` to disable networking
  altogether);

- ``restart``, to specify the restart policy (see :doc:`restart_policy`);

- ``dns``, to specify one (as a single IP address) or more DNS servers (as a
  list) to be declared inside the container;

- ``security_opt``, to specify additional security options to customize
  container labels, apparmor profiles, etc.

- ``ulimits``, to override the default ulimits for a container. You can either
  specify a single limit as an integer or soft/hard limits as a mapping.

- ``username``, to set the name of the user under which the container's
  processes will run.

- ``labels``, a list or a map (dictionary) of labels to set on the container.

For example:

.. code-block:: yaml

  services:
    zookeeper:
      image: zookeeper:3.4.5
      instances:
        zk-1:
          ship: vm1.ore1
          ports: {client: 2181, peer: 2888, leader_election: 3888}
          privileged: true
          read_only: true
          volumes:
            /data/zookeeper: /var/lib/zookeeper
          limits:
            memory: 1g
            cpu: 2
          labels:
            - no-relocate
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
          labels:
            - no-relocate
      lifecycle:
        running: [{type: tcp, port: client}]
    kafka:
      image: kafka:latest
      requires: [ zookeeper ]
      envfile: kafka.env
      instances:
        kafka-broker:
          ship: vm2.ore1
          ports: {broker: 9092}
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
          ulimits:
            nproc: 65535
            nofile:
              soft: 1024
              hard: 1024
      lifecycle:
        running: [{type: tcp, port: broker}]
