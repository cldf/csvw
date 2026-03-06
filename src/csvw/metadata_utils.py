"""
Helpers to model CSVW metadata as dataclasses.
"""
import re
import copy
import html
import json
import decimal
import warnings
import collections
from collections.abc import Generator
import dataclasses
from typing import Any, Optional, Union, TYPE_CHECKING

from language_tags import tags

from .utils import is_url, slug

if TYPE_CHECKING:
    from csvw.metadata import TableGroup  # pragma: no cover

__all__ = ['valid_common_property', 'valid_id_property', 'valid_context_property',
           'DescriptionBase', 'dataclass_asdict', 'NAMESPACES', 'dialect_props']

NumberType = Union[int, float, decimal.Decimal]
NAMESPACES = {
    'csvw': 'http://www.w3.org/ns/csvw#',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
    'dc': 'http://purl.org/dc/terms/',
    'dcat': 'http://www.w3.org/ns/dcat#',
    'prov': 'http://www.w3.org/ns/prov#',
    'schema': 'http://schema.org/',
    "as": "https://www.w3.org/ns/activitystreams#",
    "cc": "http://creativecommons.org/ns#",
    "ctag": "http://commontag.org/ns#",
    "dc11": "http://purl.org/dc/elements/1.1/",
    "dctypes": "http://purl.org/dc/dcmitype/",
    "dqv": "http://www.w3.org/ns/dqv#",
    "duv": "https://www.w3.org/ns/duv#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "gr": "http://purl.org/goodrelations/v1#",
    "grddl": "http://www.w3.org/2003/g/data-view#",
    "ical": "http://www.w3.org/2002/12/cal/icaltzd#",
    "jsonld": "http://www.w3.org/ns/json-ld#",
    "ldp": "http://www.w3.org/ns/ldp#",
    "ma": "http://www.w3.org/ns/ma-ont#",
    "oa": "http://www.w3.org/ns/oa#",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "og": "http://ogp.me/ns#",
    "org": "http://www.w3.org/ns/org#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "qb": "http://purl.org/linked-data/cube#",
    "rdfa": "http://www.w3.org/ns/rdfa#",
    "rev": "http://purl.org/stuff/rev#",
    "rif": "http://www.w3.org/2007/rif#",
    "rr": "http://www.w3.org/ns/r2rml#",
    "sd": "http://www.w3.org/ns/sparql-service-description#",
    "sioc": "http://rdfs.org/sioc/ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "skosxl": "http://www.w3.org/2008/05/skos-xl#",
    "sosa": "http://www.w3.org/ns/sosa/",
    "ssn": "http://www.w3.org/ns/ssn/",
    "time": "http://www.w3.org/2006/time#",
    "v": "http://rdf.data-vocabulary.org/#",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "void": "http://rdfs.org/ns/void#",
    "wdr": "http://www.w3.org/2007/05/powder#",
    "wrds": "http://www.w3.org/2007/05/powder-s#",
    "xhv": "http://www.w3.org/1999/xhtml/vocab#",
    "xml": "http://www.w3.org/XML/1998/namespace",
}
CSVW_TERMS = """Cell
Column
Datatype
Dialect
Direction
ForeignKey
JSON
NumericFormat
Row
Schema
Table
TableGroup
TableReference
Transformation
aboutUrl
base
columnReference
columns
commentPrefix
datatype
decimalChar
default
delimiter
describes
dialect
doubleQuote
encoding
foreignKeys
format
groupChar
header
headerRowCount
json
lang
length
lineTerminators
maxExclusive
maxInclusive
maxLength
maximum
minExclusive
minInclusive
minLength
minimum
name
notes
null
ordered
pattern
primaryKey
propertyUrl
quoteChar
reference
referencedRows
required
resource
row
rowTitles
rownum
schemaReference
scriptFormat
separator
skipBlankRows
skipColumns
skipInitialSpace
skipRows
source
suppressOutput
tableDirection
tableSchema
tables
targetFormat
textDirection
titles
transformations
trim
uriTemplate
url
valueUrl
virtual""".split()


