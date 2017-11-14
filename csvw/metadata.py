# coding: utf8
"""
Functionality to read and write metadata for CSV files.

This module implements (partially) the W3C recommendation
"Metadata Vocabulary for Tabular Data".

.. seealso:: https://www.w3.org/TR/tabular-metadata/
"""
from __future__ import unicode_literals, print_function, division

import re
from collections import OrderedDict

from six import text_type

import attr
from uritemplate import URITemplate as _URITemplate

from clldutils.dsv import Dialect, UnicodeReaderWithLineNumber, UnicodeWriter
from clldutils.jsonlib import load, dump
from clldutils.path import Path
from clldutils.misc import UnicodeMixin, NO_DEFAULT, log_or_raise
from clldutils import attrlib
from clldutils.csvw.datatypes import DATATYPES

# Level 1 variable names according to https://tools.ietf.org/html/rfc6570#section-2.3:
_varchar = '([a-zA-Z0-9_]|\%[a-fA-F0-9]{2})'
_varname = re.compile('(' + _varchar + '([.]?' + _varchar + ')*)$')


class URITemplate(_URITemplate):
    def __eq__(self, other):
        if not hasattr(other, 'uri'):
            return False
        return _URITemplate.__eq__(self, other)  # pragma: no cover

    def asdict(self, **kw):
        return '{0}'.format(self)


def uri_template_property():
    """
    Note: We do not currently provide support for supplying the "_" variables like "_row"
    when expanding a URI template.

    .. seealso:: http://w3c.github.io/csvw/metadata/#uri-template-properties
    """
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(URITemplate)),
        convert=lambda v: v if v is None else URITemplate(v))


class Link(UnicodeMixin):
    """
    .. seealso:: http://w3c.github.io/csvw/metadata/#link-properties
    """
    def __init__(self, string):
        self.string = string

    def __unicode__(self):
        return self.string

    def asdict(self, omit_defaults=True):
        return self.string

    def __eq__(self, other):
        # FIXME: Only naive, un-resolved comparison is supported at the moment.
        return self.string == other.string if isinstance(other, Link) else False

    def resolve(self, base):
        if not base:
            return self.string
        if isinstance(base, Path):
            return base.joinpath(self.string)
        if not base.endswith('/'):
            base += '/'
        return base + self.string


def link_property():
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(Link)),
        convert=lambda v: v if v is None else Link(v))


class NaturalLanguage(UnicodeMixin, OrderedDict):
    """
    .. seealso:: http://w3c.github.io/csvw/metadata/#natural-language-properties
    """
    def __init__(self, value):
        OrderedDict.__init__(self)
        self.value = value
        if isinstance(self.value, text_type):
            self[None] = [self.value]
        elif isinstance(self.value, (list, tuple)):
            self[None] = list(self.value)
        elif isinstance(self.value, (dict, OrderedDict)):
            for k, v in self.value.items():
                if not isinstance(v, (list, tuple)):
                    v = [v]
                self[k] = v
        else:
            raise ValueError('invalid value type for NaturalLanguage')

    def asdict(self, omit_defaults=True):
        if list(self.keys()) == [None]:
            if len(self[None]) == 1:
                return self.getfirst()
            return self[None]
        return OrderedDict(
            [('und' if k is None else k, v[0] if len(v) == 1 else v)
             for k, v in self.items()])

    def add(self, string, lang=None):
        if lang not in self:
            self[lang] = []
        self[lang].append(string)

    def __unicode__(self):
        return self.getfirst() or list(self.values())[0][0]

    def getfirst(self, lang=None):
        return self.get(lang, [None])[0]


@attr.s
class DescriptionBase(object):
    """
    Container for
    - common properties (see http://w3c.github.io/csvw/metadata/#common-properties)
    - @-properies.
    """
    common_props = attr.ib(default=attr.Factory(dict))
    at_props = attr.ib(default=attr.Factory(dict))

    @staticmethod
    def partition_properties(d):
        c, a, dd = {}, {}, {}
        for k, v in (d or {}).items():
            if k.startswith('@'):
                a[k[1:]] = v
            elif ':' in k:
                c[k] = v
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

        for k, v in attrlib.asdict(self, omit_defaults=omit_defaults).items():
            if k not in ['common_props', 'at_props']:
                yield k, _asdict_multiple(v)

    def asdict(self, omit_defaults=True):
        return OrderedDict(
            [(k, v) for k, v in
             self._iter_dict_items(omit_defaults) if v not in [None, [], {}]])


