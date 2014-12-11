#!/usr/bin/env python

import os
import unittest

from maestro import entities, exceptions, maestro, lifecycle
from maestro.__main__ import load_config_from_file, create_parser


class EntityTest(unittest.TestCase):

    def test_get_name(self):
        self.assertEqual(entities.Entity('foo').name, 'foo')


class ShipTest(unittest.TestCase):

    def test_simple_ship(self):
        ship = entities.Ship('foo', '10.0.0.1')
        self.assertEqual(ship.name, 'foo')
        self.assertEqual(ship.ip, '10.0.0.1')
        self.assertEqual(ship.endpoint, '10.0.0.1')

    def test_ship_endpoint(self):
        ship = entities.Ship('foo', '10.0.0.1', '192.168.10.1')
        self.assertEqual(ship.name, 'foo')
        self.assertEqual(ship.ip, '10.0.0.1')
        self.assertEqual(ship.endpoint, '192.168.10.1')
        self.assertTrue(ship.endpoint in ship.backend.base_url)


class ServiceTest(unittest.TestCase):

    def test_get_image(self):
        service = entities.Service('foo', 'stackbrew/ubuntu:13.10')
        self.assertEqual(service.image, 'stackbrew/ubuntu:13.10')

class ContainerTest(unittest.TestCase):

    def test_image_propagates_from_service(self):
        service = entities.Service('foo', 'stackbrew/ubuntu:13.10')
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={})
        self.assertEqual(container.image, service.image)

    def test_get_image_details_basic(self):
        service = entities.Service('foo', 'stackbrew/ubuntu:13.10')
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={})
        d = container.get_image_details()
        self.assertEqual(d['repository'], 'stackbrew/ubuntu')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_notag(self):
        service = entities.Service('foo', 'stackbrew/ubuntu')
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={})
        d = container.get_image_details()
        self.assertEqual(d['repository'], 'stackbrew/ubuntu')
        self.assertEqual(d['tag'], 'latest')

    def test_get_image_details_custom_registry(self):
        service = entities.Service('foo', 'quay.io/foo/bar:13.10')
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={})
        d = container.get_image_details()
        self.assertEqual(d['repository'], 'quay.io/foo/bar')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_custom_port(self):
        service = entities.Service('foo', 'quay.io:8081/foo/bar:13.10')
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={})
        d = container.get_image_details()
        self.assertEqual(d['repository'], 'quay.io:8081/foo/bar')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_custom_port_notag(self):
        service = entities.Service('foo', 'quay.io:8081/foo/bar')
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={})
        d = container.get_image_details()
        self.assertEqual(d['repository'], 'quay.io:8081/foo/bar')
        self.assertEqual(d['tag'], 'latest')

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

    def test_dns_option(self):
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={'dns': '8.8.8.8'})
        self.assertEqual(container.dns, ['8.8.8.8'])

    def test_dns_as_list_option(self):
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service,
                                       config={'dns': ['8.8.8.8', '8.8.4.4']})
        self.assertEqual(container.dns, ['8.8.8.8', '8.8.4.4'])

    def test_no_dns_option(self):
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config={})
        self.assertIsNone(container.dns)

    def test_swap_limit_number(self):
        config = {'limits': {'swap': 42}}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.memswap_limit, 42)

    def test_swap_limit_string_no_suffix(self):
        config = {'limits': {'swap': '42'}}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.memswap_limit, 42)

    def test_swap_limit_string_with_suffix(self):
        config = {'limits': {'swap': '42k'}}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.memswap_limit, 42*1024)

    def test_restart_policy_default(self):
        config = {}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.restart_policy, {'Name': 'no', 'MaximumRetryCount': 0})

    def test_restart_policy_no(self):
        config = {'restart': 'no'}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.restart_policy, {'Name': 'no', 'MaximumRetryCount': 0})

    def test_restart_policy_always(self):
        config = {'restart': 'always'}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.restart_policy, {'Name': 'always', 'MaximumRetryCount': 0})

    def test_restart_policy_onfailure(self):
        config = {'restart': 'on-failure'}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.restart_policy, {'Name': 'on-failure', 'MaximumRetryCount': 0})

    def test_restart_policy_onfailure_with_max_retries(self):
        config = {'restart': {'name': 'on-failure', 'retries': 42}}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.restart_policy, {'Name': 'on-failure', 'MaximumRetryCount': 42})

    def test_restart_policy_wrong_type(self):
        config = {'restart': []}
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.restart_policy, {'Name': 'no', 'MaximumRetryCount': 0})

    def test_restart_policy_missing_retries(self):
        config = {'restart': {'name': 'on-failure'} }
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        container = entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                       service, config=config)
        self.assertEqual(container.restart_policy, {'Name': 'on-failure', 'MaximumRetryCount': 0})

    def test_restart_policy_wrong_name(self):
        config = {'restart': 'noclue' }
        service = entities.Service('foo', 'stackbrew/ubuntu', env={})
        self.assertRaises(
            exceptions.InvalidRestartPolicyConfigurationException,
                    lambda: entities.Container('foo1', entities.Ship('ship', 'shipip'),
                                                 service, config=config))

