CSV on the Web with `csvw`
==========================

Overview
--------

Exploring CSVW described data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    >>> from csvw import TableGroup
    >>> tg = TableGroup.from_url(
    ...     'https://raw.githubusercontent.com/cldf/csvw/master/tests/fixtures/csv.txt-metadata.json')
    >>> len(tg.tables)
    1
    >>> len(tg.tables[0].tableSchema.columns)
    2
    >>> tg.tables[0].tableSchema.columns[0].datatype.base
    'string'
    >>> tg.tables[0].tableSchema.columns[0].name
    'ID'
    >>> list(tg.tables[0])[0]['ID']
    'first'


Creating CSVW described data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    >>> from csvw import Table
    >>> t = Table(url='data.csv')
    >>> t.tableSchema.columns.append(Column.fromvalue(dict(name='ID', datatype='integer')))
    >>> t.write([dict(ID=1), dict(ID=2)])
    2
    >>> t.to_file('data.csv-metadata.json')
    PosixPath('data.csv-metadata.json')
    >>> list(Table.from_file('data.csv-metadata.json').iterdicts())
    [OrderedDict([('ID', 1)]), OrderedDict([('ID', 2)])]


Where's the "on the Web" part?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

While it's nice that we can fetch data descriptions from URLs with :class:`TableGroup` and :class:`Table`, CSVW
also includes a specification for `locating metadata <https://www.w3.org/TR/tabular-data-model/#locating-metadata>`_.
This is meant to support use cases where you find the data first - and might be missing out on the description without
such mechanisms. This part of the spec is implemented in :class:`csvw.CSVW`.

.. code-block:: python

    >>> from csvw import CSVW
    >>> data = CSVW('https://raw.githubusercontent.com/cldf/csvw/master/tests/fixtures/csv.txt')
    >>> data.t
    TableGroup(...)

.. autoclass:: csvw.CSVW
    :members:


Top-level descriptions
----------------------

The `csvw` package provides a Python API to read and write CSVW decribed data. The main building blocks
of this API are Python classes representing the top-level objects of a CSVW description.

.. autoclass:: csvw.Table
    :members:

.. autoclass:: csvw.TableGroup
    :members:


Reading and writing top-level descriptions
------------------------------------------

Both types of objects are recognized as top-level descriptions, i.e. may be encountered a JSON objects
on the web or on disk. Thus, they share some factory and serialization methods inherited from a base
class:

.. autoclass:: csvw.metadata.TableLike
    :members:


Table schema descriptions
-------------------------

A table's schema is described using a hierarchy of description objects:

- :class:`csvw.metadata.Schema` - accessed through `Table.tableSchema`
- :class:`csvw.Column` - accessed through `Table.tableSchema.columns`
- :class:`csvw.Datatype` - accessed through `Column.datatype`

.. autoclass:: csvw.metadata.Schema
    :members:

.. autoclass:: csvw.Column
    :members:

.. autoclass:: csvw.Datatype
    :members:


For a list of datatypes supported by `csvw`, see :doc:`datatypes`