# _compat.py - Python 2/3 compatibility
# flake8: noqa

import io
import sys
import base64

if sys.version_info < (3, 5):  # pragma: no cover
    import pathlib2 as pathlib
else:  # pragma: no cover
    import pathlib

PY2 = sys.version_info < (3,)


if PY2:  # pragma: no cover
    string_types = basestring
    binary_type = str
    text_type = unicode
    base64_decodebytes = base64.decodestring

    from cStringIO import StringIO
    BytesIO = StringIO

    def to_binary(s, encoding='utf-8'):
        return str(s).encode(encoding)

    iteritems = lambda x: x.iteritems()
    itervalues = lambda x: x.itervalues()

    class Iterator(object):
        def next(self):
            return self.__next__()

    from itertools import imap as map, izip as zip

    def py3_unicode_to_str(cls):
        if not hasattr(cls, '__str__'):  # maybe not needed
            cls.__str__ = lambda self: self.__unicode__().encode('utf-8')
        return cls

    def json_open(filename, mode='rb', encoding='utf-8'):
        if not mode.endswith('b'):
            mode += 'b'
        assert encoding == 'utf-8'  # default of json.dump() json.load()
        return io.open(filename, mode)

    def fix_kw(kw):
        """Convert unicode parameters to str."""
        return {k: str(v) if isinstance(v, unicode) else v for k, v in iteritems(kw)}


else:
    string_types = text_type = str
    binary_type = bytes
    base64_decodebytes = base64.decodebytes

    StringIO, BytesIO = io.StringIO, io.BytesIO

    def to_binary(s, encoding='utf-8'):
        if not isinstance(s, bytes):
            return bytes(s, encoding=encoding)
        return s  # pragma: no cover

    iteritems = lambda x: iter(x.items())
    itervalues = lambda x: iter(x.values())

    Iterator = object

    map, zip = map, zip

    def py3_unicode_to_str(cls):
        cls.__str__ = cls.__unicode__
        del cls.__unicode__
        return cls

    def json_open(filename, mode='r', encoding='utf-8'):
        assert encoding == 'utf-8'  # cf. above
        return io.open(filename, mode, encoding=encoding)

    def fix_kw(kw):
        return kw
