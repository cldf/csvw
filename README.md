# csvw

[![Build Status](https://github.com/cldf/csvw/workflows/tests/badge.svg)](https://github.com/cldf/csvw/actions?query=workflow%3Atests)
[![PyPI](https://img.shields.io/pypi/v/csvw.svg)](https://pypi.org/project/csvw)
[![Documentation Status](https://readthedocs.org/projects/csvw/badge/?version=latest)](https://csvw.readthedocs.io/en/latest/?badge=latest)


This package provides
- a Python API to read and write relational, tabular data according to the [CSV on the Web](https://csvw.org/) specification and 
- commandline tools for reading and validating CSVW data.


## Links

- GitHub: https://github.com/cldf/csvw
- PyPI: https://pypi.org/project/csvw
- Issue Tracker: https://github.com/cldf/csvw/issues


## Installation

This package runs under Python >=3.8, use pip to install:

```bash
$ pip install csvw
```


## CLI

### `csvw2json`

Converting CSVW data [to JSON](https://www.w3.org/TR/csv2json/)

```shell
$ csvw2json tests/fixtures/zipped-metadata.json 
{
    "tables": [
        {
            "url": "tests/fixtures/zipped.csv",
            "row": [
                {
                    "url": "tests/fixtures/zipped.csv#row=2",
                    "rownum": 1,
                    "describes": [
                        {
                            "ID": "abc",
                            "Value": "the value"
                        }
                    ]
                },
                {
                    "url": "tests/fixtures/zipped.csv#row=3",
                    "rownum": 2,
                    "describes": [
                        {
                            "ID": "cde",
                            "Value": "another one"
                        }
                    ]
                }
            ]
        }
    ]
}
```

### `csvwvalidate`

Validating CSVW data

```shell
$ csvwvalidate tests/fixtures/zipped-metadata.json 
OK
```

### `csvwdescribe`

Describing tabular-data files with CSVW metadata

```shell
$ csvwdescribe --delimiter "|" tests/fixtures/frictionless-data.csv
{
    "@context": "http://www.w3.org/ns/csvw",
    "dc:conformsTo": "data-package",
    "tables": [
        {
            "dialect": {
                "delimiter": "|"
            },
            "tableSchema": {
                "columns": [
                    {
                        "datatype": "string",
                        "name": "FK"
                    },
                    {
                        "datatype": "integer",
                        "name": "Year"
                    },
                    {
                        "datatype": "string",
                        "name": "Location name"
                    },
                    {
                        "datatype": "string",
                        "name": "Value"
                    },
                    {
                        "datatype": "string",
                        "name": "binary"
                    },
                    {
                        "datatype": "string",
                        "name": "anyURI"
                    },
                    {
                        "datatype": "string",
                        "name": "email"
                    },
                    {
                        "datatype": "string",
                        "name": "boolean"
                    },
                    {
                        "datatype": {
                            "dc:format": "application/json",
                            "base": "json"
                        },
                        "name": "array"
                    },
                    {
                        "datatype": {
                            "dc:format": "application/json",
                            "base": "json"
                        },
                        "name": "geojson"
                    }
                ]
            },
            "url": "tests/fixtures/frictionless-data.csv"
        }
    ]
}
```


## Python API

Find the Python API documentation at [csvw.readthedocs.io](https://csvw.readthedocs.io/en/latest/).

A quick example for using `csvw` from Python code:

```python
import json
from csvw import CSVW
data = CSVW('https://raw.githubusercontent.com/cldf/csvw/master/tests/fixtures/test.tsv')
print(json.dumps(data.to_json(minimal=True), indent=4))
[
    {
        "province": "Hello",
        "territory": "world",
        "precinct": "1"
    }
]
```


## Known limitations

- We read **all** data which is specified as UTF-8 encoded using the 
  [`utf-8-sig` codecs](https://docs.python.org/3/library/codecs.html#module-encodings.utf_8_sig).
  Thus, if such data starts with `U+FEFF` this will be interpreted as [BOM](https://en.wikipedia.org/wiki/Byte_order_mark)
  and skipped.
- Low level CSV parsing is delegated to the `csv` module in Python's standard library. Thus, if a `commentPrefix`
  is specified in a `Dialect` instance, this will lead to skipping rows where the first value starts
  with `commentPrefix`, **even if the value was quoted**.
- Also, cell content containing `escapechar` may not be round-tripped as expected (when specifying
  `escapechar` or a `csvw.Dialect` with `quoteChar` but `doubleQuote==False`),
  when minimal quoting is specified. This is due to inconsistent `csv` behaviour
  across Python versions (see https://bugs.python.org/issue44861).


## CSVW conformance

While we use the CSVW specification as guideline, this package does not (and 
probably never will) implement the full extent of this spec.

- When CSV files with a header are read, columns are not matched in order with
  column descriptions in the `tableSchema`, but instead are matched based on the
  CSV column header and the column descriptions' `name` and `titles` atributes.
  This allows for more flexibility, because columns in the CSV file may be
  re-ordered without invalidating the metadata. A stricter matching can be forced
  by specifying `"header": false` and `"skipRows": 1` in the table's dialect
  description.

However, `csvw.CSVW` works correctly for
- 269 out of 270 [JSON tests](https://w3c.github.io/csvw/tests/#manifest-json),
- 280 out of 282 [validation tests](https://w3c.github.io/csvw/tests/#manifest-validation),
- 10 out of 18 [non-normative tests](https://w3c.github.io/csvw/tests/#manifest-nonnorm)

from the [CSVW Test suites](https://w3c.github.io/csvw/tests/).


## Compatibility with [Frictionless Data Specs](https://specs.frictionlessdata.io/)

A CSVW-described dataset is basically equivalent to a Frictionless DataPackage where all 
[Data Resources](https://specs.frictionlessdata.io/data-resource/) are [Tabular Data](https://specs.frictionlessdata.io/tabular-data-resource/).
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
of [`frictionless describe`](https://framework.frictionlessdata.io/docs/guides/describing-data/) - provides
a convenient way to bootstrap CSVW metadata for a set of "raw" CSV
files, implemented in the [`csvwdescribe` command described above](#csvwdescribe).


## See also

- https://www.w3.org/2013/csvw/wiki/Main_Page
- https://csvw.org
- https://github.com/CLARIAH/COW
- https://github.com/CLARIAH/ruminator
- https://github.com/bloomberg/pycsvw
- https://specs.frictionlessdata.io/table-schema/
- https://github.com/theodi/csvlint.rb
- https://github.com/ruby-rdf/rdf-tabular
- https://github.com/rdf-ext/rdf-parser-csvw
- https://github.com/Robsteranium/csvwr


## License

This package is distributed under the [Apache 2.0 license](https://opensource.org/licenses/Apache-2.0).
