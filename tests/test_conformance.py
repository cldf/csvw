import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


@pytest.mark.conformance
def test_csvw_json(csvwjsontest):
    csvwjsontest.run()


@pytest.mark.conformance
def test_csvw_nonnorm(csvwnonnormtest):
    csvwnonnormtest.run()


@pytest.mark.conformance
def test_csvw_validation(csvwvalidationtest):
    csvwvalidationtest.run()


def test_prefix_in_property_url():
    from csvw import CSVW

    obj = CSVW(str(FIXTURES / 'csv.txt'), md_url=str(FIXTURES / 'csv.txt-table-metadata.json'))
    row = obj.to_json()['tables'][0]['row'][0]['describes'][0]
    assert 'dc:identifier' in row
