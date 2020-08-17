#!/usr/bin/env python3
import re
from setuptools import setup, find_packages

with open('hoordu/_version.py') as f:
    content = f.read()
    version = re.search('__version__ = \'(.+?)\'', content).group(1)
    description = re.search('__desc__ = \'(.+?)\'', content).group(1)

with open('README.md') as f:
    long_description = f.read()

setup(
    name='hoordu',
    version=version,
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/Patchonn/py-hoordu',
    license='BSD-3-Clause',
    author='patchon',
    author_email='patchon@myon.moe',
    packages=find_packages(include=['hoordu', 'hoordu.*']),
    include_package_data=True,
    install_requires=[l.strip() for l in open('requirements.txt').readlines()]
)
