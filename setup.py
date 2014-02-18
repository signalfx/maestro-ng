#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
# Setuptools install description file.

import os
from setuptools import setup, find_packages

setup(
    name='maestro',
    version='0.1.7-dev',
    description='Orchestrator for multi-host Docker deployments',
    zip_safe=True,
    packages=find_packages(),
    install_requires=['docker-py', 'pyyaml', 'jinja2'],
    dependency_links=['https://github.com/dotcloud/docker-py/archive/master.zip#egg=docker-py'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Utilities',
    ],

    entry_points={
        'console': ['maestro = maestro.maestro'],
        'setuptools.installation': ['eggsecutable = maestro.maestro:main'],
    },

    author='Maxime Petazzoni',
    author_email='max@signalfuse.com',
    license='GNU Lesser General Public License v3',
    keywords='maestro docker orchestration deployment',
    url='http://github.com/signalfuse/maestro-ng',
)
