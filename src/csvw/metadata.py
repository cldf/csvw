# pylint: disable=too-many-lines
"""Functionality to read and write metadata for CSV files.

This module implements (partially) the W3C recommendation
"Metadata Vocabulary for Tabular Data".

.. seealso:: https://www.w3.org/TR/tabular-metadata/
"""
import io
import logging
import re
import json
import shutil
import decimal
import pathlib
from typing import Optional, Union, Any, Literal, TypeVar
import zipfile
import datetime
import operator
import warnings
import functools
import itertools
import contextlib
import collections
from collections.abc import Iterable, Generator
import dataclasses
from urllib.parse import urljoin, urlparse, urlunparse

from language_tags import tags
import uritemplate

from . import utils
from .datatypes import DATATYPES
from .dsv import Dialect as BaseDialect, UnicodeReaderWithLineNumber, UnicodeWriter
from .frictionless import DataPackage
from . import jsonld
from .metadata_utils import DescriptionBase, dataclass_asdict, NAMESPACES, dialect_props, \
    valid_context_property

DEFAULT = object()

__all__ = [
    'TableGroup', 'Table', 'Column', 'ForeignKey', 'Link', 'NaturalLanguage', 'Datatype',
    'is_url', 'CSVW',
]

is_url = utils.is_url

OrderedType = Union[
    int, float, decimal.Decimal, datetime.date, datetime.datetime, datetime.timedelta]
ColRefType = tuple[str]
RowType = collections.OrderedDict[str, Any]
T = TypeVar('T')


class Invalid:  # pylint: disable=R0903,C0115:
    pass


INVALID = Invalid()


@dataclasses.dataclass
class Dialect(BaseDialect):
    """
    The spec is ambiguous regarding a default for the commentPrefix property:

    > commentPrefix
    >     An atomic property that sets the comment prefix flag to the single provided value, which
    >     MUST be a string. The default is "#".

    vs.

    > comment prefix
    >     A string that, when it appears at the beginning of a row, indicates that the row is a
    >     comment that should be associated as a rdfs:comment annotation to the table. This is set
    >     by the commentPrefix property of a dialect description. The default is null, which means
    >     no rows are treated as comments. A value other than null may mean that the source numbers
    >     of rows are different from their numbers.

    So, in order to pass the number formatting tests, with column names like `##.#`, we chose
    the second reading - i.e. by default no rows are treated as comments.
    """
    commentPrefix: str = None


class URITemplate(uritemplate.URITemplate):
    """URITemplate properties support expansion, given suitable context."""
    def __eq__(self, other):
        if isinstance(other, str):
            return self.uri == other
        if not hasattr(other, 'uri'):
            return False
        return super().__eq__(other)

    def asdict(self, **_):  # pylint: disable=C0116
        return f'{self}'


def convert_uri_template(v):  # pylint: disable=C0116
    if v is None:
        return None  # pragma: no cover
    if not isinstance(v, str):
        warnings.warn('Invalid value for Url property')
        return INVALID
    return URITemplate(v)


class Link:
    """

    .. seealso:: http://w3c.github.io/csvw/metadata/#link-properties
    """

    def __init__(self, string: Union[str, pathlib.Path]):
        if not isinstance(string, (str, pathlib.Path)):
            raise ValueError('Invalid value for link property')
        self.string = string

    @classmethod
    def from_value(cls, v: Union['Link', str, pathlib.Path]):  # pylint: disable=C0116
        if isinstance(v, Link):
            return v  # pragma: no cover
        return cls(v)

    def __str__(self):
        return self.string

    def asdict(self, **_):
        """Not really a dict, but at least a JSON-serializable datatype."""
        return self.string

    def __eq__(self, other):
        # FIXME: pylint: disable=W0511
        #  Only naive, un-resolved comparison is supported at the moment.
        return self.string == other.string if isinstance(other, Link) else False

    def resolve(self, base):
        """
        Resolve a `Link` relative to `base`.

        :param base:
        :return: Either a string, representing a URL, or a `pathlib.Path` object, representing \
        a local file.
        """
        if hasattr(base, 'joinpath'):
            if is_url(self.string):
                return self.string
            return (base if base.is_dir() else base.parent) / self.string
        return urljoin(base, self.string)


class NaturalLanguage(collections.OrderedDict):
    """
    A natural language property holds a collection of string, optionally categorized into languages.

    .. seealso:: http://w3c.github.io/csvw/metadata/#natural-language-properties
    """
    def __init__(
            self,
            value: Union[str, list[str], tuple[str], dict[str, Union[str, list[str], tuple[str]]]]):
        super().__init__()
        self.value = value
        if isinstance(self.value, str):
            self[None] = [self.value]
        elif isinstance(self.value, (list, tuple)):
            if not all(isinstance(v, str) for v in self.value):
                warnings.warn('titles with array values containing non-string values are ignored')
            else:
                self[None] = list(self.value)
        elif isinstance(self.value, dict):
            for k, v in self.value.items():
                if not tags.check(k):
                    raise ValueError('Invalid language tag for NaturalLanguage')
                if not isinstance(v, (list, tuple)):
                    v = [v]
                titles = []
                for vv in v:
                    if isinstance(vv, str):
                        titles.append(vv)
                    else:
                        warnings.warn('Title with value which is not a string is ignored')
                self[k] = titles
        else:
            raise ValueError('invalid value type for NaturalLanguage')

    def asdict(self, **_):
        """Serialize as dict."""
        if list(self) == [None]:
            if len(self[None]) == 1:
                return self.getfirst()
            return self[None]
        return collections.OrderedDict(
            ('und' if k is None else k, v[0] if len(v) == 1 else v)
            for k, v in self.items())

    def add(self, string: str, lang: Optional[str] = None) -> None:
        """Add a string for a language."""
        if lang not in self:
            self[lang] = []
        self[lang].append(string)

    def __str__(self) -> str:
        return self.getfirst() or next(iter(self.values()))[0]

    def getfirst(self, lang: Optional[str] = None) -> Optional[str]:
        """Return the first string specified for the given language tag."""
        return self.get(lang, [None])[0]


