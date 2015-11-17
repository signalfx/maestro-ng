
Defining dependencies
================================================================================

Services can depend on each other (circular dependencies are not
supported though). This dependency tree instructs Maestro to start and
stop the services in an order that will respect these dependencies.
Dependent services are started before services that depend on them, and
conversly leaves of the dependency tree are stopped before the services
they depend on so that at no point in time a service may run without its
dependencies -- unless this was forced by the user with the ``-o`` flag of
course.

You can define dependencies by listing the names of dependent service
in ``requires``:

.. code:: yaml

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

Defining a dependency also makes Maestro inject environment variables
into the instances of these services that describe where the instances of
the services it depends on can be found (similarly to Docker links). See
"How Maestro orchestrates" below for more details on these variables.

You can also define "soft" dependencies that do not impact the
start/stop orders but that still make Maestro inject these variables.
This can be useful if you know your application gracefully handles its
dependencies not being present at start time, through reconnects and
retries for examples. Defining soft dependencies is done via the
``wants_info`` entry:

.. code:: yaml

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
