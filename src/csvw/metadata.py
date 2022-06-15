# metadata.py

"""Functionality to read and write metadata for CSV files.

This module implements (partially) the W3C recommendation
"Metadata Vocabulary for Tabular Data".

.. seealso:: https://www.w3.org/TR/tabular-metadata/
"""
import io
import re
import json
import shutil
import pathlib
import zipfile
import datetime
import operator
import warnings
import functools
import itertools
import contextlib
import collections
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import urlopen

import attr
import requests
import uritemplate
from rfc3986 import URIReference

from . import utils
from .datatypes import DATATYPES
from .dsv import Dialect, UnicodeReaderWithLineNumber, UnicodeWriter
from .frictionless import DataPackage

DEFAULT = object()

__all__ = [
    'TableGroup',
    'Table', 'Column', 'ForeignKey',
    'Link', 'NaturalLanguage',
    'Datatype',
    'is_url',
]

NAMESPACES = {
    'csvw': 'http://www.w3.org/ns/csvw#',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
    'dc': 'http://purl.org/dc/terms/',
    'dcat': 'http://www.w3.org/ns/dcat#',
    'prov': 'http://www.w3.org/ns/prov#',
    'schema': 'http://schema.org/',
}


class Invalid:
    pass


INVALID = Invalid()


def is_url(s):
    return re.match(r'https?://', str(s))


def json_open(filename, mode='r', encoding='utf-8'):
    assert encoding == 'utf-8'
    return io.open(filename, mode, encoding=encoding)


def get_json(fname):
    fname = str(fname)
    if is_url(fname):
        with io.TextIOWrapper(urlopen(fname), encoding='utf8') as f:
            return json.load(f, object_pairs_hook=collections.OrderedDict)
    with json_open(fname) as f:
        return json.load(f, object_pairs_hook=collections.OrderedDict)


def log_or_raise(msg, log=None, level='warning', exception_cls=ValueError):
    if log:
        getattr(log, level)(msg)
    else:
        raise exception_cls(msg)


def nolog(level='warning'):
    from types import MethodType

    class Log(object):
        pass

    log = Log()
    setattr(log, level, MethodType(lambda *args, **kw: None, log))
    return log


class URITemplate(uritemplate.URITemplate):

    def __eq__(self, other):
        if isinstance(other, str):
            return self.uri == other
        if not hasattr(other, 'uri'):
            return False
        return super(URITemplate, self).__eq__(other)

    def asdict(self, **kw):
        return '{}'.format(self)


def uri_template_property():
    """

    Note: We do not currently provide support for supplying the "_" variables like "_row"
    when expanding a URI template.

    .. seealso:: http://w3c.github.io/csvw/metadata/#uri-template-properties
    """
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of((URITemplate, Invalid))),
        converter=lambda v: None if v is None else (INVALID if not isinstance(v, str) else URITemplate(v)))


class Link(object):
    """

    .. seealso:: http://w3c.github.io/csvw/metadata/#link-properties
    """

    def __init__(self, string):
        self.string = string

    def __str__(self):
        return self.string

    def asdict(self, omit_defaults=True):
        return self.string

    def __eq__(self, other):
        # FIXME: Only naive, un-resolved comparison is supported at the moment.
        return self.string == other.string if isinstance(other, Link) else False

    def resolve(self, base):
        """
        Resolve a `Link` relative to `base`.

        :param base:
        :return: Either a string, representing a URL, or a `pathlib.Path` object, representing \
        a local file.
        """
        if hasattr(base, 'joinpath'):
            return base / self.string
        return urljoin(base, self.string)


def link_property(required=False):
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(Link)),
        converter=lambda v: v if v is None else Link(v))


class NaturalLanguage(collections.OrderedDict):
    """

    .. seealso:: http://w3c.github.io/csvw/metadata/#natural-language-properties
    """

    def __init__(self, value):
        super(NaturalLanguage, self).__init__()
        self.value = value
        if isinstance(self.value, str):
            self[None] = [self.value]
        elif isinstance(self.value, (list, tuple)):
            self[None] = list(self.value)
        elif isinstance(self.value, dict):
            for k, v in self.value.items():
                if not isinstance(v, (list, tuple)):
                    v = [v]
                self[k] = v
        else:
            raise ValueError('invalid value type for NaturalLanguage')

    def asdict(self, omit_defaults=True):
        if list(self) == [None]:
            if len(self[None]) == 1:
                return self.getfirst()
            return self[None]
        return collections.OrderedDict(
            ('und' if k is None else k, v[0] if len(v) == 1 else v)
            for k, v in self.items())

    def add(self, string, lang=None):
        if lang not in self:
            self[lang] = []
        self[lang].append(string)

    def __str__(self):
        return self.getfirst() or next(iter(self.values()))[0]

    def getfirst(self, lang=None):
        return self.get(lang, [None])[0]


