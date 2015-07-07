# Usage

Once installed, Maestro is available both as a library through the
`maestro` package and as an executable. To run Maestro, simply execute
`maestro`. Note that if you didn't install Maestro system-wide, you can
still run it with the same commands as long as your `PYTHONPATH`
contains the path to your `maestro-ng` repository clone and using
`python -m maestro ...`.

```
$ maestro -h
usage: maestro [-h] [-f FILE] [-v]
               {status,pull,start,stop,restart,logs,deptree} ...

Maestro, Docker container orchestrator.

positional arguments:
  {status,pull,start,stop,restart,logs,deptree}
    status              display container status
    pull                pull images from repository
    start               start services and containers
    stop                stop services and containers
    restart             restart services and containers
    logs                show logs from a container
    deptree             show the dependency tree
    complete            shell auto-completion helper

optional arguments:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  read environment description from FILE (use - for
                        stdin, defaults to ./maestro.yaml)
  -v, --version         show program version and exit
```

You can then get help on each individual command with:

```
$ maestro start -h
usage: maestro start [-h] [-c LIMIT] [-d] [-i] [-r] [thing [thing ...]]

Start services and containers

positional arguments:
  thing                 container(s) or service(s) to display

optional arguments:
  -h, --help            show this help message and exit
  -c LIMIT, --concurrency LIMIT
                        limit how many containers can be acted on at the same
                        time to LIMIT
  -d, --with-dependencies
                        include dependencies
  -i, --ignore-dependencies
                        ignore dependency order
  -r, --refresh-images  force refresh of container images from registry
```

By default, Maestro will read the environment description configuration
from the `maestro.yaml` file in the current directory. You can override
this with the `-f` flag to specify the path to the environment
configuration file. Additionally, you can use `-` to read the
configuration from `stdin`. The following commands are identical:

```
$ maestro status
$ maestro -f maestro.yaml status
$ maestro -f - status < maestro.yaml
```

The first positional argument is a command you want Maestro to execute.
The available commands are `status`, `start`, `stop`, `restart`, `logs`
and `deptree`. They should all be self-explanatory.

Most commands operate on one or more "things", which can be services or
instances, by name. When passing service names, Maestro will
automatically expand those to their corresponding list of instances. The
`logs` command is the only one that operates on strictly one container
instance.

## Impact of defined dependencies on orchestration order

One of the main features of Maestro is its understand of dependencies
between services. When Maestro carries out an orchestration action,
dependencies are always considered unless the `-i |
--ignore-dependencies` flag is passed.

**But Maestro will only respect the dependencies to other services and
containers that the current orchestration action includes.** If you want
Maestro to automatically include the dependencies of the services or
containers you want to act on in the orchestration that will be carried
out, you must pass the `-d | --with-dependencies` flag!

For example, assuming we have two services, ZooKeeper (`zookeeper`) and
Kafka (`kafka`). Kafka depends on ZooKeeper:

```
# Starts Kafka and only Kafka:
$ maestro start kafka

# Starts ZooKeeper, then Kafka:
$ maestro start -d kafka
# Which is equivalent to:
$ maestro start kafka zookeeper

# Starts ZooKeeper and Kafka at the same time (includes dependencies but
# ignores dependency order constraints):
$ maestro start -d -i kafka
```
