#!/usr/bin/env python

# Copyright (C) 2013-2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Unit tests for Maestro, Docker container orchestration utility.

import os
import six
import unittest
import yaml

from maestro import entities, exceptions, loader, lifecycle, maestro, plays


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

    def test_no_limits_option(self):
        service = entities.Service('foo', 'stackbrew/ubuntu:13.10')
        self.assertEqual(service.limits, {})

    def test_limits_option(self):
        service = entities.Service('foo',
                                   'stackbrew/ubuntu:13.10',
                                   limits={'cpu': 2, 'memory': '10m'})
        self.assertEqual(service.limits, {'cpu': 2, 'memory': '10m'})

    def test_no_ports_option(self):
        service = entities.Service('foo', 'stackbrew/ubuntu:13.10')
        self.assertEqual(service.ports, {})

    def test_ports_option(self):
        service = entities.Service('foo',
                                   'stackbrew/ubuntu:13.10',
                                   ports={'server: 4848'})
        self.assertEqual(service.ports, {'server: 4848'})


class ContainerTest(unittest.TestCase):

    SERVICE = 'foo'
    IMAGE = 'stackbrew/ubuntu:13.10'
    CONTAINER = 'foo1'
    SHIP = 'ship'
    SHIP_IP = '10.0.0.1'
    SCHEMA = {'schema': 2}
    DOCKER_VERSION = '1.12'
    PORTS = {'server': 4848}

    def _cntr(service_name=SERVICE, service_env=None, image=IMAGE,
              ship_name=SHIP, ship_ip=SHIP_IP,
              container_name=CONTAINER, config=None, schema=SCHEMA,
              api_version=DOCKER_VERSION, ports=PORTS):
        service = entities.Service(service_name, image, schema=schema,
                                   env=service_env, ports=ports)
        return entities.Container(container_name,
                                  entities.Ship(ship_name, ship_ip,
                                                api_version=api_version),
                                  service, config=config, schema=schema)

    def test_image_propagates_from_service(self):
        container = self._cntr()
        self.assertEqual(container.image, container.service.image)

    def test_ports_propagates_from_service(self):
        container = self._cntr()
        self.assertEqual(container.ports, container._parse_ports(container.service.ports))

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
        container = self._cntr(service_env=service_env,
                               config={'env': container_env})
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

    def test_no_ulimit_option(self):
        self.assertIsNone(self._cntr().ulimits)

    def test_ulimit_with_hard_soft_limit(self):
        container = self._cntr(
                config={'ulimits': {'nofile': {'hard': 1024, 'soft': 1024}}})
        self.assertEqual(container.ulimits,
                         [{'hard': 1024, 'soft': 1024, 'name': 'nofile'}])

    def test_ulimit_with_single_limit(self):
        container = self._cntr(config={'ulimits': {'nproc': 65535}})
        self.assertEqual(container.ulimits,
                         [{'hard': 65535, 'soft': 65535, 'name': 'nproc'}])

    def test_log_config_default(self):
        self.assertTrue("LogConfig" not in self._cntr().host_config)

    def test_log_config_syslog(self):
        container = self._cntr(config={'log_driver': 'syslog'})
        self.assertTrue("LogConfig" in container.host_config)
        self.assertEqual(container.host_config['LogConfig'],
                         {'Type': 'syslog', 'Config': {}})

    def test_log_config_syslog_with_opts(self):
        container = self._cntr(config={'log_driver': 'syslog', 'log_opt': {
            'syslog-address': 'tcp://127.0.0.1:514'
        }})
        self.assertTrue("LogConfig" in container.host_config)
        self.assertEqual(container.host_config['LogConfig'], {
            'Type': 'syslog', 'Config': {
                'syslog-address': 'tcp://127.0.0.1:514'
            }})

    def test_log_config_wrong_driver_type(self):
        self.assertRaises(
            exceptions.InvalidLogConfigurationException,
            lambda: self._cntr(config={'log_driver': 'notvalid'}))

    def test_log_config_wrong_opt_type(self):
        self.assertRaises(
            exceptions.InvalidLogConfigurationException,
            lambda: self._cntr(
                config={'log_driver': 'syslog', "log_opt": 'shouldbeadict'}))

    def test_log_config_converts_options_to_string(self):
        container = self._cntr(config={'log_driver': 'json-file', 'log_opt': {
            'max-size': '2M', 'max-file': 2
        }})
        self.assertTrue("LogConfig" in container.host_config)
        self.assertEqual(len(container.host_config['LogConfig']['Config']), 2)
        for value in container.host_config['LogConfig']['Config'].values():
            self.assertTrue(isinstance(value, six.string_types))

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
                         {'/outside': {'bind': '/inside'}})

    def test_volumes_dict_bind_no_mode(self):
        container = self._cntr(config={'volumes': {
            '/outside': {'target': '/inside'}}})
        self.assertTrue('/outside' in container.volumes)
        self.assertEqual(container.volumes,
                         {'/outside': {'bind': '/inside', 'mode': 'rw'}})

    def test_volumes_ro_bind(self):
        container = self._cntr(config={'volumes': {
            '/outside': {
                'target': '/inside', 'mode': 'ro'
            }}})
        self.assertTrue('/outside' in container.volumes)
        self.assertEqual(container.volumes,
                         {'/outside': {'bind': '/inside', 'mode': 'ro'}})

    def test_volumes_bind_with_mode(self):
        container = self._cntr(config={'volumes': {
            '/outside': {
                'target': '/inside', 'mode': 'ro,Z'
            }}})
        self.assertTrue('/outside' in container.volumes)
        self.assertEqual(container.volumes,
                         {'/outside': {'bind': '/inside', 'mode': 'ro,Z'}})

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
        container = self._cntr(
            config={'volumes': {'/inside': '/outside'}},
            schema={'schema': 1})
        self.assertEqual(container.volumes,
                         {'/outside': {'bind': '/inside', 'ro': False}})

    def test_workdir(self):
        container = self._cntr(config={'workdir': '/tmp'})
        self.assertEqual(container.workdir, '/tmp')

    def test_volume_conflict_container(self):
        six.assertRaisesRegex(self,
                exceptions.InvalidVolumeConfigurationException,
                'Conflict in {} between bind-mounted volume '
                'and container-only volume on /in1'
                .format(ContainerTest.CONTAINER),
                lambda: self._cntr(config={'volumes': {'/out': '/in1'},
                                           'container_volumes': ['/in1']}))

    def test_simple_port_mapping_no_protocol_defaults_to_tcp(self):
        container = self._cntr(config={'ports': {'http': '80'}})
        self.assertEqual(container.ports['http'],
                         {'exposed': '80/tcp',
                          'external': ('0.0.0.0', '80/tcp')})

    def test_simple_port_mapping_with_protocol(self):
        container = self._cntr(config={'ports': {'http': '80/udp'}})
        self.assertEqual(container.ports['http'],
                         {'exposed': '80/udp',
                          'external': ('0.0.0.0', '80/udp')})

    def test_remapped_port_mapping(self):
        container = self._cntr(config={'ports': {'http': '80:8080'}})
        self.assertEqual(container.ports['http'],
                         {'exposed': '80/tcp',
                          'external': ('0.0.0.0', '8080/tcp')})

    def test_remapped_port_mapping_different_protocols_not_allowed(self):
        six.assertRaisesRegex(self,
                exceptions.InvalidPortSpecException,
                'Mismatched protocols between 80/tcp and 8080/udp!',
                lambda: self._cntr(
                    config={'ports': {'http': '80/tcp:8080/udp'}}))

    def test_direct_port_range_mapping(self):
        container = self._cntr(
                config={
                    'ports': {
                        'http': {
                            'exposed': '1234-1236',
                            'external': '1234-1236'
                            }
                        }})
        self.assertEqual(container.ports['http'],
                         {'exposed': '1234-1236/tcp',
                          'external': ('0.0.0.0', '1234-1236/tcp')})

    def test_port_range_mapping_to_single_port(self):
        container = self._cntr(
                config={
                    'ports': {
                        'http': {
                            'exposed': '1234',
                            'external': '1234-1236'
                            }
                        }})
        self.assertEqual(container.ports['http'],
                         {'exposed': '1234/tcp',
                          'external': ('0.0.0.0', '1234-1236/tcp')})