def valid_id_property(v):
    if v.startswith('_'):
        raise ValueError('Invalid @id property: {}'.format(v))
    return v


@attr.s
class DescriptionBase(object):
    """Container for
    - common properties (see http://w3c.github.io/csvw/metadata/#common-properties)
    - @-properties.
    """

    common_props = attr.ib(default=attr.Factory(dict))
    at_props = attr.ib(default=attr.Factory(dict))

    @classmethod
    def partition_properties(cls, d, type_name=None, strict=True):
        if d and not isinstance(d, dict):
            return
        fields = attr.fields_dict(cls)
        type_name = type_name or cls.__name__
        c, a, dd = {}, {}, {}
        for k, v in (d or {}).items():
            if k.startswith('@'):
                if k == '@id':
                    v = valid_id_property(v)
                if k == '@type' and v != type_name:
                    raise ValueError('Invalid @type property {} for {}'.format(v, type_name))
                a[k[1:]] = v
            elif ':' in k:
                c[k] = v
            else:
                if strict and (k not in fields):
                    warnings.warn('Invalid property {} for {}'.format(k, type_name))
                else:
                    dd[k] = v
        return dict(common_props=c, at_props=a, **dd)

    @classmethod
    def fromvalue(cls, d):
        return cls(**cls.partition_properties(d))

    def _iter_dict_items(self, omit_defaults):
        def _asdict_single(v):
            return v.asdict(omit_defaults=omit_defaults) if hasattr(v, 'asdict') else v

        def _asdict_multiple(v):
            if isinstance(v, (list, tuple)):
                return [_asdict_single(vv) for vv in v]
            return _asdict_single(v)

        for k, v in sorted(self.at_props.items()):
            yield '@' + k, _asdict_multiple(v)

        for k, v in sorted(self.common_props.items()):
            yield k, _asdict_multiple(v)

        for k, v in utils.attr_asdict(self, omit_defaults=omit_defaults).items():
            if k not in ('common_props', 'at_props'):
                yield k, _asdict_multiple(v)

    def asdict(self, omit_defaults=True):
        return collections.OrderedDict(
            (k, v) for k, v in self._iter_dict_items(omit_defaults) if v not in ([], {}))


def optional_int():
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(int)),
        converter=lambda v: v if v is None else int(v))


@attr.s
class Datatype(DescriptionBase):
    """

    .. seealso:: http://w3c.github.io/csvw/metadata/#datatypes
    """

    base = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.in_(DATATYPES)))
    format = attr.ib(default=None)
    length = optional_int()
    minLength = optional_int()
    maxLength = optional_int()
    minimum = attr.ib(default=None)
    maximum = attr.ib(default=None)
    minInclusive = attr.ib(default=None)
    maxInclusive = attr.ib(default=None)
    minExclusive = attr.ib(default=None)
    maxExclusive = attr.ib(default=None)

    @classmethod
    def fromvalue(cls, v):
        """
        :param v: Initialization data for `cls`; either a single string that is the main datatype \
        of the values of the cell or a datatype description object, i.e. a `dict` or a `cls`
        instance.
        :return: An instance of `cls`
        """
        if isinstance(v, str):
            return cls(base=v)

        if isinstance(v, dict):
            return cls(**cls.partition_properties(v))

        if isinstance(v, cls):
            return v

        raise ValueError(v)

    def __attrs_post_init__(self):
        for attr_ in [
            'minimum', 'maximum', 'minInclusive', 'maxInclusive', 'minExclusive', 'maxExclusive'
        ]:
            if getattr(self, attr_) is not None:
                setattr(self, attr_, self.parse(getattr(self, attr_)))

        if self.length is not None:
            if self.minLength is not None and self.length < self.minLength:
                raise ValueError('minLength > length')

            if self.maxLength is not None:
                if self.length > self.maxLength:
                    raise ValueError('maxLength < length')

        if self.minLength is not None and self.maxLength is not None \
                and self.minLength > self.maxLength:
            raise ValueError('minLength > maxLength')

        if not isinstance(self.derived_description, dict):
            raise ValueError()  # pragma: no cover

    def asdict(self, omit_defaults=True):
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
    def basetype(self):
        return DATATYPES[self.base]

    @property
    def derived_description(self):
        return self.basetype.derived_description(self)

    def formatted(self, v):
        return self.basetype.to_string(v, **self.derived_description)

    def parse(self, v):
        if v is None:
            return v
        return self.basetype.to_python(v, **self.derived_description)

    def validate(self, v):
        if v is None:
            return v
        try:
            l_ = len(v or '')
            if self.length is not None and l_ != self.length:
                raise ValueError('value must have length {}'.format(self.length))
            if self.minLength is not None and l_ < self.minLength:
                raise ValueError('value must have at least length {}'.format(self.minLength))
            if self.maxLength is not None and l_ > self.maxLength:
                raise ValueError('value must have at most length {}'.format(self.maxLength))
        except TypeError:
            pass
        if self.basetype.minmax:
            if self.minimum is not None and v < self.minimum:
                raise ValueError('value must be >= {}'.format(self.minimum))
            if self.maximum is not None and v > self.maximum:
                raise ValueError('value must be <= {}'.format(self.maximum))
        return v

    def read(self, v):
        return self.validate(self.parse(v))


