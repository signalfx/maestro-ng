
Port mapping
================================================================================

Maestro supports several syntaxes for specifying port mappings. Unless
the syntax supports and/or specifies otherwise, Maestro will make the
following assumptions:

* the exposed and external ports are the same (_exposed_ means the port bound to
  inside the container, _external_ means the port mapped by Docker on the host
  to the port inside the container);

* the protocol is TCP (`/tcp`);

* the external port is bound on all host interfaces using the `0.0.0.0` address.

The simplest form is a single numeric value, which maps the given TCP
port from the container to all interfaces of the host on that same port::

  # 25/tcp -> 0.0.0.0:25/tcp
  ports: {smtp: 25}

If you want UDP, you can specify so::

  # 53/udp -> 0.0.0.0:53/udp
  ports: {dns: 53/udp}

If you want a different external port, you can specify a mapping by
separating the two port numbers by a colon::

  # 25/tcp -> 0.0.0.0:2525/tcp
  ports: {smtp: "25:2525"}

Similarly, specifying the protocol (they should match!)::

  # 53/udp -> 0.0.0.0:5353/udp
  ports: {dns: "53/udp:5353/udp"}

You can also use the dictionary form for any of these::

  ports:
    # 25/tcp -> 0.0.0.0:25/tcp
    smtp:
      exposed: 25
      external: 25

    # 53/udp -> 0.0.0.0:5353/udp
    dns:
      exposed: 53/udp
      external: 5353/udp

If you need to bind to a specific interface or IP address on the host,
you need to use the dictionary form::

  # 25/tcp -> 192.168.10.2:25/tcp
  ports:
    smtp:
      exposed: 25
      external: [ 192.168.10.2, 25 ]


    # 53/udp -> 192.168.10.2:5353/udp
    dns:
      exposed: 53/udp
      external: [ 192.168.10.2, 5353/udp ]

Note that YAML supports references, which means you don't have to repeat
your _ship_'s IP address if you do something like this::

  ship:
    demo: {ip: &demoip 192.168.10.2, docker_port: 4243}

  services:
    ...
      ports:
        smtp:
          exposed: 25/tcp
          external: [ *demoip, 25/tcp ]

Port mappings and named ports
--------------------------------------------------------------------------------

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
