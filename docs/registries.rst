
Working with image registries
================================================================================

When Maestro needs to start a new container, it will do whatever it can
to make sure the image this container needs is available; the image full
name is specified at the service level.

Maestro will first check if the target Docker daemon reports the image
to be available. If the image is not available, or if the ``-r`` flag was
passed on the command-line (to force refresh the images), Maestro will
attempt to pull the image.

To do so, it will first analyze the name of the image and try to
identify a registry name (for example, in
``my-private-registry/my-image:tag``, the address of the registry is
``my-private-registry``) and look for a corresponding entry in the
``registries`` section of the environment description file to look for
authentication credentials. Note that Maestro will also look at each
registry's address FQDN for a match as a fallback.

You can also put your credentials into ``${HOME}/.dockercfg`` in the
appropriate format expected by Docker and ``docker-py``. Maestro, via the
``docker-py`` library, will also be looking at the contents of this file
for credentials to registries you are already logged in against.

If credentials are found, Maestro will login to the registry before
attempting to pull the image.

Additionally, you can configure a retry policy or image pull errors or a
per-registry basis. You can specify a maximum number of retries, and a list of
returned HTTP status codes to retry on. For example, the following
configuration will make two attempts to pull images from the ``quay.io``
registry if a 500 is returned.

.. code-block:: yaml

  registries:
    quay.io:
      registry: https://quay.io/v1/
      email: user@example.com
      username: user
      password: super-secret
      retry:
        attempts: 2
        when:
          - 500
