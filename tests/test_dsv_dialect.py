import pytest

from csvw.dsv_dialects import Dialect


@pytest.mark.filterwarnings("ignore:Invalid")
def test_init():
    assert Dialect(skipRows=-3).skipRows == 0
