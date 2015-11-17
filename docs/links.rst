
.. _Docker Links: http://docs.docker.io/en/latest/use/working_with_links_names/

Links
================================================================================

Maestro also supports defining links to link same-host containers together via
Docker's Links feature. Read more about `Docker Links`_ to learn more. Note that
the format of the environment variables is not the same as the ones Maestro
inserts into the container's environment, so software running inside the
containers needs to deal with that on its own.

Defining links is done through the instance-level ``links`` section, with
each link defined as a child in the format ``name: alias``:

.. code:: yaml

  services:
    myservice:
      image: ...
      instances:
        myservice-1:
          # ...
          links:
            mongodb01: db
