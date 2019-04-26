# setup.py

from setuptools import setup, find_packages


setup(
    name='csvw',
    version='1.5.0',
    author='Robert Forkel',
    author_email='forkel@shh.mpg.de',
    description='',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    keywords='csv w3c',
    license='Apache 2.0',
    url='https://github.com/cldf/csvw',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    zip_safe=False,
    platforms='any',
    python_requires='>=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*',
    install_requires=[
        'attrs>=18.1',
        'isodate',
        'pathlib2; python_version < "3.5"',
        'python-dateutil',
        'rfc3986',
        'uritemplate>=3.0.0',
    ],
    extras_require={
        'dev': ['flake8', 'wheel', 'twine'],
        'test': ['mock', 'pytest>=3.6', 'pytest-mock', 'pytest-cov'],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
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