class BaseConfigFileUsingTest(unittest.TestCase):

    def _get_config(self, name):
        path = os.path.join(os.path.dirname(__file__),
                            'yaml/{}.yaml'.format(name))
        return loader.load(path)


class ConductorTest(BaseConfigFileUsingTest):

    def test_duplicate_container_name(self):
        self.assertRaises(
                yaml.constructor.ConstructorError,
                lambda: self._get_config('duplicate_container'))

    def test_empty_registry_list(self):
        config = self._get_config('empty_registries')
        c = maestro.Conductor(config)
        self.assertIsNot(c.registries, None)
        self.assertEqual(c.registries, {})

    def test_volumes_parsing(self):
        config = self._get_config('test_volumes')
        c = maestro.Conductor(config)
        instance1 = c.containers['instance-1']
        instance2 = c.containers['instance-2']
        self.assertEqual(instance1.get_volumes(),
                         set(['/in1', '/in2']))
        self.assertEqual(instance2.get_volumes(),
                         set(['/in3']))
        self.assertEqual(instance2.volumes_from,
                         set([instance1.name]))

    def test_volume_conflict_volumes_from(self):
        config = self._get_config('test_volume_conflict_volumes_from')
        six.assertRaisesRegex(self,
                exceptions.InvalidVolumeConfigurationException,
                'Volume conflicts between instance-2 and instance-1: /in1!',
                lambda: maestro.Conductor(config))

    def test_volumes_from_unknown(self):
        config = self._get_config('test_volumes_from_unknown')
        six.assertRaisesRegex(self,
                exceptions.InvalidVolumeConfigurationException,
                'Unknown container instance-2 to get volumes from '
                'for instance-1!',
                lambda: maestro.Conductor(config))

    def test_volumes_from_adds_dependency(self):
        config = self._get_config('test_volumes_from_adds_dependency')
        c = maestro.Conductor(config)
        self.assertEqual(len(c.services), 2)
        self.assertEqual(len(c.containers), 2)
        self.assertEqual(len(list(c.services['myservice'].containers)), 1)
        self.assertEqual(c.services['myservice'].dependencies,
                         set([c.services['mydata']]))
        self.assertEqual(c.services['myservice'].requires,
                         set([c.services['mydata']]))

    def test_env_name(self):
        config = self._get_config('test_envname')
        c = maestro.Conductor(config)
        self.assertEqual(c.env_name, 'test')
        foo1 = c.containers['foo-1']
        self.assertEqual(foo1.env['MAESTRO_ENVIRONMENT_NAME'], 'test')

    def test_missing_env_name(self):
        config = self._get_config('test_missing_envname')
        six.assertRaisesRegex(self,
                exceptions.EnvironmentConfigurationException,
                'Environment name is missing',
                lambda: maestro.Conductor(config))


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


