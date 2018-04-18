from __future__ import unicode_literals

import sys

import pytest


@pytest.fixture(scope='session')
def py2():
    return sys.version_info < (3,)
