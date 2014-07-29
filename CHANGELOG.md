ChangeLog
=========

* Docker Links support (#21)

Maestro 0.2.2
-------------

_July 22nd, 2014_

* Provide no-tty output without ANSI escape codes (output still looks a
  bit funky, but at least it's not riddle with unreadable escape codes)
* Fix "time ago" calculation that shows hours as days
* Correctly bubble up orchestration errors and exit with a non-zero
  returncode
* Fix install requirements when installing through setup.py (which pip
  does by default)

Maestro 0.2.1
-------------

_July 22nd, 2014_

* New pluggable audit trail functionality to send orchestration commands
  and results notifications to audit trail targets. Currently supports
  HipChat (via python-simple-hipchat) and log file
* Fix status orchestration play to not enforce dependency order as it's
  useless and slows it down
* Show how long a container has been up or down for

Maestro 0.2.0
-------------

_July 21st, 2014_

This release warrants jumping to the 0.2.x series as the extent of the
changes is significant and it contains some potentially breaking changes
in usage (not in the YAML format though).

* Major rework of the argument parser; each command now has its own
  subparser with appropriate arguments; one downside is that Maestro can
  now longer default to the 'status' command when no command is
  specified
* Maestro no longer assumes dependencies should be included in an
  orchestration play. Use `-d` or `--with-dependencies` to automatically
  include the dependencies of the given services/containers (#50)
* It is now possible to ignore the dependency order during an
  orchestration play by passing `-i` or `--ignore-dependencies` to the
  start, stop or restart commands
* Orchestration plays can now execute container operations in parallel,
  respecting the dependency order as needed and/or as requested.
  Additionally, a maximum concurrency limit can be specified with `-c`
  or `--concurrency-limit` to restrict the number of containers that can
  be acted upon at the same time. This can be used to implement rolling
  restarts for example
* Add `-v` / `--version` flag to show Maestro version
* New `deptree` commands that shows the dependency tree of each provided
  service or container (supports `-r` / `--recursive` to include
  duplicate indirect dependencies)
* Removed `fullstatus` command, replaced with `status -F`.
* Compatibility improvements with docker-py mainline and Docker versions
* Dropped support for `docker_endpoint` in ship configuration
* SSH tunneling support via `bgtunnel` on-demand SSH tunnels (#35, #44)
* Maestro now reads a maestro.yaml file from the current working
  directory instead of stdin by default. `-f -` can still be used to
  read from stdin (#47)
* Include workaround for Python multiprocessing bug in Python < 2.7.5
  (#48)
* Implement simple 'sleep' lifecycle check that simply sleeps for the
  given amount of time
* Changed `cmd` to `command` in YAML instance spec. `cmd` is still
  accepted but deprecated and will be removed in the next release (part
  of #39)

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
