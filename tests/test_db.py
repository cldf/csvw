import sqlite3
from datetime import date

import pytest

from csvw import TableGroup, Column, Table, ForeignKey
from csvw.metadata import DATATYPES
from csvw.db import Database
from csvw._compat import pathlib

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


@pytest.fixture
def tg():
    return TableGroup.fromvalue({'tables': [
        {
            'url': 'data',
            'tableSchema': {
                'columns': []
            }
        }
    ]})


@pytest.fixture
def translate():
    def _t(t, c=None):
        if t == 'data' and c == 'v':
            return 'vv'
        if c:
            return c
        return t
    return _t


@pytest.mark.parametrize('datatype', [dt for dt in DATATYPES.values() if dt.name != 'time'])
def test_datatypes(tg, datatype):
    tg.tables[0].tableSchema.columns.extend([
        Column.fromvalue({'datatype': datatype.name, 'name': 'v1'}),
        Column.fromvalue({'datatype': datatype.name, 'name': 'v2'}),
    ])
    db = Database(tg)
    v = datatype.to_python(datatype.example)
    db.write(data=[{'v1': v, 'v2': None}])
    data = db.read()['data']
    assert data[0]['v1'] == v
    assert data[0]['v2'] is None


def test_list_valued(tg):
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'separator': '#', 'name': 'v'}))
    db = Database(tg)
    with pytest.raises(TypeError):
        db.write(data=[{'v': [1, 2, 3]}])
    db.write(data=[{'v': ['a', 'b', ' c']}, {'v': []}])
    data = db.read()['data']
    assert data[0]['v'] == ['a', 'b', ' c']
    assert data[1]['v'] == []


def test_required(tg):
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'required': 'True', 'name': 'v'}))
    db = Database(tg)
    with pytest.raises(sqlite3.IntegrityError):
        db.write(data=[{'v': None}])


@pytest.mark.parametrize(
    'datatype,value,error',
    [
        ({'base': 'decimal', 'minimum': -90, 'maximum': 90}, -100, True),
        ({'base': 'decimal', 'minimum': -90, 'maximum': 90}, 100, True),
        ({'base': 'decimal', 'minimum': -90, 'maximum': 90}, -10, False),
        ({'base': 'string', 'length': 3}, 'ab', True),
        ({'base': 'string', 'length': 3}, 'abcd', True),
        ({'base': 'string', 'length': 3}, 'abc', False),
        ({'base': 'string', 'minLength': 3}, 'ab', True),
        ({'base': 'string', 'minLength': 3}, 'abc', False),
        ({'base': 'string', 'maxLength': 3}, 'abcd', True),
        ({'base': 'string', 'maxLength': 3}, 'abc', False),
        ({'base': 'date', 'minimum': '2019-02-01'}, date(year=2018, month=2, day=1), True),
        ({'base': 'date', 'maximum': '2019-02-01'}, date(year=2018, month=2, day=1), False),
    ]
)
def test_constraints(tg, datatype, value, error):
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'datatype': datatype, 'name': 'v'}))
    db = Database(tg)
    if error:
        with pytest.raises(sqlite3.IntegrityError):
            db.write(data=[{'v': value}])
    else:
        db.write(data=[{'v': value}])


def test_file(tmpdir, tg):
    fname = tmpdir.join('test.sqlite')
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'name': 'v'}))
    db = Database(tg, fname=str(fname))
    db.write()
    assert fname.check()
    with pytest.raises(ValueError):
        db.write()


def test_foreign_keys(tg, translate):
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'name': 'v'}))
    tg.tables[0].tableSchema.primaryKey = ['v']
    tg.tables.append(Table.fromvalue({
        'url': 'ref',
        'tableSchema': {
            'columns': [{'name': 'ref'}],
            'foreignKeys': [
                {
                    'columnReference': 'ref',
                    'reference': {
                        'resource': 'data',
                        'columnReference': 'v',
                    }
                }
            ]
        }
    }))
    db = Database(tg, translate=translate)
    with pytest.raises(sqlite3.IntegrityError):
        db.write(ref=[{'ref': 'y'}], data=[{'v': 'x'}])
    db.write(ref=[{'ref': 'x'}], data=[{'v': 'x'}])
    # 'vv' is used as column name as specified by the translate fixture:
    assert 'vv' in db.read()['data'][0]


