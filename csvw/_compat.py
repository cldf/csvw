# _compat.py - Python 2/3 compatibility

import sys

PY2 = sys.version_info < (3,)


if PY2:  # pragma: no cover
    text_type = unicode

    iteritems = lambda x: x.iteritems()
    itervalues = lambda x: x.itervalues()

    import pathlib2 as pathlib


else:  # pragma: no cover
    text_type = str

    iteritems = lambda x: iter(x.items())
    itervalues = lambda x: iter(x.values())

    import pathlib
