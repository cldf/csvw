# setup.py

from setuptools import setup, find_packages


setup(
    name='csvw',
    version='0.0.dev0',
    author='',
    author_email='',
    description='',
    keywords='',
    license='Apache 2.0',
    url='',
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        'attrs>=17.1.0',
        'clldutils>=1.13.10',
        'six',
        'pathlib2; python_version < "3"',
    ],
    extras_require={
        'dev': ['flake8', 'wheel', 'twine'],
        'test': [
            'pytest>=3.1',
            'pytest-mock',
            'mock',
            'pytest-cov',
        ],
    },
    platforms='any',
    long_description=open('README.rst').read(),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
)