@attr.s
class Description(DescriptionBase):
    """Adds support for inherited properties.

    .. seealso:: http://w3c.github.io/csvw/metadata/#inherited-properties
    """

    # To be able to resolve inheritance chains, we also provide a place to store a
    # reference to the containing object:
    _parent = attr.ib(default=None, repr=False)

    aboutUrl = uri_template_property()
    datatype = attr.ib(
        default=None,
        converter=lambda v: v if not v else Datatype.fromvalue(v))
    default = attr.ib(default="")
    lang = attr.ib(default="und")
    null = attr.ib(
        default=attr.Factory(lambda: [""]),
        converter=lambda v: [] if v is None else (v if isinstance(v, list) else [v]))
    ordered = attr.ib(default=None)
    propertyUrl = uri_template_property()
    required = attr.ib(default=None)
    separator = attr.ib(
        converter=functools.partial(utils.converter, str, None, allow_none=True),
        default=None,
    )
    textDirection = attr.ib(default=None)
    valueUrl = uri_template_property()

    def inherit(self, attr):
        v = getattr(self, attr)
        if v is None and self._parent:
            return self._parent.inherit(attr) if hasattr(self._parent, 'inherit') \
                else  getattr(self._parent, attr)
        return v


@attr.s
class Column(Description):

    name = attr.ib(default=None)
    suppressOutput = attr.ib(default=False)
    titles = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(NaturalLanguage)),
        converter=lambda v: v if v is None else NaturalLanguage(v))
    virtual = attr.ib(default=False)
    _number = attr.ib(default=None, repr=False)

    def __str__(self):
        return self.name or \
            (self.titles and self.titles.getfirst()) or \
            '_col.{}'.format(self._number)

    @property
    def header(self):
        return '{}'.format(self)

    def read(self, v):
        required = self.inherit('required')
        null = self.inherit('null')
        default = self.inherit('default')
        separator = self.inherit('separator')
        datatype = self.inherit('datatype')

        if not v:
            v = default

        if required and v in null:
            raise ValueError('required column value is missing')

        if separator:
            if not v:
                v = []
            elif v in null:
                v = None
            else:
                v = (vv or default for vv in v.split(separator))
                v = [None if vv in null else vv for vv in v]
        elif v in null:
            v = None

        if datatype:
            if isinstance(v, list):
                return [datatype.read(vv) for vv in v]
            return datatype.read(v)
        return v

    def write(self, v):
        sep = self.inherit('separator')
        null = self.inherit('null')
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


def column_reference():
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(list)),
        converter=lambda v: v if isinstance(v, list) or v is None else [v])


@attr.s
class Reference(object):

    resource = link_property()
    schemaReference = link_property()
    columnReference = column_reference()

    def __attrs_post_init__(self):
        if self.resource is not None and self.schemaReference is not None:
            raise ValueError(self)


@attr.s
class ForeignKey(object):

    columnReference = column_reference()
    reference = attr.ib(default=None)

    @classmethod
    def fromdict(cls, d):
        kw = dict(d, reference=Reference(**d['reference']))
        return cls(**kw)

    def asdict(self, **kw):
        res = utils.attr_asdict(self, **kw)
        res['reference'] = utils.attr_asdict(res['reference'], **kw)
        return res


@attr.s
class Schema(Description):

    columns = attr.ib(
        default=attr.Factory(list),
        converter=lambda v: [Column.fromvalue(c) for c in v])
    foreignKeys = attr.ib(
        default=attr.Factory(list),
        converter=lambda v: [] if v is None else [
            ForeignKey.fromdict(d) for d in functools.partial(utils.converter, dict, None)(v)])
    primaryKey = column_reference()
    rowTitles = attr.ib(default=attr.Factory(list))

    def __attrs_post_init__(self):
        virtual, seen = False, set()
        for i, col in enumerate(self.columns):
            if col.virtual:  # first virtual column sets the flag
                virtual = True
            elif virtual:  # non-virtual column after virtual column!
                raise ValueError('no non-virtual column allowed after virtual columns')
            if not virtual:
                if col.header in seen:
                    warnings.warn('Duplicate column name!')
                seen.add(col.header)
            col._parent = self
            col._number = i + 1

    @classmethod
    def fromvalue(cls, v):
        if isinstance(v, str):
            try:
                # The schema is referenced with a URL
                v = json.loads(urlopen(v).read().decode('utf8'))
            except:
                return v
        return cls(**cls.partition_properties(v))

    @property
    def columndict(self):
        return {c.header: c for c in self.columns}

    def get_column(self, name):
        col = self.columndict.get(name)
        if not col:
            for c in self.columns:
                if c.titles and c.titles.getfirst() == name:
                    return c
                if c.propertyUrl and c.propertyUrl.uri == name:
                    return c
        return col


