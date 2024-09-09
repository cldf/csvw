import sys
import json
import shutil
import decimal
import pathlib
import datetime
import operator
import warnings
import collections

from csvw.metadata import json_open

import pytest

import csvw
from csvw.dsv import Dialect

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


def test_URITemplate():
    ut = csvw.URITemplate('http://example.org')
    assert ut == csvw.URITemplate('http://example.org')
    assert ut == 'http://example.org'
    assert ut != csvw.URITemplate('https://example.org')
    assert ut != 1


@pytest.mark.parametrize(
    'link,base,res',
    [
        ('abc.csv', None, 'abc.csv'),
        ('abc.csv', 'http://example.com', 'http://example.com/abc.csv'),
        ('abc.csv', pathlib.Path('.'), pathlib.Path('abc.csv')),
        ('abc.csv', pathlib.Path(__file__), pathlib.Path(__file__).parent / 'abc.csv'),
        ('http://example.com', pathlib.Path('.'), 'http://example.com')
    ]
)
def test_Link(link, base, res):
    assert str(csvw.Link(link)) == str(link)
    assert csvw.Link(link).resolve(base) == res


class TestColumnEquality(object):

    def test_get_column(self):
        t1 = csvw.Table.fromvalue({
            "url": '1.csv',
            "tableSchema": {"columns": [{"name": "col1", "datatype": "string"}]}
        })
        t2 = csvw.Table.fromvalue({
            "url": '2.csv',
            "tableSchema": {"columns": [{"name": "col1", "datatype": "string"}]}
        })
        # Columns derived from identical specifications are considered equal even if they are used
        # in different tables:
        assert t1.tableSchema.columns[0] == t2.tableSchema.columns[0]


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
        # We support 3 ways of retrieving a column: by name, by title or by propertyUrl:
        assert t.get_column('col1').name == 'col1'
        assert t.get_column('http://example.org').name == 'col2'
        assert t.get_column('xyz').name is None


