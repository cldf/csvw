from __future__ import unicode_literals

from ._compat import text_type, iteritems

import attr

from . import utils

__all__ = ['Dialect']


def _non_negative(instance, attribute, value):
    if value < 0:
        raise ValueError('{0} is not a valid {1}'.format(value, attribute.name))


non_negative_int = [attr.validators.instance_of(int), _non_negative]


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
        converter=lambda v: '{0}'.format(v).lower() if isinstance(v, bool) else v)

    def updated(self, **kw):
        res = self.__class__(**attr.asdict(self))
        for k, v in iteritems(kw):
            setattr(res, k, v)
        return res

    @utils.lazyproperty
    def escape_character(self):
        return None if self.quoteChar is None else ('"' if self.doubleQuote else '\\')

    @utils.lazyproperty
    def line_terminators(self):
        return [self.lineTerminators] \
            if isinstance(self.lineTerminators, text_type) else self.lineTerminators

    @utils.lazyproperty
    def trimmer(self):
        return {
            'true': lambda s: s.strip(),
            'false': lambda s: s,
            'start': lambda s: s.lstrip(),
            'end': lambda s: s.rstrip()
        }[self.trim]

    def asdict(self, omit_defaults=True):
        return utils.attr_asdict(self, omit_defaults=omit_defaults)

    def as_python_formatting_parameters(self):
        return {
            'delimiter': self.delimiter,
            'doublequote': self.doubleQuote,
            # We have to hack around incompatible ways escape char is interpreted in csvw
            # and python's csv lib:
            'escapechar': self.escape_character if not self.doubleQuote else None,
            'lineterminator': self.line_terminators[0],
            'quotechar': self.quoteChar,
            'skipinitialspace': self.skipInitialSpace,
            'strict': True,
        }
