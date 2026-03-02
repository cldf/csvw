"""
Helpers to model CSVW metadata as dataclasses.
"""
import decimal
import warnings
import collections
from collections.abc import Generator
import dataclasses
from typing import Any, Optional, Union

from language_tags import tags

from .utils import is_url

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


def valid_context_property(ctx):
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
