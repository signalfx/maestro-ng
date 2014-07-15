#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

import argparse
import jinja2
import logging
import sys
import os
import yaml

from . import exceptions, maestro
from . import name, version

# Define the commands
ACCEPTED_COMMANDS = ['status', 'fullstatus', 'start', 'stop', 'restart',
                     'logs', 'deptree']
DEFAULT_MAESTRO_FILE = 'maestro.yaml'


def load_config_from_file(filename):
    """Load a config from a string.

    Args:
        filename: A string filename of a yaml maestro config. A '-' means
            stdin.

    Returns:
        A python data structure corresponding to the yaml string. A proper
        maestro config will likely return a dict.
    """
    if filename == '-':
        template = jinja2.Template(sys.stdin.read())
    else:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.dirname(filename)),
            extensions=['jinja2.ext.with_'])
        try:
            template = env.get_template(os.path.basename(filename))
        except jinja2.exceptions.TemplateNotFound:
            raise exceptions.MaestroException(
                'Environment description file {} not found!'.format(filename))
        except:
            raise exceptions.MaestroException(
                'Error reading environment description file {}!'.format(
                    filename))

    return yaml.load(template.render(env=os.environ))


def create_parser():
    parser = argparse.ArgumentParser(prog=name, description=(
        '{} v{}, Docker container orchestrator.'.format(
            name.title(), version)))
    parser.add_argument('command', nargs='?',
                        choices=ACCEPTED_COMMANDS,
                        default='status',
                        help='orchestration command to execute')
    parser.add_argument('things', nargs='*', metavar='thing',
                        help='container(s) or service(s) to act on')
    parser.add_argument('-f', '--file', nargs='?', metavar='FILE',
                        default=DEFAULT_MAESTRO_FILE,
                        help=('read environment description from FILE ' +
                              '(use - for stdin)'))
    parser.add_argument('-c', '--completion', metavar='CMD',
                        help=('list commands, services or containers in ' +
                              'environment based on CMD'))
    parser.add_argument('-r', '--refresh-images', action='store_const',
                        const=True, default=False,
                        help='force refresh of container images from registry')
    parser.add_argument('-F', '--follow', action='store_const',
                        const=True, default=False,
                        help='follow logs as they are generated')
    parser.add_argument('-n', metavar='LINES', default=15,
                        help='Only show the last LINES lines for logs')
    parser.add_argument('-o', '--only', action='store_const',
                        const=True, default=False,
                        help='only affect the selected container or service')
    parser.add_argument('-v', '--version', action='version',
                        version='{}-{}'.format(name, version),
                        help='show program version and exit')
    return parser


def main(args=None, config=None):
    options = create_parser().parse_args(args)

    if config is None:
        config = load_config_from_file(options.file)

    # Shutup urllib3, wherever it comes from.
    (logging.getLogger('requests.packages.urllib3.connectionpool')
            .setLevel(logging.WARN))
    (logging.getLogger('urllib3.connectionpool')
            .setLevel(logging.WARN))

    c = maestro.Conductor(config)
    if options.completion is not None:
        args = filter(lambda x: not x.startswith('-'),
                      options.completion.split(' '))
        if len(args) == 2:
            prefix = args[1]
            choices = ACCEPTED_COMMANDS
        elif len(args) >= 3:
            prefix = args[len(args)-1]
            choices = c.services + c.containers
        else:
            return 0

        print(' '.join(filter(lambda x: x.startswith(prefix), set(choices))))
        return 0

    try:
        options.things = set(options.things)
        getattr(c, options.command)(**vars(options))
    except exceptions.MaestroException as e:
        sys.stderr.write('{}\n'.format(e))
        return 1
    except KeyboardInterrupt:
        return 1


if __name__ == '__main__':
    sys.exit(main())