def dataclass_asdict(obj, omit_defaults: bool = True, omit_private: bool = True) -> dict[str, Any]:
    """Enhanced conversion of dataclass instances to a dict."""
    res = collections.OrderedDict()
    for field in dataclasses.fields(obj):
        default = field.default_factory() if callable(field.default_factory) else field.default
        if not (omit_private and field.name.startswith('_')):
            value = getattr(obj, field.name)
            if not (omit_defaults and value == default):
                if hasattr(value, 'asdict'):
                    value = value.asdict(omit_defaults=True)
                res[field.name] = value
    return res


def valid_id_property(v: str) -> Optional[str]:
    """Validator for the @id property."""
    if not isinstance(v, str):
        warnings.warn('Inconsistent link property')
        return None
    if v.startswith('_'):
        raise ValueError(f'Invalid @id property: {v}')
    return v


def valid_context_property(ctx: Union[None, str, list]) -> Union[None, str, list]:
    """
    Make sure the requirements for @context objects in CSVW are met.
    If not, warn or raise exceptions accordingly.
    """
    nsurl = NAMESPACES['csvw'].replace('#', '')
    if ctx is None:
        return ctx
    if isinstance(ctx, str):
        assert ctx == nsurl
        return ctx
    assert isinstance(ctx, list), ctx
    for obj in ctx:
        if any((isinstance(obj, dict) and not set(obj.keys()).issubset({'@base', '@language'}),
                isinstance(obj, str) and obj != nsurl)):
            raise ValueError(
                f'The @context MUST have one of the following values: An array composed of a '
                f'string followed by an object, where the string is {nsurl} and the '
                f'object represents a local context definition, which is restricted to contain '
                f'either or both of @base and @language.')
        if isinstance(obj, dict) and '@language' in obj and not tags.check(obj['@language']):
            warnings.warn('Invalid value for @language property')
            del obj['@language']
    return ctx


def valid_common_property(v):  # pylint: disable=too-many-branches
    """Validator for values of common properties."""
    if not isinstance(v, (dict, list)):
        # No JSON container types. We'll just assume all is good.
        return v

    if isinstance(v, list):  # Recurse into the items.
        return [valid_common_property(vv) for vv in v]

    if not {k[1:] for k in v if k.startswith('@')}.issubset({'id', 'language', 'type', 'value'}):
        raise ValueError(
            "Aside from @value, @type, @language, and @id, the properties used on an object "
            "MUST NOT start with @.")
    if '@value' in v:
        if any((
            len(v) > 2,
            set(v.keys()) not in [{'@value', '@language'}, {'@value', '@type'}],
            not isinstance(v['@value'], (str, bool, int, float, decimal.Decimal))
        )):
            raise ValueError(
                "If a @value property is used on an object, that object MUST NOT have any other "
                "properties aside from either @type or @language, and MUST NOT have both @type and "
                "@language as properties. The value of the @value property MUST be a string, "
                "number, or boolean value.")
    if '@language' in v and '@value' not in v:
        raise ValueError(
            "A @language property MUST NOT be used on an object unless it also has a @value "
            "property.")
    if '@id' in v:
        v['@id'] = valid_id_property(v['@id'])
    if '@language' in v:
        if not (isinstance(v['@language'], str) and tags.check(v['@language'])):
            warnings.warn('Invalid language tag')
            del v['@language']
    if '@type' in v:
        vv = v['@type']
        if isinstance(vv, str):
            if vv.startswith('_:'):
                raise ValueError(
                    'The value of any @id or @type contained within a metadata document '
                    'MUST NOT be a blank node.')
            if not any((
                is_url(vv),
                any(vv == ns or vv.startswith(ns + ':') for ns in NAMESPACES),
                vv in CSVW_TERMS
            )):
                raise ValueError(
                    'The value of any member of @type MUST be either a term defined in '
                    '[csvw-context], a prefixed name where the prefix is a term defined in '
                    '[csvw-context], or an absolute URL.')
        elif not isinstance(vv, (list, dict)):
            raise ValueError('Invalid datatype for @type')
    return {k: valid_common_property(vv) for k, vv in v.items()}


