import pathlib

import pytest

from csvw.jsonld import *


@pytest.mark.parametrize(
    'input,output',
    [
        (1, 1),
        ("a", "a"),
        ([1, 2, 3], [1, 2, 3]),
        ({'@id': 'url'}, 'url'),
    ]
)
def test_to_json(input, output):
    assert to_json(input) == output


def test_to_json_flatten():
    assert to_json([1], flatten_list=True) == 1


def test_grouped():
    res = group_triples([
        Triple(about=None, property='x', value='y'),
        Triple(about='http://example.com/1', property='schema:name', value='The Name'),
    ])
    assert len(res) == 1


def test_format_value():
    assert format_value(pathlib.Path(__file__), None) == __file__
