
Lifecycle checks
================================================================================

When controlling containers (your service instances), Maestro can
perform additional checks to confirm that the service reached the
desired lifecycle state, in addition to looking at the state of the
container itself. A common use-case of this is to check for a given
service port to become available to confirm that the application
correctly started and is accepting connections.

When starting containers, Maestro will execute all the lifecycle checks
for the ``running`` target state; all must pass for the instance to be
considered correctly up and running. Similarly, after stopping a
container, Maestro will execute all ``stopped`` target state checks.

Checks are defined via the ``lifecycle`` dictionary for each defined
instance. The following checks are available: TCP port pinging, and
script execution (using the return code). Keep in mind that if no
``running`` lifecycle checks are defined, Maestro considers the service up
as soon as the container is up and will keep going with the
orchestration play immediately.

**TCP port pinging** makes Maestro attempt to connect to the configured
port (by name), once per second until it succeeds or the ``max_wait``
value is reached (defaults to 300 seconds).

Assuming your instance declares a ``client`` named port, you can make
Maestro wait up to 10 seconds for this port to become available by doing
the following:

.. code:: yaml

  services:
    zookeeper:
      image: zookeeper:3.4.5
      ports: {client: 2181}
      lifecycle:
        running:
          - {type: tcp, port: client, max_wait: 10}

**HTTP Request** makes Maestro execute web requests to a target, once
per second until it succeeds or the ``max_wait`` value is reached
(defaults to 300 seconds).

Assuming your instance declares a ``admin`` named port that runs a
webserver, you can make Maestro wait up to 10 seconds for an HTTP
request to this port for the default path "/" to succeed by doing the
following:

.. code:: yaml

  services:
    frontend:
      image: frontend
      ports: {admin: 8080}
      lifecycle:
        running:
          - {type: http, port: admin, max_wait: 10}

Options:

- ``port``, named port for an instance or explicit numbered port
- ``host``, IP or resolvable hostname (defaults to ship.ip)
- ``match_regex``, regular expression to test response against (defaults
   to checking for HTTP 200 response code)
- ``path``, path (including querystring) to use for request (defaults to
   /)
- ``scheme``, request scheme (defaults to http)
- ``method``, HTTP method (defaults to GET)
- ``max_wait``, max number of seconds to wait for a successful response
   (defaults to 300)
- ``requests_options``, additional dictionary of options passed directly
   to python's requests.request() method (e.g. verify=False to disable
   certificate validation)

**Script execution** makes Maestro execute the given command, using the
return code to denote the success or failure of the test (a return code
of zero indicates success, as per the Unix convention). The command is
executed a certain number of attempts (defaulting to 180), with a delay
between each attempt of 1 second. For example:

.. code:: yaml

  type: exec
  command: "python my_cool_script.py"
  attempts: 30

The command's execution environment is extended with the same
environment that your running container would have, which means it
contains all the environment information about the container's
configuration, ports, dependencies, etc. You can then use Maestro guest
utility functions to easily grok that information from the environment
(in Python). See "How Maestro orchestrates and service
auto-configuration" and "Guest utils helper functions" below for more
information.

Note that the current working directory is never changed by Maestro
directly; paths to your scripts will be resolved from wherever you run
Maestro, not from where the environment YAML file lives.