@dataclasses.dataclass
class DescriptionBase:
    """Container for
    - common properties (see http://w3c.github.io/csvw/metadata/#common-properties)
    - @-properties.
    """
    common_props: dict[str, Any] = dataclasses.field(default_factory=dict)
    at_props: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def partition_properties(
            cls,
            d: Union[dict, Any],
            type_name: Optional[str] = None,
            strict: bool = True
    ) -> Union[dict, None]:
        """
        Partitions properties in d into `common_props`, `at_props` and the remaining.
        """
        if d and not isinstance(d, dict):
            return None
        fields = {f.name: f for f in dataclasses.fields(cls)}
        type_name = type_name or cls.__name__
        c, a, dd = {}, {}, {}
        for k, v in (d or {}).items():
            if k.startswith('@'):
                if k == '@id':
                    v = valid_id_property(v)
                if k == '@type' and v != type_name:
                    raise ValueError(f'Invalid @type property {v} for {type_name}')
                a[k[1:]] = v
            elif ':' in k:
                c[k] = valid_common_property(v)
            else:
                if strict and (k not in fields):
                    warnings.warn(f'Invalid property {k} for {type_name}')
                else:
                    dd[k] = v
        return dict(common_props=c, at_props=a, **dd)  # pylint: disable=R1735

    @classmethod
    def fromvalue(cls, d: dict):
        """Initialize instance from dict."""
        return cls(**cls.partition_properties(d))

    def _iter_dict_items(self, omit_defaults) -> Generator[tuple[str, Any], None, None]:
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

        for k, v in dataclass_asdict(self, omit_defaults=omit_defaults).items():
            if k not in ('common_props', 'at_props'):
                yield k, _asdict_multiple(v)

    def asdict(self, omit_defaults=True) -> collections.OrderedDict[str, Any]:
        """Serialization as dict."""
        # Note: The `null` property is the only inherited, list-valued property where the default
        # is not the empty list. Thus, to allow setting it to empty, we must treat `null` as
        # special case here.
        # See also https://www.w3.org/TR/tabular-metadata/#dfn-inherited-property
        return collections.OrderedDict(
            (k, v) for k, v in self._iter_dict_items(omit_defaults)
            if (k == 'null' or (v not in ([], {}))))


def dialect_props(d: dict[str, Any]) -> dict:
    """Slightly massage the a dialect specification into something accepted by our Dialect class."""
    if not isinstance(d, dict):
        warnings.warn('Invalid dialect spec')
        return {}
    partitioned = DescriptionBase.partition_properties(d, type_name='Dialect', strict=False)
    del partitioned['at_props']
    del partitioned['common_props']
    if partitioned.get('headerRowCount'):
        partitioned['header'] = True
    return partitioned


def qname2url(qname: str) -> Optional[str]:
    """Turn a qname into an http URL by replacing the prefix with the associated URL."""
    for prefix, uri in NAMESPACES.items():
        if qname.startswith(prefix + ':'):
            return qname.replace(prefix + ':', uri)
    return None


def metadata2markdown(tg: 'TableGroup', link_files: bool = False) -> str:
    """
    Render the metadata of a dataset as markdown.

    :param link_files: If True, links to data files will be added, assuming the markdown is stored \
    in the same directory as the metadata file.
    :return: `str` with markdown formatted text
    """
    fname = tg._fname  # pylint: disable=W0212
    res = [f"# {tg.common_props.get('dc:title', 'Dataset')}\n"]
    if fname and link_files:
        res.append(f'> [!NOTE]\n> Described by [{fname.name}]({fname.name}).\n')

    res.append(_properties({k: v for k, v in tg.common_props.items() if k != 'dc:title'}))

    for table in tg.tables:
        res.extend(list(_iter_table2markdown(tg, table, link_files)))
    return '\n'.join(res)


