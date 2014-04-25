#!/usr/bin/env python

import os
import unittest

from maestro import entities, exceptions, maestro, lifecycle
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

    def test_get_image_details_custom_port_notag(self):
        service = entities.Service('foo', 'quay.io:8081/foo/bar')
        d = service.get_image_details()
        self.assertEqual(d['repository'], 'quay.io:8081/foo/bar')
        self.assertEqual(d['tag'], 'latest')


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


class LifecycleHelperTest(unittest.TestCase):

    def _get_container(self):
        ship = entities.Ship('ship', 'ship.ip')
        service = entities.Service('foo', 'stackbrew/ubuntu')
        return entities.Container('foo1', ship, service,
            config={'ports': {'server': '4242/tcp', 'data': '4243/udp'}})

    def test_parse_checker_exec(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'exec', 'command': 'exit 1'})
        self.assertIsNot(c, None)
        self.assertIsInstance(c, lifecycle.ScriptExecutor)
        self.assertEqual(c.command, 'exit 1')

    def test_parse_checker_tcp(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'tcp', 'port': 'server'})
        self.assertIsInstance(c, lifecycle.TCPPortPinger)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.attempts, lifecycle.TCPPortPinger.DEFAULT_MAX_WAIT)

    def test_parse_checker_tcp(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'tcp', 'port': 'server', 'max_wait': 2})
        self.assertIsInstance(c, lifecycle.TCPPortPinger)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.attempts, 2)

    def test_parse_checker_tcp_unknown_port(self):
        container = self._get_container()
        self.assertRaises(exceptions.InvalidLifecycleCheckConfigurationException,
            lifecycle.LifecycleHelperFactory.from_config,
            container, {'type': 'tcp', 'port': 'test-does-not-exist'})

    def test_parse_checker_tcp_invalid_port(self):
        container = self._get_container()
        self.assertRaises(exceptions.InvalidLifecycleCheckConfigurationException,
            lifecycle.LifecycleHelperFactory.from_config,
            container, {'type': 'tcp', 'port': 'data'})

    def test_parse_unknown_checker_type(self):
        self.assertRaises(KeyError,
            lifecycle.LifecycleHelperFactory.from_config,
            self._get_container(), {'type': 'test-does-not-exist'})

if __name__ == '__main__':
    unittest.main()
