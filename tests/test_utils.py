import pathlib

from csvw import utils


def test_ensure_path():
    assert isinstance(utils.ensure_path('test.csv'), pathlib.Path)


def test_lazyproperty():
    import itertools

    class Spam(object):
        @utils.lazyproperty
        def eggs(self, _ints=itertools.count()):
            return next(_ints)

    assert Spam.eggs
    spam = Spam()
    assert spam.eggs == 0
    spam.eggs = 42
    assert spam.eggs == 42
    assert Spam().eggs == 1
    del spam.eggs
    assert spam.eggs, spam.eggs == (2, 2)


def test_normalize_name():
    assert utils.normalize_name('') == '_'
    assert utils.normalize_name('0') == '_0'


def test_slug():
    assert utils.slug('ABC') == 'abc'
