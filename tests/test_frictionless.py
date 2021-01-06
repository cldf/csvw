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


def test_DataPackage(tmpfixtures):
    dp = DataPackage(tmpfixtures / 'datapackage.json')
    tg = dp.to_tablegroup()
    rows = list(tg.tables[0])
    assert len(rows) == 9
    assert rows[-1]['Year'] == 2012
    assert rows[-1]['Location%20name'] == 'Rural'

    tg.to_file(tmpfixtures / 'metadata.json')
    tg = TableGroup.from_file(tmpfixtures / 'metadata.json')
    assert 'Location name' == str(tg.tables[0].tableSchema.columns[1].titles)
    rows = list(tg.tables[0])
    assert len(rows) == 9
    assert rows[-1]['Year'] == 2012