class AuditorConfigTest(BaseConfigFileUsingTest):

    def test_ignore_errors_wraps_with_non_failing_auditor(self):
        config = self._get_config('auditor_ignore_errors')
        c = maestro.Conductor(config)
        self.assertTrue(len(c.auditor.get_auditors()), 2)
        self.assertTrue(isinstance(c.auditor.get_auditors()[0],
                                   maestro.audit._AlwaysFailAuditor))
        self.assertTrue(isinstance(c.auditor.get_auditors()[1],
                                   maestro.audit.NonFailingAuditor))

    def test_non_failing_auditor(self):
        config = self._get_config('auditor_ignore_errors')
        c = maestro.Conductor(config)
        # Should not fail
        c.auditor.get_auditors()[1].action(maestro.audit.INFO, 'foo', 'start')


class LifecycleHelperTest(unittest.TestCase):

    def _get_container(self):
        ship = entities.Ship('ship', 'ship.ip')
        service = entities.Service('foo', 'stackbrew/ubuntu')
        return entities.Container(
            'foo1', ship, service,
            config={'ports': {'server': '4242/tcp', 'data': '4243/udp'},
                    'env': {'foo': 'bar', 'wid': 42}})

    def test_script_env_all_strings(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container, {'type': 'exec', 'command': 'python foo.py -arg'})
        env = c._create_env()
        self.assertEqual(type(env['wid']), str)
        self.assertEqual(env['wid'], '42')

    def test_parse_checker_exec(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container, {'type': 'exec', 'command': 'python foo.py -arg'})
        self.assertIsNot(c, None)
        self.assertIsInstance(c, lifecycle.ScriptExecutor)
        self.assertEqual(c.command, ['python', 'foo.py', '-arg'])

    def test_parse_checker_tcp(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container, {'type': 'tcp', 'port': 'server'})
        self.assertIsInstance(c, lifecycle.TCPPortPinger)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.attempts,
                         lifecycle.TCPPortPinger.DEFAULT_MAX_ATTEMPTS)

    def test_parse_checker_tcp_with_max_wait(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container, {'type': 'tcp', 'port': 'server', 'max_wait': 2})
        self.assertIsInstance(c, lifecycle.TCPPortPinger)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.attempts, 2)

    def test_parse_checker_tcp_unknown_port(self):
        container = self._get_container()
        self.assertRaises(
            exceptions.InvalidLifecycleCheckConfigurationException,
            lifecycle.LifecycleHelperFactory.from_config,
            container, {'type': 'tcp', 'port': 'test-does-not-exist'})

    def test_parse_checker_tcp_invalid_port(self):
        container = self._get_container()
        self.assertRaises(
            exceptions.InvalidLifecycleCheckConfigurationException,
            lifecycle.LifecycleHelperFactory.from_config,
            container, {'type': 'tcp', 'port': 'data'})

    def test_parse_unknown_checker_type(self):
        self.assertRaises(
            KeyError,
            lifecycle.LifecycleHelperFactory.from_config,
            self._get_container(), {'type': 'test-does-not-exist'})

    def test_parse_checker_http_defaults(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container, {'type': 'http', 'port': 'server'})
        self.assertIsInstance(c, lifecycle.HttpRequestLifecycle)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.max_wait,
                         lifecycle.HttpRequestLifecycle.DEFAULT_MAX_WAIT)
        self.assertEqual(c.match_regex, None)
        self.assertEqual(c.path, '/')
        self.assertEqual(c.scheme, 'http')
        self.assertEqual(c.method, 'get')
        self.assertEqual(c.requests_options, {})

        self.assertTrue(c._test_response)

    def test_parse_checker_http_explicits(self):
        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container,
            {
                'type': 'http',
                'port': 'server',
                'match_regex': 'abc[^d]',
                'path': '/blah',
                'scheme': 'https',
                'method': 'put',
                'max_wait': 2,
                'requests_options': {'verify': False}
            })
        self.assertIsInstance(c, lifecycle.HttpRequestLifecycle)
        self.assertEqual(c.host, container.ship.ip)
        self.assertEqual(c.port, 4242)
        self.assertEqual(c.max_wait, 2)
        self.assertFalse(c.match_regex.search('abcd'))
        self.assertTrue(c.match_regex.search('abce'))
        self.assertEqual(c.path, '/blah')
        self.assertEqual(c.scheme, 'https')
        self.assertEqual(c.method, 'put')
        self.assertEqual(c.requests_options, {'verify': False})

    def test_parse_checker_http_status_match(self):
        class FakeEmptyResponse(object):
            status_code = 200

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container, {'type': 'http', 'port': 'server'})
        self.assertTrue(c._test_response(FakeEmptyResponse()))

    def test_parse_checker_http_status_fail(self):
        class FakeEmptyResponse(object):
            status_code = 500

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container, {'type': 'http', 'port': 'server'})
        self.assertFalse(c._test_response(FakeEmptyResponse()))

    def test_parse_checker_http_regex_match(self):
        class FakeEmptyResponse(object):
            text = 'blah abce blah'

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container,
            {'type': 'http', 'port': 'server', 'match_regex': 'abc[^d]'})
        self.assertTrue(c._test_response(FakeEmptyResponse()))

    def test_parse_checker_http_regex_fail(self):
        class FakeEmptyResponse(object):
            text = 'blah abcd blah'

        container = self._get_container()
        c = lifecycle.LifecycleHelperFactory.from_config(
            container,
            {'type': 'http', 'port': 'server', 'match_regex': 'abc[^d]'})
        self.assertFalse(c._test_response(FakeEmptyResponse()))


