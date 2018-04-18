# coding: utf8
from __future__ import unicode_literals

import pytest

from csvw.dsv_dialects import Dialect


def test_init():
    with pytest.raises(ValueError):
        Dialect(skipRows=-3)
