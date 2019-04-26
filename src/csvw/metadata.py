# metadata.py

"""Functionality to read and write metadata for CSV files.

This module implements (partially) the W3C recommendation
"Metadata Vocabulary for Tabular Data".

.. seealso:: https://www.w3.org/TR/tabular-metadata/
"""

from __future__ import unicode_literals

import re
import json
import shutil
import operator
import warnings
import itertools
import collections

from ._compat import (pathlib, text_type, iteritems, itervalues, zip,
    py3_unicode_to_str, json_open, urljoin)

import attr
import uritemplate

from . import utils
from .datatypes import DATATYPES
from .dsv import Dialect, UnicodeReaderWithLineNumber, UnicodeWriter

DEFAULT = object()

__all__ = [
    'TableGroup',
    'Table', 'Column', 'ForeignKey',
    'Link', 'NaturalLanguage',
    'Datatype',
]


# Level 1 variable names according to https://tools.ietf.org/html/rfc6570#section-2.3:
_varchar = '([a-zA-Z0-9_]|\%[a-fA-F0-9]{2})'
_varname = re.compile('(' + _varchar + '([.]?' + _varchar + ')*)$')


def log_or_raise(msg, log=None, level='warn', exception_cls=ValueError):
    if log:
        getattr(log, level)(msg)
    else:
        raise exception_cls(msg)


def nolog(level='warn'):
    from types import MethodType

    class Log(object):
        pass

    log = Log()
    setattr(log, level, MethodType(lambda *args, **kw: None, log))
    return log


class URITemplate(uritemplate.URITemplate):

    def __eq__(self, other):
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
        validator=attr.validators.optional(attr.validators.instance_of(URITemplate)),
        converter=lambda v: v if v is None else URITemplate(v))


@py3_unicode_to_str
class Link(object):
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
        """
        Resolve a `Link` relative to `base`.

        :param base:
        :return: Either a string, representing a URL, or a `pathlib.Path` object, representing \
        a local file.
        """
        if hasattr(base, 'joinpath'):
            return base / self.string
        return urljoin(base, self.string)


def link_property():
    return attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(Link)),
        converter=lambda v: v if v is None else Link(v))


@py3_unicode_to_str
class NaturalLanguage(collections.OrderedDict):
    """

    .. seealso:: http://w3c.github.io/csvw/metadata/#natural-language-properties
    """

    def __init__(self, value):
        super(NaturalLanguage, self).__init__()
        self.value = value
        if isinstance(self.value, text_type):
            self[None] = [self.value]
        elif isinstance(self.value, (list, tuple)):
            self[None] = list(self.value)
        elif isinstance(self.value, dict):
            for k, v in iteritems(self.value):
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
            for k, v in iteritems(self))

    def add(self, string, lang=None):
        if lang not in self:
            self[lang] = []
        self[lang].append(string)

    def __unicode__(self):
        return self.getfirst() or next(itervalues(self))[0]

    def getfirst(self, lang=None):
        return self.get(lang, [None])[0]


@attr.s
class DescriptionBase(object):
    """Container for
    - common properties (see http://w3c.github.io/csvw/metadata/#common-properties)
    - @-properies.
    """

    common_props = attr.ib(default=attr.Factory(dict))
    at_props = attr.ib(default=attr.Factory(dict))

    @staticmethod
    def partition_properties(d):
        c, a, dd = {}, {}, {}
        for k, v in iteritems(d or {}):
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

        for k, v in sorted(iteritems(self.at_props)):
            yield '@' + k, _asdict_multiple(v)

        for k, v in sorted(iteritems(self.common_props)):
            yield k, _asdict_multiple(v)

        for k, v in iteritems(utils.attr_asdict(self, omit_defaults=omit_defaults)):
            if k not in ('common_props', 'at_props'):
                yield k, _asdict_multiple(v)

    def asdict(self, omit_defaults=True):
        return collections.OrderedDict(
            (k, v) for k, v in
            self._iter_dict_items(omit_defaults) if v not in (None, [], {}))


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
        if isinstance(v, text_type):
            return cls(base=v)

        if isinstance(v, dict):
            return cls(**DescriptionBase.partition_properties(v))

        if isinstance(v, cls):
            return v

        raise ValueError(v)

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
            l_ = len(v or '')
            if self.length is not None and l_ != self.length:
                raise ValueError()
            if self.minLength is not None and l_ < self.minLength:
                raise ValueError()
            if self.maxLength is not None and l_ > self.maxLength:
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
    separator = attr.ib(default=None)
    textDirection = attr.ib(default=None)
    valueUrl = uri_template_property()

    def inherit(self, attr):
        v = getattr(self, attr)
        if v is None and self._parent:
            return getattr(self._parent, attr)
        return v


