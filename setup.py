# setup.py

from setuptools import setup, find_packages


setup(
    name='csvw',
    version='0.2.dev0',
    author='Robert Forkel',
    author_email='forkel@shh.mpg.de',
    description='',
    keywords='csv w3c',
    license='Apache 2.0',
    url='https://github.com/cldf/csvw',
    packages=find_packages(),
    zip_safe=False,
    platforms='any',
    python_requires='>=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*',
    install_requires=[
        'attrs>=17.1.0',
        'clldutils>=1.14.0',
        'uritemplate>=3.0.0',
    ],
    extras_require={
        'dev': ['flake8', 'wheel', 'twine'],
        'test': ['mock', 'pytest>=3.3', 'pytest-mock', 'pytest-cov'],
    },
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
