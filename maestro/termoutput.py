# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.

import datetime
import threading
import re
import sys


STRIP_COLORS = re.compile(r'\033\[[0-9;]+m')


def color(n, s, bold=True):
    return '\033[{};{}m{}\033[;0m'.format(n, '1' if bold else '', s)


def green(s):
    return color(32, s)


def blue(s):
    return color(36, s, bold=False)


def red(s):
    return color(31, s)


def _default_printer(s):
    sys.stdout.write(s)
    sys.stdout.write('\033[K\r')
    sys.stdout.flush()


def time_ago(t, base=None):
    """Return a string representing the time delta between now and the given
    datetime object.

    Args:
        t (datetime.datetime): A UTC timestamp as a datetime object.
        base (datetime.datetime): If not None, the time to calculate the delta
            against.
    """
    if not t:
        return ''

    delta = (base or datetime.datetime.utcnow()) - t
    duration = int(delta.total_seconds())
    days, seconds = delta.days, delta.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = (seconds % 60)

    if duration < 0:
        return ''
    if duration < 60:
        return ' for {}s'.format(duration)
    if duration < 3600:
        return ' for {}m{}s'.format(minutes, seconds)
    if duration < 86400:
        return ' for {}h{}m'.format(hours, minutes)
    # Biggest step is by day.
    return ' for {}d{}h{}m'.format(days, hours, minutes)


class OutputManager:
    """Multi-line concurrently updated output.

    Manages a multi-line, position-indexed output that is concurrently updated
    by multiple threads. The total number of expected lines must be known in
    advance so that terminal space can be provisioned.

    Output is automatically synchronized between the threads, each individual
    thread operating using an OutputFormatter that targets a specific,
    positioned line on the output block.
    """

    def __init__(self, lines, out=sys.stdout):
        self._lines = lines
        self._out = out
        self._formatters = {}
        self._lock = threading.Lock()

    def get_formatter(self, pos, prefix=None):
        f = OutputFormatter(lambda s: self._print(s, pos), prefix=prefix)
        self._formatters[pos] = f
        return f

    def start(self):
        if not self._out.isatty():
            return
        self._print('{}\033[{}A'.format('\n' * self._lines, self._lines))

    def end(self):
        if not self._out.isatty():
            return
        self._print('\033[{}B'.format(self._lines))

    def _print(self, s, pos=None):
        if not self._out.isatty():
            s = STRIP_COLORS.sub('', s)
            self._out.write(s + '\n')
            self._out.flush()
            return

        with self._lock:
            if pos:
                self._out.write('\033[{}B'.format(pos))
            self._out.write('\r{}\033[K\r'.format(s))
            if pos:
                self._out.write('\033[{}A'.format(pos))
            self._out.flush()


class OutputFormatter:
    """Output formatter for nice, progressive terminal output.

    Manages the output of a progressively updated terminal line, with "in
    progress" labels and a "committed" base label.
    """

    def __init__(self, printer=_default_printer, prefix=None):
        self._printer = printer
        self._prefix = prefix
        self._committed = prefix

    def commit(self, s=None):
        """Output, and commit, a string at the end of the currently committed
        line."""
        if self._committed and s:
            self._committed = '{} {}'.format(self._committed, s)
        elif not self._committed and s:
            self._committed = s
        self._printer(self._committed)

    def pending(self, s):
        """Output a temporary message at the end of the currently committed
        line."""
        if self._committed and s:
            self._printer('{} {}'.format(self._committed, s))
        if not self._committed and s:
            self._printer(s)

    def reset(self):
        """Reset the line to its base, saved prefix."""
        self._committed = self._prefix
        self.commit()
