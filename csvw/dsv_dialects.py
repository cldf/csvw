from __future__ import unicode_literals

from ._compat import text_type, iteritems

import attr

from clldutils import attrlib
from clldutils.misc import lazyproperty

__all__ = ['Dialect']


def non_negative_int(*_):
    return attr.validators.and_(
        attr.validators.instance_of(int), attrlib.valid_range(0, None))


@attr.s
class Dialect(object):
    """A CSV dialect specification.

    .. seealso:: http://w3c.github.io/csvw/metadata/#dialect-descriptions
    """

    encoding = attr.ib(
        default='utf-8',
        validator=attr.validators.instance_of(text_type))

    lineTerminators = attr.ib(
        default=attr.Factory(lambda: ['\r\n', '\n']))

    quoteChar = attr.ib(
        default='"',
    )

    doubleQuote = attr.ib(
        default=True,
        validator=attr.validators.instance_of(bool))

    skipRows = attr.ib(
        default=0,
        validator=non_negative_int)

    commentPrefix = attr.ib(
        default='#',
        validator=attr.validators.optional(attr.validators.instance_of(text_type)))

    header = attr.ib(
        default=True,
        validator=attr.validators.instance_of(bool))

    headerRowCount = attr.ib(
        default=1,
        validator=non_negative_int)

    delimiter = attr.ib(
        default=',',
        validator=attr.validators.instance_of(text_type))

    skipColumns = attr.ib(
        default=0,
        validator=non_negative_int)

    skipBlankRows = attr.ib(
        default=False,
        validator=attr.validators.instance_of(bool))

    skipInitialSpace = attr.ib(
        default=False,
        validator=attr.validators.instance_of(bool))

    trim = attr.ib(
        default='false',
        validator=attr.validators.in_(['true', 'false', 'start', 'end']),
        convert=lambda v: '{0}'.format(v).lower() if isinstance(v, bool) else v)

    def updated(self, **kw):
        res = self.__class__(**attr.asdict(self))
        for k, v in iteritems(kw):
            setattr(res, k, v)
        return res

    @lazyproperty
    def escape_character(self):
        return None if self.quoteChar is None else ('"' if self.doubleQuote else '\\')

    @lazyproperty
    def line_terminators(self):
        return [self.lineTerminators] \
            if isinstance(self.lineTerminators, text_type) else self.lineTerminators

    @lazyproperty
    def trimmer(self):
        return {
            'true': lambda s: s.strip(),
            'false': lambda s: s,
            'start': lambda s: s.lstrip(),
            'end': lambda s: s.rstrip()
        }[self.trim]

    def asdict(self, omit_defaults=True):
        return attrlib.asdict(self, omit_defaults=omit_defaults)

    def as_python_formatting_parameters(self):
        return {
            'delimiter': self.delimiter,
            'doublequote': self.doubleQuote,
            # We have to hack around incompatible ways escape char is interpreted in csvw
            # and python's csv lib:
            'escapechar': self.escape_character if self.escape_character is None else '\\',
            'lineterminator': self.line_terminators[0],
            'quotechar': self.quoteChar,
            'skipinitialspace': self.skipInitialSpace,
            'strict': True,
        }