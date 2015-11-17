
MaestroNG, an orchestrator of Docker-based deployments
================================================================================

MaestroNG is an orchestrator of Docker-based, multi-hosts environments.
Working from a description of your environment, MaestroNG offers
service-level and container-level controls that rely on Maestro's
understanding of your declared service dependencies, and placement of
your containers in your fleet of hosts.

Maestro aims at being simple to use whether you are controlling a few
containers in a local virtual machine, or hundreds of containers spread
across as many hosts.

The orchestration features of Maestro obviously rely on the
collaboration of the Docker containers that you are controlling with
Maestro. Maestro basically takes care of two things:

#. Controlling the start (and stop) order of services during environment
   bring up and tear down according to the defined dependencies between
   services.
#. Passing extra environment variables to each container to pass all the
   information it may need to operate in that environment, in particular
   information about its dependencies.

The most common way to integrate your application with Maestro is to
make your container's entrypoint a simple Python init script that acts
as the glue between Maestro, the information that it passes through the
container's environment, and your application. To make this easier to
write and put together, Maestro provides a set of [Guest
functions](guest-functions.md) that know how to grok this environment
information.

User Guide
--------------------------------------------------------------------------------

This part of the documentation focuses on step-by-step instructions for getting
the most out of MaestroNG.

.. toctree::
   :maxdepth: 2

   environment
   dependencies
   port_mapping
   volume_bindings
   lifecycle_checks
   restart_policy
   orchestration
   links
   registries
   environment_variables