class TestDialect(object):

    @staticmethod
    def _roundtrip(t, fpath, *items):
        t.write(items, fname=fpath)
        return fpath.read_text(encoding='utf-8'), list(t.iterdicts(fname=fpath))

    @pytest.mark.xfail(sys.version_info >= (3, 10), reason="https://bugs.python.org/issue44861")
    def test_doubleQuote(self, tmp_path):
        fpath = tmp_path / 'test'
        t = csvw.Table.fromvalue({
            "url": fpath,
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
        assert r'""a\\b\c\""d' in c
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

    @pytest.mark.xfail(reason='commentPrefix is checked only after csv.reader has parsed the line')
    def test_commentPrefix(self, tmp_path):
        fpath = tmp_path / 'test'
        t = csvw.TableGroup.fromvalue({
            "dialect": {"commentPrefix": "$"},
            "tables": [
                {
                    "url": str(fpath),
                    "tableSchema": {"columns": [{"name": "col1", "datatype": "string"}]}}]
        })
        t._fname = fpath
        fpath.write_text("""col1\n"$val"\n""", encoding='utf8')
        res = list(t.tables[0])
        assert res[0]['col1'] == '$val'


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

        with pytest.raises(ValueError):
            col = csvw.Column.fromvalue(
                {'separator': ' ', 'datatype': {'base': 'string', 'minLength': 3}})
            col.read('abc ab')

    def test_read_required_empty_string(self):
        col = csvw.Column.fromvalue({'required': True})
        with pytest.raises(ValueError):
            col.read('')

    def test_read_required_empty_string_no_null(self):
        col = csvw.Column.fromvalue({'required': True, 'null': None})
        assert col.read('') == ''

    def test_reuse_datatype(self):
        col1 = csvw.Column(name='col1', datatype={'base': 'string', 'format': '[0-9]+[a-z]+'})
        col2 = csvw.Column(name='col2', datatype=col1.datatype)
        assert col2.datatype.format

    def test_serialize_empty_null(self):
        col = csvw.Column.fromvalue({'name': 'col', 'null': []})
        assert col.read('') == ''
        ser = col.asdict()
        assert 'null' in ser
        assert csvw.Column.fromvalue(ser).read('') == ''

        table = csvw.Table.fromvalue({'url': 'x', 'tableSchema': {'columns': [ser]}})
        assert table.tableSchema.columns[0].inherit_null() == []


def test_Schema():
    from csvw.metadata import Schema

    with pytest.warns(UserWarning, match='uplicate'):
        Schema.fromvalue({'columns': [{'name': 'a'}, {'titles': 'a'}]})


def _make_table_like(cls, tmp_path, data=None, metadata=None, mdname=None):
    md = tmp_path / 'md'
    if metadata is None:
        shutil.copy(FIXTURES / mdname, md)
    else:
        md.write_text(str(metadata), encoding='utf-8')
    if isinstance(data, dict):
        for fname, content in data.items():
            (tmp_path / fname).write_text(content, encoding='utf-8')
    else:
        data = data or (FIXTURES / 'csv.txt').read_text(encoding='utf-8')
        with (tmp_path / 'csv.txt').open('w', encoding='utf-8', newline='') as f:
            f.write(data)
    return cls.from_file(str(md))


def _load_json(path):
    with json_open(str(path)) as f:
        return json.load(f)


class TestTable(object):

    @staticmethod
    def _make_table(tmp_path, data=None, metadata=None):
        return _make_table_like(
            csvw.Table, tmp_path, data=data, metadata=metadata, mdname='csv.txt-table-metadata.json')

    def test_roundtrip(self, tmp_path):
        t = self._make_table(tmp_path)
        assert _load_json(t.to_file(tmp_path / 'out')) == \
               _load_json(FIXTURES / 'csv.txt-table-metadata.json')
        t.common_props['dc:title'] = 'the title'
        t.aboutUrl = 'http://example.org/{ID}'
        assert _load_json(t.to_file(tmp_path / 'out')) != \
               _load_json(FIXTURES / 'csv.txt-table-metadata.json')
        assert _load_json(t.to_file(tmp_path / 'out', omit_defaults=False)) != \
               _load_json(FIXTURES / 'csv.txt-table-metadata.json')

    def test_read_write(self, tmp_path):
        t = self._make_table(tmp_path)
        items = list(t)
        assert len(items) == 2
        t.write(items, fname=tmp_path / 'out.csv')
        assert tmp_path.joinpath('out.csv').read_text('utf-8-sig').strip() == \
               FIXTURES.joinpath('csv.txt').read_text('utf-8-sig').strip()

    def test_iteritems_column_renaming(self, tmp_path):
        t = self._make_table(tmp_path)
        items = list(t)
        # The metadata specifies "ID" as name of the first column:
        assert 'ID' in items[0]

        md = t.asdict()
        md['tableSchema']['columns'][0]['name'] = 'xyz'
        t = self._make_table(tmp_path, metadata=json.dumps(md))
        items = list(t)
        assert 'xyz' in items[0]

        del md['tableSchema']['columns'][0]['name']
        md['tableSchema']['columns'][0]['titles'] = 'abc'
        t = self._make_table(tmp_path, metadata=json.dumps(md))
        items = list(t)
        assert 'abc' in items[0]

    def test_unspecified_column_in_table_without_url(self, tmp_path):
        t = csvw.Table.fromvalue({
            "@context": ["http://www.w3.org/ns/csvw", {"@language": "en"}],
            "url": "x",
            "tableSchema": {
                "columns": [
                    {"name": "ID", "datatype": {"base": "string", "minLength": 3}},
                    {"datatype": "string"}
                ]
            }
        })
        data = tmp_path / 'test.csv'
        data.write_text('ID,b,c\nabc,2,3', encoding='utf8')
        with pytest.warns(UserWarning):
            list(t.iterdicts(fname=str(data)))


class TestTableGroup(object):

    @staticmethod
    def _make_tablegroup(tmp_path, data=None, metadata=None):
        return _make_table_like(
            csvw.TableGroup, tmp_path, data=data, metadata=metadata, mdname='csv.txt-metadata.json')

    def test_from_frictionless(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            tg = csvw.TableGroup.from_frictionless_datapackage(FIXTURES / 'datapackage.json')
            assert list(tg.tables[0])

    def test_iteritems_column_renaming(self):
        t = csvw.TableGroup.from_file(FIXTURES / 'test.tsv-metadata.json')
        items = list(t.tables[0])
        assert items[0] == {'precinct': '1', 'province': 'Hello', 'territory': 'world'}

    def test_roundtrip(self, tmp_path):
        t = self._make_tablegroup(tmp_path)
        assert _load_json(t.to_file(tmp_path / 'out')) == \
               _load_json(FIXTURES / 'csv.txt-metadata.json')
        t.common_props['dc:title'] = 'the title'
        t.aboutUrl = 'http://example.org/{ID}'
        assert _load_json(t.to_file(tmp_path / 'out')) != \
               _load_json(FIXTURES / 'csv.txt-metadata.json')
        assert _load_json(t.to_file(tmp_path / 'out', omit_defaults=False)) != \
               _load_json(FIXTURES / 'csv.txt-metadata.json')

    def test_copy(self, tmp_path):
        t = csvw.TableGroup.from_file(FIXTURES / 'csv.txt-metadata.json')
        l = len(list(t.tabledict['csv.txt']))
        assert not tmp_path.joinpath('csv.txt-metadata.json').exists()
        t.copy(tmp_path)
        assert tmp_path.joinpath('csv.txt-metadata.json').exists()
        assert tmp_path.joinpath('csv.txt').exists()
        # Make sure the copied TableGroup reads from the new files:
        tmp_path.joinpath('csv.txt').write_text(
            tmp_path.joinpath('csv.txt').read_text('utf8') + '\nabc,b', 'utf8')
        assert len(list(t.tabledict['csv.txt'])) == l + 1

    def test_write_all(self, tmp_path):
        t = self._make_tablegroup(tmp_path)
        tmp_path.joinpath('x').mkdir()
        nmd = tmp_path.joinpath('x', 'cldf-metadata.json')
        t.write(nmd, **t.read())
        t2 = csvw.TableGroup.from_file(nmd)
        for tname in t.tabledict:
            for r1, r2 in zip(t.tabledict[tname].__iter__(), t2.tabledict[tname].__iter__()):
                assert r1 == r2

    def test_write_strict(self, tmp_path):
        t = self._make_tablegroup(tmp_path)
        tmp_path.joinpath('x').mkdir()
        nmd = tmp_path.joinpath('x', 'cldf-metadata.json')
        t.write(nmd, **{'csv.txt': [{'ID': '5', 'other': 'x'}]})
        with pytest.raises(ValueError):
            t.write(nmd, strict=True, **{'csv.txt': [{'ID': '5', 'other': 'x'}]})

    def test_all(self, tmp_path):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t = self._make_tablegroup(tmp_path)
            assert len(list(t.tables[0])) == 2

            # Test appication of null property on columns:
            t = self._make_tablegroup(tmp_path)
            t.tables[0].tableSchema.columns[1].null = ['line']
            assert list(t.tables[0])[0]['_col.2'] is None

            t = self._make_tablegroup(tmp_path)
            t.tables[0].tableSchema.columns[1].separator = 'n'
            assert list(t.tables[0])[0]['_col.2'] == ['li', 'e']

            t = self._make_tablegroup(tmp_path)
            t.tables[0].tableSchema.columns[1].titles = csvw.NaturalLanguage('colname')
            assert 'colname' in list(t.tables[0])[0]

            t = self._make_tablegroup(tmp_path)
            t.dialect.header = True
            assert len(list(t.tables[0])) == 1

            t = self._make_tablegroup(tmp_path, 'edferd,f\r\nabc,')
            t.tables[0].tableSchema.columns[0].required = True
            t.tables[0].tableSchema.columns[0].null = ['abc']
            with pytest.raises(
                    ValueError, match=r'csv\.txt:2:1 ID: required column value is missing'):
                list(t.tables[0])

            t = self._make_tablegroup(tmp_path, ',')
            t.tables[0].tableSchema.columns[0].required = True
            with pytest.raises(ValueError):
                list(t.tables[0])

            t = self._make_tablegroup(tmp_path, 'abc,9\r\ndef,10')
            items = list(t.tables[0])
            assert items[0]['_col.2'] > items[1]['_col.2']
            t.tables[0].tableSchema.columns[1].datatype.base = 'integer'
            items = list(t.tables[0])
            assert items[0]['_col.2'] < items[1]['_col.2']

    def test_separator(self, tmp_path):
        t = self._make_tablegroup(tmp_path, 'abc,')
        t.tables[0].tableSchema.columns[1].separator = ' '
        assert list(t.tables[0])[0]['_col.2'] == []

        t = self._make_tablegroup(tmp_path, 'abc,a')
        t.tables[0].tableSchema.columns[1].separator = ' '
        t.tables[0].tableSchema.columns[1].null = 'a'
        assert list(t.tables[0])[0]['_col.2'] is None

    def test_None_value_in_common_props(self, tmp_path):
        f = tmp_path / 'test.json'
        tg = csvw.TableGroup()
        tg.common_props['dc:title'] = None
        tg.to_file(f)
        assert 'dc:title' in _load_json(f)

    def test_virtual_columns1(self, tmp_path):
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
            self._make_tablegroup(tmp_path, data='', metadata=metadata)

    def test_virtual_columns2(self, tmp_path):
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
        tg = self._make_tablegroup(tmp_path, data='GID\n123', metadata=metadata)
        item = list(tg.tables[0])[0]
        assert item['copy'] == '#123'

    def test_required_column1(self, tmp_path, mocker):
        metadata = """\
{
  "@context": ["http://www.w3.org/ns/csvw", {"@language": "en"}],
  "tables": [{"url": "csv.txt", "tableSchema": {"columns": [{"name": "GID", "required": true}]}}]
}"""
        tg = self._make_tablegroup(tmp_path, data='x\n123', metadata=metadata)
        with pytest.raises(ValueError):
            list(tg.tables[0])

        tg = self._make_tablegroup(tmp_path, data='x,GID\n123', metadata=metadata)
        log = mocker.Mock()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = list(tg.tables[0].iterdicts(log=log))
        assert log.warning.called
        assert len(res) == 0

    def test_write(self, tmp_path):
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
        tg = self._make_tablegroup(tmp_path, data=data, metadata=metadata)
        items = list(tg.tables[0])
        assert tg.tables[0].write(items) == len(items)
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

    def test_spec_examples(self, tmp_path, mocker):
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
        tg = self._make_tablegroup(tmp_path, data=data, metadata=metadata)
        items = list(tg.tables[0])
        assert len(items) == 2
        assert items[0]['inventory_date'] > items[1]['inventory_date']
        assert tg.tables[0].tableSchema.inherit('aboutUrl').expand(items[0]) == \
               '#gid-1'

        tg = self._make_tablegroup(tmp_path,
            data=data.replace('10/18/2010', '18.10.2010'), metadata=metadata)
        log = mocker.Mock()
        l = list(tg.tables[0].iterdicts(log=log))
        assert len(l) == 1
        assert log.warning.call_count == 1
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

    def test_foreignkeys(self, tmp_path, mocker):
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
        tg = self._make_tablegroup(tmp_path, data=data, metadata=metadata)
        assert tg.tabledict['countries.csv'].check_primary_key()
        assert tg.check_referential_integrity()
        (tmp_path / 'country_slice.csv').write_text(
            data['country_slice.csv'].replace('AF', 'AX'), encoding='utf-8')
        with pytest.raises(ValueError):
            tg.check_referential_integrity()
        assert not tg.check_referential_integrity(log=mocker.Mock())

        # Now remove the foreign keys:
        tg.tabledict['country_slice.csv'].tableSchema.foreignKeys = []
        tg.check_referential_integrity()

        # And add them back in:
        with pytest.raises(ValueError):
            tg.tabledict['country_slice.csv'].add_foreign_key(
                'zcountryRef', 'countries.csv', 'countryCode')
        tg.tabledict['country_slice.csv'].add_foreign_key(
            'countryRef', 'countries.csv', 'countryCode')
        with pytest.raises(ValueError):
            tg.check_referential_integrity()

        data['countries.csv'] = data['countries.csv'].replace('AF', 'AD')
        tg = self._make_tablegroup(tmp_path, data=data, metadata=metadata)
        with pytest.raises(ValueError):
            tg.tabledict['countries.csv'].check_primary_key()
        assert not tg.tabledict['countries.csv'].check_primary_key(log=mocker.Mock())
        tg.to_file(tg._fname)

    def test_foreignkeys_2(self, tmp_path):
        data = {
            "countries.csv": """\
countryCode,name
AD,Andorra
AE,United Arab Emirates
AF,Afghanistan""",
            "country_slice.csv": """\
countryRef,year,population
AF;AD,9616353
NA,12345
AF,9799379"""}
        metadata = """{
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
        {"name": "countryRef", "separator": ";", "null": ["NA"]},
        {"name": "population", "datatype": "integer"}
      ],
      "foreignKeys": [{
        "columnReference": "countryRef",
        "reference": {"resource": "countries.csv", "columnReference": "countryCode"}
    }]}}]}"""
        tg = self._make_tablegroup(tmp_path, data=data, metadata=metadata)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tg.check_referential_integrity()
            (tmp_path / 'country_slice.csv').write_text(
                data['country_slice.csv'].replace('AF;AD', 'AF;AX'), encoding='utf-8')
            with pytest.raises(ValueError):
                tg.check_referential_integrity()

    def test_remote_schema(self, tmp_path):
        import requests_mock

        with requests_mock.Mocker() as m:
            schema = """
            {"columns": [
                {"name": "countryCode", "datatype": "string"},
                {"name": "name", "datatype": "string"}]}
            """
            m.get("http://example.com/schema", content=schema.encode('utf8'))
            tg = self._make_tablegroup(
                tmp_path,
                metadata="""{
  "@context": "http://www.w3.org/ns/csvw",
  "tables": [{"url": "countries.csv", "tableSchema": "http://example.com/schema"}]}""")
            assert len(tg.tables[0].tableSchema.columns) == 2

        # The remote content has been inlined:
        out = tmp_path / 'md.json'
        tg.to_file(out)
        assert 'countryCode' in out.read_text(encoding='utf8')

    def test_missing_data(self, tmp_path):
        data = {  # The last row is missing one column
            "countries.csv": """\
countryCode,name,custom
AD,Andorra,a
AF,Afghanistan"""
        }
        metadata = """{
  "@context": "http://www.w3.org/ns/csvw",
  "tables": [{
    "url": "countries.csv",
    "tableSchema": {
      "columns": [
        {"name": "countryCode", "datatype": "string"},
        {"name": "name", "datatype": "string"},
        {"name": "custom", "datatype": "string"}
      ],
      "primaryKey": "countryCode"
    }}]}"""
        tg = self._make_tablegroup(tmp_path, data=data, metadata=metadata)
        rows = list(tg.tables[0])
        assert 'custom' in rows[0]
        assert 'custom' in rows[1]


def test_zip_support(tmp_path):
    tg = csvw.TableGroup.from_file(FIXTURES / 'zipped-metadata.json')
    res = list(tg.tables[0])
    assert len(res) == 2
    assert res[0]['ID'] == 'abc'

    out = tmp_path / 'zipped.csv'
    tg.tables[0].write(res, fname=out, _zipped=True)
    assert not out.exists() and out.parent.joinpath(out.name + '.zip').exists()

    shutil.copy(FIXTURES / 'zipped-metadata.json', out.parent)
    tg = csvw.TableGroup.from_file(out.parent / 'zipped-metadata.json')
    assert res == list(tg.tables[0])

    tg.write(out.parent / 'md.json', _zipped=True, **{'zipped.csv': res + res})
    assert len(list(csvw.TableGroup.from_file(out.parent / 'md.json').tables[0])) == 4


def test_from_url():
    import requests_mock

    def content(req, ctx):
        ctx.status_code = 200
        return FIXTURES.joinpath(req.url.split('/')[-1]).read_bytes()

    with requests_mock.Mocker() as m:
        m.get(
            requests_mock.ANY,
            content=content)

        t = csvw.Table.from_file('http://example.com/csv.txt-table-metadata.json')
        assert len(list(t)) == 2


def test_datatype_limits(tmp_path):
    tg = csvw.Table(url='x')
    tg.tableSchema.columns.append(
        csvw.Column.fromvalue(dict(name='dec', datatype='decimal'))
    )
    tg.tableSchema.columns[0].datatype.minimum = decimal.Decimal('0.1')
    tg.to_file(tmp_path / 'md.json')
    tg = csvw.Table.from_file(tmp_path / 'md.json')
    assert isinstance(tg.tableSchema.columns[0].datatype.minimum, decimal.Decimal)

    tg = csvw.Table(url='x')
    tg.tableSchema.columns.append(
        csvw.Column.fromvalue(dict(name='date', datatype='date'))
    )
    tg.tableSchema.columns[0].datatype.maximum = datetime.date(1999, 12, 12)
    tg.to_file(tmp_path / 'md.json')
    tg = csvw.Table.from_file(tmp_path / 'md.json')
    tg.tableSchema.columns[0].datatype.parse(datetime.date.today().isoformat())
    with pytest.raises(ValueError):
        tg.tableSchema.columns[0].datatype.read(datetime.date.today().isoformat())


@pytest.fixture
def tables():
    return [
        {
            "url": "countries.csv",
            "tableSchema": {
                "columns": [{"name": "countryCode", "datatype": "string"}],
                "primaryKey": "countryCode"
            }
        }, {
            "url": "country_slice.csv",
            "tableSchema": {
                "columns": [
                    {"name": "countryRef", "datatype": "string"},
                ],
                "foreignKeys": [{
                    "columnReference": "countryRef",
                    "reference": {"resource": "countries.csv", "columnReference": "countryCode"}
                }]
            }
        }
    ]


@pytest.mark.parametrize(
    'breakage,match_error',
    [
        (lambda t: t, None),
        (lambda t: operator.setitem(t[1]['tableSchema']['columns'][0], 'datatype', 'integer'),
         'datatype'),
        (lambda t: operator.setitem(t[0], 'url', 'other'),
         'missing table'),
        (lambda t: operator.setitem(t[1]['tableSchema']['columns'][0], 'name', 'other'),
         'missing column'),
        (lambda t: operator.setitem(
            t[1]['tableSchema']['foreignKeys'][0], 'columnReference', ['a', 'b']),
         'non-matching number'),
    ]
)
def test_fk_non_matching_datatypes(tables, breakage, match_error):
    breakage(tables)
    tg = csvw.TableGroup.fromvalue(dict(tables=tables))
    if match_error:
        with pytest.raises(ValueError, match=match_error):
            tg.check_referential_integrity()
    else:
        tg.validate_schema()


def test_CSVW():
    res = csvw.CSVW(FIXTURES / 'csv.txt')
    assert res.to_json()
    res = csvw.CSVW(FIXTURES / 'csv.txt-table-metadata.json')
    assert res.to_json()