@dataclasses.dataclass
class Datatype(DescriptionBase):  # pylint: disable=too-many-instance-attributes
    """
    A datatype description

        Cells within tables may be annotated with a datatype which indicates the type of the values
        obtained by parsing the string value of the cell.

    .. seealso:: `<https://www.w3.org/TR/tabular-metadata/#datatypes>`_
    """
    base: str = None
    format: Optional[str] = None
    length: Optional[int] = None
    minLength: Optional[int] = None  # pylint: disable=C0103
    maxLength: Optional[int] = None  # pylint: disable=C0103
    minimum: OrderedType = None
    maximum: OrderedType = None
    minInclusive: Optional[bool] = None  # pylint: disable=C0103
    maxInclusive: Optional[bool] = None  # pylint: disable=C0103
    minExclusive: Optional[bool] = None  # pylint: disable=C0103
    maxExclusive: Optional[bool] = None  # pylint: disable=C0103

    def __post_init__(self):
        self.base = functools.partial(
            utils.type_checker,
            str,
            'string',
            allow_none=True,
            cond=lambda ss: ss is None or ss in DATATYPES)(self.base)
        self._set_constraints()
        self._validate_constraints()

    def _validate_constraints(self):
        def error_if(msg, *conditions):
            if any(conditions):
                raise ValueError(msg)

        if self.length is not None:
            error_if(
                'Length limits interfere',
                self.minLength is not None and self.length < self.minLength,
                self.maxLength is not None and self.length > self.maxLength,
            )

        if self.minLength is not None and self.maxLength is not None \
                and self.minLength > self.maxLength:
            raise ValueError('minLength > maxLength')

        if not isinstance(self.derived_description, dict):
            raise ValueError()  # pragma: no cover

        if not isinstance(
                self.basetype(),
                tuple((DATATYPES[name] for name in ['decimal', 'float', 'datetime', 'duration']))):
            error_if(
                'Applications MUST raise an error if minimum, minInclusive, maximum, '
                'maxInclusive, minExclusive, or maxExclusive are specified and the base '
                'datatype is not a numeric, date/time, or duration type.',
                *[getattr(self, at) for at in
                    'minimum maximum minExclusive maxExclusive minInclusive maxInclusive'.split()])

        if not isinstance(
                self.basetype(),
                (DATATYPES['string'], DATATYPES['base64Binary'], DATATYPES['hexBinary'])):
            error_if(
                'Applications MUST raise an error if length, maxLength, or minLength are '
                'specified and the base datatype is not string or one of its subtypes, or a '
                'binary type.',
                self.length, self.minLength, self.maxLength)

        error_if(
            'Applications MUST raise an error if both minInclusive and minExclusive are '
            'specified, or if both maxInclusive and maxExclusive are specified.',
            self.minInclusive and self.minExclusive,
            self.maxInclusive and self.maxExclusive,
        )
        error_if(
            'Limits overlap',
            self.minInclusive and self.maxExclusive and self.maxExclusive <= self.minInclusive,
            self.minInclusive and self.maxInclusive and self.maxInclusive < self.minInclusive,
            self.minExclusive and self.maxExclusive and self.maxExclusive <= self.minExclusive,
            self.minExclusive and self.maxInclusive and self.maxInclusive <= self.minExclusive,
        )

        if 'id' in self.at_props and any(
                self.at_props['id'] == NAMESPACES['xsd'] + dt for dt in DATATYPES):
            raise ValueError('datatype @id MUST NOT be the URL of a built-in datatype.')

        if isinstance(self.basetype(), DATATYPES['decimal']) and \
                'pattern' in self.derived_description:
            if not set(self.derived_description['pattern']).issubset(set('#0.,;%‰E-+')):
                self.format = None
                warnings.warn('Invalid number pattern')

    def _set_constraints(self):
        for att in ('length', 'maxLength', 'minLength'):
            setattr(self, att, utils.optcast(int)(getattr(self, att)))
        for attr_ in [
            'minimum', 'maximum', 'minInclusive', 'maxInclusive', 'minExclusive', 'maxExclusive'
        ]:
            if getattr(self, attr_) is not None:
                setattr(self, attr_, self.parse(getattr(self, attr_)))

    @classmethod
    def fromvalue(cls, d: Union[str, dict, 'Datatype']) -> 'Datatype':
        """
        :param v: Initialization data for `cls`; either a single string that is the main datatype \
        of the values of the cell or a datatype description object, i.e. a `dict` or a `cls` \
        instance.
        :return: An instance of `cls`
        """
        if isinstance(d, str):
            return cls(base=d)

        if isinstance(d, dict):
            d.setdefault('base', 'string')
            return cls(**cls.partition_properties(d))

        if isinstance(d, cls):
            return d

        raise ValueError(d)

    def asdict(self, omit_defaults=True) -> dict:
        """The datatype serialized as dict suitable for conversion to JSON."""
        res = DescriptionBase.asdict(self, omit_defaults=omit_defaults)
        for attr_ in [
            'minimum', 'maximum', 'minInclusive', 'maxInclusive', 'minExclusive', 'maxExclusive'
        ]:
            if attr_ in res:
                res[attr_] = self.formatted(res[attr_])
        if len(res) == 1 and 'base' in res:
            return res['base']
        return res

    @property
    def basetype(self) -> type:  # pylint: disable=C0116
        return DATATYPES[self.base]

    @property
    def derived_description(self) -> dict:  # pylint: disable=C0116
        return self.basetype.derived_description(self)

    def formatted(self, v: Any) -> str:
        """Format a value as string."""
        return self.basetype.to_string(v, **self.derived_description)

    def parse(self, v: str) -> Any:
        """Parse a string value into a Python type."""
        if v is None:
            return v
        return self.basetype.to_python(v, **self.derived_description)

    def validate(self, v: T) -> T:
        """Make sure the datatype-level constraints are met."""
        if v is None:
            return v
        try:
            l_ = len(v or '')
            if self.length is not None and l_ != self.length:
                raise ValueError(f'value must have length {self.length}')
            if self.minLength is not None and l_ < self.minLength:
                raise ValueError(f'value must have at least length {self.minLength}')
            if self.maxLength is not None and l_ > self.maxLength:
                raise ValueError(f'value must have at most length {self.maxLength}')
        except TypeError:
            pass
        if self.basetype.minmax:
            if self.minimum is not None and v < self.minimum:
                raise ValueError(f'value must be >= {self.minimum}')
            if self.minInclusive is not None and v < self.minInclusive:
                raise ValueError(f'value must be >= {self.minInclusive}')
            if self.minExclusive is not None and v <= self.minExclusive:
                raise ValueError(f'value must be > {self.minExclusive}')
            if self.maximum is not None and v > self.maximum:
                raise ValueError(f'value must be <= {self.maximum}')
            if self.maxInclusive is not None and v > self.maxInclusive:
                raise ValueError(f'value must be <= {self.maxInclusive}')
            if self.maxExclusive is not None and v >= self.maxExclusive:
                raise ValueError(f'value must be < {self.maxExclusive}')
        return v

    def read(self, v: str) -> Any:
        """Read a value according to the spec of the Datatype."""
        return self.validate(self.parse(v))


@dataclasses.dataclass
class Description(DescriptionBase):  # pylint: disable=R0902
    """Adds support for inherited properties.

    .. seealso:: http://w3c.github.io/csvw/metadata/#inherited-properties
    """

    # To be able to resolve inheritance chains, we also provide a place to store a
    # reference to the containing object. Note that this attribute is ignored when judging
    # equality between objects. Thus, identically specified columns of different tables will be
    # considered equal.
    _parent: Optional[DescriptionBase] = None

    aboutUrl: Optional[Union[URITemplate, Invalid]] = None  # pylint: disable=C0103
    datatype: Optional[Datatype] = None
    default: Optional[Union[str, list[str]]] = ""
    lang: str = "und"
    null: list[str] = dataclasses.field(default_factory=lambda: [""])
    ordered: Optional[bool] = None
    propertyUrl: Optional[Union[URITemplate, Invalid]] = None  # pylint: disable=C0103
    required: Optional[bool] = None
    separator: Optional[str] = None
    textDirection: Optional[  # pylint: disable=C0103
        Literal["ltr", "rtl", "auto", "inherit"]] = None
    valueUrl: Optional[Union[URITemplate, Invalid]] = None  # pylint: disable=C0103

    def __post_init__(self):
        if self.datatype is not None:
            self.datatype = Datatype.fromvalue(self.datatype)
        self.default = utils.type_checker(str, "", self.default, allow_list=False)
        if not tags.check(self.lang):
            warnings.warn('Invalid language tag')
            self.lang = 'und'

        self.null = [] if self.null is None else \
            (self.null if isinstance(self.null, list) else [self.null])
        if not all(isinstance(vv, str) for vv in self.null):
            warnings.warn('Invalid null property')
            self.null = [""]
        self.ordered = utils.type_checker(bool, False, self.ordered, allow_none=True)
        self.separator = utils.type_checker(str, None, self.separator, allow_none=True)
        self.textDirection = utils.type_checker(
            str,
            None,
            self.textDirection,
            allow_none=True,
            cond=lambda v: v in [None, "ltr", "rtl", "auto", "inherit"])
        for att in ('valueUrl', 'aboutUrl', 'propertyUrl'):
            if getattr(self, att) is not None:
                setattr(self, att, convert_uri_template(getattr(self, att)))

    def inherit(self, attr) -> Optional[Any]:
        """
        The implementation of the inheritance mechanism.

        The chain of inheritance is established by assigning a an object to `_parent`. If this
        object has a method `inherit` as well (i.e. is derived from Description), the chain
        may continue.
        """
        v = getattr(self, attr)
        if v is None and self._parent:
            return self._parent.inherit(attr) if hasattr(self._parent, 'inherit') \
                else getattr(self._parent, attr)
        return v

    def inherit_null(self) -> list[str]:
        """Inheritance of null is a special case due to the default value not being None."""
        if self.null == [""]:
            if self._parent and hasattr(self._parent, 'inherit_null'):
                return self._parent.inherit_null()
        return self.null


