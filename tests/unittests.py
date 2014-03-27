#!/usr/bin/env python

import os
import unittest

from maestro import entities, maestro
from maestro.__main__ import load_config, create_parser

class EntityTest(unittest.TestCase):

    def test_get_name(self):
        self.assertEqual(entities.Entity('foo').name, 'foo')

class ServiceTest(unittest.TestCase):

    def test_get_image(self):
        service = entities.Service('foo', 'stackbrew/ubuntu:13.10')
        self.assertEqual(service.image, 'stackbrew/ubuntu:13.10')

    def test_get_image_details_basic(self):
        service = entities.Service('foo', 'stackbrew/ubuntu:13.10')
        d = service.get_image_details()
        self.assertEqual(d['repository'], 'stackbrew/ubuntu')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_notag(self):
        service = entities.Service('foo', 'stackbrew/ubuntu')
        d = service.get_image_details()
        self.assertEqual(d['repository'], 'stackbrew/ubuntu')
        self.assertEqual(d['tag'], 'latest')

    def test_get_image_details_custom_registry(self):
        service = entities.Service('foo', 'quay.io/foo/bar:13.10')
        d = service.get_image_details()
        self.assertEqual(d['repository'], 'quay.io/foo/bar')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_custom_port(self):
        service = entities.Service('foo', 'quay.io:8081/foo/bar:13.10')
        d = service.get_image_details()
        self.assertEqual(d['repository'], 'quay.io:8081/foo/bar')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_custom_port_notag_invalid(self):
        # If the registry as a non-standard port, the tag must be specified.
        # This test case validates that it is still parsed correctly, and
        # yielded the invalid result.
        service = entities.Service('foo', 'quay.io:8081/foo/bar')
        d = service.get_image_details()
        self.assertEqual(d['repository'], 'quay.io')
        self.assertEqual(d['tag'], '8081/foo/bar')


class ContainerTest(unittest.TestCase):

    def test_env_propagates_from_service(self):
        service_env = {'ENV_VAR': 'value'}
        container_env = {'OTHER_ENV_VAR': 'other-value'}
        service = entities.Service('foo', 'stackbrew/ubuntu', service_env)
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={'env': container_env})
        for k, v in service_env.items():
            self.assertIn(k, container.env)
            self.assertEqual(v, container.env[k])
        for k, v in container_env.items():
            self.assertIn(k, container.env)
            self.assertEqual(v, container.env[k])


class BaseConfigUsingTest(unittest.TestCase):

    def _get_config(self, name):
        return load_config(
            create_parser().parse_args([
                '-f',
                os.path.join(os.path.dirname(__file__),
                             'yaml/{}.yaml'.format(name))
            ])
        )

class ConductorTest(BaseConfigUsingTest):

    def test_empty_registry_list(self):
        config = self._get_config('empty_registries')
        c = maestro.Conductor(config)
        self.assertIsNot(c.registries, None)
        self.assertEqual(c.registries, [])

class ConfigTest(BaseConfigUsingTest):

    def test_yaml_parsing_test1(self):
        """Make sure the env variables are working."""
        os.environ['BAR'] = 'bar'
        config = self._get_config('test_env')
        self.assertEqual('bar', config['foo'])

if __name__ == '__main__':
    unittest.main()
