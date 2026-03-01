"""
DSV data can be surprisingly diverse. While Python's `csv` module offers out-of-the-box support
for the basic formatting parameters, CSVW recognizes a couple more, like `skipColumns` or
`skipRows`.

.. seealso::

    - `<https://www.w3.org/TR/2015/REC-tabular-metadata-20151217/#dialect-descriptions>`_
    - `<https://docs.python.org/3/library/csv.html#dialects-and-formatting-parameters>`_
    - `<https://specs.frictionlessdata.io/csv-dialect/>`_
"""
import typing
import warnings
import functools
import dataclasses

from . import utils

__all__ = ['Dialect']

ENCODING_MAP = {
    'UTF-8-BOM': 'utf-8-sig',  # Recognize the name of this encoding in R.
}


def convert_encoding(s):
    s = utils.converter(str, 'utf-8', s)
    try:
        _ = 'x'.encode(ENCODING_MAP.get(s, s))
        return s
    except LookupError:
        warnings.warn('Invalid value for property: {}'.format(s))
        return 'utf-8'


@dataclasses.dataclass
class Dialect:
    """
    A CSV dialect specification.

    .. seealso:: `<https://www.w3.org/TR/2015/REC-tabular-metadata-20151217/#dialect-descriptions>`_
    """

    encoding: str = 'utf-8'
    lineTerminators: list[str] = dataclasses.field(default_factory=lambda: ['\r\n', '\n'])
    quoteChar: str = '"'
    doubleQuote: bool = True
    skipRows: int = 0
    commentPrefix: str = '#'
    header: bool = True
    headerRowCount: int = 1
    delimiter: str = ','
    skipColumns: int = 0
    skipBlankRows: bool = False
    skipInitialSpace: bool = False
    trim: typing.Literal['true', 'false', 'start', 'end'] = 'false'

    def __post_init__(self):
        self.encoding = convert_encoding(self.encoding)
        self.line_terminators = utils.converter(list, ['\r\n', '\n'], self.line_terminators)
        self.quoteChar = utils.converter(str, '"', self.quoteChar, allow_none=True)
        self.doubleQuote = utils.converter(bool, True, self.doubleQuote)
        self.skipRows = utils.converter(int, 0, self.skipRows, cond=lambda s: s >= 0)
        self.commentPrefix = utils.converter(str, '#', self.commentPrefix, allow_none=True)
        self.header = utils.converter(bool, True, self.header)
        self.headerRowCount = utils.converter(
            int, 1, self.headerRowCount, cond=lambda s: s >= 0)
        self.delimiter = utils.converter(str, ',', self.delimiter)
        self.skipColumns = utils.converter(int, 0, self.skipColumns, cond=lambda s: s >= 0)
        self.skipBlankRows = utils.converter(bool, False, self.skipBlankRows)
        self.skipInitialSpace = utils.converter(bool, False, self.skipInitialSpace)
        self.trim = utils.converter((str, bool), 'false', str(self.trim).lower() if isinstance(self.trim, bool) else self.trim)
        assert self.trim in ['true', 'false', 'start', 'end'], 'invalid trim'

    def updated(self, **kw):
        res = self.__class__(**dataclasses.asdict(self))
        for k, v in kw.items():
            setattr(res, k, v)
        return res

    @functools.cached_property
    def escape_character(self):
        return None if self.quoteChar is None else ('"' if self.doubleQuote else '\\')

    @functools.cached_property
    def line_terminators(self):
        return [self.lineTerminators] \
            if isinstance(self.lineTerminators, str) else self.lineTerminators

    @functools.cached_property
    def trimmer(self):
        return {
            True: lambda s: s.strip(),
            'true': lambda s: s.strip(),
            False: lambda s: s,
            'false': lambda s: s,
            'start': lambda s: s.lstrip(),
            'end': lambda s: s.rstrip()
        }[self.trim]

    def asdict(self, omit_defaults=True):
        return utils.attr_asdict(self, omit_defaults=omit_defaults)

    @property
    def python_encoding(self):
        return ENCODING_MAP.get(self.encoding, self.encoding)

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