def optional_int():
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(int)),
        convert=lambda v: v if v is None else int(v))


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

    def __attrs_post_init__(self):
        if self.length is not None:
            if self.minLength is not None and self.length < self.minLength:
                raise ValueError()

            if self.maxLength is not None:
                if self.length > self.maxLength:
                    raise ValueError()

        if self.minLength is not None and self.maxLength is not None \
                and self.minLength > self.maxLength:
            raise ValueError()

        if not isinstance(self.derived_description, dict):
            raise ValueError()  # pragma: no cover

    @classmethod
    def fromvalue(cls, v):
        """
        either a single string that is the main datatype of the values of the cell or a
        datatype description object.
        """
        if isinstance(v, text_type):
            return cls(base=v)

        if isinstance(v, (dict, OrderedDict)):
            return cls(**DescriptionBase.partition_properties(v))

        raise ValueError(v)

    def asdict(self, omit_defaults=True):
        res = DescriptionBase.asdict(self, omit_defaults=omit_defaults)
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
            l = len(v or '')
            if self.length is not None and l != self.length:
                raise ValueError()
            if self.minLength is not None and l < self.minLength:
                raise ValueError()
            if self.maxLength is not None and l > self.maxLength:
                raise ValueError()
        except TypeError:
            pass
        if self.basetype.minmax:
            if self.minimum is not None and v < self.minimum:
                raise ValueError()
            if self.maximum is not None and v > self.maximum:
                raise ValueError()
        return v

    def read(self, v):
        return self.validate(self.parse(v))


@attr.s
class Description(DescriptionBase):
    """
    Adds support for inherited properties.

    .. seealso:: http://w3c.github.io/csvw/metadata/#inherited-properties
    """
    # To be able to resolve inheritance chains, we also provide a place to store a
    # reference to the containing object:
    _parent = attr.ib(default=None, repr=False)

    aboutUrl = uri_template_property()
    datatype = attr.ib(
        default=None,
        convert=lambda v: v if not v else Datatype.fromvalue(v))
    default = attr.ib(default="")
    lang = attr.ib(default="und")
    null = attr.ib(
        default=attr.Factory(lambda: [""]),
        convert=lambda v: [] if v is None else (v if isinstance(v, list) else [v]))
    ordered = attr.ib(default=None)
    propertyUrl = uri_template_property()
    required = attr.ib(default=None)
    separator = attr.ib(default=None)
    textDirection = attr.ib(default=None)
    valueUrl = uri_template_property()

    def inherit(self, attr):
        v = getattr(self, attr)
        if v is None and self._parent:
            return getattr(self._parent, attr)
        return v


@attr.s
class Column(UnicodeMixin, Description):
    name = attr.ib(
        default=None,
        validator=attrlib.valid_re(_varname, nullable=True))
    suppressOutput = attr.ib(default=False)
    titles = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(NaturalLanguage)),
        convert=lambda v: v if v is None else NaturalLanguage(v))
    virtual = attr.ib(default=False)
    _number = attr.ib(default=None, repr=False)

    def __unicode__(self):
        return self.name or \
            (self.titles and self.titles.getfirst()) or \
            '_col.{0}'.format(self._number)

    @property
    def header(self):
        return '{0}'.format(self)

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
                v = v.split(separator)
                v = [vv or default for vv in v]
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
        convert=lambda v: v if isinstance(v, list) or v is None else [v])


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
        d = dict(d, reference=Reference(**d['reference']))
        return cls(**d)

    def asdict(self, **kw):
        res = attrlib.asdict(self, **kw)
        res['reference'] = attrlib.asdict(res['reference'], **kw)
        return res


@attr.s
class Schema(Description):
    columns = attr.ib(
        default=attr.Factory(list),
        convert=lambda v: [Column.fromvalue(c) for c in v])
    foreignKeys = attr.ib(
        default=attr.Factory(list),
        convert=lambda v: [] if v is None else [ForeignKey.fromdict(d) for d in v])
    primaryKey = column_reference()
    rowTitles = attr.ib(default=attr.Factory(list))

    def __attrs_post_init__(self):
        virtual = False
        for i, col in enumerate(self.columns):
            if col.virtual:  # first virtual column sets the flag
                virtual = True
            elif virtual:  # non-virtual column after virtual column!
                raise ValueError('no non-virtual column allowed after virtual columns')
            col._parent = self
            col._number = i + 1

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


@attr.s
class TableLike(Description):
    dialect = attr.ib(
        default=None, convert=lambda v: Dialect(**v) if isinstance(v, dict) else v)
    notes = attr.ib(default=attr.Factory(list))
    tableDirection = attr.ib(
        default='auto',
        validator=attr.validators.in_(['rtl', 'ltr', 'auto']))
    tableSchema = attr.ib(
        default=None,
        convert=lambda v: Schema.fromvalue(v))
    transformations = attr.ib(default=attr.Factory(list))

    def __attrs_post_init__(self):
        if self.tableSchema:
            self.tableSchema._parent = self

    def get_column(self, spec):
        return self.tableSchema.get_column(spec) if self.tableSchema else None


