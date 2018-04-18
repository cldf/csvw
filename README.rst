Csvw
====

|PyPI version| |License| |Supported Python| |Format| |requires|

|Travis| |codecov|

CSV on the web


Links
-----

- GitHub: https://github.com/cldf/csvw
- PyPI: https://pypi.python.org/pypi/csvw
- Issue Tracker: https://github.com/cldf/csvw/issues
- Download: https://pypi.python.org/pypi/csvw#downloads


Installation
------------

This package runs under Python 2.7, and 3.4+, use pip_ to install:

.. code:: bash

    $ pip install csvw


Example
-------

.. code:: python

    >>> import csvw
    >>> tg = csvw.TableGroup.from_file('tests/csv.txt-metadata.json')

    >>> tg.check_referential_integrity()
    >>> assert len(tg.tables) == 1

    >>> assert tg.tables[0] is tg.tabledict['csv.txt']
    >>> tg.tables[0].check_primary_key()

    >>> from collections import OrderedDict
    >>> row = next(tg.tables[0].iterdicts())
    >>> assert row == OrderedDict([('ID', 'first'), ('_col.2', 'line')])

    >>> assert len(list(tg.tables[0].iterdicts())) == 2


See also
--------

- https://www.w3.org/2013/csvw/wiki/Main_Page
- https://github.com/CLARIAH/COW
- https://github.com/CLARIAH/ruminator
- https://github.com/bloomberg/pycsvw
- https://github.com/frictionlessdata/goodtables-py
- https://github.com/frictionlessdata/tableschema-py
- https://github.com/theodi/csvlint.rb
- https://github.com/ruby-rdf/rdf-tabular
- https://github.com/rdf-ext/rdf-parser-csvw


License
-------

This package is distributed under the `Apache 2.0 license`_.


.. _pip: https://pip.readthedocs.io

.. _Apache 2.0 license: https://opensource.org/licenses/Apache-2.0


.. |--| unicode:: U+2013


.. |PyPI version| image:: https://img.shields.io/pypi/v/csvw.svg
    :target: https://pypi.python.org/pypi/csvw
    :alt: Latest PyPI Version
.. |License| image:: https://img.shields.io/pypi/l/csvw.svg
    :target: https://pypi.python.org/pypi/csvw
    :alt: License
.. |Supported Python| image:: https://img.shields.io/pypi/pyversions/csvw.svg
    :target: https://pypi.python.org/pypi/csvw
    :alt: Supported Python Versions
.. |Format| image:: https://img.shields.io/pypi/format/csvw.svg
    :target: https://pypi.python.org/pypi/csvw
    :alt: Format
.. |Travis| image:: https://img.shields.io/travis/cldf/csvw.svg
   :target: https://travis-ci.org/cldf/csvw
   :alt: Travis
.. |requires| image:: https://requires.io/github/cldf/csvw/requirements.svg?branch=master
    :target: https://requires.io/github/cldf/csvw/requirements/?branch=master
    :alt: Requirements Status
.. |codecov| image:: https://codecov.io/gh/cldf/csvw/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/cldf/csvw

