# Copyright (C) 2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Docker container orchestration utility.

from __future__ import print_function

from . import exceptions
from . import entities


class ShipsProvider:
    """Base abstract class for ship provider implementations.

    Ship providers can implement additional logic to determine the set of Ships
    that Maestro will work with.
    """

    def __init__(self, config):
        self._config = config
        self._defaults = config.get('ship_defaults', {})

    def _from_ship_or_defaults(self, ship, key):
        return ship.get(key, self._defaults.get(key))

    def ships(self):
        """Returns the dictionary of instantiated Ship objects, indexed by ship
        name."""
        raise NotImplementedError


class StaticShipsProvider(ShipsProvider):
    """
    Static ship provider.

    Provides a set of ships defined by static configuration in the 'ships' YAML
    map. This is the default provider and most commonly used. It is also the
    original way of defining ships in Maestro.
    """

    def __init__(self, config):
        ShipsProvider.__init__(self, config)

        # Create container ships.
        self._ships = dict(
            (k, entities.Ship(
                k, ip=v['ip'], endpoint=v.get('endpoint'),
                docker_port=self._from_ship_or_defaults(v, 'docker_port'),
                socket_path=self._from_ship_or_defaults(v, 'socket_path'),
                ssh_tunnel=self._from_ship_or_defaults(v, 'ssh_tunnel'),
                api_version=self._from_ship_or_defaults(v, 'api_version'),
                timeout=self._from_ship_or_defaults(v, 'timeout'),
                tls=v.get('tls', False),
                tls_cert=v.get('tls_cert', None),
                tls_key=v.get('tls_key', None),
                tls_verify=v.get('tls_verify', False),
                tls_ca_cert=v.get('tls_ca_cert', None),
                ssl_version=v.get('ssl_version', None)))
            for k, v in self._config['ships'].items())

    def ships(self):
        return self._ships


class ShipsProviderFactory:
    """
    Factory for ships providers, returning the appropriate ship provider
    implementation based on the 'ship_provider' setting from the YAML
    configuration.
    """

    DEFAULT_PROVIDER = 'static'
    PROVIDERS = {
        'static': StaticShipsProvider,
    }

    @staticmethod
    def from_config(config):
        provider = config.get('ship_provider',
                              ShipsProviderFactory.DEFAULT_PROVIDER)

        if provider not in ShipsProviderFactory.PROVIDERS:
            raise exceptions.EnvironmentConfigurationException(
                'Invalid ship provider {}! Available providers: {}'
                .format(provider,
                        ', '.join(ShipsProviderFactory.PROVIDERS.keys())))
        return ShipsProviderFactory.PROVIDERS[provider](config)