@dataclasses.dataclass
class Column(Description):
    """
    A column description is an object that describes a single column.

        The description provides additional human-readable documentation for a column, as well as
        additional information that may be used to validate the cells within the column, create a
        user interface for data entry, or inform conversion into other formats.

    .. seealso:: `<https://www.w3.org/TR/tabular-metadata/#columns>`_
    """
    name: str = None
    suppressOutput: bool = False  # pylint: disable=C0103
    titles: Optional[NaturalLanguage] = None
    virtual: bool = False
    _number: Optional[int] = None

    def __post_init__(self):
        super().__post_init__()
        self.name = utils.type_checker(str, None, self.name, allow_none=True)
        self.suppressOutput = utils.type_checker(bool, False, self.suppressOutput)

        if self.titles is not None:
            try:
                self.titles = NaturalLanguage(self.titles)
            except ValueError:
                warnings.warn('Invalid titles property')
                self.titles = None

        self.virtual = utils.type_checker(bool, False, self.virtual)

    def __str__(self):
        return self.name or (self.titles and self.titles.getfirst()) or f'_col.{self._number}'

    def __eq__(self, other):
        return self.asdict() == other.asdict()

    def has_title(self, v) -> Union[str, bool]:
        """
        Check whether the name or a title of the column matches v.

        If v matches a title, the associated language tag (or 'und') is returned.
        """
        if self.name and self.name == v:
            return True
        for tag, titles in (self.titles or {}).items():
            if v in titles:
                return tag or 'und'
        return False

    @property
    def header(self) -> str:  # pylint: disable=missing-function-docstring
        return f'{self}'

    def read(self, v: str, strict=True) -> Any:
        """Convert a str to a Python object according to the spec for the column."""
        required = self.inherit('required')
        null = self.inherit_null()
        default = self.inherit('default')
        separator = self.inherit('separator')
        datatype = self.inherit('datatype')

        if not v:
            v = default

        if required and v in null:
            if not strict:
                warnings.warn('required column value is missing')
            raise ValueError('required column value is missing')

        if separator:  # A list-valued column.
            if not v:
                v = []  # Empty string is interpreted as empty list.
            elif v in null:
                v = None  # A null value is interpreted as missing data.
            else:
                v = (vv or default for vv in v.split(separator))
                v = [None if vv in null else vv for vv in v]
        elif v in null:
            v = None  # A null value.

        if datatype:  # Apply datatype conversion.
            if isinstance(v, list):
                try:
                    return [datatype.read(vv) for vv in v]
                except ValueError:
                    if not strict:
                        warnings.warn('Invalid value for list element.')
                        return v
                    raise
            return datatype.read(v)
        return v

    def write(self, v: Any) -> str:
        """Convert v to a string according to the specifications for the column."""
        sep = self.inherit('separator')
        null = self.inherit_null()
        datatype = self.inherit('datatype')

        def fmt(v):
            if v is None:
                return null[0]
            if datatype:
                return datatype.formatted(v)
            return v

        if sep:
            return sep.join(fmt(vv) for vv in v or [])
        return fmt(v)


@dataclasses.dataclass
class Reference:
    """A reference specification as used to describe the targets of foreign keys."""
    resource: Optional[Link] = None
    schemaReference: Optional[Link] = None  # pylint: disable=C0103
    columnReference: Optional[list[str]] = None  # pylint: disable=C0103

    def __post_init__(self):
        if self.resource is not None:
            if self.schemaReference is not None:
                # Either a local resource may be referenced or a schema - not both.
                raise ValueError(self)
            self.resource = Link.from_value(self.resource)

        if self.schemaReference is not None:
            self.schemaReference = Link.from_value(self.schemaReference)

        if isinstance(self.columnReference, str):
            self.columnReference = [self.columnReference]


@dataclasses.dataclass
class ForeignKey:
    """A specification of a foreign key."""
    columnReference: Optional[list[str]] = None  # pylint: disable=C0103
    reference: Optional[Reference] = None

    def __post_init__(self):
        if isinstance(self.columnReference, str):
            self.columnReference = [self.columnReference]

    @classmethod
    def fromdict(cls, d):
        """Instantiate an object from a dict as returned by parsing the JSON metadata."""
        if isinstance(d, dict):
            try:
                _ = Reference(**d['reference'])
            except TypeError as e:
                raise ValueError('Invalid reference property') from e
            if not set(d.keys()).issubset({'columnReference', 'reference'}):
                raise ValueError('Invalid foreignKey spec')
        kw = dict(d, reference=Reference(**d['reference']))
        return cls(**kw)

    def asdict(self, **kw) -> dict[str, Any]:  # pylint: disable=C0116
        res = dataclass_asdict(self, **kw)
        res['reference'] = dataclass_asdict(res['reference'], **kw)
        return res


@dataclasses.dataclass
class Schema(Description):
    """
    A schema description is an object that encodes the information about a schema, which describes
    the structure of a table.

    :ivar columns: `list` of :class:`Column` descriptions.
    :ivar foreignKeys: `list` of :class:`ForeignKey` descriptions.

    .. seealso:: `<https://www.w3.org/TR/tabular-metadata/#schemas>`_
    """
    columns: list[Column] = dataclasses.field(default_factory=list)
    foreignKeys: list[ForeignKey] = dataclasses.field(default_factory=list)  # pylint: disable=C0103
    primaryKey: Optional[list[str]] = None  # pylint: disable=C0103
    rowTitles: list[str] = dataclasses.field(default_factory=list)  # pylint: disable=C0103

    def __post_init__(self):
        super().__post_init__()
        self.columns = [
            Column.fromvalue(c) for c in
            utils.type_checker(dict, None, utils.type_checker(list, [], self.columns))]
        for i, col in enumerate(self.columns):
            col._number = i + 1  # pylint: disable=protected-access
        if self.foreignKeys is None:
            self.foreignKeys = []  # pragma: no cover
        else:
            res = []
            for d in utils.type_checker(dict, None, self.foreignKeys):
                try:
                    res.append(ForeignKey.fromdict(d))
                except TypeError:
                    warnings.warn('Invalid foreignKeys spec')
            self.foreignKeys = res

        if self.primaryKey is not None and not isinstance(self.primaryKey, list):
            self.primaryKey = [self.primaryKey]
        self.rowTitles = self.rowTitles if isinstance(self.rowTitles, list) else [self.rowTitles]

        virtual, seen, names = False, set(), set()
        for i, col in enumerate(self.columns):
            virtual = self._check_col(col, virtual, names, seen)
            col._parent = self  # pylint: disable=protected-access
        for colref in self.primaryKey or []:
            col = self.columndict.get(colref)
            if col and not col.name:
                warnings.warn('A primaryKey referenced column MUST have a `name` property')
                self.primaryKey = None

    def _check_col(self, col, virtual: bool, names: set[str], seen: set[str]) -> bool:
        if col.name and (col.name.startswith('_') or re.search(r'\s', col.name)):
            warnings.warn('Invalid column name')
        if col.virtual:  # first virtual column sets the flag
            virtual = True
        elif virtual:  # non-virtual column after virtual column!
            raise ValueError('no non-virtual column allowed after virtual columns')
        if not virtual:
            if col.header in seen:
                warnings.warn('Duplicate column name!')
            if col.name:
                if col.name in names:
                    raise ValueError(f'Duplicate column name {col.name}')
                names.add(col.name)
            seen.add(col.header)
        return virtual

    @classmethod
    def fromvalue(cls, d: Union[dict, str]) -> 'Schema':
        """Instantiate a Schema from a dict or a URL to a JSON file."""
        if isinstance(d, str):
            try:
                # The schema is referenced with a URL
                d = utils.request_get(d).json()
            except:  # pragma: no cover # noqa: E722  # pylint: disable=W0702
                return d
        if not isinstance(d, dict):
            if isinstance(d, int):
                warnings.warn('Invalid value for tableSchema property')
            d = {}
        return cls(**cls.partition_properties(d))

    @property
    def columndict(self) -> dict[str, Column]:
        """A table's columns mapped by header, i.e. normalized name."""
        return {c.header: c for c in self.columns}

    def get_column(self, name: str, strict: bool = False) -> Optional[Column]:
        """Resolve a Column by name, titles or propertyUrl."""
        col = self.columndict.get(name)
        assert (not strict) or (col and col.name), name
        if not col:
            for c in self.columns:
                if c.titles and c.titles.getfirst() == name:
                    return c
                if c.propertyUrl and c.propertyUrl.uri == name:
                    return c
        return col


