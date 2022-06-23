from setuptools import setup, find_packages


setup(
    name='csvw',
    version='3.0.0.dev0',
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
    python_requires='>=3.7',
    install_requires=[
        'attrs>=18.1',
        'isodate',
        'python-dateutil',
        'rfc3986<2',  # Pin until https://github.com/python-hyper/rfc3986/issues/86 is resolved.
        'uritemplate>=3.0.0',
        'babel',
        'requests',
        'language-tags',
        'rdflib',
        'colorama',
    ],
    extras_require={
        'dev': ['flake8', 'wheel', 'twine'],
        'test': [
            'pytest>=5',
            'pytest-mock',
            'requests-mock',
            'pytest-cov',
        ],
        'docs': [
            'sphinx',
            'sphinx-autodoc-typehints',
            'sphinx-rtd-theme',
        ],
    },
    entry_points = {
        'console_scripts': [
            'csvw2json=csvw.__main__:csvw2json',
            'csvwvalidate=csvw.__main__:csvwvalidate',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
)
