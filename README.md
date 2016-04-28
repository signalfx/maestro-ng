# MaestroNG

[![Build Status](https://travis-ci.org/signalfx/maestro-ng.png)](https://travis-ci.org/signalfx/maestro-ng) [![Docs](https://readthedocs.org/projects/maestro-ng/badge/?version=latest)](http://maestro-ng.readthedocs.io)

_MaestroNG is an orchestrator of Docker-based, multi-hosts environments._

The original [Maestro](http://github.com/toscanini/maestro) was developed
as a single-host orchestrator for Docker-based deployments. Given the
state of Docker at the time of its writing, it was a great first step
towards orchestration of deployments using Docker containers as the unit
of application distribution.

Docker having made significant advancements since then, deployments and
environments spanning across several hosts are becoming more and more
common and are in the need for some orchestration.

Based off ideas from the original Maestro and taking inspiration from
Docker's _links_ feature, MaestroNG makes the deployment and control of
complex, multi-host environments using Docker containers possible and
easy to use. Maestro of course supports declared dependencies between
services and makes sure to honor those during environment bring up.

## What is Maestro?

MaestroNG is, for now, a command-line utility that allows for
automatically managing the orchestrated deployment and bring up of a set
of service instance containers that compose an environment on a set of
target host machines.

Each host machine is expected to run a Docker daemon. Maestro will then
contact the Docker daemon of each host in the environment to figure out
the status of the environment and what actions to take based on the
requested command.

## Dependencies

MaestroNG requires Docker 0.6.7 or newer on the hosts as it makes use of
the container naming feature and bug fixes in NAT port forwarding.

You'll also need the following Python modules, although these will be
automatically installed by `setuptools` if you follow the instructions
below.

* A recent [docker-py](http://github.com/dotcloud/docker-py)
* PyYAML (you may need to install this manually, e.g. `apt-get install python-yaml`)
* Jinja2
* Python Requests
* `bgtunnel`
* `six`

If you plan on using the HipChat auditor, you'll also need
`python-simple-hipchat`.

## Installation

Maestro is distributed on the Python Package Index. You can install
Maestro via _Pip_:

```
$ pip install --user --upgrade maestro-ng
```

If you want the bleeding edge, you can install directly from the Git
repository:

```
$ pip install --user --upgrade git+git://github.com/signalfx/maestro-ng
```

### Note for MacOS users

The above command may fail if you installed Python and `pip` via
Homebrew, usually with the following error message:

```
error: can't combine user with prefix, exec_prefix/home, or install_(plat)base
```

This is because the Homebrew formula for `pip` configures distutils with
an installation prefix, and this cannot be combined with the use of the
`--user` flag, as describe in https://github.com/Homebrew/homebrew/wiki/Homebrew-and-Python#note-on-pip-install---user.

If you encounter this problem, simply install the package without the
`--user` flag:

```
$ pip install --upgrade git+git://github.com/signalfx/maestro-ng
```

### Use as a Docker container

First, build your maestro-ng image using :
```
docker build -t maestro-ng .
```

Then say you have a maestro-ng configuration named /fu/bar/myconf.yml

If you want to start this on a docker host without install python and its pip modules :
```
docker run --rm -t -i -v /fu/bar/myconf.yml:/maestro.yaml maestro-ng <start/stop/status/clean>
```
or, if the myconf.yml is in the current dir :
```
docker run --rm -t -i -v $(pwd)/myconf.yml:/maestro.yaml maestro-ng <start/stop/status/clean>
```

## Documentation

The [MaestroNG documentation](http://maestro-ng.readthedocs.io/) is
available on ReadTheDocs. For a overview of recent changes, see the
[ChangeLog](docs/changes.md).

## License

MaestroNG is licensed under the Apache License, Version 2.0. See LICENSE for
full license text.