def _qname2link(qname, html=False):  # pylint: disable=W0621
    url = qname2url(qname)
    if url:
        if html:
            return f'<a href="{url}">{qname}</a>'
        return f'[{qname}]({url})'
    return qname


def _htmlify(obj, key=None):
    """
    For inclusion in tables we must use HTML for lists.
    """
    if isinstance(obj, list):
        lis = ''.join(f'<li>{_htmlify(item, key=key)}</li>' for item in obj)
        return f'<ol>{lis}</ol>'
    if isinstance(obj, dict):
        items = []
        for k, v in obj.items():
            items.append(f'<dt>{_qname2link(k, html=True)}</dt><dd>{html.escape(str(v))}</dd>')
        return f"<dl>{''.join(items)}</dl>"
    return str(obj)


def _properties(props):
    def _img(img: Union[str, dict]):
        if isinstance(img, str):  # pragma: no cover
            img = {'https://schema.org/contentUrl': img}
        return (f"![{img.get('https://schema.org/caption') or ''}]"
                f"({img.get('https://schema.org/contentUrl')})\n")

    props = {k: v for k, v in copy.deepcopy(props).items() if v}
    res = []
    desc = props.pop('dc:description', None)
    if desc:
        res.append(desc + '\n')
    img = props.pop('https://schema.org/image', None)
    if img:
        res.append(_img(img))
    if props:
        res.append('property | value\n --- | ---')
        for k, v in props.items():
            res.append(f'{_qname2link(k)} | {_htmlify(v, key=k)}')
    return '\n'.join(res) + '\n'


def _iter_table2markdown(tg, table, link_files):
    fks = {
        fk.columnReference[0]: (fk.reference.columnReference[0], fk.reference.resource.string)
        for fk in table.tableSchema.foreignKeys if len(fk.columnReference) == 1}
    header = f'## <a name="table-{slug(table.url.string)}"></a>Table '
    fname = tg._fname  # pylint: disable=W0212
    if (link_files and fname and fname.parent.joinpath(table.url.string).exists()):
        header += f'[{table.url.string}]({table.url.string})\n'
    else:  # pragma: no cover
        header += table.url.string
    yield '\n' + header + '\n'
    yield _properties(table.common_props)
    dialect = table.inherit('dialect')
    if dialect.asdict():
        yield f'\n**CSV dialect**: `{json.dumps(dialect.asdict())}`\n'
    yield '\n### Columns\n'
    yield 'Name/Property | Datatype | Description'
    yield ' --- | --- | --- '
    for col in table.tableSchema.columns:
        yield _colrow(col, fks, table.tableSchema.primaryKey)


def _colrow(col, fks, pk):
    dt = f"`{col.datatype.base if col.datatype else 'string'}`"
    if col.datatype:
        if col.datatype.format:
            if re.fullmatch(r'[\w\s]+(\|[\w\s]+)*', col.datatype.format):
                dt += '<br>Valid choices:<br>'
                dt += ''.join(f' `{w}`' for w in col.datatype.format.split('|'))
            elif col.datatype.base == 'string':
                dt += f'<br>Regex: `{col.datatype.format}`'
        if col.datatype.minimum:
            dt += f'<br>&ge; {col.datatype.minimum}'
        if col.datatype.maximum:
            dt += f'<br>&le; {col.datatype.maximum}'
    if col.separator:
        dt = f'list of {dt} (separated by `{col.separator}`)'
    desc = col.common_props.get('dc:description', '').replace('\n', ' ')

    if pk and col.name in pk:
        desc = (desc + '<br>') if desc else desc
        desc += 'Primary key'

    if col.name in fks:
        desc = (desc + '<br>') if desc else desc
        cname, tname = fks[col.name]
        desc += f'References [{tname}::{cname}](#table-{slug(tname)})'

    return ' | '.join([
        f'[{col.name}]({col.propertyUrl})' if col.propertyUrl else f'`{col.name}`', dt, desc])