@attr.s
class Table(TableLike):
    url = link_property()
    suppressOutput = attr.ib(default=False)

    @property
    def local_name(self):
        return self.url.string

    def _get_dialect(self):
        return self.dialect or (self._parent and self._parent.dialect) or Dialect()

    def write(self, items, fname=NO_DEFAULT):
        dialect = self._get_dialect()
        non_virtual_cols = [c for c in self.tableSchema.columns if not c.virtual]
        if fname is NO_DEFAULT:
            fname = self.url.resolve(self._parent.base)

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
                writer.writerow(row)
            if fname is None:
                return writer.read()

    def check_primary_key(self, log=None, items=None):
        pks = set()
        if self.tableSchema.primaryKey:
            for fname, lineno, row in (
                self.iterdicts(log=log, with_metadata=True) if items is None else items
            ):
                pk = tuple(row[col] for col in self.tableSchema.primaryKey)
                if pk in pks:
                    log_or_raise(
                        '{0}:{1} duplicate primary key: {2}'.format(fname, lineno, pk),
                        log=log)
                pks.add(pk)

    def __iter__(self):
        return self.iterdicts()

    def iterdicts(self, log=None, with_metadata=False, fname=None):
        dialect = self._get_dialect()
        fname = fname or self.url.resolve(self._parent.base)
        colnames, virtualcols = [], []
        for col in self.tableSchema.columns:
            if col.virtual:
                if col.valueUrl:
                    virtualcols.append((col.header, col.valueUrl))
            else:
                colnames.append(col.header)

        with UnicodeReaderWithLineNumber(fname, dialect=dialect) as reader:
            header = colnames
            # If columns in the data are ordered as in the spec, we can match values to
            # columns by index, rather than looking up columns by name.
            cols_in_order = True
            for i, (lineno, row) in enumerate(reader):
                if dialect.header and i == 0:
                    # If the data file has a header row, this row overrides the header as
                    # specified in the metadata.
                    header = row
                    cols_in_order = header == colnames
                    continue

                res = OrderedDict()
                error = False
                for j, (k, v) in enumerate(zip(header, row)):
                    # see http://w3c.github.io/csvw/syntax/#parsing-cells
                    if cols_in_order:
                        col = self.tableSchema.columns[j]
                    else:
                        col = self.tableSchema.get_column(k)

                    if col:
                        try:
                            res[col.header] = col.read(v)
                        except ValueError as e:
                            log_or_raise(
                                '{0}:{1}:{2} {3}: {4}'.format(fname, lineno, j + 1, k, e),
                                log=log)
                            error = True
                    else:
                        res[k] = v

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
    _fname = attr.ib(default=None)
    url = attr.ib(default=None)
    tables = attr.ib(
        repr=False,
        default=attr.Factory(list),
        convert=lambda v: [Table.fromvalue(vv) for vv in v])

    def __attrs_post_init__(self):
        TableLike.__attrs_post_init__(self)
        for table in self.tables:
            table._parent = self

    @property
    def tabledict(self):
        return {t.local_name: t for t in self.tables}

    def check_referential_integrity(self, data=None, log=None):
        if data is None:
            data = {}
            for n, table in self.tabledict.items():
                data[n] = list(table.iterdicts(log=log, with_metadata=True))

        for n, table in self.tabledict.items():
            for fk in table.tableSchema.foreignKeys:
                if fk.reference.schemaReference:
                    # FIXME: We only support Foreign Key references between tables!
                    continue

                keys = set(tuple(ref[k] for k in fk.reference.columnReference)
                           for _, _, ref in data[fk.reference.resource.string])
                for fname, lineno, item in data[n]:
                    colref = tuple(item[k] for k in fk.columnReference)
                    if len(colref) == 1 and isinstance(colref[0], list):
                        # We allow list-valued columns as foreign key columns in case
                        # it's not a composite key. If a foreign key is list-valued, we
                        # check for a matching row for each of the values in the list.
                        colrefs = [(cr,) for cr in colref[0]]
                    else:
                        colrefs = [colref]
                    for colref in colrefs:
                        if any(c is not None for c in colref) and colref not in keys:
                            log_or_raise(
                                '{0}:{1} Key {2} not found in table {3}'.format(
                                    fname,
                                    lineno,
                                    colref,
                                    fk.reference.resource.string),
                                log=log)

    #
    # FIXME: to_sqlite()!
    #

    @property
    def base(self):
        return self._fname.parent

    @classmethod
    def from_file(cls, fname):
        res = cls.fromvalue(load(fname))
        res._fname = Path(fname)
        return res

    def to_file(self, fname, omit_defaults=True):
        dump(self.asdict(omit_defaults=omit_defaults), fname, indent=4)
        return fname
