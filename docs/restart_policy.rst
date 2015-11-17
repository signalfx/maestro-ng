
Restart policy
================================================================================

Since version 1.2 docker allows to define the restart policy of a
container when it stops. The available policies are:

- ``restart: no``, the default. The container is not restarted;
- ``restart: always``: the container is _always_ restarted, regardless
      of its exit code;
- ``restart: on-failure``: the container is restarted if it exits with a
      non-zero exit code.

You can also specify the number of maximum retries for restarting the
container before giving up:

.. code-block:: yaml

  restart:
    name: on-failure
    retries: 3

Or as a single string (similar to Docker's command line option):

.. code-block:: yaml

  restart: "on-failure:3"