@attr.s
@py3_unicode_to_str
class Column(Description):

    name = attr.ib(
        default=None,
        validator=utils.attr_valid_re(_varname, nullable=True))
    suppressOutput = attr.ib(default=False)
    titles = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(NaturalLanguage)),
        converter=lambda v: v if v is None else NaturalLanguage(v))
    virtual = attr.ib(default=False)
    _number = attr.ib(default=None, repr=False)

    def __unicode__(self):
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
        converter=lambda v: [] if v is None else [ForeignKey.fromdict(d) for d in v])
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
        default=None, converter=lambda v: Dialect(**v) if isinstance(v, dict) else v)
    notes = attr.ib(default=attr.Factory(list))
    tableDirection = attr.ib(
        default='auto',
        validator=attr.validators.in_(['rtl', 'ltr', 'auto']))
    tableSchema = attr.ib(
        default=None,
        converter=lambda v: Schema.fromvalue(v))
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

    def write(self, items, fname=DEFAULT, base=None):
        dialect = self._get_dialect()
        non_virtual_cols = [c for c in self.tableSchema.columns if not c.virtual]
        if fname is DEFAULT:
            fname = self.url.resolve(pathlib.Path(base) if base else self._parent.base)

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

        :param log: Logger object (default None) The object that reports parsing errors.\
        If none is given, parsing errors raise ValueError instead.
        :param bool with_metadata: (default False) Also yield fname and lineno
        :param fname: file-like, pathlib.Path, or str (default None)\
        The file to be read. Defaults to inheriting from a parent object, if one exists.
        :return: A generator of dicts or triples (fname, lineno, dict) if with_metadata
        """
        dialect = self._get_dialect()
        fname = fname or self.url.resolve(self._parent.base)
        colnames, virtualcols, requiredcols = [], [], set()
        for col in self.tableSchema.columns:
            if col.virtual:
                if col.valueUrl:
                    virtualcols.append((col.header, col.valueUrl))
            else:
                colnames.append(col.header)
            if col.required:
                requiredcols.add(col.header)

        with UnicodeReaderWithLineNumber(fname, dialect=dialect) as reader:
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
                        res[k] = v

                for k, j in required.items():
                    if k not in res:
                        log_or_raise(
                            '{0}:{1}:{2} {3}: {4}'.format(
                                fname, lineno, j + 1, k, 'required column value is missing'),
                            log=log)
                        error = True

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

    _fname = attr.ib(default=None)  # The path of the metadata file.
    url = attr.ib(default=None)
    tables = attr.ib(
        repr=False,
        default=attr.Factory(list),
        converter=lambda v: [Table.fromvalue(vv) for vv in v])

    @classmethod
    def from_file(cls, fname):
        if not isinstance(fname, pathlib.Path):
            fname = pathlib.Path(fname)
        with json_open(str(fname)) as f:
            data = json.load(f)
        res = cls.fromvalue(data)
        res._fname = fname
        return res

    def __attrs_post_init__(self):
        TableLike.__attrs_post_init__(self)
        for table in self.tables:
            table._parent = self

    def to_file(self, fname, omit_defaults=True):
        if not isinstance(fname, pathlib.Path):
            fname = pathlib.Path(fname)
        data = self.asdict(omit_defaults=omit_defaults)
        with json_open(str(fname), 'w') as f:
            json.dump(data, f, indent=4, separators=(',', ': '))
        return fname

    def read(self):
        """
        Read all data of a TableGroup
        """
        return {tname: list(t.iterdicts()) for tname, t in self.tabledict.items()}

    def write(self, fname, **items):
        """
        Write a TableGroup's data and metadata to files.

        :param fname:
        :param items:
        :return:
        """
        fname = pathlib.Path(fname)
        for tname, rows in items.items():
            self.tabledict[tname].write(rows, base=fname.parent)
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

    @property
    def base(self):
        """
        We only support data in the filesystem, thus we make sure `base` is a `pathlib.Path`.
        """
        return self._fname.parent

    def check_referential_integrity(self, data=None, log=None):
        success = True
        if data is not None:
            warnings.warn('the data argument of check_referential_integrity '
                          'is deprecated (its content will be ignored)')  # pragma: no cover
        fkeys = [
            (
                self.tabledict[fk.reference.resource.string],
                fk.reference.columnReference,
                t,
                fk.columnReference)
            for t in self.tables for fk in t.tableSchema.foreignKeys
            if not fk.reference.schemaReference]
        # FIXME: We only support Foreign Key references between tables!
        fkeys = sorted(fkeys, key=lambda x: (x[0].local_name, x[1], x[2].local_name))
        for table, grp in itertools.groupby(fkeys, lambda x: x[0]):
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
                                    '{0}:{1} Key {2} not found in table {3}'.format(
                                        fname,
                                        lineno,
                                        colref,
                                        table.url.string),
                                    log=log)
                                success = False
        return success

    #
    # FIXME: to_sqlite()!
    #
