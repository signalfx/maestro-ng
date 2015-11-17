
How Maestro orchestrates and service auto-configuration
================================================================================

The orchestration performed by Maestro is two-fold. The first part is
providing a way for each container to learn about the environment they
evolve into, to discover about their peers and/or the container
instances of other services in their environment. The second part is by
controlling the start/stop sequence of services and their containers,
taking service dependencies into account.

With inspiration from Docker's _links_ feature, Maestro utilizes
environment variables to pass information down to each container. Each
container is guaranteed to get the following environment variables:

* ``DOCKER_IMAGE``: the full name of the image this container is started
  from.
* ``DOCKER_TAG``: the tag of the image this container is started from.
* ``SERVICE_NAME``: the friendly name of the service the container is an
  instance of. Note that it is possible to have multiple clusters of the
  same kind of application by giving them distinct friendly names.
* ``CONTAINER_NAME``: the friendly name of the instance, which is also
  used as the name of the container itself. This will also be the
  visible hostname from inside the container.
* ``CONTAINER_HOST_ADDRESS``: the external IP address of the host of the
  container. This can be used as the "advertised" address when services
  use dynamic service discovery techniques.

Then, for each container of each service that the container depends on,
a set of environment variables is added:

* ``<SERVICE_NAME>_<CONTAINER_NAME>_HOST``: the external IP address of the
  host of the container, which is the address the application inside the
  container can be reached with accross the network.
* For each port declared by the dependent container, a
  ``<SERVICE_NAME>_<CONTAINER_NAME>_<PORT_NAME>_PORT`` environment
  variable, containing the external, addressable port number, is
  provided.

Each container of a service also gets these two variables for each
instance of that service so it knows about its peers. It also gets the
following variable for each port defined:

* ``<SERVICE_NAME>_<CONTAINER_NAME>_<PORT_NAME>_INTERNAL_PORT``,
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
available in its ``maestro.guestutils`` module. The recommended (or
easiest) way to build this startup script is to write it in Python, and
have the Maestro package installed in your container.
