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

    SERVICE = 'foo'
    IMAGE = 'stackbrew/ubuntu:13.10'
    CONTAINER = 'foo1'
    SHIP = 'ship'
    SHIP_IP = '10.0.0.1'
    SCHEMA = {'schema': 2}

    def _cntr(service_name=SERVICE, service_env=None, image=IMAGE,
              ship_name=SHIP, ship_ip=SHIP_IP,
              container_name=CONTAINER, config=None, schema=SCHEMA):
        service = entities.Service(service_name, image, schema, service_env)
        return entities.Container(container_name,
                                  entities.Ship(ship_name, ship_ip),
                                  service, config=config, schema=schema)

    def test_image_propagates_from_service(self):
        container = self._cntr()
        self.assertEqual(container.image, container.service.image)

    def test_get_image_details_basic(self):
        d = self._cntr().get_image_details()
        self.assertEqual(d['repository'], 'stackbrew/ubuntu')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_notag(self):
        d = self._cntr(image='stackbrew/ubuntu').get_image_details()
        self.assertEqual(d['repository'], 'stackbrew/ubuntu')
        self.assertEqual(d['tag'], 'latest')

    def test_get_image_details_custom_registry(self):
        d = self._cntr(image='quay.io/foo/bar:13.10').get_image_details()
        self.assertEqual(d['repository'], 'quay.io/foo/bar')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_custom_port(self):
        d = self._cntr(image='quay.io:8081/foo/bar:13.10').get_image_details()
        self.assertEqual(d['repository'], 'quay.io:8081/foo/bar')
        self.assertEqual(d['tag'], '13.10')

    def test_get_image_details_custom_port_notag(self):
        d = self._cntr(image='quay.io:8081/foo/bar').get_image_details()
        self.assertEqual(d['repository'], 'quay.io:8081/foo/bar')
        self.assertEqual(d['tag'], 'latest')

    def test_env_propagates_from_service(self):
        service_env = {'ENV': 'value'}
        container_env = {'OTHER_ENV': 'other-value'}
        container = self._cntr(service_env=service_env, config={'env': container_env})
        for k, v in service_env.items():
            self.assertIn(k, container.env)
            self.assertEqual(v, container.env[k])
        for k, v in container_env.items():
            self.assertIn(k, container.env)
            self.assertEqual(v, container.env[k])

    def test_dns_option(self):
        container = self._cntr(config={'dns': '8.8.8.8'})
        self.assertEqual(container.dns, ['8.8.8.8'])

    def test_dns_as_list_option(self):
        container = self._cntr(config={'dns': ['8.8.8.8', '8.8.4.4']})
        self.assertEqual(container.dns, ['8.8.8.8', '8.8.4.4'])

    def test_no_dns_option(self):
        self.assertIsNone(self._cntr().dns)

    def test_swap_limit_number(self):
        container = self._cntr(config={'limits': {'swap': 42}})
        self.assertEqual(container.memswap_limit, 42)

    def test_swap_limit_string_no_suffix(self):
        container = self._cntr(config={'limits': {'swap': '42'}})
        self.assertEqual(container.memswap_limit, 42)

    def test_swap_limit_string_with_suffix(self):
        container = self._cntr(config={'limits': {'swap': '42k'}})
        self.assertEqual(container.memswap_limit, 42*1024)

    def test_restart_policy_default(self):
        self.assertEqual(self._cntr().restart_policy,
                         {'Name': 'no', 'MaximumRetryCount': 0})

    def test_restart_policy_no(self):
        container = self._cntr(config={'restart': 'no'})
        self.assertEqual(container.restart_policy,
                         {'Name': 'no', 'MaximumRetryCount': 0})

    def test_restart_policy_always(self):
        container = self._cntr(config={'restart': 'always'})
        self.assertEqual(container.restart_policy,
                         {'Name': 'always', 'MaximumRetryCount': 0})

    def test_restart_policy_onfailure(self):
        container = self._cntr(config={'restart': 'on-failure'})
        self.assertEqual(container.restart_policy,
                         {'Name': 'on-failure', 'MaximumRetryCount': 0})

    def test_restart_policy_onfailure_with_max_retries(self):
        container = self._cntr(
                config={'restart': {'name': 'on-failure', 'retries': 42}})
        self.assertEqual(container.restart_policy,
                         {'Name': 'on-failure', 'MaximumRetryCount': 42})

    def test_restart_policy_wrong_type(self):
        container = self._cntr(config={'restart': []})
        self.assertEqual(container.restart_policy,
                         {'Name': 'no', 'MaximumRetryCount': 0})

    def test_restart_policy_missing_retries(self):
        container = self._cntr(config={'restart': {'name': 'on-failure'}})
        self.assertEqual(container.restart_policy,
                         {'Name': 'on-failure', 'MaximumRetryCount': 0})

    def test_restart_policy_wrong_name(self):
        self.assertRaises(
            exceptions.InvalidRestartPolicyConfigurationException,
            lambda: self._cntr(config={'restart': 'noclue'}))

    def test_volumes_simple_bind(self):
        container = self._cntr(config={'volumes': {'/outside': '/inside'}})
        self.assertTrue('/outside' in container.volumes)
        self.assertEqual(container.volumes,
                         {'/outside': {'bind': '/inside', 'ro': False}})

    def test_volumes_dict_bind_no_mode(self):
        container = self._cntr(config={'volumes': {
            '/outside': {'target': '/inside'}}})
        self.assertTrue('/outside' in container.volumes)
        self.assertEqual(container.volumes,
                         {'/outside': {'bind': '/inside', 'ro': False}})

    def test_volumes_ro_bind(self):
        container = self._cntr(config={'volumes': {
            '/outside': {
                'target': '/inside', 'mode': 'ro'
            }}})
        self.assertTrue('/outside' in container.volumes)
        self.assertEqual(container.volumes,
                         {'/outside': {'bind': '/inside', 'ro': True}})

    def test_volumes_multibind_throws(self):
        self.assertRaises(
            exceptions.InvalidVolumeConfigurationException,
            lambda: self._cntr(config={'volumes': {
                '/outside': ['/inside1', '/inside2']}}))

    def test_volumes_invalid_params_throws(self):
        self.assertRaises(
            exceptions.InvalidVolumeConfigurationException,
            lambda: self._cntr(config={'volumes': {
                '/outside': {'bind': '/inside'}}}))

    def test_volumes_old_schema(self):
        container = self._cntr(config={'volumes':
            {'/inside': '/outside'}
        }, schema={'schema': 1})
        self.assertEqual(container.volumes,
                {'/outside': {'bind': '/inside', 'ro': False}})


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