@dataclasses.dataclass
class TableLike(Description):
    """
    A CSVW description object as encountered "in the wild", i.e. identified by URL on the web or
    as file on disk.

    Since `TableLike` objects may be instantiated from "externally referenced" objects
    (via file paths or URLs), they have the necessary means to resolve
    `link properties <https://www.w3.org/TR/tabular-metadata/#link-properties>`_

    .. code-block:: python

        >>> from csvw import Table, TableGroup, Link
        >>> t = Table.from_file('tests/fixtures/csv.txt-table-metadata.json')
        >>> Link('abc.txt').resolve(t.base)
        PosixPath('tests/fixtures/abc.txt')
        >>> tg = TableGroup.from_url(
        ...     'https://raw.githubusercontent.com/cldf/csvw/master/tests/fixtures/'
        ...     'csv.txt-metadata.json')
        >>> str(tg.tables[0].url)
        'csv.txt'
        >>> tg.tables[0].url.resolve(tg.base)
        'https://raw.githubusercontent.com/cldf/csvw/master/tests/fixtures/csv.txt'

    and `URI template properties <https://www.w3.org/TR/tabular-metadata/#uri-template-properties>`_
    (see :meth:`~TableLike.expand`).
    """
    dialect: Optional[Union[str, Dialect]] = None
    notes: list[str] = dataclasses.field(default_factory=list)
    tableDirection: Literal['rtl', 'ltr', 'auto'] = 'auto'  # pylint: disable=invalid-name
    tableSchema: Optional[Schema] = None  # pylint: disable=invalid-name
    transformations: list = dataclasses.field(default_factory=list)
    url: Optional[Link] = None
    _fname: Union[str, pathlib.Path] = None  # The path of the metadata file.

    def __post_init__(self):
        super().__post_init__()
        if isinstance(self.dialect, str):
            self.dialect = Dialect(
                **dialect_props(utils.get_json(Link(self.dialect).resolve(self.base))))
        elif self.dialect is not None:
            self.dialect = Dialect(**dialect_props(self.dialect))

        self.tableDirection = utils.type_checker(
            str, 'auto', self.tableDirection, cond=lambda s: s in ['rtl', 'ltr', 'auto'])
        self.tableSchema = Schema.fromvalue(self.tableSchema)

        if not isinstance(self.transformations, list):
            warnings.warn('Invalid transformations property')
        for tr in self.transformations:
            DescriptionBase.partition_properties(tr, type_name='Template')
        if self.url is not None:
            self.url = Link(self.url)

        if self.tableSchema and not isinstance(self.tableSchema, str):
            self.tableSchema._parent = self  # pylint: disable=protected-access
        if 'id' in self.at_props and self.at_props['id'] is None:
            self.at_props['id'] = self.base
        valid_context_property(self.at_props.get('context'))

    def get_column(self, spec: str) -> Optional[Column]:  # pylint: disable=C0116
        return self.tableSchema.get_column(spec) if self.tableSchema else None

    @classmethod
    def from_file(cls, fname: Union[str, pathlib.Path], data=None) -> 'TableLike':
        """
        Instantiate a CSVW Table or TableGroup description from a metadata file.
        """
        if is_url(str(fname)):
            return cls.from_url(str(fname), data=data)
        res = cls.fromvalue(data or utils.get_json(fname))
        res._fname = pathlib.Path(fname)
        return res

    @classmethod
    def from_url(cls, url: str, data=None) -> 'TableLike':
        """
        Instantiate a CSVW Table or TableGroup description from a metadata file specified by URL.
        """
        data = data or utils.get_json(url)
        url = urlparse(url)
        data.setdefault('@base', urlunparse((url.scheme, url.netloc, url.path, '', '', '')))
        for table in data.get('tables', [data]):
            if isinstance(table, dict) and isinstance(table.get('tableSchema'), str):
                table['tableSchema'] = Link(table['tableSchema']).resolve(data['@base'])
        res = cls.fromvalue(data)
        return res

    def to_file(self, fname: Union[str, pathlib.Path], omit_defaults=True) -> pathlib.Path:
        """
        Write a CSVW Table or TableGroup description as JSON object to a local file.

        :param omit_defaults: The CSVW spec specifies defaults for most properties of most \
        description objects. If `omit_defaults==True`, these properties will be pruned from \
        the JSON object.
        """
        fname = pathlib.Path(fname)
        data = self.asdict(omit_defaults=omit_defaults)
        with utils.json_open(str(fname), 'w') as f:
            json.dump(data, f, indent=4, separators=(',', ': '))
        return fname

    @property
    def base(self) -> Union[str, pathlib.Path]:
        """
        The "base" to resolve relative links against.
        """
        at_props = self._parent.at_props if self._parent else self.at_props
        ctxbase = None
        for obj in self.at_props.get('context', []):
            if isinstance(obj, dict) and '@base' in obj:
                ctxbase = obj['@base']
        if 'base' in at_props:
            if ctxbase:
                # If present, its value MUST be a string that is interpreted as a URL which is
                # resolved against the location of the metadata document to provide the
                # **base URL** for other URLs in the metadata document.
                return Link(ctxbase).resolve(at_props['base'])
            return at_props['base']
        if self._parent and self._parent._fname:  # pylint: disable=protected-access
            return self._parent._fname.parent  # pylint: disable=protected-access
        return self._fname.parent if self._fname else None  # pylint: disable=protected-access

    def expand(self, tmpl: URITemplate, row: dict, _row, _name=None, qname=False) -> str:
        """
        Expand a `URITemplate` using `row`, `_row` and `_name` as context and resolving the result
        against `TableLike.url`.

        .. code-block:: python

            >>> from csvw import URITemplate, TableGroup
            >>> tg = TableGroup.from_url(
            ...     'https://raw.githubusercontent.com/cldf/csvw/master/tests/fixtures/'
            ...     'csv.txt-metadata.json')
            >>> tg.expand(URITemplate('/path?{a}{#b}'), dict(a='1', b='2'), None)
            'https://raw.githubusercontent.com/path?1#2'

        """
        if tmpl is INVALID:
            return self.url.resolve(self.base)

        for prefix, url in NAMESPACES.items():
            if tmpl.uri.startswith(prefix + ':'):
                # If the URI Template is a QName, we expand it to a URL to prevent `Link.resolve`
                # from turning it into a local path.
                res = f"{url}{tmpl.uri.split(':')[1]}"
                break
        else:
            res = Link(
                tmpl.expand(
                    _row=_row,
                    _name=_name,
                    **{_k: _v for _k, _v in row.items() if isinstance(_k, str)}
                )).resolve(self.url.resolve(self.base) if self.url else self.base)
        if not isinstance(res, pathlib.Path):
            if qname:
                for prefix, url in NAMESPACES.items():
                    if res.startswith(url):
                        res = res.replace(url, prefix + ':')
                        break
        return res


