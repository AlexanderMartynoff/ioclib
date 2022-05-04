from setuptools import setup, find_packages


__version__ = '0.1a1'


setup(
    name='dipy',
    version=__version__,
    packages=find_packages(),
    install_requires=[
        'typing_extensions',
    ],
)
