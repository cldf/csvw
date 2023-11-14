import pathlib

from csvw import utils


def test_ensure_path():
    assert isinstance(utils.ensure_path('test.csv'), pathlib.Path)


def test_normalize_name():
    assert utils.normalize_name('') == '_'
    assert utils.normalize_name('0') == '_0'


def test_slug():
    assert utils.slug('ABC') == 'abc'