@dataclasses.dataclass(frozen=True)
class CsvRow:
    """A bag of attributes specifying a row in a CSV file."""
    fname: str
    lineno: int
    row: list[str]


@dataclasses.dataclass
class RowParseSpec:
    """A bag of attributes used when parsing a CSV row."""
    strict: bool
    log: Optional[logging.Logger]
    row_implementation: type = collections.OrderedDict
    error: bool = False

    def log_error(self, msg: str):
        """Log and record error."""
        utils.log_or_raise(msg, log=self.log)
        self.error = True


@dataclasses.dataclass
class TableParseSpec:
    """Some metadata, categorizing columns in a table."""
    colnames: list[str] = dataclasses.field(default_factory=list)
    virtualcols: list[tuple[str, URITemplate]] = dataclasses.field(default_factory=list)
    requiredcols: set[str] = dataclasses.field(default_factory=set)

    @classmethod
    def from_columns(cls, columns: Iterable[Column]) -> 'TableParseSpec':
        """Initialize from columns (e.g. columns property of Schema)."""
        res = cls()
        for col in columns:
            if col.virtual:
                if col.valueUrl:
                    res.virtualcols.append((col.header, col.valueUrl))
            else:
                res.colnames.append(col.header)
            if col.required:
                res.requiredcols.add(col.header)
        return res


@dataclasses.dataclass
class Table(TableLike):
    """
    A table description is an object that describes a table within a CSV file.

    `Table` objects provide access to schema manipulation either by manipulating the `tableSchema`
    property directly or via higher-level methods like :meth:`~Table.add_foreign_key`

    `Table` objects also mediate read/write access to the actual data through

    - :meth:`~Table.write`
    - :meth:`~Table.iterdicts`

    .. seealso:: `<https://www.w3.org/TR/tabular-metadata/#tables>`_
    """
    suppressOutput: bool = False  # pylint: disable=invalid-name
    _comments = []

    def add_foreign_key(self, colref, ref_resource, ref_colref):
        """
        Add a foreign key constraint to `tableSchema.foreignKeys`.

        :param colref: Column reference for the foreign key.
        :param ref_resource: Referenced table.
        :param ref_colref: Column reference of the key in the referenced table.
        """
        colref = [colref] if not isinstance(colref, (tuple, list)) else colref
        if not all(col in [c.name for c in self.tableSchema.columns] for col in colref):
            raise ValueError(f'unknown column in foreignKey {colref}')

        self.tableSchema.foreignKeys.append(ForeignKey.fromdict({
            'columnReference': colref,
            'reference': {'resource': ref_resource, 'columnReference': ref_colref}
        }))

    def __post_init__(self):
        TableLike.__post_init__(self)
        if not self.url:
            raise ValueError('url property is required for Tables')

    @property
    def local_name(self) -> Union[str, None]:
        """The filename of a table."""
        return self.url.string if self.url else None

    def _get_dialect(self) -> Dialect:
        return self.dialect or (self._parent and self._parent.dialect) or Dialect()

    def write(self,
              items: Iterable[Union[dict, list, tuple]],
              fname: Optional[Union[str, pathlib.Path]] = DEFAULT,
              base: Optional[Union[str, pathlib.Path]] = None,
              strict: Optional[bool] = False,
              _zipped: Optional[bool] = False) -> Union[str, int]:
        """
        Write row items to a CSV file according to the table schema.

        :param items: Iterator of `dict` storing the data per row.
        :param fname: Name of the file to which to write the data.
        :param base: Base directory relative to which to interpret table urls.
        :param strict: Flag signaling to use strict mode when writing. This will raise `ValueError`\
        if any row (dict) passed in `items` contains unspecified fieldnames.
        :param _zipped: Flag signaling whether the resulting data file should be zipped.
        :return: The CSV content if `fname==None` else the number of rows written.
        """
        dialect = self._get_dialect()
        non_virtual_cols = [c for c in self.tableSchema.columns if not c.virtual]
        if fname is DEFAULT:
            fname = self.url.resolve(pathlib.Path(base) if base else self.base)

        rowcount = 0
        with UnicodeWriter(fname, dialect=dialect) as writer:
            if dialect.header:
                writer.writerow([c.header for c in non_virtual_cols])
            for item in items:
                if isinstance(item, (list, tuple)):
                    row = [col.write(item[i]) for i, col in enumerate(non_virtual_cols)]
                else:
                    if strict:
                        add = set(item.keys()) - {f'{col}' for col in non_virtual_cols}
                        if add:
                            add = ', '.join(f"'{field}'" for field in add)
                            raise ValueError(f"dict contains fields not in fieldnames: {add}")
                    row = [
                        col.write(item.get(col.header, item.get(f'{col}')))
                        for col in non_virtual_cols]
                rowcount += 1
                writer.writerow(row)
            if fname is None:
                return writer.read()
        if fname and _zipped:
            fpath = pathlib.Path(fname)
            with zipfile.ZipFile(
                str(fpath.parent.joinpath(fpath.name + '.zip')),
                'w',
                compression=zipfile.ZIP_DEFLATED
            ) as zipf:
                zipf.write(str(fpath), arcname=fpath.name)
            fpath.unlink()
        return rowcount

    def check_primary_key(self, log=None, items=None) -> bool:
        """Make sure primary keys are unique."""
        # We want to silence error logging when reading table rows, because we are not interested
        # in conversion errors here.
        nolog = logging.getLogger(__name__)
        nolog.addHandler(logging.NullHandler())

        success = True
        if items is not None:
            warnings.warn('the items argument of check_primary_key '
                          'is deprecated (its content will be ignored)')  # pragma: no cover
        if self.tableSchema.primaryKey:
            get_pk = operator.itemgetter(*self.tableSchema.primaryKey)
            seen = set()
            # Read all rows in the table, ignoring errors:
            for fname, lineno, row in self.iterdicts(log=nolog, with_metadata=True):
                pk = get_pk(row)
                if pk in seen:
                    utils.log_or_raise(f'{fname}:{lineno} duplicate primary key: {pk}', log=log)
                    success = False
                else:
                    seen.add(pk)
        return success

    def __iter__(self):
        return self.iterdicts()

    def _get_csv_reader(self, fname, dialect, stack) -> UnicodeReaderWithLineNumber:
        if is_url(fname):
            handle = io.TextIOWrapper(
                io.BytesIO(utils.request_get(str(fname)).content), encoding=dialect.encoding)
        else:
            handle = fname
            fpath = pathlib.Path(fname)
            if not fpath.exists():
                zipfname = fpath.parent.joinpath(fpath.name + '.zip')
                if zipfname.exists():
                    zipf = stack.enter_context(zipfile.ZipFile(zipfname))  # pylint: disable=R1732
                    handle = io.TextIOWrapper(
                        zipf.open([n for n in zipf.namelist() if n.endswith(fpath.name)][0]),
                        encoding=dialect.encoding)

        return stack.enter_context(UnicodeReaderWithLineNumber(handle, dialect=dialect))

    def _validated_csv_header(self, header, strict) -> list[str]:
        if not strict:
            if self.tableSchema.columns and len(self.tableSchema.columns) < len(header):
                warnings.warn('Column number mismatch')
            for name, col in zip(header, self.tableSchema.columns):
                res = col.has_title(name)
                if (not col.name) and not res:
                    warnings.warn('Incompatible table models')
                if (isinstance(res, str) and  # noqa: W504
                        res.split('-')[0] not in ['und', (self.lang or 'und').split('-')[0]]):
                    warnings.warn('Incompatible column titles')
        return header

    def _read_row(
            self,
            row: CsvRow,
            parse_spec: RowParseSpec,
            header_cols: list[tuple[int, str, Column]],
            spec: TableParseSpec,
    ) -> RowType:
        required = {h: j for j, h, c in header_cols if c and c.required}
        res = parse_spec.row_implementation()

        for (j, k, col), v in zip(header_cols, row.row):
            # see http://w3c.github.io/csvw/syntax/#parsing-cells
            if col:
                try:
                    res[col.header] = col.read(v, strict=parse_spec.strict)
                except ValueError as e:
                    if not parse_spec.strict:
                        warnings.warn(f'Invalid column value: {v} {col.datatype}; {e}')
                        res[col.header] = v
                    else:
                        parse_spec.log_error(f'{row.fname}:{row.lineno}:{j + 1} {k}: {e}')
                if k in required:
                    del required[k]
            else:
                if parse_spec.strict:
                    warnings.warn(f'Unspecified column "{k}" in table {self.local_name}')
                res[k] = v

        for k, j in required.items():
            if k not in res:
                parse_spec.log_error(
                    f'{row.fname}:{row.lineno}:{j + 1} {k}: required column value is missing')

        # Augment result with regular columns not provided in the data:
        for key in spec.colnames:
            res.setdefault(key, None)

        # Augment result with virtual columns:
        for key, value_url in spec.virtualcols:
            res[key] = value_url.expand(**res)
        return res

    def _get_header_cols(
            self,
            header: list[str],
            colnames: list[str],
            strict: bool,
            row: Iterable,
    ) -> list[tuple[int, str, Column]]:
        def default_col(index):
            return Column.fromvalue({'name': f'_col.{index}'})

        # If columns in the data are ordered as in the spec, we can match values to
        # columns by index, rather than looking up columns by name.
        if (header == colnames) or \
                (len(self.tableSchema.columns) >= len(header) and not strict):
            # Note that virtual columns are only allowed to come **after** regular ones,
            # so we can simply zip the whole columns list, and silently ignore surplus
            # virtual columns.
            header_cols = list(zip(header, self.tableSchema.columns))
        elif not strict and self.tableSchema.columns and \
                (len(self.tableSchema.columns) < len(header)):
            header_cols = []
            for i, cname in enumerate(header):
                try:
                    header_cols.append((cname, self.tableSchema.columns[i]))
                except IndexError:
                    col = default_col(i + 1)
                    header_cols.append((col.name, col))
        else:
            header_cols = [(h, self.tableSchema.get_column(h)) for h in header]

        if not header_cols:
            for i, _ in enumerate(row):
                col = default_col(i + 1)
                header_cols.append((col.name, col))

        return [(j, h, c) for j, (h, c) in enumerate(header_cols)]

    def iterdicts(  # pylint: disable=too-many-locals
            self,
            log: Optional[logging.Logger] = None,
            with_metadata: bool = False,
            fname=None,
            _Row: type = collections.OrderedDict,  # pylint: disable=invalid-name
            strict=True,
    ) -> Generator[Union[dict[str, Any], tuple[str, int, dict[str, Any]]], None, None]:
        """Iterate over the rows of the table

        Create an iterator that maps the information in each row to a `dict` whose keys are
        the column names of the table and whose values are the values in the corresponding
        table cells, or for virtual columns (which have no values) the valueUrl for that
        column. This includes columns not specified in the table specification.

        Note: If the resolved data filename does not exist - but there is a zip file of the form
        `fname+'.zip'`, we try to read the data from this file after unzipping.

        :param log: Logger object (default None) The object that reports parsing errors.\
        If none is given, parsing errors raise ValueError instead.
        :param bool with_metadata: (default False) Also yield fname and lineno
        :param fname: file-like, pathlib.Path, or str (default None)\
        The file to be read. Defaults to inheriting from a parent object, if one exists.
        :param strict: Flag signaling whether data is read strictly - i.e. raising `ValueError` \
        when invalid data is encountered - or not - i.e. only issueing a warning and returning \
        invalid data as `str` as provided by the undelying DSV reader.
        :return: A generator of dicts or triples (fname, lineno, dict) if with_metadata
        """
        dialect = self._get_dialect()
        fname = fname or self.url.resolve(self.base)

        table_parse_spec = TableParseSpec.from_columns(self.tableSchema.columns)

        with contextlib.ExitStack() as stack:
            reader = iter(self._get_csv_reader(fname, dialect, stack))

            # If the data file has a header row, this row overrides the header as
            # specified in the metadata.
            if dialect.header:
                try:
                    header = self._validated_csv_header(next(reader)[1], strict)
                except StopIteration:  # pragma: no cover
                    return
            else:
                header = table_parse_spec.colnames

            header_cols = None
            for i, (lineno, row) in enumerate(reader):
                if i == 0:
                    header_cols = self._get_header_cols(
                        header, table_parse_spec.colnames, strict, row)
                    missing = table_parse_spec.requiredcols - \
                        {c.header for j, h, c in header_cols if c}
                    if missing:
                        raise ValueError(f'{fname} is missing required columns {missing}')

                parse_spec = RowParseSpec(strict=strict, log=log, row_implementation=_Row)
                res = self._read_row(
                    CsvRow(fname=fname, lineno=lineno, row=row),
                    parse_spec,
                    header_cols,
                    table_parse_spec,
                )
                if not parse_spec.error:
                    yield (fname, lineno, res) if with_metadata else res
        self._comments = reader.comments


