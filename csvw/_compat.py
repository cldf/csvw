# _compat.py - Python 2/3 compatibility

import sys

PY2 = sys.version_info < (3,)


if PY2:  # pragma: no cover
    text_type = unicode

    def to_binary(s, encoding='utf-8'):
        return str(s).encode(encoding)

    iteritems = lambda x: x.iteritems()
    itervalues = lambda x: x.itervalues()

    def py3_unicode_to_str(cls):
        if not hasattr(cls, __str__):  # maybe not needed
            cls.__str__ = lambda self: self.__unicode__().encode('utf-8')
        return cls

    import pathlib2 as pathlib


else:  # pragma: no cover
    text_type = str

    def to_binary(s, encoding='utf-8'):
        if not isinstance(s, bytes):
            return bytes(s, encoding=encoding)
        return s

    iteritems = lambda x: iter(x.items())
    itervalues = lambda x: iter(x.values())

    def py3_unicode_to_str(cls):
        cls.__str__ = cls.__unicode__
        del cls.__unicode__
        return cls

    import pathlib