def dialect_props(d):
    partitioned = Description.partition_properties(d, type_name='Dialect', strict=False)
    del partitioned['at_props']
    del partitioned['common_props']
    return partitioned


def valid_transformations(instance, attribute, value):
    if not isinstance(value, list):
        warnings.warn('Invalid transformations property')
    for tr in value:
        Description.partition_properties(tr, type_name='Template')


@attr.s
class TableLike(Description):

    dialect = attr.ib(
        default=None,
        converter=lambda v: Dialect(**dialect_props(v)) if isinstance(v, dict) else v)
    notes = attr.ib(default=attr.Factory(list))
    tableDirection = attr.ib(
        default='auto',
        converter=functools.partial(
            utils.converter, str, 'auto', cond=lambda s: s in ['rtl', 'ltr', 'auto']),
        validator=attr.validators.in_(['rtl', 'ltr', 'auto']))
    tableSchema = attr.ib(
        default=None,
        converter=lambda v: Schema.fromvalue(v))
    transformations = attr.ib(
        validator=valid_transformations,
        default=attr.Factory(list),
    )
    url = link_property()
    _fname = attr.ib(default=None)  # The path of the metadata file.

    def __attrs_post_init__(self):
        if self.tableSchema and not(isinstance(self.tableSchema, str)):
            self.tableSchema._parent = self

    def get_column(self, spec):
        return self.tableSchema.get_column(spec) if self.tableSchema else None

    @classmethod
    def from_file(cls, fname, data=None):
        if is_url(str(fname)):
            return cls.from_url(str(fname), data=data)
        res = cls.fromvalue(data or get_json(fname))
        res._fname = pathlib.Path(fname)
        return res

    @classmethod
    def from_url(cls, url, data=None):
        data = data or get_json(url)
        url = urlparse(url)
        data.setdefault('@base', urlunparse((url.scheme, url.netloc, url.path, '', '', '')))
        res = cls.fromvalue(data or get_json(url))
        return res

    def to_file(self, fname, omit_defaults=True):
        fname = utils.ensure_path(fname)
        data = self.asdict(omit_defaults=omit_defaults)
        with json_open(str(fname), 'w') as f:
            json.dump(data, f, indent=4, separators=(',', ': '))
        return fname

    @property
    def base(self):
        """
        We only support data in the filesystem, thus we make sure `base` is a `pathlib.Path`.
        """
        at_props = self._parent.at_props if self._parent else self.at_props
        if 'base' in at_props:
            return at_props['base']
        return self._parent._fname.parent if (self._parent and self._parent._fname) else \
            (self._fname.parent if self._fname else None)


