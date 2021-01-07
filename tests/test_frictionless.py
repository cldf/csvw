import shutil
import pathlib

import pytest

from csvw import TableGroup
from csvw.frictionless import DataPackage

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


@pytest.fixture
def tmpfixtures(tmpdir):
    shutil.copytree(str(pathlib.Path(__file__).parent / 'fixtures'), str(tmpdir.join('fixtures')))
    return pathlib.Path(str(tmpdir)) / 'fixtures'


def test_DataPackage_init():
    dp = DataPackage(dict(resources=[], name='x'))
    assert dp.to_tablegroup().common_props['dc:identifier'] == 'x'
    dp = DataPackage('{"resources": [], "name": "x", "id": "y"}')
    assert dp.to_tablegroup().common_props['dc:identifier'] == 'y'
    assert dp.to_tablegroup().common_props['dc:title'] == 'x'


def test_DataPackage(tmpfixtures):
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
    assert list(rows[0].values())[-1] != '+', "custom line terminator must be stripped"

    tg.to_file(tmpfixtures / 'metadata.json')
    tg = TableGroup.from_file(tmpfixtures / 'metadata.json')
    rows = list(tg.tables[0])
    assert len(rows) == 9
    assert rows[-1]['Year'] == 2012
