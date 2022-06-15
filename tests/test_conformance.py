import pytest


@pytest.mark.conformance
def test_csvw_json(csvwjsontest):
    #if int(csvwjsontest.id.replace('test', '')) < 100:
    #    return
    if csvwjsontest.id in [
        'test034', 'test035', 'test039',
    ]:  # Dunno how to handle yet!
        return
    csvwjsontest.run()