@dataclasses.dataclass(frozen=True)
class ForeignKeyInstance:
    """Simple structure holding the specification of a foreign key."""
    target_table: Table
    pk: ColRefType
    source_table: Table
    fk: ColRefType

    def validate(self, strict: bool) -> None:
        """Checks whether the colrefs for fk and pk match."""
        if len(self.fk) != len(self.pk):
            raise ValueError(
                'Foreign key error: non-matching number of columns in source and target')
        for scol, tcol in zip(self.fk, self.pk):
            scolumn = self.source_table.tableSchema.get_column(scol, strict=strict)
            tcolumn = self.target_table.tableSchema.get_column(tcol, strict=strict)
            if not (scolumn and tcolumn):
                raise ValueError(
                    f'Foreign key error: missing column "{scol}" or "{tcol}"')
            if scolumn.datatype and tcolumn.datatype and \
                    scolumn.datatype.base != tcolumn.datatype.base:
                raise ValueError(
                    f'Foregin key error: non-matching datatype "{scol}:{scolumn.datatype.base}" '
                    f'or "{tcol}:{tcolumn.datatype.base}"')


@dataclasses.dataclass
class TableGroup(TableLike):
    """
    A table group description is an object that describes a group of tables.

    A `TableGroup` delegates most of its responsibilities to the `Table` objects listed in its
    `tables` property. For convenience, `TableGroup` provides methods to
    - read data from all tables: :meth:`TableGroup.read`
    - write data for all tables: :meth:`TableGroup.write`

    It also provides a method to check the referential integrity of data in related tables via
    :meth:`TableGroup.check_referential_integrity`

    .. seealso:: `<https://www.w3.org/TR/tabular-metadata/#table-groups>`_
    """
    tables: list[Table] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        res = []
        for vv in self.tables:
            if not isinstance(vv, (dict, Table)):
                warnings.warn('Invalid value for Table spec')
            else:
                res.append(Table.fromvalue(vv) if isinstance(vv, dict) else vv)
        self.tables = res
        super().__post_init__()
        for table in self.tables:
            table._parent = self  # pylint: disable=protected-access

    @classmethod
    def from_frictionless_datapackage(cls, dp):
        """Initialize a TableGroup from a frictionless DataPackage."""
        return DataPackage(dp).to_tablegroup(cls)

    def read(self):
        """
        Read all data of a TableGroup
        """
        return {tname: list(t.iterdicts()) for tname, t in self.tabledict.items()}

    def write(self,
              fname: Union[str, pathlib.Path],
              strict: Optional[bool] = False,
              _zipped: Optional[bool] = False,
              **items: Iterable[Union[list, tuple, dict]]):
        """
        Write a TableGroup's data and metadata to files.

        :param fname: Filename for the metadata file.
        :param items: Keyword arguments are used to pass iterables of rows per table, where the \
        table URL is specified as keyword.
        """
        fname = pathlib.Path(fname)
        for tname, rows in items.items():
            self.tabledict[tname].write(rows, base=fname.parent, strict=strict, _zipped=_zipped)
        self.to_file(fname)

    def copy(self, dest: Union[pathlib.Path, str]):
        """
        Write a TableGroup's data and metadata to files relative to `dest`, adapting the `base`
        attribute.

        :param dest:
        :return:
        """
        dest = pathlib.Path(dest)
        for table in self.tables:
            shutil.copy(str(table.url.resolve(self.base)), str(table.url.resolve(dest)))
        self._fname = dest / self._fname.name
        self.to_file(self._fname)

    @property
    def tabledict(self) -> dict[str, Table]:
        """Convenient access to tables by name."""
        return {t.local_name: t for t in self.tables}

    def validate_schema(self, strict: bool = False) -> list[ForeignKeyInstance]:
        """Check whether pk and fk specs in foreign key constraints match."""
        try:
            fkis = sorted(
                [
                    ForeignKeyInstance(
                        self.tabledict[fk.reference.resource.string],
                        tuple(fk.reference.columnReference),
                        t,
                        tuple(fk.columnReference))
                    for t in self.tables for fk in t.tableSchema.foreignKeys
                    if not fk.reference.schemaReference],
                key=lambda x: (x.target_table.local_name, x.pk, x.source_table.local_name))
        except KeyError as e:
            raise ValueError(f'Foreign key error: missing table "{e}" referenced') from e
        try:
            for fki in fkis:
                fki.validate(strict=strict)
        except AssertionError as e:
            raise ValueError(f'Foreign key error: missing column "{e}" referenced') from e
        return fkis

    def check_referential_integrity(self, data=None, log=None, strict=False):
        """
        Strict validation does not allow for nullable foreign key columns.
        """
        if data is not None:
            warnings.warn('the data argument of check_referential_integrity '
                          'is deprecated (its content will be ignored)')  # pragma: no cover
        if strict:
            for t in self.tables:
                for fk in t.tableSchema.foreignKeys:
                    for row in t:
                        if any(row.get(col) is None for col in fk.columnReference):
                            raise ValueError(
                                f'Foreign key column is null: '
                                f'{[row.get(col) for col in fk.columnReference]} '
                                f'{fk.columnReference}')
        try:
            fkis = self.validate_schema()
            success = True
        except ValueError as e:
            fkis = []
            success = False
            utils.log_or_raise(str(e), log=log, level='error')

        # FIXME: We only support Foreign Key references between tables!  pylint: disable=W0511
        # We group foreign key constraints by target table, because we only want to read the
        # available primary keys once and then check all tables referencing the target table in
        # a loop.
        #
        # Grouping by local_name of tables - even though we'd like to have the table objects
        # around, too. This it to prevent going down the rabbit hole of comparing table objects
        # for equality, when comparison of the string names is enough.
        for _, grp in itertools.groupby(fkis, lambda x: x.target_table.local_name):
            grp = list(grp)
            target_table = grp[0].target_table
            fks = collections.OrderedDict()
            for pk, kgrp in itertools.groupby(grp, lambda x: x.pk):
                fks[tuple(pk)] = [(fk.source_table, tuple(fk.fk)) for fk in kgrp]
            success = self._check_fks_referencing_table(success, target_table, fks, strict, log)
        return success

    @staticmethod
    def _check_fks_referencing_table(
            success: bool,
            target_table: Table,
            fks: collections.OrderedDict[ColRefType, list[tuple[Table, ColRefType]]],
            strict: bool,
            log: logging.Logger,
    ) -> bool:
        """Check all foreign keys referencing the same table."""
        target_table = ReferencedTable(
            target_table, collections.OrderedDict((fk, len(fk) == 1) for fk in fks), log)
        # Now read the available primary keys for each foreign key constraint to the table.
        success = target_table.get_pks(success, strict)
        for pk, source_tables in fks.items():
            # For each foreign key constraint referencing `target_table` we check the fk values.
            for source_table, fk in source_tables:
                success = target_table.check_fks(success, pk, source_table, fk)
        return success


