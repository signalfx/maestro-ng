
Volume bindings
================================================================================

Volume bindings are specified in a way similar to ``docker-py`` and
Docker's expected format, and the ``mode`` (read-only 'ro', or read-write
'rw') can be specified for each binding if needed. Volume bindings
default to being read-write.

.. code:: yaml

  volumes:
    # This will be a read-write binding
    /on/the/host: /inside/the/container

    # This will be a read-only binding
    /also/on/the/host/:
      target: /inside/the/container/too
      mode: ro

Note that it is currently not possible to bind-mount the same host
location into two distinct places inside the container as this is not
supported by ``docker-py`` (it's a dictionary keyed on the host location).

Container-only volumes can be specified with the ``container_volumes``
setting on each instance, as a path or list of paths:

  container_volumes:
    - /inside/the/container/1
    - /inside/the/container/2

Finally, you can get the volumes of one or more containers into a
container with the ``volumes_from`` feature of Docker, as long as the
containers run on the same ship:

.. code:: yaml

  # other1 and other2 run on the same ship as this container
  volumes_from: [ other1, other2 ]
