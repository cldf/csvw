# _compat.py - Python 3.4 compatibility
# flake8: noqa

import io
import sys

if sys.version_info < (3, 5):  # pragma: no cover
    import pathlib2 as pathlib
else:  # pragma: no cover
    import pathlib


def to_binary(s, encoding='utf-8'):
    if not isinstance(s, bytes):
        return bytes(s, encoding=encoding)
    return s  # pragma: no cover


def py3_unicode_to_str(cls):
    cls.__str__ = cls.__unicode__
    del cls.__unicode__
    return cls


def json_open(filename, mode='r', encoding='utf-8'):
    assert encoding == 'utf-8'  # cf. above
    return io.open(filename, mode, encoding=encoding)
