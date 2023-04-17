from setuptools import setup, find_namespace_packages


__version__ = '1.8'


setup(
    name='ioclib-injector',
    version=__version__,
    packages=find_namespace_packages(include=['ioclib.*']),
    install_requires=[
        'typing_extensions>=4',
    ],
)