@attr.s
class Table(TableLike):

    suppressOutput = attr.ib(default=False)

    def add_foreign_key(self, colref, ref_resource, ref_colref):
        """
        Add a foreign key constraint to `tableSchema.foreignKeys`.

        :param colref: Column reference for the foreign key.
        :param ref_resource: Referenced table.
        :param ref_colref: Column reference of the key in the referenced table.
        """
        colref = [colref] if not isinstance(colref, (tuple, list)) else colref
        if not all(col in [c.name for c in self.tableSchema.columns] for col in colref):
            raise ValueError('unknown column in foreignKey {0}'.format(colref))

        self.tableSchema.foreignKeys.append(ForeignKey.fromdict({
            'columnReference': colref,
            'reference': {'resource': ref_resource, 'columnReference': ref_colref}
        }))

    def __attrs_post_init__(self):
        TableLike.__attrs_post_init__(self)
        if not self.url:
            raise ValueError('url property is required for Tables')

    @property
    def local_name(self):
        return self.url.string if self.url else None

    def _get_dialect(self):
        return self.dialect or (self._parent and self._parent.dialect) or Dialect()

    def write(self, items, fname=DEFAULT, base=None, _zipped=False):
        """
        Write row items to a CSV file according to the table schema.

        :param items: Iterator of `dict`s storing the data per row.
        :param fname: Name of the file to which to write the data.
        :param base: Base directory relative to which to interpret table urls.
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
                    row = [
                        col.write(item.get(
                            col.header, item.get('{0}'.format(col))))
                        for col in non_virtual_cols]
                rowcount += 1
                writer.writerow(row)
            if fname is None:
                return writer.read()
        if fname and _zipped:
            fpath = pathlib.Path(fname)
            with zipfile.ZipFile(str(fpath.parent.joinpath(fpath.name + '.zip')), 'w') as zipf:
                zipf.write(str(fpath))
            fpath.unlink()
        return rowcount

    def check_primary_key(self, log=None, items=None):
        success = True
        if items is not None:
            warnings.warn('the items argument of check_primary_key '
                          'is deprecated (its content will be ignored)')  # pragma: no cover
        if self.tableSchema.primaryKey:
            get_pk = operator.itemgetter(*self.tableSchema.primaryKey)
            seen = set()
            # Read all rows in the table, ignoring errors:
            for fname, lineno, row in self.iterdicts(log=nolog(), with_metadata=True):
                pk = get_pk(row)
                if pk in seen:
                    log_or_raise(
                        '{0}:{1} duplicate primary key: {2}'.format(fname, lineno, pk),
                        log=log)
                    success = False
                else:
                    seen.add(pk)
        return success

    def __iter__(self):
        return self.iterdicts()

    def iterdicts(self, log=None, with_metadata=False, fname=None, _Row=collections.OrderedDict):
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
        :return: A generator of dicts or triples (fname, lineno, dict) if with_metadata
        """
        dialect = self._get_dialect()
        fname = fname or self.url.resolve(self.base)
        colnames, virtualcols, requiredcols = [], [], set()
        for col in self.tableSchema.columns:
            if col.virtual:
                if col.valueUrl:
                    virtualcols.append((col.header, col.valueUrl))
            else:
                colnames.append(col.header)
            if col.required:
                requiredcols.add(col.header)

        with contextlib.ExitStack() as stack:
            if is_url(fname):
                handle = io.TextIOWrapper(urlopen(str(fname)), encoding=dialect.encoding)
            else:
                handle = fname
                fpath = pathlib.Path(fname)
                if not fpath.exists():
                    zipfname = fpath.parent.joinpath(fpath.name + '.zip')
                    if zipfname.exists():
                        zipf = stack.enter_context(zipfile.ZipFile(str(zipfname)))
                        handle = io.TextIOWrapper(
                            zipf.open([n for n in zipf.namelist() if n.endswith(fpath.name)][0]),
                            encoding=dialect.encoding)

            reader = stack.enter_context(UnicodeReaderWithLineNumber(handle, dialect=dialect))
            reader = iter(reader)

            # If the data file has a header row, this row overrides the header as
            # specified in the metadata.
            if dialect.header:
                try:
                    _, header = next(reader)
                except StopIteration:  # pragma: no cover
                    return
            else:
                header = colnames

            # If columns in the data are ordered as in the spec, we can match values to
            # columns by index, rather than looking up columns by name.
            if header == colnames:
                # Note that virtual columns are only allowed to come **after** regular ones,
                # so we can simply zip the whole columns list, and silently ignore surplus
                # virtual columns.
                header_cols = list(zip(header, self.tableSchema.columns))
            else:
                header_cols = [(h, self.tableSchema.get_column(h)) for h in header]
            header_cols = [(j, h, c) for j, (h, c) in enumerate(header_cols)]
            missing = requiredcols - set(c.header for j, h, c in header_cols if c)
            if missing:
                raise ValueError('{0} is missing required columns {1}'.format(fname, missing))

            for lineno, row in reader:
                required = {h: j for j, h, c in header_cols if c and c.required}
                res = _Row()
                error = False
                if (not header_cols) and row:
                    header_cols = [
                        (i,
                         '_col.{}'.format(i + 1),
                         Column.fromvalue({'name': '_col.{}'.format(i + 1)}))
                        for i, _ in enumerate(row)]
                for (j, k, col), v in zip(header_cols, row):
                    # see http://w3c.github.io/csvw/syntax/#parsing-cells
                    if col:
                        if k in required:
                            del required[k]
                        try:
                            res[col.header] = col.read(v)
                        except ValueError as e:
                            log_or_raise(
                                '{0}:{1}:{2} {3}: {4}'.format(fname, lineno, j + 1, k, e),
                                log=log)
                            error = True
                    else:
                        warnings.warn(
                            'Unspecified column "{0}" in table {1}'.format(k, self.local_name))
                        res[k] = v

                for k, j in required.items():
                    if k not in res:
                        log_or_raise(
                            '{0}:{1}:{2} {3}: {4}'.format(
                                fname, lineno, j + 1, k, 'required column value is missing'),
                            log=log)
                        error = True

                # Augment result with regular columns not provided in the data:
                for key in colnames:
                    res.setdefault(key, None)

                # Augment result with virtual columns:
                for key, valueUrl in virtualcols:
                    res[key] = valueUrl.expand(**res)

                if not error:
                    if with_metadata:
                        yield fname, lineno, res
                    else:
                        yield res


