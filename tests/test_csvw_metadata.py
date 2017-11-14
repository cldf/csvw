# coding: utf8
from __future__ import unicode_literals, print_function, division
from unittest import TestCase
from collections import OrderedDict
import json

from mock import Mock
import clldutils
from clldutils.path import Path, copy, write_text, read_text
from clldutils.testing import WithTempDir
from clldutils import jsonlib
from clldutils.dsv import Dialect

FIXTURES = Path(clldutils.__file__).parent.joinpath('tests', 'fixtures')


class TestColumnAccess(TestCase):
    def test_get_column(self):
        from clldutils.csvw.metadata import Table

        t = Table.fromvalue({
            "url": '',
            "tableSchema": {
                "columns": [
                    {"name": "col1", "datatype": "string"},
                    {"datatype": "string", "titles": "xyz"},
                    {"name": "col2", "propertyUrl": "http://example.org"},
                ]
            }
        })
        self.assertEqual(t.get_column('col1').name, 'col1')
        self.assertEqual(t.get_column('http://example.org').name, 'col2')
        self.assertEqual(t.get_column('xyz').name, None)


class TestDialect(WithTempDir):
    def _roundtrip(self, t, fname, *items):
        t.write(items, fname=fname)
        return read_text(fname), list(t.iterdicts(fname=fname))

    def test_doubleQuote(self):
        from clldutils.csvw.metadata import Table

        fname = self.tmp_path('test')
        t = Table.fromvalue({
            "url": fname.as_posix(),
            "dialect": {"doubleQuote": True},
            "tableSchema": {
                "columns": [
                    {"name": "col1", "datatype": "string"},
                    {"name": "col2", "datatype": "string"},
                ]
            }
        })
        value = r'"a\\b\c\"d'
        c, res = self._roundtrip(t, fname, {"col1": "", "col2": value})
        self.assertIn(r'""a\\\\b\\c\\""d', c)
        self.assertEqual(res[0]['col2'], value)

        t.dialect.doubleQuote = False
        c, res = self._roundtrip(t, fname, {"col1": "", "col2": value})
        self.assertIn(r'\"a\\\\b\\c\\\"d', c)
        self.assertEqual(res[0]['col2'], value)

        t.dialect.quoteChar = '*'
        c, res = self._roundtrip(t, fname, {"col1": "", "col2": value})
        self.assertEqual(res[0]['col2'], value)

        t.dialect.doubleQuote = True
        c, res = self._roundtrip(t, fname, {"col1": "", "col2": value})
        self.assertEqual(res[0]['col2'], value)

        value = value.replace('"', '*')
        c, res = self._roundtrip(t, fname, {"col1": "", "col2": value})
        self.assertEqual(res[0]['col2'], value)


class NaturalLanguageTests(TestCase):
    def test_string(self):
        from clldutils.csvw.metadata import NaturalLanguage

        l = NaturalLanguage('abc')
        self.assertEqual(l.getfirst(), 'abc')
        self.assertEqual(l.get(None), ['abc'])
        self.assertEqual('{0}'.format(l), 'abc')

    def test_array(self):
        from clldutils.csvw.metadata import NaturalLanguage

        l = NaturalLanguage(['abc', 'def'])
        self.assertEqual(l.getfirst(), 'abc')
        self.assertEqual(l.get(None), ['abc', 'def'])
        self.assertEqual('{0}'.format(l), 'abc')

    def test_object(self):
        from clldutils.csvw.metadata import NaturalLanguage

        l = NaturalLanguage(OrderedDict([('en', ['abc', 'def']), ('de', 'äöü')]))
        self.assertEqual(l.getfirst('de'), 'äöü')
        self.assertEqual(l.get('en'), ['abc', 'def'])
        self.assertEqual('{0}'.format(l), 'abc')

    def test_error(self):
        from clldutils.csvw.metadata import NaturalLanguage

        with self.assertRaises(ValueError):
            NaturalLanguage(1)

    def test_serialize(self):
        from clldutils.csvw.metadata import NaturalLanguage

        l = NaturalLanguage('ä')
        self.assertEqual(json.dumps(l.asdict()), '"\\u00e4"')
        l.add('a')
        self.assertEqual(json.dumps(l.asdict()), '["\\u00e4", "a"]')
        l.add('ö', 'de')
        self.assertEqual(
            json.dumps(l.asdict()), '{"und": ["\\u00e4", "a"], "de": "\\u00f6"}')