@dataclasses.dataclass
class ReferencedTable:
    """
    Wraps a Table object to simplify checking of foreign key references.
    """
    table: Table
    # The colrefs which are referenced in foreign keys to the table mapped to whether they are a
    # single column or a composite key:
    pks: collections.OrderedDict[ColRefType, bool]
    log: logging.Logger
    # We store values in table rows for each pk colref:
    refs: dict[ColRefType, set] = dataclasses.field(
        default_factory=lambda: collections.defaultdict(set))

    def get_pks(self, success: bool, strict: bool) -> bool:
        """Read the actual fk values in the table."""
        itemgetters = {pk: operator.itemgetter(*pk) for pk in self.pks}
        for row in self.table.iterdicts(log=self.log):
            for pk in self.pks:
                vals = itemgetters[pk](row)
                if vals in self.refs[pk]:
                    # Values for a primary key are not unique!
                    # https://w3c.github.io/csvw/tests/#manifest-validation#test258
                    if strict:
                        success = False
                self.refs[pk].add(vals)
        return success

    def _check_item(self, success: bool, vals: 'RefValues', pk: ColRefType) -> bool:
        """
        We check if the value for the foreign key are available in the referenced table.
        """
        pks = self.refs[pk]
        single_column = self.pks[pk]
        if vals.values is None:  # null-valued foreign key.
            return success
        if single_column and isinstance(vals.values, list):
            # We allow list-valued columns as foreign key columns in case it's not a composite key.
            # If a foreign key is list-valued, we check for a matching row for each of the values
            # in the list.
            refs = vals.values
        else:
            refs = [vals.values]
        for ref in refs:
            if not single_column and None in ref:  # pragma: no cover
                # A composite key and one component of the fk is null?
                # TODO: raise if any(c is not None for c in values)?  pylint: disable=W0511
                continue
            if ref not in pks:
                utils.log_or_raise(
                    f'{vals} not found in table {self.table.url.string}', log=self.log)
                success = False
        return success

    def check_fks(
            self,
            success: bool,
            pk: ColRefType,
            source_table: Table,
            fk: ColRefType,
    ) -> bool:
        """
        Check one fk constraint, i.e. whether the fk values in self.table actually can be found
        in `target_table`.
        """
        for fname, lineno, item in source_table.iterdicts(log=self.log, with_metadata=True):
            item = RefValues(fname=fname, lineno=lineno, values=operator.itemgetter(*fk)(item))
            success = self._check_item(success, item, pk)
        return success


@dataclasses.dataclass(frozen=True)
class RefValues:
    """Bundle properties of a table row for simpler checking."""
    fname: str
    lineno: int
    values: Union[str, list[str]]

    def __str__(self):
        return f'{self.fname}:{self.lineno} Key `{self.values}`'