@attr.s
class TableGroup(TableLike):

    tables = attr.ib(
        repr=False,
        default=attr.Factory(list),
        converter=lambda v: [Table.fromvalue(vv) for vv in v])

    def __attrs_post_init__(self):
        TableLike.__attrs_post_init__(self)
        for table in self.tables:
            table._parent = self
            if isinstance(table.tableSchema, str):
                table.tableSchema = Schema.fromvalue(
                    Link(table.tableSchema).resolve(self.base))
                if isinstance(table.tableSchema, str):
                    table.tableSchema = Schema.fromvalue({})
                table.tableSchema._parent = table

    @classmethod
    def from_frictionless_datapackage(cls, dp):
        return DataPackage(dp).to_tablegroup(cls)

    def read(self):
        """
        Read all data of a TableGroup
        """
        return {tname: list(t.iterdicts()) for tname, t in self.tabledict.items()}

    def write(self, fname, _zipped=False, **items):
        """
        Write a TableGroup's data and metadata to files.

        :param fname:
        :param items:
        :return:
        """
        fname = pathlib.Path(fname)
        for tname, rows in items.items():
            self.tabledict[tname].write(rows, base=fname.parent, _zipped=_zipped)
        self.to_file(fname)

    def copy(self, dest):
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
    def tabledict(self):
        return {t.local_name: t for t in self.tables}

    def foreign_keys(self):
        return [
            (
                self.tabledict[fk.reference.resource.string],
                fk.reference.columnReference,
                t,
                fk.columnReference)
            for t in self.tables for fk in t.tableSchema.foreignKeys
            if not fk.reference.schemaReference]

    def validate_schema(self):
        try:
            for st, sc, tt, tc in self.foreign_keys():
                if len(sc) != len(tc):
                    raise ValueError(
                        'Foreign key error: non-matching number of columns in source and target')
                for scol, tcol in zip(sc, tc):
                    scolumn = st.tableSchema.get_column(scol)
                    tcolumn = tt.tableSchema.get_column(tcol)
                    if not (scolumn and tcolumn):
                        raise ValueError(
                            'Foregin key error: missing column "{}" or "{}"'.format(scol, tcol))
                    if scolumn.datatype and tcolumn.datatype and \
                            scolumn.datatype.base != tcolumn.datatype.base:
                        raise ValueError(
                            'Foregin key error: non-matching datatype "{}:{}" or "{}:{}"'.format(
                                scol, scolumn.datatype.base, tcol, tcolumn.datatype.base))
        except KeyError as e:
            raise ValueError('Foreign key error: missing table "{}" referenced'.format(e))

    def check_referential_integrity(self, data=None, log=None):
        if data is not None:
            warnings.warn('the data argument of check_referential_integrity '
                          'is deprecated (its content will be ignored)')  # pragma: no cover
        try:
            self.validate_schema()
            success = True
        except ValueError as e:
            success = False
            log_or_raise(str(e), log=log, level='error')
        fkeys = self.foreign_keys()
        # FIXME: We only support Foreign Key references between tables!
        fkeys = sorted(fkeys, key=lambda x: (x[0].local_name, x[1], x[2].local_name))
        # Grouping by local_name of tables - even though we'd like to have the table objects
        # around, too. This it to prevent going down the rabbit hole of comparing table objects
        # for equality, when comparison of the string names is enough.
        for _, grp in itertools.groupby(fkeys, lambda x: x[0].local_name):
            grp = list(grp)
            table = grp[0][0]
            t_fkeys = [(key, [(child, ref) for _, _, child, ref in kgrp])
                       for key, kgrp in itertools.groupby(grp, lambda x: x[1])]
            get_seen = [(operator.itemgetter(*key), set()) for key, _ in t_fkeys]
            for row in table.iterdicts(log=log):
                for get, seen in get_seen:
                    seen.add(get(row))
            for (key, children), (_, seen) in zip(t_fkeys, get_seen):
                single_column = (len(key) == 1)
                for child, ref in children:
                    get_ref = operator.itemgetter(*ref)
                    for fname, lineno, item in child.iterdicts(log=log, with_metadata=True):
                        colref = get_ref(item)
                        if colref is None:
                            continue
                        elif single_column and isinstance(colref, list):
                            # We allow list-valued columns as foreign key columns in case
                            # it's not a composite key. If a foreign key is list-valued, we
                            # check for a matching row for each of the values in the list.
                            colrefs = colref
                        else:
                            colrefs = [colref]
                        for colref in colrefs:
                            if not single_column and None in colref:  # pragma: no cover
                                # TODO: raise if any(c is not None for c in colref)?
                                continue
                            elif colref not in seen:
                                log_or_raise(
                                    '{0}:{1} Key `{2}` not found in table {3}'.format(
                                        fname,
                                        lineno,
                                        colref,
                                        table.url.string),
                                    log=log)
                                success = False
        return success


