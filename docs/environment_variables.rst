
Passing extra environment variables
================================================================================

You can pass in or override arbitrary environment variables by providing
a dictionary of environment variables key/value pairs. This can be done
both at the service level and the container level; the latter taking
precedence:

.. code-block:: yaml

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

Additionally, Maestro will automatically expand all levels of YAML lists
in environment variable values. The following are equivalent:

.. code-block:: yaml

  env:
    FOO: This is a test
    BAR: [ This, [ is, a ], test ]

This becomes useful when used in conjunction with YAML references to
build more complex environment variable values:

.. code-block:: yaml

  _globals:
    DEFAULT_JVM_OPTS: &jvmopts [ '-Xms500m', '-Xmx2g', '-showversion', '-server' ]

  ...

  env:
    JVM_OPTS: [ *jvmopts, '-XX:+UseConcMarkSweep' ]

Examples of Docker images with Maestro orchestration
--------------------------------------------------------------------------------

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
