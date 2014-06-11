ChangeLog
=========

* Compatibility improvements with docker-py mainline and Docker versions
* Parallelization of orchestration plays, respecting dependency and
  execution order but doing as much work as possible in parallel

Maestro 0.1.8.1
---------------

_May 30th, 2014_

* Fixed link variable naming for port names containing dashes

Maestro 0.1.8
-------------

_May 28th, 2014_

* Support for custom image command
* Implement restart Maestro command
* Add support for "soft" dependencies through `wants_info`. Containers
  get the link environment variable, but the dependency has no impact on
  the start/stop orders
* Improve guestutils service matching by including a list of each
  service's instances as a `<service_name>_INSTANCES` environment
  variable

Maestro 0.1.7.1
---------------

_April 28th, 2014_

* Support for memory and cpu shares limits
* Fix image:tag parsing when custom registries are involved
* Improve Jinja2 setup to include filesystem loader and with extension
  for more flexible and complex Jinja2 templating capabalities

Maestro 0.1.7
-------------

_April 9th, 2014_

* Use `docker-py` 0.3.x
* Deep expend of environment variables list values
* Pre-processing of the YAML environment description through Jinja2
  templating
* Correctly pass-in specified volumes to create_container() in case the
  image's Dockerfile didn't define them
* Support service-level environment variables that trickle down to all
  instances of the service
* Documentation improvements, flake8 and unit-test fixes
* Support for privileged containers
* Support for timeout on container stop


Maestro 0.1.6
-------------

_January 30th, 2014_

* Fullstatus output now shows port numbers
* Improved port specification syntax for more precise control about
  internal and exposed ports and interfaces
* Maestro extension for logstash-based logging scaffolding
* Docker and `docker-py` compatibility fixes (Id/ID, `docker-py` API
  tweaks)
* Show image being pulled when creating a container

Maestro 0.1.5
-------------

_January 16th, 2014_

* Fix download indicator for compatibility with Docker 0.7.x
* Renamed 'status' command to 'fullstatus', and implemented new, faster
  'status' command that only looks at the state of the containers, not
  the services themselves
* Sort containers before building dependencies to try to keep them a bit
  more organized without breaking the dependency order
* Don't use white in commands output, just bold text
* Compatibility fixes with docker-py 0.2.3
* The 'logs' command now streams logs instead of dumping them, until you
  hit ^C to stop
* Implement registry login before pull, when needed and if possible
* Renamed 'scores' to 'plays', makes more sense
* Updates to the 'logs' command:
  - by default, the 'logs' command now dumps the full log and doesn't
    stream/follow
  - with the '-F' flag, logs will be followed
  - the new '-n N' flag will only show the last N lines of the log, but
    it doesn't work with streaming logs
* Setup for Travis-CI build with flake8 validation

Maestro 0.1.4
-------------

_December 9th, 2013_

* Optimize status score by not polling the service if the container is
  down (it can't be running then)
* Add guest helper function to retrieve the internal IP address of the
  container

Maestro 0.1.3
-------------

_December 6th, 2013_

* Download progress indicator when pulling an image
* Correctly exit with a non-zero exit code on error through better
  exception handling and reporting
* Removed the useless -v/--verbose option
* Bugfixes and code cleanups

Maestro 0.1.2
-------------

_November 25th, 2013_

* Seamless understanding of parameters as either containers or services
  for all operations
* Independent control of only the containers and/or services provided on
  the command-line without affecting dependencies or dependents with the
  new -o flag

Maestro 0.1.1
-------------

_November 25th, 2013_

* Improved output display
* Correctly show already up/already down containers when starting/stopping
  services and containers
* Add documentation for the guest utils functions
* Automatic pulling of missing images

Maestro 0.1.0
-------------

_November 21st, 2013_

Initial Maestro version with the basic orchestration features
implemented. Environment description, dependency management and basic
start/stop orchestration scores.

Maestro 0.1.0 is also the first version that provides the guestutils
helper functions.
