# csvw

[![Build Status](https://github.com/cldf/csvw/workflows/tests/badge.svg)](https://github.com/cldf/csvw/actions?query=workflow%3Atests)
[![codecov](https://codecov.io/gh/cldf/csvw/branch/master/graph/badge.svg)](https://codecov.io/gh/cldf/csvw)
[![Requirements Status](https://requires.io/github/cldf/csvw/requirements.svg?branch=master)](https://requires.io/github/cldf/csvw/requirements/?branch=master)
[![PyPI](https://img.shields.io/pypi/v/csvw.svg)](https://pypi.org/project/csvw)


CSV on the Web



## Links

- GitHub: https://github.com/cldf/csvw
- PyPI: https://pypi.org/project/csvw
- Issue Tracker: https://github.com/cldf/csvw/issues


## Installation

This package runs under Python >=3.4, use pip to install:

```bash
$ pip install csvw
```


## Example


```python
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
```


## Known limitations

- We read **all** data which is specified as UTF-8 encoded using the 
  [`utf-8-sig` codecs](https://docs.python.org/3/library/codecs.html#module-encodings.utf_8_sig).
  Thus, if such data starts with `U+FEFF` this will be interpreted as [BOM](https://en.wikipedia.org/wiki/Byte_order_mark)
  and skipped.
- Low level CSV parsing is delegated to the `csv` module in Python's standard library. Thus, if a `commentPrefix`
  is specified in a `Dialect` instance, this will lead to skipping rows where the first value starts
  with `commentPrefix`, even if the value was quoted.


### Deviations from the CSVW specificaton

While we use the CSVW specification as guideline, this package does not (and 
probably never will) implement the full extent of this spec.

- When CSV files with a header are read, columns are not matched in order with
  column descriptions in the `tableSchema`, but instead are matched based on the
  CSV column header and the column descriptions' `name` and `titles` atributes.
  This allows for more flexibility, because columns in the CSV file may be
  re-ordered without invalidating the metadata. A stricter matching can be forced
  by specifying `"header": false` and `"skipRows": 1` in the table's dialect
  description.


## Compatibility with [Frictionless Data Specs](https://specs.frictionlessdata.io/)

The CSVW-described dataset is basically equivalent to a [Frictionless DataPackage] where all [Data Resources](https://specs.frictionlessdata.io/data-resource/) are [Tabular Data](https://specs.frictionlessdata.io/tabular-data-resource/).
Thus, the `csvw` package provides some conversion functionality. To
"read CSVW data from a Data Package", there's the `csvw.TableGroup.from_frictionless_datapackage` method:
```python
from csvw import TableGroup
tg = TableGroup.from_frictionless_datapackage('PATH/TO/datapackage.json')
```
To convert the metadata, the `TableGroup` can then be serialzed:
```python
tg.to_file('csvw-metadata.json')
```

Note that the CSVW metadata file must be written to the Data Package's directory
to make sure relative paths to data resources work.

This functionality - together with the schema inference capabilities
of [`frictionless describe`](https://frictionlessdata.io/tooling/python/describing-data/#describe-functions) - provides
a convenient way to bootstrap CSVW metadata for a set of "raw" CSV
files.


## See also

- https://www.w3.org/2013/csvw/wiki/Main_Page
- https://github.com/CLARIAH/COW
- https://github.com/CLARIAH/ruminator
- https://github.com/bloomberg/pycsvw
- https://specs.frictionlessdata.io/table-schema/
- https://github.com/theodi/csvlint.rb
- https://github.com/ruby-rdf/rdf-tabular
- https://github.com/rdf-ext/rdf-parser-csvw


## License

This package is distributed under the [Apache 2.0 license](https://opensource.org/licenses/Apache-2.0).
