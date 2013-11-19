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
    parser = argparse.ArgumentParser(description='Docker container orchestrator')
    parser.add_argument('command', nargs='?',
                        choices=['status', 'start', 'stop', 'clean'],
                        default='status',
                        help='Orchestration command to execute')
    parser.add_argument('services', nargs='*',
                        help='Service(s) to affect')
    parser.add_argument('-f', '--file', nargs='?', default='-', metavar='FILE',
                        help='Read environment description from FILE (use - for stdin)')
    parser.add_argument('-v', '--verbose', action='store_const',
                        const=logging.DEBUG, default=logging.INFO,
                        help='Be verbose')
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
    getattr(c, options.command)(set(options.services))

if __name__ == '__main__':
    main(sys.argv[1:])
