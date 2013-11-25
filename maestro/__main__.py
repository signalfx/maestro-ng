#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import argparse
import logging
import sys
import yaml

from . import maestro

def main(args):
    commands = ['status', 'start', 'stop', 'clean', 'logs']
    parser = argparse.ArgumentParser(prog='maestro',
                                     description='Docker container orchestrator.')
    parser.add_argument('command', nargs='?',
                        choices=commands,
                        default='status',
                        help='orchestration command to execute')
    parser.add_argument('thing', nargs='*',
                        help='container(s) or service(s) to act on')
    parser.add_argument('-f', '--file', nargs='?', default='-', metavar='FILE',
                        help='read environment description from FILE (use - for stdin)')
    parser.add_argument('-c', '--completion', metavar='CMD',
                        help='list commands, services or containers in environment based on CMD')
    parser.add_argument('-v', '--verbose', action='store_const',
                        const=logging.DEBUG, default=logging.INFO,
                        help='be verbose; show debugging messages')
    parser.add_argument('-r', '--refresh-images', action='store_const',
                        const=True, default=False,
                        help='force refresh of container images from registry')
    parser.add_argument('-o', '--only', action='store_const',
                        const=True, default=False,
                        help='only affect the selected container or service')
    options = parser.parse_args(args)

    stream = options.file == '-' and sys.stdin or open(options.file)
    config = yaml.load(stream)
    stream.close()

    logging.basicConfig(stream=sys.stdout, level=options.verbose,
            format='%(message)s')

    # Shutup urllib3, wherever it comes from.
    logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARN)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARN)

    c = maestro.Conductor(config)
    if options.completion is not None:
        args = filter(lambda x: not x.startswith('-'), options.completion.split(' '))
        if len(args) == 2:
            print ' '.join([x for x in commands if x.startswith(args[1])])
        elif len(args) == 3:
            if args[1] != 'logs':
                print ' '.join([x for x in c.services if x.startswith(args[2])])
            else:
                print ' '.join([x for x in c.containers if x.startswith(args[2])])
        return

    try:
        getattr(c, options.command)(services=set(options.thing),
                                    refresh_images=options.refresh_images)
    except KeyError, e:
        logging.error('Service or container {} does not exist!\n'.format(e))
        sys.exit(1)

if __name__ == '__main__':
    main(sys.argv[1:])