class CSVW:
    """
    Python API to read CSVW described data and convert it to JSON.
    """
    def __init__(
            self,
            url: str,
            md_url: Optional[str] = None,
            validate: bool = False,
            strict: bool = True,
    ):
        self.warnings = []
        self._strict = strict
        w = None
        with contextlib.ExitStack() as stack:
            if validate:
                w = stack.enter_context(warnings.catch_warnings(record=True))

            no_header = False
            try:
                md = utils.get_json(md_url or url)
                # The URL could be read as JSON document, thus, the user supplied us with overriding
                # metadata as per https://w3c.github.io/csvw/syntax/#overriding-metadata
            except json.decoder.JSONDecodeError:
                # So we got a CSV file, no JSON. Let's locate metadata using the other methods.
                md, no_header = self.locate_metadata(url)

            self.no_metadata = set(md.keys()) == {'@context', 'url'}
            if "http://www.w3.org/ns/csvw" not in md.get('@context', ''):
                raise ValueError('Invalid or no @context')
            self._set_tables(md, url, no_header)
            self.tables = self.t.tables if isinstance(self.t, TableGroup) else [self.t]
            for table in self.tables:
                for col in table.tableSchema.columns:
                    if col.name and (re.search(r'\s', col.name) or col.name.startswith('_')):
                        col.name = None
            self.common_props = self.t.common_props
        if w:
            self.warnings.extend(w)

    def _set_tables(self, md, url, no_header):
        if 'tables' in md:
            if not md['tables'] or not isinstance(md['tables'], list):
                raise ValueError('Invalid TableGroup with empty tables property')
            if is_url(url):
                self.t = TableGroup.from_url(url, data=md)
                self.t.validate_schema(strict=True)
            else:
                self.t = TableGroup.from_file(url, data=md)
        else:
            if is_url(url):
                self.t = Table.from_url(url, data=md)
                if no_header:
                    if self.t.dialect:
                        self.t.dialect.header = False  # pragma: no cover
                    else:
                        self.t.dialect = Dialect(header=False)
            else:
                self.t = Table.from_file(url, data=md)

    @property
    def is_valid(self) -> bool:
        """
        Performs CSVW validation.

        .. note::

            For this to also catch problems during metadata location, the
            `CSVW` instance must be initialized with `validate=True`.
        """
        if self.warnings:
            return False
        with warnings.catch_warnings(record=True) as w:
            for table in self.tables:
                for _ in table.iterdicts(strict=False):
                    pass
                if not table.check_primary_key():  # pragma: no cover
                    warnings.warn('Duplicate primary key')
            if not self.tablegroup.check_referential_integrity(strict=self._strict):
                warnings.warn('Referential integrity check failed')
            if w:
                self.warnings.extend(w)
        return not bool(self.warnings)

    @property
    def tablegroup(self) -> TableGroup:
        """The table spec."""
        return self.t if isinstance(self.t, TableGroup) else \
            TableGroup(at_props={'base': self.t.base}, tables=self.tables)

    @staticmethod
    def locate_metadata(url=None) -> tuple[dict, bool]:
        """
        Implements metadata discovery as specified in
        `§5. Locating Metadata <https://w3c.github.io/csvw/syntax/#locating-metadata>`_
        """
        def describes(md, url):
            for table in md.get('tables', [md]):
                # FIXME: pylint: disable=W0511
                # We check whether the metadata describes a CSV file just superficially,
                # by comparing the last path components of the respective URLs.
                if url.split('/')[-1] == table['url'].split('/')[-1]:
                    return True
            return False

        no_header = False
        if url and is_url(url):
            # §5.2 Link Header
            # https://w3c.github.io/csvw/syntax/#link-header
            content_type, links = utils.request_head(url)
            no_header = bool(re.search(r'header\s*=\s*absent', content_type))
            for link in links:
                if link.params.get('rel') == 'describedby':
                    if link.params.get('type') in [
                            "application/csvm+json", "application/ld+json", "application/json"]:
                        md = utils.get_json(Link(link.url).resolve(url))
                        if describes(md, url):
                            return md, no_header
                warnings.warn('Ignoring linked metadata because it does not reference the data')

            # §5.3 Default Locations and Site-wide Location Configuration
            # https://w3c.github.io/csvw/syntax/
            # #default-locations-and-site-wide-location-configuration
            res = utils.request_get(Link('/.well-known/csvm').resolve(url))
            locs = res.text if res.status_code == 200 else '{+url}-metadata.json\ncsv-metadata.json'
            for line in locs.split('\n'):
                res = utils.request_get(Link(URITemplate(line).expand(url=url)).resolve(url))
                if res.status_code == 200:
                    try:
                        md = res.json()
                        if describes(md, url):
                            return md, no_header
                        warnings.warn('Ignoring metadata because it does not reference the data')
                    except json.JSONDecodeError:
                        pass

            # §5.4 Embedded Metadata
            # https://w3c.github.io/csvw/syntax/#embedded-metadata
            # We only recognize column names read from the first row of a CSV file.
        elif url:
            # Default Locations for local files:
            if pathlib.Path(str(url) + '-metadata.json').exists():
                return utils.get_json(pathlib.Path(str(url) + '-metadata.json')), no_header
        res = {
            '@context': "http://www.w3.org/ns/csvw",
            'url': url,
        }
        if not is_url(url or ''):
            # No metadata detected for a local CSV file. To make table reading work, we set the
            # directory as @base and the filename as url property of the description.
            p = pathlib.Path(url)
            res['@base'] = str(p)
            res['url'] = p.name
        return res, no_header

    def to_json(self, minimal=False):
        """
        Implements algorithm described in `<https://w3c.github.io/csvw/csv2json/#standard-mode>`_
        """
        res = collections.OrderedDict()
        # Insert any notes and non-core annotations specified for the group of tables into object
        # G according to the rules provided in § 5. JSON-LD to JSON.
        if self.t.common_props and not isinstance(self.t, Table):
            res.update(jsonld.to_json(self.t.common_props, flatten_list=True))
        res['tables'] = [
            self._table_to_json(table) for table in self.tables if not table.suppressOutput]
        if minimal:
            return list(
                itertools.chain(*[[r['describes'][0] for r in t['row']] for t in res['tables']]))

        return res

    def _table_to_json(self, table):
        res = collections.OrderedDict()
        # FIXME: id  pylint: disable=W0511
        res['url'] = str(table.url.resolve(table.base))
        if 'id' in table.at_props:
            res['@id'] = table.at_props['id']
        if table.notes:
            res['notes'] = jsonld.to_json(table.notes)
        # Insert any notes and non-core annotations specified for the group of tables into object
        # G according to the rules provided in § 5. JSON-LD to JSON.
        res.update(jsonld.to_json(table.common_props))

        cols = collections.OrderedDict([(col.header, col) for col in table.tableSchema.columns])
        for col in cols.values():
            col.propertyUrl = col.inherit('propertyUrl')
            col.valueUrl = col.inherit('valueUrl')

        row = [
            self._row_to_json(table, cols, row, rownum, rowsourcenum)
            for rownum, (_, rowsourcenum, row) in enumerate(
                table.iterdicts(with_metadata=True, strict=False), start=1)
        ]
        if table._comments:  # pylint: disable=W0212
            res['rdfs:comment'] = [c[1] for c in table._comments]  # pylint: disable=W0212
        res['row'] = row
        return res

    def _row_to_json(self, table, cols, row, rownum, rowsourcenum):  # pylint: disable=R0913,R0917
        res = collections.OrderedDict()
        res['url'] = f'{table.url.resolve(table.base)}#row={rowsourcenum}'
        res['rownum'] = rownum
        if table.tableSchema.rowTitles:
            res['titles'] = [
                t for t in [row.get(name) for name in table.tableSchema.rowTitles] if t]
            if len(res['titles']) == 1:
                res['titles'] = res['titles'][0]
        # Insert any notes and non-core annotations specified for the group of tables into object
        # G according to the rules provided in § 5. JSON-LD to JSON.

        res['describes'] = self._describes(table, cols, row, rownum)
        return res

    def _describes(self, table, cols, row, rownum):
        triples = []

        aboutUrl = table.tableSchema.inherit('aboutUrl')  # pylint: disable=invalid-name
        if aboutUrl:
            triples.append(jsonld.Triple(
                about=None, property='@id', value=table.expand(aboutUrl, row, _row=rownum)))

        for i, (k, v) in enumerate(row.items(), start=1):
            col = cols.get(k)
            if col and (col.suppressOutput or col.virtual):
                continue

            # Skip null values:
            null = col.inherit_null() if col else table.inherit_null()
            if any([null and v in null, v == "", v is None, col and col.separator and v == []]):
                continue

            triples.append(jsonld.Triple.from_col(
                table,
                col,
                row,
                f'_col.{i}' if (not table.tableSchema.columns and not self.no_metadata) else k,
                v,
                rownum))

        for col in table.tableSchema.columns:
            if col.virtual:
                triples.append(jsonld.Triple.from_col(table, col, row, col.header, None, rownum))
        return jsonld.group_triples(triples)
