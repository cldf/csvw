from csvw.dsv_dialects import Dialect


def test_init():
    assert Dialect(skipRows=-3).skipRows == 0
