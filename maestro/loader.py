# Copyright (C) 2015 SignalFx, Inc. All rights reserved.
#
# Docker container orchestration utility.

import jinja2
import os
import sys
import yaml

from . import exceptions


class MaestroYamlConstructor(yaml.constructor.Constructor):
    """A PyYAML object constructor that errors on duplicate keys in YAML
    mappings. Because for some reason PyYAML doesn't do that since 3.x."""

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.nodes.MappingNode):
            raise yaml.constructor.ConstructorError(
                None, None,
                "expected a mapping node, but found %s" % node.id,
                node.start_mark)
        keys = set([])
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    "found duplicate key (%s)" % key, key_node.start_mark)
            keys.add(key)
        return yaml.constructor.Constructor.construct_mapping(self, node, deep)


class MaestroYamlLoader(yaml.reader.Reader, yaml.scanner.Scanner,
                        yaml.parser.Parser, yaml.composer.Composer,
                        MaestroYamlConstructor, yaml.resolver.Resolver):
    """A custom YAML Loader that uses the custom MaestroYamlConstructor."""

    def __init__(self, stream):
        yaml.reader.Reader.__init__(self, stream)
        yaml.scanner.Scanner.__init__(self)
        yaml.parser.Parser.__init__(self)
        yaml.composer.Composer.__init__(self)
        MaestroYamlConstructor.__init__(self)
        yaml.resolver.Resolver.__init__(self)


def load(filename):
    """Load a config from the given file.

    Args:
        filename (string): Path to the YAML environment description
            configuration file to load. Use '-' for stdin.

    Returns:
        A python data structure corresponding to the YAML configuration.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(filename)),
        extensions=['jinja2.ext.with_'])
    try:
        if filename == '-':
            template = env.from_string(sys.stdin.read())
        else:
            template = env.get_template(os.path.basename(filename))
    except jinja2.exceptions.TemplateNotFound:
        raise exceptions.MaestroException(
            'Environment description file {} not found!'.format(filename))
    except Exception as e:
        raise exceptions.MaestroException(
            'Error reading environment description file {}: {}!'
            .format(filename, e))

    return yaml.load(template.render(env=os.environ), Loader=MaestroYamlLoader)
