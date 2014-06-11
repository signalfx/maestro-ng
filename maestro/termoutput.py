# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import threading
import sys


def _default_printer(s):
    sys.stdout.write(s)
    sys.stdout.write('\033[K\r')
    sys.stdout.flush()


class OutputManager:
    """Multi-line concurrently updated output.

    Manages a multi-line, position-indexed output that is concurrently updated
    by multiple threads. The total number of expected lines must be known in
    advance so that terminal space can be provisioned.

    Output is automatically synchronized between the threads, each individual
    thread operating using an OutputFormatter that targets a specific,
    positioned line on the output block.
    """

    def __init__(self, lines):
        self._lines = lines
        self._formatters = {}
        self._lock = threading.Lock()

    def start(self):
        self._print('{}\033[{}A'.format('\n' * self._lines, self._lines))

    def get_formatter(self, pos, prefix=None):
        f = OutputFormatter(lambda s: self._print(s, pos), prefix=prefix)
        self._formatters[pos] = f
        return f

    def end(self):
        self._print('\033[{}B'.format(self._lines))

    def _print(self, s, pos=None):
        with self._lock:
            if pos:
                sys.stdout.write('\033[{}B'.format(pos))
            sys.stdout.write('\r{}\033[K\r'.format(s))
            if pos:
                sys.stdout.write('\033[{}A'.format(pos))
            sys.stdout.flush()


class OutputFormatter:
    """Output formatter for nice, progressive terminal output.

    Manages the output of a progressively updated terminal line, with "in
    progress" labels and a "committed" base label.
    """

    def __init__(self, printer=_default_printer, prefix=None):
        self._printer = printer
        self._committed = prefix

    def commit(self, s=None):
        if self._committed and s:
            self._committed = '{} {}'.format(self._committed, s)
        elif not self._committed and s:
            self._committed = s
        self._printer(self._committed)

    def pending(self, s):
        if self._committed and s:
            self._printer('{} {}'.format(self._committed, s))
        if not self._committed and s:
            self._printer(s)