@pytest.fixture
def tg_with_foreign_keys(tg):
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'name': 'v'}))
    tg.tables[0].tableSchema.primaryKey = ['v']
    tg.tables.append(Table.fromvalue({
        'url': 'ref',
        'tableSchema': {
            # Define two list-valued foreign key:
            'columns': [
                {'name': 'pk'},
                {'name': 'ref1', 'separator': ';'},
                {'name': 'ref2', 'separator': ';'},
            ],
            'foreignKeys': [
                {
                    'columnReference': 'ref1',
                    'reference': {
                        'resource': 'data',
                        'columnReference': 'v',
                    }
                },
                {
                    'columnReference': 'ref2',
                    'reference': {
                        'resource': 'data',
                        'columnReference': 'v',
                    }
                }
            ],
            'primaryKey': ['pk']
        }
    }))
    return tg


def test_many_to_many(tg_with_foreign_keys):
    db = Database(tg_with_foreign_keys)
    with pytest.raises(sqlite3.IntegrityError):
        # Foreign key violates referential integrity:
        db.write(ref=[{'pk': '1', 'ref1': ['y']}], data=[{'v': 'x'}])

    db.write(ref=[{'pk': '1', 'ref1': ['y', 'x']}], data=[{'v': 'x'}, {'v': 'y'}])
    res = db.read()['ref'][0]
    # Associations between the same pair of tables are grouped by foreign key column:
    assert res['ref1'] == ['y', 'x']
    assert res['ref2'] == []


def test_many_to_many_no_context(tg_with_foreign_keys):
    class DatabaseWithoutContext(Database):
        def association_table_context(self, table, column, fkey):
            return fkey, '1234'

        def select_many_to_many(self, db, table, context):
            # Tables with at most one foreign key to another table can use the context
            # to store something else.
            return Database.select_many_to_many(self, db, table, None)

    db = DatabaseWithoutContext(tg_with_foreign_keys)
    db.write(ref=[{'pk': '1', 'ref1': ['y', 'x']}], data=[{'v': 'x'}, {'v': 'y'}])
    res = db.read()['ref'][0]
    # The context will then be returned for **each** foreign key column!
    assert res['ref2'] == [('y', '1234'), ('x', '1234')]


def test_many_to_many_self_referential(tg):
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'name': 'v'}))
    tg.tables[0].tableSchema.columns.append(Column.fromvalue({'name': 'ref', 'separator': ';'}))
    tg.tables[0].tableSchema.primaryKey = ['v']
    tg.tables[0].tableSchema.foreignKeys.append(ForeignKey.fromdict({
        'columnReference': 'ref',
        'reference': {
            'resource': 'data',
            'columnReference': 'v',
        }
    }))
    db = Database(tg)
    with pytest.raises(sqlite3.IntegrityError):
        db.write(data=[{'v': 'x', 'ref': ['y']}])
    db.write(data=[{'v': 'x', 'ref': []}, {'v': 'y', 'ref': ['x', 'y']}])
    assert db.read()['data'][1]['ref'] == ['x', 'y']


def test_integration():
    tg = TableGroup.from_file(FIXTURES / 'csv.txt-metadata.json')
    orig = tg.read()
    db = Database(tg)
    db.write_from_tg()
    for table, items in db.read().items():
        assert items == orig[table]


def test_write_file_exists(tmpdir):
    target = pathlib.Path(str(tmpdir / 'db.sqlite3'))
    target.touch(exist_ok=False)
    mtime = target.stat().st_mtime
    tg = TableGroup.from_file(FIXTURES / 'csv.txt-metadata.json')
    db = Database(tg, fname=target)
    with pytest.raises(ValueError, match=r'already exists'):
        db.write()
    db.write(force=True)
    assert target.stat().st_mtime > mtime
