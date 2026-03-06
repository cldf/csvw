"""
DSV data can be surprisingly diverse. While Python's `csv` module offers out-of-the-box support
for the basic formatting parameters, CSVW recognizes a couple more, like `skipColumns` or
`skipRows`.

.. seealso::

    - `<https://www.w3.org/TR/2015/REC-tabular-metadata-20151217/#dialect-descriptions>`_
    - `<https://docs.python.org/3/library/csv.html#dialects-and-formatting-parameters>`_
    - `<https://specs.frictionlessdata.io/csv-dialect/>`_
"""
from typing import Callable, Literal
import warnings
import functools
import dataclasses

from . import utils
from .metadata_utils import dataclass_asdict

__all__ = ['Dialect']

ENCODING_MAP = {
    'UTF-8-BOM': 'utf-8-sig',  # Recognize the name of this encoding in R.
}


def convert_encoding(s):
    """We want to force utf-8 encoding, but accept diverse ways of specifying this :)."""
    s = utils.type_checker(str, 'utf-8', s)
    try:
        _ = 'x'.encode(ENCODING_MAP.get(s, s))
        return s
    except LookupError:
        warnings.warn(f'Invalid value for property: {s}')
        return 'utf-8'


@dataclasses.dataclass
class Dialect:  # pylint: disable=too-many-instance-attributes
    """
    A CSV dialect specification.

    .. seealso:: `<https://www.w3.org/TR/2015/REC-tabular-metadata-20151217/#dialect-descriptions>`_
    """

    encoding: str = 'utf-8'
    lineTerminators: list[str] = dataclasses.field(  # pylint: disable=invalid-name
        default_factory=lambda: ['\r\n', '\n'])
    quoteChar: str = '"'  # pylint: disable=invalid-name
    doubleQuote: bool = True  # pylint: disable=invalid-name
    skipRows: int = 0  # pylint: disable=invalid-name
    commentPrefix: str = '#'  # pylint: disable=invalid-name
    header: bool = True
    headerRowCount: int = 1  # pylint: disable=invalid-name
    delimiter: str = ','
    skipColumns: int = 0  # pylint: disable=invalid-name
    skipBlankRows: bool = False  # pylint: disable=invalid-name
    skipInitialSpace: bool = False  # pylint: disable=invalid-name
    trim: Literal['true', 'false', 'start', 'end'] = 'false'

    def __post_init__(self):
        self.encoding = convert_encoding(self.encoding)
        self.line_terminators = utils.type_checker(list, ['\r\n', '\n'], self.line_terminators)
        self.quoteChar = utils.type_checker(str, '"', self.quoteChar, allow_none=True)
        self.doubleQuote = utils.type_checker(bool, True, self.doubleQuote)
        self.skipRows = utils.type_checker(int, 0, self.skipRows, cond=lambda s: s >= 0)
        self.commentPrefix = utils.type_checker(str, '#', self.commentPrefix, allow_none=True)
        self.header = utils.type_checker(bool, True, self.header)
        self.headerRowCount = utils.type_checker(
            int, 1, self.headerRowCount, cond=lambda s: s >= 0)
        self.delimiter = utils.type_checker(str, ',', self.delimiter)
        self.skipColumns = utils.type_checker(int, 0, self.skipColumns, cond=lambda s: s >= 0)
        self.skipBlankRows = utils.type_checker(bool, False, self.skipBlankRows)
        self.skipInitialSpace = utils.type_checker(bool, False, self.skipInitialSpace)
        self.trim = utils.type_checker(
            (str, bool), 'false', str(self.trim).lower()
            if isinstance(self.trim, bool) else self.trim)
        assert self.trim in ['true', 'false', 'start', 'end'], 'invalid trim'

    def updated(self, **kw) -> 'Dialect':
        """Update the spec, returning a new updated object."""
        res = self.__class__(**dataclasses.asdict(self))
        for k, v in kw.items():
            setattr(res, k, v)
        return res

    @functools.cached_property
    def escape_character(self):  # pylint: disable=C0116
        return None if self.quoteChar is None else ('"' if self.doubleQuote else '\\')

    @functools.cached_property
    def line_terminators(self) -> list[str]:  # pylint: disable=C0116
        return [self.lineTerminators] \
            if isinstance(self.lineTerminators, str) else self.lineTerminators

    @functools.cached_property
    def trimmer(self) -> Callable[[str], str]:
        """Map trim spec to a callable to do the trimming."""
        return {
            True: lambda s: s.strip(),
            'true': lambda s: s.strip(),
            False: lambda s: s,
            'false': lambda s: s,
            'start': lambda s: s.lstrip(),
            'end': lambda s: s.rstrip()
        }[self.trim]

    def asdict(self, omit_defaults=True):
        """The dialect spec as dict suitable for JSON serialization."""
        return dataclass_asdict(self, omit_defaults=omit_defaults)

    @property
    def python_encoding(self):
        """
        Turn the encoding name into something understood by python.
        """
        return ENCODING_MAP.get(self.encoding, self.encoding)

    def as_python_formatting_parameters(self):
        """
        Turn the dialect spec into a dict suitable as kwargs for Python's csv implementation.
        """
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
