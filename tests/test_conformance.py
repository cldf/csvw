import pytest


@pytest.mark.conformance
def test_csvw_json(csvwjsontest):
    csvwjsontest.run()


@pytest.mark.conformance
def test_csvw_nonnorm(csvwnonnormtest):
    csvwnonnormtest.run()


@pytest.mark.conformance
def test_csvw_validation(csvwvalidationtest):
    csvwvalidationtest.run()
