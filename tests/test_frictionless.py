import json
import shutil
import pathlib
import warnings

import pytest

from csvw.dsv import UnicodeWriter
from csvw import TableGroup
from csvw.frictionless import DataPackage

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


@pytest.fixture
def tmpfixtures(tmp_path):
    shutil.copytree(pathlib.Path(__file__).parent / 'fixtures', tmp_path / 'fixtures')
    return tmp_path / 'fixtures'


@pytest.fixture
def datafactory(tmp_path):
    def make(fields, data):
        p = tmp_path / 'datapackage.json'
        with p.open(mode='wt') as f:
            rsc = dict(
                profile='tabular-data-resource',
                scheme='file',
                format='csv',
                path='data.csv',
                schema=dict(fields=fields),
            )
            json.dump(dict(resources=[rsc]), f)
        with UnicodeWriter(p.parent / 'data.csv') as w:
            w.writerow([f['name'] for f in fields])
            w.writerows(data)
        return p
    return make


def test_DataPackage_init():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        dp = DataPackage(dict(resources=[], name='x'))
        dp = DataPackage(dp)
        assert dp.to_tablegroup().common_props['dc:identifier'] == 'x'
        dp = DataPackage('{"resources": [], "name": "x", "id": "y"}')
        assert dp.to_tablegroup().common_props['dc:identifier'] == 'y'
        assert dp.to_tablegroup().common_props['dc:title'] == 'x'


def test_DataPackage_constraints(datafactory):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        dp = datafactory([{'name': 'col', 'constraints': {'maxLength': 3}}], [['abcd']])
        with pytest.raises(ValueError):
            _ = list(DataPackage(dp).to_tablegroup().tables[0])

        dp = datafactory([{'name': 'col', 'constraints': {'pattern': '[a-z]{2}'}}], [['abcd']])
        with pytest.raises(ValueError):
            _ = list(DataPackage(dp).to_tablegroup().tables[0])

        dp = datafactory(
            [{'name': 'col', 'type': 'year', 'constraints': {'pattern': '[2].*'}}], [['1990']])
        with pytest.raises(ValueError):
            _ = list(DataPackage(dp).to_tablegroup().tables[0])


def test_DataPackage(tmpfixtures):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        dp = DataPackage(tmpfixtures / 'datapackage.json')
        tg = dp.to_tablegroup()
        rows = list(tg.tables[0])
        assert len(rows) == 9
        assert rows[-1]['Year'] == 2012
        assert rows[-1]['Location name'] == 'Rural'
        with pytest.raises(ValueError):
            tg.check_referential_integrity()
        schema = tg.tables[0].tableSchema
        for c in ['binary', 'anyURI']:
            assert schema.columndict[c].datatype.base == c
        assert rows[0]['boolean'] is True and rows[1]['boolean'] is False
        assert rows[0]['Value'] == 10123

        tg.to_file(tmpfixtures / 'metadata.json')
        tg = TableGroup.from_file(tmpfixtures / 'metadata.json')
        rows = list(tg.tables[0])
        assert len(rows) == 9
        assert rows[-1]['Year'] == 2012
