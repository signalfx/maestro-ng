# Copyright (C) 2013-2014 SignalFuse, Inc.
# Copyright (C) 2015-2019 SignalFx, Inc.
#
# Docker container orchestration utility.

from docker.utils import parse_env_file
import os
import six


def _env_list_expand(elt):
    return type(elt) != list and elt \
        or ' '.join(map(_env_list_expand, elt))


def build(base_path, *args):
    """Constructs an environment dictionary from the given list of sources. The
    sources may be strings, representing filenames of Docker envfiles to be
    loaded (in the context of the given base_path); they may be lists of
    sources (recursively), or they may be dictionaries of values to add to the
    environment. Sources are consumed in order to offer reliable overrides."""
    env = {}
    for arg in filter(None, args):
        if isinstance(arg, six.string_types):
            envfile = os.path.join(base_path, arg)
            env.update(parse_env_file(envfile))
        elif type(arg) == list:
            env.update(build(base_path, *arg))
        elif type(arg) == dict:
            env.update(arg)
            continue
        else:
            raise ValueError('unhandled env type {}'.format(type(arg)))

    for k, v in env.items():
        if type(v) == list:
            env[k] = _env_list_expand(v)

    return env
