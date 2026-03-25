import dataclasses

import pytest

from csvw.metadata_utils import *


@pytest.fixture
def Dataclass():
    @dataclasses.dataclass
    class Test:
        _private: int = 5
        public: str = 'hello'

    return Test


@pytest.mark.parametrize(
    'data,kw,expected',
    [
        (dict(), dict(), {}),
        (dict(), dict(omit_defaults=False), {'public': 'hello'}),
        (dict(), dict(omit_defaults=False, omit_private=False), {'public': 'hello', '_private': 5}),
        (dict(), dict(omit_private=False), {}),
        (dict(_private=1), dict(omit_private=False), {'_private': 1}),
        (dict(public='world'), dict(), {'public': 'world'}),
    ]
)
def test_dataclass_asdict(Dataclass, data, kw, expected):
    assert dataclass_asdict(Dataclass(**data), **kw) == expected
