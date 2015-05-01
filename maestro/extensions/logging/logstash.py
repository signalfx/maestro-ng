# Copyright (C) 2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.

# Maestro extension that can be used for wrapping the execution of a
# long-running service with log management scaffolding, potentially sending the
# log output to a file, or through Pipestash, or both, depending on the use
# case and parameters.

import os
import random
import signal
import subprocess

from ...guestutils import get_container_name, get_service_name, get_node_list


def run_service(cmd, logtype='log', logbase=None, logtarget=None):
    """Wrap the execution of a service with the necessary logging nets.

    If logbase is provided (it is by default), log output will be redirected
    (or teed) to a file named after the container executing the service inside
    the logbase directory.

    If Redis nodes are available in the environment as referenced by the given
    logtarget, log output will be streamed via pipestash to one of the
    available node containers, chosen at random when the service starts.

    The way this is accomplished varied on whether logbase is provided or not,
    and whether Redis nodes are available:

        - if neither, log output flows to stdout and will be captured by
          Docker;
        - if logbase is provided, but no Redis nodes are available, the
          output of the service is directly redirected to the log file;
        - if logbase is not provided, but Redis nodes are available, the
          output of the service is piped to pipestash;
        - if logbase is provided and Redis nodes are available, the output
          of the service is piped to a tee that will write the log file, and
          the output of the tee is piped to pipestash.

    The whole pipeline, whatever its construct is, waits for the service to
    terminate. SIGTERM is also redirected from the parent to the service.
    """
    if type(cmd) == str:
        cmd = cmd.split(' ')

    log = logbase \
        and os.path.join(logbase, '{}.log'.format(get_container_name())) \
        or None
    if logbase and not os.path.exists(logbase):
        os.makedirs(logbase)

    redis = logtarget \
        and get_node_list(logtarget, ports=['redis'], minimum=0) \
        or None
    stdout = redis and subprocess.PIPE or (log and open(log, 'w+') or None)

    # Start the service with the provided command.
    service = subprocess.Popen(cmd, stdout=stdout,
                               stderr=subprocess.STDOUT)
    last = service

    # Connect SIGTERM to the service process.
    signal.signal(signal.SIGTERM, lambda signum, frame: service.terminate())

    if redis:
        if log:
            # Tee to a local log file.
            tee = subprocess.Popen(['tee', log], stdin=last.stdout,
                                   stdout=subprocess.PIPE)
            last.stdout.close()
            last = tee

        pipestash = subprocess.Popen(
            ['pipestash', '-t', logtype,
             '-r', 'redis://{}/0'.format(random.choice(redis)),
             '-R', 'logstash',
             '-f', 'service={}'.format(get_service_name()),
             '-S', get_container_name()],
            stdin=last.stdout)
        last.stdout.close()
        last = pipestash

    # Wait for the service to exit and return its return code.
    last.communicate()
    return service.wait()
