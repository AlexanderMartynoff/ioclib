from setuptools import setup, find_packages


__version__ = '0.4'


setup(
    name='ioclib',
    version=__version__,
    packages=find_packages(),
    install_requires=[
        'typing_extensions>=4',
    ],
)
