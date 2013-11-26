ChangeLog
=========

* Removed the useless -v/--verbose option
* Implemented properly typed and defined exceptions that allow for
  correct error reporting and non-zero exit codes when necessary

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
