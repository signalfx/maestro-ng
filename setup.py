#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
# Setuptools install description file.

import os
from setuptools import setup, find_packages

requirements = ['docker-py==0.2.2']

setup(
    name='maestro',
    version='0.0.1',
    description='Orchestrator for multi-host Docker deployments',

    packages=find_packages(),
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