#
# CSVW to JSON
#
def get_metadata(url):
    if is_url(url):
        # 1. Look for a link header!
        desc = requests.head(url).links.get('describedby')
        if desc:
            #
            # FIXME: check mimetype!
            #
            return get_json(Link(desc['url']).resolve(url))
        # 2. Get /.well-known/csvw - fallback to
        # {+url}-metadata.json
        # csv-metadata.json
        # get URITemplate for each line, expand with url=url resolve against url - last path comp
        res = requests.get(Link('/.well-known/csvw').resolve(url))
        locs = res.text if res.status_code == 200 else '{+url}-metadata.json\ncsv-metadata.json'
        for line in locs.split('\n'):
            res = requests.get(Link(URITemplate(line).expand(url=url)).resolve(url))
            if res.status_code == 200:
                return res.json()
    else:
        if pathlib.Path(str(url) + '-metadata.json').exists():
            return get_json(pathlib.Path(str(url) + '-metadata.json'))
    return {
        '@context': "http://www.w3.org/ns/csvw",
        'url': url,
    }


def get_property_and_value(table, col, row, k, v, rownum):
    def format(value):
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.isoformat()
        if isinstance(value, URIReference):
            return value.unsplit()
        return value

    def expand(tmpl, ctx):
        if tmpl is INVALID:
            return table.url.resolve(table.base)
        return Link(
            tmpl.expand(**{_k: _v for _k, _v in ctx.items() if isinstance(_k, str)})).resolve(
            table.url.resolve(table.base))

    # Copy the row data as context for expanding URI templates:
    ctx = {_k: _v for _k, _v in row.items()}
    ctx['_row'] = rownum
    if col:
        ctx[col.name] = ctx.pop(k)
        ctx['_name'] = col.header

    # Skip null values:
    null = col.inherit('null') if col else table.inherit('null')
    if (not (col and col.virtual)) and ((null and v in null) or v == ""):
        return
    if col and col.separator and v == []:
        return

    # Resolve property and value URLs:
    propertyUrl = col.propertyUrl if col else table.inherit('propertyUrl')
    if propertyUrl:
        k = expand(propertyUrl, ctx)
        for prefix, uri in NAMESPACES.items():
            if k.startswith(uri):
                k = k.replace(uri, prefix + ':')
                break
    valueUrl = col.valueUrl if col else table.inherit('valueUrl')
    if valueUrl:
        v = expand(valueUrl, ctx)
        if k != 'rdf:type':
            for prefix, uri in NAMESPACES.items():
                if v.startswith(prefix + ':'):
                    v = v.replace(prefix + ':', uri)
                    break
    s = None
    if col and col.aboutUrl:
        ss = expand(col.aboutUrl, ctx)
        if ss:
            s = ss
    return k, format(v), s


def simplyframe(data):
    items, refs = collections.OrderedDict(), {}
    for item in data:
        itemid = item.get('@id')
        if itemid:
            items[itemid] = item
        for vs in item.values():
            for v in [vs] if not isinstance(vs, list) else vs:
                if isinstance(v, dict):
                    refid = v.get('@id')
                    if refid:
                        refs.setdefault(refid, (v, []))[1].append(item)
    for ref, subjects in refs.values():
        if len(subjects) == 1 and ref['@id'] in items:
            ref.update(items.pop(ref['@id']))
    return items.values()


