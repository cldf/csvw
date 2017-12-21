from __future__ import unicode_literals

import json
import shutil
import collections

from csvw._compat import pathlib, json_open

import pytest

import csvw
from csvw.dsv import Dialect

FIXTURES = pathlib.Path(__file__).parent


class TestColumnAccess(object):

    def test_get_column(self):
        t = csvw.Table.fromvalue({
            "url": '',
            "tableSchema": {
                "columns": [
                    {"name": "col1", "datatype": "string"},
                    {"datatype": "string", "titles": "xyz"},
                    {"name": "col2", "propertyUrl": "http://example.org"},
                ]
            }
        })
        assert t.get_column('col1').name == 'col1'
        assert t.get_column('http://example.org').name == 'col2'
        assert t.get_column('xyz').name is None


class TestDialect(object):

    @staticmethod
    def _roundtrip(t, fpath, *items):
        fname = str(fpath)
        t.write(items, fname=fname)
        return fpath.read_text(encoding='utf-8'), list(t.iterdicts(fname=fname))

    def test_doubleQuote(self, tmpdir):
        fpath = tmpdir / 'test'
        t = csvw.Table.fromvalue({
            "url": str(fpath),
            "dialect": {"doubleQuote": True},
            "tableSchema": {
                "columns": [
                    {"name": "col1", "datatype": "string"},
                    {"name": "col2", "datatype": "string"},
                ]
            }
        })
        value = r'"a\\b\c\"d'
        c, res = self._roundtrip(t, fpath, {"col1": "", "col2": value})
        assert r'""a\\\\b\\c\\""d' in c
        assert res[0]['col2'] == value

        t.dialect.doubleQuote = False
        c, res = self._roundtrip(t, fpath, {"col1": "", "col2": value})
        assert r'\"a\\\\b\\c\\\"d' in c
        assert res[0]['col2'] == value

        t.dialect.quoteChar = '*'
        c, res = self._roundtrip(t, fpath, {"col1": "", "col2": value})
        assert res[0]['col2'] == value

        t.dialect.doubleQuote = True
        c, res = self._roundtrip(t, fpath, {"col1": "", "col2": value})
        assert res[0]['col2'] == value

        value = value.replace('"', '*')
        c, res = self._roundtrip(t, fpath, {"col1": "", "col2": value})
        assert res[0]['col2'] == value


class TestNaturalLanguage(object):

    def test_string(self):
        l = csvw.NaturalLanguage('abc')
        assert l.getfirst() == 'abc'
        assert l.get(None) == ['abc']
        assert '{}'.format(l) == 'abc'

    def test_array(self):
        l = csvw.NaturalLanguage(['abc', 'def'])
        assert l.getfirst() == 'abc'
        assert l.get(None) == ['abc', 'def']
        assert '{}'.format(l) == 'abc'

    def test_object(self):
        l = csvw.NaturalLanguage(collections.OrderedDict([('en', ['abc', 'def']), ('de', '\u00e4\u00f6\u00fc')]))
        assert l.getfirst('de') == '\u00e4\u00f6\u00fc'
        assert l.get('en') == ['abc', 'def']
        assert '{}'.format(l) == 'abc'

    def test_error(self):
        with pytest.raises(ValueError):
            csvw.NaturalLanguage(1)

    def test_serialize(self):
        l = csvw.NaturalLanguage('\u00e4')
        assert json.dumps(l.asdict()) == '"\\u00e4"'
        l.add('a')
        assert json.dumps(l.asdict()) == '["\\u00e4", "a"]'
        l.add('\u00f6', 'de')
        assert json.dumps(l.asdict()) == \
               '{"und": ["\\u00e4", "a"], "de": "\\u00f6"}'


class TestColumn(object):

    def test_read_rite_with_separator(self):
        col = csvw.Column.fromvalue({'separator': ';', 'null': 'nn'})
        for parsed, serialized in [
                (['a', 'b'], 'a;b'),
                (['a', None], 'a;nn'),
                ([], '')]:
            assert col.read(serialized) == parsed
            assert col.write(parsed) == serialized
        assert col.write(None) == ''
        assert col.write('') == ''

    def test_read_required_empty_string(self):
        col = csvw.Column.fromvalue({'required': True})
        with pytest.raises(ValueError):
            col.read('')

    def test_read_required_empty_string_no_null(self):
        col = csvw.Column.fromvalue({'required': True, 'null': None})
        assert col.read('') == ''


class TestLink(object):

    def test_link(self):
        l = csvw.Link('a.csv')
        assert '{}'.format(l) == l.resolve(None)
        assert 'http://example.org/a.csv' == l.resolve('http://example.org')
        base = pathlib.Path('.')
        assert base == l.resolve(base).parent


