#!/usr/bin/env python

# Copyright (C) 2013-2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Setuptools install description file.

from setuptools import setup, find_packages

with open('maestro/version.py') as f:
    exec(f.read())

with open('requirements.txt') as f:
    requirements = [line.strip() for line in f.readlines()]

try:
    import pypandoc
    # Convert the README to reStructuredText for PyPi
    long_description = pypandoc.convert(source='README.md',
                                        format='markdown',
                                        to='rst')
except ImportError:
    # No pandoc/pypandoc, just use raw
    with open('README.md') as readme:
        long_description = readme.read()

setup(
    name=name, # flake8: noqa
    version=version, # flake8: noqa
    description='Orchestrator for multi-host Docker deployments',
    long_description=long_description,
    zip_safe=True,
    packages=find_packages(),
    install_requires=requirements,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Utilities',
    ],

    entry_points={
        'console_scripts': ['maestro = maestro.__main__:main'],
        'setuptools.installation': ['eggsecutable = maestro.__main__:main'],
    },

    author='Maxime Petazzoni',
    author_email='max@signalfx.com',
    license='Apache Software License v2',
    keywords='maestro docker orchestration deployment',
    url='https://github.com/signalfuse/maestro-ng',
)
