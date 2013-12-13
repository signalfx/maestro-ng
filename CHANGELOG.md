ChangeLog
=========

* Fix download indicator for compatibility with Docker 0.7.x
* Renamed 'status' command to 'fullstatus', and implemented new, faster
  'status' command that only looks at the state of the containers, not
  the services themselves
* Sort containers before building dependencies to try to keep them a bit
  more organized without breaking the dependency order
* Don't use white in commands output, just bold text
* Compatibility fixes with docker-py 0.2.3

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