class TestTableGroup(object):

    @staticmethod
    def _make_tablegroup(tmpdir, data=None, metadata=None):
        md = tmpdir / 'md'
        if metadata is None:
            shutil.copy(str(FIXTURES / 'csv.txt-metadata.json'), str(md))
        else:
            md.write_text(metadata, encoding='utf-8')
        if isinstance(data, dict):
            for fname, content in data.items():
                (tmpdir / fname).write_text(content, encoding='utf-8')
        else:
            data = data or (FIXTURES / 'csv.txt').read_text(encoding='utf-8')
            with pathlib.Path(str(tmpdir / 'csv.txt')).open('w', encoding='utf-8', newline='') as f:
                f.write(data)
        return csvw.TableGroup.from_file(str(md))

    @staticmethod
    def _load_json(path):
        with json_open(str(path)) as f:
            return json.load(f)

    def test_roundtrip(self, tmpdir):
        t = self._make_tablegroup(tmpdir)
        assert self._load_json(t.to_file(str(tmpdir / 'out'))) == \
               self._load_json(FIXTURES / 'csv.txt-metadata.json')
        t.common_props['dc:title'] = 'the title'
        t.aboutUrl = 'http://example.org/{ID}'
        assert self._load_json(t.to_file(str(tmpdir / 'out'))) != \
               self._load_json(FIXTURES / 'csv.txt-metadata.json')
        assert self._load_json(t.to_file(str(tmpdir / 'out'), omit_defaults=False)) != \
               self._load_json(FIXTURES / 'csv.txt-metadata.json')

    def test_all(self, tmpdir):
        t = self._make_tablegroup(tmpdir)
        assert len(list(t.tables[0])) == 2

        # Test appication of null property on columns:
        t = self._make_tablegroup(tmpdir)
        t.tables[0].tableSchema.columns[1].null = ['line']
        assert list(t.tables[0])[0]['_col.2'] is None

        t = self._make_tablegroup(tmpdir)
        t.tables[0].tableSchema.columns[1].separator = 'n'
        assert list(t.tables[0])[0]['_col.2'] == ['li', 'e']

        t = self._make_tablegroup(tmpdir)
        t.tables[0].tableSchema.columns[1].titles = csvw.NaturalLanguage('colname')
        assert 'colname' in list(t.tables[0])[0]

        t = self._make_tablegroup(tmpdir)
        t.dialect.header = True
        assert len(list(t.tables[0])) == 1

        t = self._make_tablegroup(tmpdir, 'edferd,f\r\nabc,')
        t.tables[0].tableSchema.columns[0].required = True
        t.tables[0].tableSchema.columns[0].null = ['abc']
        with pytest.raises(ValueError, match=r'csv\.txt:2:1 ID: required column value is missing'):
            list(t.tables[0])

        t = self._make_tablegroup(tmpdir, ',')
        t.tables[0].tableSchema.columns[0].required = True
        with pytest.raises(ValueError):
            list(t.tables[0])

        t = self._make_tablegroup(tmpdir, 'abc,9\r\ndef,10')
        items = list(t.tables[0])
        assert items[0]['_col.2'] > items[1]['_col.2']
        t.tables[0].tableSchema.columns[1].datatype.base = 'integer'
        items = list(t.tables[0])
        assert items[0]['_col.2'] < items[1]['_col.2']

    def test_separator(self, tmpdir):
        t = self._make_tablegroup(tmpdir, 'abc,')
        t.tables[0].tableSchema.columns[1].separator = ' '
        assert list(t.tables[0])[0]['_col.2'] == []

        t = self._make_tablegroup(tmpdir, 'abc,a')
        t.tables[0].tableSchema.columns[1].separator = ' '
        t.tables[0].tableSchema.columns[1].null = 'a'
        assert list(t.tables[0])[0]['_col.2'] is None

    def test_virtual_columns1(self, tmpdir):
        metadata = """\
{
  "@context": ["http://www.w3.org/ns/csvw", {"@language": "en"}],
  "tables": [
    {
      "url": "csv.txt",
      "tableSchema": {
        "columns": [{
          "name": "GID",
          "virtual": true
        }, {
          "name": "on_street",
          "titles": "On Street",
          "separator": ";",
          "datatype": "string"
        }]
      }
    }
  ]
}"""
        with pytest.raises(ValueError):
            self._make_tablegroup(tmpdir, data='', metadata=metadata)

    def test_virtual_columns2(self, tmpdir):
        metadata = """\
{
  "@context": ["http://www.w3.org/ns/csvw", {"@language": "en"}],
  "tables": [
    {
      "url": "csv.txt",
      "tableSchema": {
        "columns": [{
          "name": "GID",
          "datatype": "string"
        }, {
          "name": "copy",
          "valueUrl": "#{GID}",
          "virtual": true
        }]
      }
    }
  ]
}"""
        tg = self._make_tablegroup(tmpdir, data='GID\n123', metadata=metadata)
        item = list(tg.tables[0])[0]
        assert item['copy'] == '#123'

    def test_write(self, tmpdir):
        data = """\
GID,On Street,Species,Trim Cycle,Inventory Date
1,ADDISON AV,Celtis australis,Large Tree Routine Prune,10/18/2010
2,EMERSON ST,Liquidambar\tstyraciflua,Large Tree Routine Prune,6/2/2010"""
        metadata = """\
{
  "@context": ["http://www.w3.org/ns/csvw", {"@language": "en"}],
  "tables": [
    {
      "url": "csv.txt",
      "tableSchema": {
        "columns": [{
          "name": "GID",
          "titles": ["GID", "Generic Identifier"],
          "datatype": "string",
          "required": true
        }, {
          "name": "on_street",
          "titles": "On Street",
          "separator": ";",
          "datatype": "string"
        }, {
          "name": "species",
          "titles": "Species"
        }, {
          "name": "trim_cycle",
          "titles": "Trim Cycle",
          "datatype": "string"
        }, {
          "name": "inventory_date",
          "titles": "Inventory Date",
          "datatype": {"base": "date", "format": "M/d/yyyy"}
        }],
        "aboutUrl": "#gid-{GID}"
      }
    }
  ]
}"""
        tg = self._make_tablegroup(tmpdir, data=data, metadata=metadata)
        items = list(tg.tables[0])
        tg.tables[0].write(items)
        items_roundtrip = list(tg.tables[0])
        assert items == items_roundtrip
        tg.dialect = Dialect(delimiter='\t')
        tg.tables[0].tableSchema.columns[4].datatype.format = None
        tg.tables[0].tableSchema.columns[3].null = ['null']
        items[-1]['on_street'] = ['a', 'b']
        items[-1]['trim_cycle'] = None
        assert 'a;b\t"Liquidambar\tstyraciflua"\tnull\t2010-06-02' in \
                tg.tables[0].write(items, fname=None).decode('ascii')
        tg.dialect.header = False
        assert tg.tables[0].write([['1', [], '', None, None]], fname=None).decode('ascii') == \
               '1\t\t\tnull\t\r\n'

    def test_spec_examples(self, tmpdir, mocker):
        data = """\
GID,On Street,Species,Trim Cycle,Inventory Date
1,ADDISON AV,Celtis australis,Large Tree Routine Prune,10/18/2010
2,EMERSON ST,Liquidambar styraciflua,Large Tree Routine Prune,6/2/2010"""
        metadata = """\
{
  "@context": ["http://www.w3.org/ns/csvw", {"@language": "en"}],
  "dc:title": "Tree Operations",
  "dcat:keyword": ["tree", "street", "maintenance"],
  "dc:publisher": {
    "schema:name": "Example Municipality",
    "schema:url": {"@id": "http://example.org"}
  },
  "dc:license": {"@id": "http://opendefinition.org/licenses/cc-by/"},
  "dc:modified": {"@value": "2010-12-31", "@type": "xsd:date"},
  "tables": [
    {
      "url": "csv.txt",
      "tableSchema": {
        "columns": [{
          "name": "GID",
          "titles": ["GID", "Generic Identifier"],
          "dc:description": "An identifier for the operation on a tree.",
          "datatype": "string",
          "required": true
        }, {
          "name": "on_street",
          "titles": "On Street",
          "dc:description": "The street that the tree is on.",
          "datatype": "string"
        }, {
          "name": "species",
          "titles": "Species",
          "dc:description": "The species of the tree.",
          "datatype": "string"
        }, {
          "name": "trim_cycle",
          "titles": "Trim Cycle",
          "dc:description": "The operation performed on the tree.",
          "datatype": "string"
        }, {
          "name": "inventory_date",
          "titles": "Inventory Date",
          "dc:description": "The date of the operation that was performed.",
          "datatype": {"base": "date", "format": "M/d/yyyy"}
        }],
        "primaryKey": "GID",
        "aboutUrl": "#gid-{GID}"
      }
    }
  ]
}"""
        tg = self._make_tablegroup(tmpdir, data=data, metadata=metadata)
        items = list(tg.tables[0])
        assert len(items) == 2
        assert items[0]['inventory_date'] > items[1]['inventory_date']
        assert tg.tables[0].tableSchema.inherit('aboutUrl').expand(items[0]) == \
               '#gid-1'

        tg = self._make_tablegroup(tmpdir,
            data=data.replace('10/18/2010', '18.10.2010'), metadata=metadata)
        log = mocker.Mock()
        l = list(tg.tables[0].iterdicts(log=log))
        assert len(l) == 1
        assert log.warn.call_count == 1
        for fname, lineno, row in tg.tables[0].iterdicts(log=log, with_metadata=True):
            assert lineno == 3
            break

    def test_foreign_keys(self):
        with pytest.raises(ValueError):
            csvw.ForeignKey.fromdict({
                "columnReference": "countryRef",
                "reference": {
                    "resource": "http://example.org/countries.csv",
                    "schemaReference": "abc",
                    "columnReference": "countryCode"
                }
            })

    def test_foreignkeys(self, tmpdir):
        data = {
            "countries.csv": """\
countryCode,latitude,longitude,name
AD,42.5,1.6,Andorra
AE,23.4,53.8,United Arab Emirates
AF,33.9,67.7,Afghanistan""",
            "country_slice.csv": """\
countryRef,year,population
,1960,9616353
AF,1961,9799379
AF,1962,9989846"""}
        metadata = """\
{
  "@context": "http://www.w3.org/ns/csvw",
  "tables": [{
    "url": "countries.csv",
    "tableSchema": {
      "columns": [{
        "name": "countryCode",
        "datatype": "string",
        "propertyUrl": "http://www.geonames.org/ontology{#_name}"
      }, {
        "name": "latitude",
        "datatype": "number"
      }, {
        "name": "longitude",
        "datatype": "number"
      }, {
        "name": "name",
        "datatype": "string"
      }],
      "aboutUrl": "http://example.org/countries.csv{#countryCode}",
      "propertyUrl": "http://schema.org/{_name}",
      "primaryKey": "countryCode"
    }
  }, {
    "url": "country_slice.csv",
    "tableSchema": {
      "columns": [{
        "name": "countryRef",
        "valueUrl": "http://example.org/countries.csv{#countryRef}"
      }, {
        "name": "year",
        "datatype": "gYear"
      }, {
        "name": "population",
        "datatype": "integer"
      }],
      "foreignKeys": [{
        "columnReference": "countryRef",
        "reference": {
          "resource": "countries.csv",
          "columnReference": "countryCode"
        }
      },
      {
        "columnReference": "countryRef",
        "reference": {
          "schemaReference": "countries.json",
          "columnReference": "countryCode"
        }
      }]
    }
  }]
}"""
        tg = self._make_tablegroup(tmpdir, data=data, metadata=metadata)
        tg.tabledict['countries.csv'].check_primary_key()
        tg.check_referential_integrity()
        (tmpdir / 'country_slice.csv').write_text(
            data['country_slice.csv'].replace('AF', 'AX'), encoding='utf-8')
        with pytest.raises(ValueError):
            tg.check_referential_integrity()

        data['countries.csv'] = data['countries.csv'].replace('AF', 'AD')
        tg = self._make_tablegroup(tmpdir, data=data, metadata=metadata)
        with pytest.raises(ValueError):
            tg.tabledict['countries.csv'].check_primary_key()
        tg.to_file(tg._fname)

    def test_foreignkeys_2(self, tmpdir):
        data = {
            "countries.csv": """\
countryCode,name
AD,Andorra
AE,United Arab Emirates
AF,Afghanistan""",
            "country_slice.csv": """\
countryRef,year,population
AF;AD,9616353
AF,9799379"""}
        metadata = """\
{
  "@context": "http://www.w3.org/ns/csvw",
  "tables": [{
    "url": "countries.csv",
    "tableSchema": {
      "columns": [
        {"name": "countryCode", "datatype": "string"},
        {"name": "name", "datatype": "string"}
      ],
      "primaryKey": "countryCode"
    }
  }, {
    "url": "country_slice.csv",
    "tableSchema": {
      "columns": [
        {"name": "countryRef", "separator": ";"},
        {"name": "population", "datatype": "integer"}
      ],
      "foreignKeys": [{
        "columnReference": "countryRef",
        "reference": {
          "resource": "countries.csv",
          "columnReference": "countryCode"
        }
      }]
    }
  }]
}"""
        tg = self._make_tablegroup(tmpdir, data=data, metadata=metadata)
        tg.check_referential_integrity()
        (tmpdir / 'country_slice.csv').write_text(
            data['country_slice.csv'].replace('AF;AD', 'AF;AX'), encoding='utf-8')
        with pytest.raises(ValueError):
            tg.check_referential_integrity()
