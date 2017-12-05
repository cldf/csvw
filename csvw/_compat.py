# _compat.py - Python 2/3 compatibility

import io
import sys

from clldutils.path import Path  # use the same variant as clldutils.dsv

PY2 = sys.version_info < (3,)


if PY2:  # pragma: no cover
    text_type = unicode

    def to_binary(s, encoding='utf-8'):
        return str(s).encode(encoding)

    iteritems = lambda x: x.iteritems()
    itervalues = lambda x: x.itervalues()

    from itertools import  izip as zip

    def py3_unicode_to_str(cls):
        if not hasattr(cls, '__str__'):  # maybe not needed
            cls.__str__ = lambda self: self.__unicode__().encode('utf-8')
        return cls

    def json_open(filename, mode='rb', encoding='utf-8'):
        if not mode.endswith('b'):
            mode += 'b'
        assert encoding == 'utf-8'  # default of json.dump() json.load()
        return io.open(filename, mode)


else:  # pragma: no cover
    text_type = str

    def to_binary(s, encoding='utf-8'):
        if not isinstance(s, bytes):
            return bytes(s, encoding=encoding)
        return s

    iteritems = lambda x: iter(x.items())
    itervalues = lambda x: iter(x.values())

    zip = zip

    def py3_unicode_to_str(cls):
        cls.__str__ = cls.__unicode__
        del cls.__unicode__
        return cls

    def json_open(filename, mode='r', encoding='utf-8'):
        assert encoding == 'utf-8'  # cf. above
        return io.open(filename, mode, encoding=encoding)