class TestColumn(TestCase):

    def _make_column(self, value):
        from clldutils.csvw.metadata import Column

        return Column.fromvalue(value)

    def test_read_rite_with_separator(self):
        col = self._make_column({'separator': ';', 'null': 'nn'})
        for parsed, serialized in [
                (['a', 'b'], 'a;b'),
                (['a', None], 'a;nn'),
                ([], '')]:
            self.assertEqual(col.read(serialized), parsed)
            self.assertEqual(col.write(parsed), serialized)
        self.assertEqual(col.write(None), '')
        self.assertEqual(col.write(''), '')

    def test_read_required_empty_string(self):
        col = self._make_column({'required': True})
        with self.assertRaises(ValueError):
            col.read('')

    def test_read_required_empty_string_no_null(self):
        col = self._make_column({'required': True, 'null': None})
        self.assertEqual(col.read(''), '')


class LinkTests(TestCase):
    def test_link(self):
        from clldutils.csvw.metadata import Link

        l = Link('a.csv')
        self.assertEqual('{0}'.format(l), l.resolve(None))
        self.assertEqual('http://example.org/a.csv', l.resolve('http://example.org'))
        base = Path('.')
        self.assertEqual(base, l.resolve(base).parent)


class TableGroupTests(WithTempDir):
    def _make_tablegroup(self, data=None, metadata=None):
        from clldutils.csvw.metadata import TableGroup

        md = self.tmp_path('md')
        if metadata is None:
            copy(FIXTURES.joinpath('csv.txt-metadata.json'), md)
        else:
            write_text(md, metadata)
        if isinstance(data, dict):
            for fname, content in data.items():
                write_text(self.tmp_path(fname), content)
        else:
            write_text(
                self.tmp_path('csv.txt'),
                data or read_text(FIXTURES.joinpath('csv.txt')),
                newline='')
        return TableGroup.from_file(md)

    def test_roundtrip(self):
        t = self._make_tablegroup()
        self.assertEqual(
            jsonlib.load(t.to_file(self.tmp_path('out'))),
            jsonlib.load(FIXTURES.joinpath('csv.txt-metadata.json')))
        t.common_props['dc:title'] = 'the title'
        t.aboutUrl = 'http://example.org/{ID}'
        self.assertNotEqual(
            jsonlib.load(t.to_file(self.tmp_path('out'))),
            jsonlib.load(FIXTURES.joinpath('csv.txt-metadata.json')))
        self.assertNotEqual(
            jsonlib.load(t.to_file(self.tmp_path('out'), omit_defaults=False)),
            jsonlib.load(FIXTURES.joinpath('csv.txt-metadata.json')))

    def test_all(self):
        from clldutils.csvw.metadata import NaturalLanguage

        t = self._make_tablegroup()
        self.assertEqual(len(list(t.tables[0])), 2)

        # Test appication of null property on columns:
        t = self._make_tablegroup()
        t.tables[0].tableSchema.columns[1].null = ['line']
        self.assertIsNone(list(t.tables[0])[0]['_col.2'])

        t = self._make_tablegroup()
        t.tables[0].tableSchema.columns[1].separator = 'n'
        self.assertEqual(list(t.tables[0])[0]['_col.2'], ['li', 'e'])

        t = self._make_tablegroup()
        t.tables[0].tableSchema.columns[1].titles = NaturalLanguage('colname')
        self.assertIn('colname', list(t.tables[0])[0])

        t = self._make_tablegroup()
        t.dialect.header = True
        self.assertEqual(len(list(t.tables[0])), 1)

        t = self._make_tablegroup('edferd,f\r\nabc,')
        t.tables[0].tableSchema.columns[0].required = True
        t.tables[0].tableSchema.columns[0].null = ['abc']
        with self.assertRaises(ValueError) as e:
            list(t.tables[0])
        self.assertIn(
            'csv.txt:2:1 ID: required column value is missing', '{0}'.format(e.exception))

        t = self._make_tablegroup(',')
        t.tables[0].tableSchema.columns[0].required = True
        with self.assertRaises(ValueError):
            list(t.tables[0])

        t = self._make_tablegroup('abc,9\r\ndef,10')
        items = list(t.tables[0])
        self.assertGreater(items[0]['_col.2'], items[1]['_col.2'])
        t.tables[0].tableSchema.columns[1].datatype.base = 'integer'
        items = list(t.tables[0])
        self.assertLess(items[0]['_col.2'], items[1]['_col.2'])

    def test_separator(self):
        t = self._make_tablegroup('abc,')
        t.tables[0].tableSchema.columns[1].separator = ' '
        self.assertEqual(list(t.tables[0])[0]['_col.2'], [])

        t = self._make_tablegroup('abc,a')
        t.tables[0].tableSchema.columns[1].separator = ' '
        t.tables[0].tableSchema.columns[1].null = 'a'
        self.assertIsNone(list(t.tables[0])[0]['_col.2'])

    def test_virtual_columns1(self):
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
        with self.assertRaises(ValueError):
            self._make_tablegroup(data='', metadata=metadata)

    def test_virtual_columns2(self):
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
        tg = self._make_tablegroup(data='GID\n123', metadata=metadata)
        item = list(tg.tables[0])[0]
        self.assertEqual(item['copy'], '#123')

    def test_write(self):
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
        tg = self._make_tablegroup(data=data, metadata=metadata)
        items = list(tg.tables[0])
        tg.tables[0].write(items)
        items_roundtrip = list(tg.tables[0])
        self.assertEqual(items, items_roundtrip)
        tg.dialect = Dialect(delimiter='\t')
        tg.tables[0].tableSchema.columns[4].datatype.format = None
        tg.tables[0].tableSchema.columns[3].null = ['null']
        items[-1]['on_street'] = ['a', 'b']
        items[-1]['trim_cycle'] = None
        self.assertIn(
            'a;b\t"Liquidambar\tstyraciflua"\tnull\t2010-06-02',
            tg.tables[0].write(items, fname=None).decode('ascii'))
        tg.dialect.header = False
        self.assertEqual(
            tg.tables[0].write([['1', [], '', None, None]], fname=None).decode('ascii'),
            '1\t\t\tnull\t\r\n')

    def test_spec_examples(self):
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
        tg = self._make_tablegroup(data=data, metadata=metadata)
        items = list(tg.tables[0])
        self.assertEqual(len(items), 2)
        self.assertGreater(items[0]['inventory_date'], items[1]['inventory_date'])
        self.assertEqual(
            tg.tables[0].tableSchema.inherit('aboutUrl').expand(items[0]), '#gid-1')

        tg = self._make_tablegroup(
            data=data.replace('10/18/2010', '18.10.2010'), metadata=metadata)
        log = Mock()
        l = list(tg.tables[0].iterdicts(log=log))
        self.assertEqual(len(l), 1)
        self.assertEqual(log.warn.call_count, 1)
        for fname, lineno, row in tg.tables[0].iterdicts(log=log, with_metadata=True):
            self.assertEqual(lineno, 3)
            break

    def test_foreign_keys(self):
        from clldutils.csvw.metadata import ForeignKey

        with self.assertRaises(ValueError):
            ForeignKey.fromdict({
                "columnReference": "countryRef",
                "reference": {
                    "resource": "http://example.org/countries.csv",
                    "schemaReference": "abc",
                    "columnReference": "countryCode"
                }
            })

    def test_foreignkeys(self):
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
        tg = self._make_tablegroup(data=data, metadata=metadata)
        tg.tabledict['countries.csv'].check_primary_key()
        tg.check_referential_integrity()
        write_text(
            self.tmp_path('country_slice.csv'),
            data['country_slice.csv'].replace('AF', 'AX'))
        with self.assertRaises(ValueError):
            tg.check_referential_integrity()

        data['countries.csv'] = data['countries.csv'].replace('AF', 'AD')
        tg = self._make_tablegroup(data=data, metadata=metadata)
        with self.assertRaises(ValueError):
            tg.tabledict['countries.csv'].check_primary_key()
        tg.to_file(tg._fname)

    def test_foreignkeys_2(self):
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
        tg = self._make_tablegroup(data=data, metadata=metadata)
        tg.check_referential_integrity()
        write_text(
            self.tmp_path('country_slice.csv'),
            data['country_slice.csv'].replace('AF;AD', 'AF;AX'))
        with self.assertRaises(ValueError):
            tg.check_referential_integrity()