class LoginTaskTest(BaseConfigFileUsingTest):

    def test_find_registry_for_container_by_name(self):
        config = self._get_config('test_find_registry')
        c = maestro.Conductor(config)
        container = c.containers['foo1']
        registry = plays.tasks.LoginTask.registry_for_container(
            container, c.registries)
        self.assertEqual(registry, c.registries['quay.io'])

    def test_find_registry_for_container_by_fqdn(self):
        config = self._get_config('test_find_registry')
        c = maestro.Conductor(config)
        container = c.containers['foo2']
        registry = plays.tasks.LoginTask.registry_for_container(
            container, c.registries)
        self.assertEqual(registry, c.registries['foo2'])

    def test_find_registry_for_container_not_found(self):
        config = self._get_config('test_find_registry')
        c = maestro.Conductor(config)
        container = c.containers['foo3']
        registry = plays.tasks.LoginTask.registry_for_container(
            container, c.registries)
        self.assertEqual(registry, None)

    def test_find_registry_by_image_name(self):
        config = self._get_config('test_find_registry')
        c = maestro.Conductor(config)
        container = c.containers['foo4']
        registry = plays.tasks.LoginTask.registry_for_container(
                container, c.registries)
        self.assertEqual(registry, c.registries['foo4'])


if __name__ == '__main__':
    unittest.main()
