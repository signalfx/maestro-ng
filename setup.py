#!/usr/bin/env python

# Copyright (C) 2013 SignalFuse, Inc.
# Setuptools install description file.

import os
from setuptools import setup, find_packages

with open('README.md') as readme:
    long_description = readme.read()

setup(
    name='maestro',
    version='0.1.7.1',
    description='Orchestrator for multi-host Docker deployments',
    long_description=long_description,
    zip_safe=True,
    packages=find_packages(),
    install_requires=['docker-py>=0.3.0', 'pyyaml', 'jinja2'],
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
    author_email='max@signalfuse.com',
    license='GNU Lesser General Public License v3',
    keywords='maestro docker orchestration deployment',
    url='http://github.com/signalfuse/maestro-ng',
)