class BaseConfigFileUsingTest(unittest.TestCase):

    def _get_config(self, name):
        path = os.path.join(os.path.dirname(__file__),
                            'yaml/{}.yaml'.format(name))
        return load_config_from_file(path)


class ConductorTest(BaseConfigFileUsingTest):

    def test_empty_registry_list(self):
        config = self._get_config('empty_registries')
        c = maestro.Conductor(config)
        self.assertIsNot(c.registries, None)
        self.assertEqual(c.registries, {})


class ConfigTest(BaseConfigFileUsingTest):

    def test_yaml_parsing_test1(self):
        """Make sure the env variables are working."""
        os.environ['BAR'] = 'bar'
        config = self._get_config('test_env')
        self.assertEqual('bar', config['foo'])

    def test_ship_parsing(self):
        config = self._get_config('test_ships')
        c = maestro.Conductor(config)
        self.assertEqual(c.ships['ship1'].ip, '10.0.0.1')
        self.assertEqual(c.ships['ship1'].endpoint, '192.168.10.1')
        self.assertTrue('192.168.10.1' in c.ships['ship1'].backend.base_url)

        self.assertEqual(c.ships['ship2'].ip, '10.0.0.2')
        self.assertEqual(c.ships['ship2'].endpoint, '10.0.0.2')
        self.assertTrue('1234' in c.ships['ship2'].backend.base_url)


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

    def test_parse_checker_http_defaults(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'http', 'port': 'server'})
        self.assertIsInstance(c, lifecycle.HttpRequestLifecycle)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.max_wait, lifecycle.HttpRequestLifecycle.DEFAULT_MAX_WAIT)
        self.assertEqual(c.match_regex,None)
        self.assertEqual(c.path,'/')
        self.assertEqual(c.scheme,'http')
        self.assertEqual(c.method,'get')
        self.assertEqual(c.requests_options,{})

        self.assertTrue(c._test_response)

    def test_parse_checker_http_explicits(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'http', 'port': 'server','match_regex':'abc[^d]','path':'/blah','scheme':'https','method':'put','max_wait': 2,'requests_options':{'verify':False}})
        self.assertIsInstance(c, lifecycle.HttpRequestLifecycle)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.max_wait, 2)
        self.assertFalse(c.match_regex.search('abcd'))
        self.assertTrue(c.match_regex.search('abce'))
        self.assertEqual(c.path,'/blah')
        self.assertEqual(c.scheme,'https')
        self.assertEqual(c.method,'put')
        self.assertEqual(c.requests_options,{'verify':False})

    def test_parse_checker_http_status_match(self):
        class FakeEmptyResponse(object):
            status_code = 200

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'http', 'port': 'server',})
        self.assertTrue(c._test_response(FakeEmptyResponse()))

    def test_parse_checker_http_status_fail(self):
        class FakeEmptyResponse(object):
            status_code = 500

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'http', 'port': 'server',})
        self.assertFalse(c._test_response(FakeEmptyResponse()))

    def test_parse_checker_http_regex_match(self):
        class FakeEmptyResponse(object):
            text = 'blah abce blah'

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'http', 'port': 'server','match_regex':'abc[^d]'})
        self.assertTrue(c._test_response(FakeEmptyResponse()))

    def test_parse_checker_http_regex_fail(self):
        class FakeEmptyResponse(object):
            text = 'blah abcd blah'

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(container,
            {'type': 'http', 'port': 'server','match_regex':'abc[^d]'})
        self.assertFalse(c._test_response(FakeEmptyResponse()))

#host,port,match_regex=None,path='/',scheme='http',method='get',max_wait=DEFAULT_MAX_WAIT,**requests_options
if __name__ == '__main__':
    unittest.main()
