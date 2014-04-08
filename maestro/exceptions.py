# Copyright (C) 2013 SignalFuse, Inc.
#
# Docker container orchestration utility.


class MaestroException(Exception):
    """Base class for Maestro exceptions."""
    pass


class DependencyException(MaestroException):
    """Dependency resolution error."""
    pass


class ParameterException(MaestroException):
    """Invalid parameter passed to Maestro."""
    pass


class OrchestrationException(MaestroException):
    """Error during the execution of the orchestration score."""
    pass


class InvalidPortSpecException(MaestroException):
    "Error thrown when a port spec is in an invalid format."""
    pass


class InvalidLifecycleCheckConfigurationException(MaestroException):
    "Error thrown when a lifecycle check isn't configured properly."""
    pass