def group_by_about_url(d):
    from rdflib import Graph, URIRef, Literal

    def jsonld_to_json(obj):
        if isinstance(obj, dict):
            if '@value' in obj:
                obj = obj['@value']
            if len(obj) == 1 and '@id' in obj:
                obj = obj['@id']
        if isinstance(obj, dict):
            return {'@type' if k == 'rdf:type' else k: jsonld_to_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            if len(obj) == 1:
                return jsonld_to_json(obj[0])
            return [jsonld_to_json(v) for v in obj]
        return obj

    grouped = collections.OrderedDict()
    triples = []
    # First pass: get top-level properties.
    for k, v in d:
        if k == '@id':
            grouped[k] = v
        else:
            about, k = k
            if not about:
                # For test48
                if k in grouped:
                    if not isinstance(grouped[k], list):
                        grouped[k] = [grouped[k]]
                    grouped[k].append(v)
                else:
                    grouped[k] = v
            else:
                triples.append((about, k, v))
    if not triples:
        return [grouped]
    g = Graph()
    for s, p, o in triples:
        g.add((URIRef(s), URIRef(p), URIRef(o) if is_url(o) else Literal(o)))
    res = g.serialize(format='json-ld')
    res = [jsonld_to_json(v) for v in simplyframe(json.loads(res))]
    if grouped and len(res) == 1:
        grouped.update(res[0])
        return [grouped]
    return res


class CSVW:
    def __init__(self, url, md_url=None):
        # read md, check for @context, determine whether it's a Table or TableGroup, provide
        # facade to access data.
        try:
            md = get_json(md_url or url)
        except json.decoder.JSONDecodeError:  # So we got a CSV file, no JSON.
            md = get_metadata(url)
        assert "http://www.w3.org/ns/csvw" in md['@context']
        if 'tables' in md:
            if not md['tables'] or not isinstance(md['tables'], list):
                raise ValueError('Invalid TableGroup with empty tables property')
            if is_url(url):
                self.t = TableGroup.from_url(url, data=md)
            else:
                self.t = TableGroup.from_file(url, data=md)
        else:
            if is_url(url):
                self.t = Table.from_url(url, data=md)
            else:
                self.t = Table.from_file(url, data=md)

    def to_json(self, minimal=False):
        """
        Implements algorithm https://w3c.github.io/csvw/csv2json/#standard-mode
        """
        def jsonld_to_json(obj):
            if isinstance(obj, dict):
                if '@value' in obj:
                    obj = obj['@value']
                if '@id' in obj:
                    obj = obj['@id']
            if isinstance(obj, dict):
                return {k: jsonld_to_json(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [jsonld_to_json(v) for v in obj]
            return obj

        res = collections.OrderedDict()
        #if 'id' in :
        #    pass
        # Insert any notes and non-core annotations specified for the group of tables into object G according to the rules provided in § 5. JSON-LD to JSON.
        if self.t.common_props and not isinstance(self.t, Table):
            res.update(jsonld_to_json(self.t.common_props))
        res['tables'] = []
        for table in self.t.tables if isinstance(self.t, TableGroup) else [self.t]:
            if table.suppressOutput:
                continue
            tres = collections.OrderedDict()
            # FIXME: id
            tres['url'] = str(table.url.resolve(table.base))
            if 'id' in table.at_props:
                tres['@id'] = table.at_props['id']
            if table.notes:
                tres['notes'] = jsonld_to_json(table.notes)
            # Insert any notes and non-core annotations specified for the group of tables into object G according to the rules provided in § 5. JSON-LD to JSON.
            tres.update(jsonld_to_json(table.common_props))
            tres['row'] = []
            cols = {col.header: col for col in table.tableSchema.columns}
            for col in cols.values():
                col.propertyUrl = col.inherit('propertyUrl')
                col.valueUrl = col.inherit('valueUrl')

            for rownum, (_, rowsourcenum, row) in enumerate(
                    table.iterdicts(with_metadata=True), start=1):
                rres = collections.OrderedDict()
                rres['url'] = '{}#row={}'.format(table.url.resolve(table.base), rowsourcenum)
                rres['rownum'] = rownum
                # Specify any titles for the row; if row titles is not null, insert the following name-value pair into object R:
                # name
                #     titles
                # value
                #     t
                # where t is the single value or array of values provided by the row titles annotation.

                # Insert any notes and non-core annotations specified for the group of tables into object G according to the rules provided in § 5. JSON-LD to JSON.
                rowd = []
                aboutUrl = table.tableSchema.inherit('aboutUrl')
                print(aboutUrl)
                if aboutUrl:
                    if aboutUrl is INVALID:
                        rurl = table.url.resolve(table.base)
                    else:
                        rurl = aboutUrl.expand(_row=rownum, **row)
                        if rurl.startswith('#'):
                            rurl = '{}{}'.format(table.url.resolve(table.base), rurl)
                    rowd.append(('@id', rurl))
                for k, v in row.items():
                    col = cols.get(k)
                    if col and col.suppressOutput:
                        continue
                    kv = get_property_and_value(table, col, row, k, v, rownum)
                    if kv:
                        rowd.append(((kv[2], kv[0]), kv[1]))
                for col in table.tableSchema.columns:
                    if col.virtual:
                        # put together from about/property/valueUrl
                        kv = get_property_and_value(table, col, row, col.header, None, rownum)
                        if kv:
                            rowd.append(((kv[2], kv[0]), kv[1]))
                rres['describes'] = group_by_about_url(rowd)
                tres['row'].append(rres)
            res['tables'].append(tres)
        if minimal:
            return list(itertools.chain(*[[r['describes'][0] for r in t['row']] for t in res['tables']]))
        return res

    def pprint(self, minimal=False):
        print(json.dumps(self.to_json(minimal=minimal), indent=4))
