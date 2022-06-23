import re
import string
import keyword
import pathlib
import warnings
import collections
import unicodedata

import attr


def is_url(s):
    return re.match(r'https?://', str(s))


def converter(type_, default, s, allow_none=False, cond=None, allow_list=True):
    if allow_list and type_ != list and isinstance(s, list):
        return [v for v in [converter(type_, None, ss, cond=cond) for ss in s] if v is not None]

    if allow_none and s is None:
        return s
    if not isinstance(s, type_) or (type_ == int and isinstance(s, bool)) or (cond and not cond(s)):
        warnings.warn('Invalid value for property: {}'.format(s))
        return default
    return s


def ensure_path(fname):
    if not isinstance(fname, pathlib.Path):
        assert isinstance(fname, str)
        return pathlib.Path(fname)
    return fname


def attr_defaults(cls):
    res = collections.OrderedDict()
    for field in attr.fields(cls):
        default = field.default
        if isinstance(default, attr.Factory):
            default = default.factory()
        res[field.name] = default
    return res


def attr_asdict(obj, omit_defaults=True, omit_private=True):
    defs = attr_defaults(obj.__class__)
    res = collections.OrderedDict()
    for field in attr.fields(obj.__class__):
        if not (omit_private and field.name.startswith('_')):
            value = getattr(obj, field.name)
            if not (omit_defaults and value == defs[field.name]):
                if hasattr(value, 'asdict'):
                    value = value.asdict(omit_defaults=True)
                res[field.name] = value
    return res


class lazyproperty(object):
    """Non-data descriptor caching the computed result as instance attribute.
    >>> import itertools
    >>> class Spam(object):
    ...     @lazyproperty
    ...     def eggs(self, _ints=itertools.count()):
    ...         return next(_ints)
    >>> spam=Spam(); spam.eggs
    0
    >>> spam.eggs=42; spam.eggs
    42
    >>> Spam().eggs
    1
    >>> del spam.eggs; spam.eggs, spam.eggs
    (2, 2)
    >>> Spam.eggs  # doctest: +ELLIPSIS
    <...lazyproperty object at 0x...>
    """

    def __init__(self, fget):
        self.fget = fget
        for attr_ in ('__module__', '__name__', '__doc__'):
            setattr(self, attr_, getattr(fget, attr_))

    def __get__(self, instance, owner):
        if instance is None:
            return self
        result = instance.__dict__[self.__name__] = self.fget(instance)
        return result


def normalize_name(s):
    """Convert a string into a valid python attribute name.
    This function is called to convert ASCII strings to something that can pass as
    python attribute name, to be used with namedtuples.

    >>> str(normalize_name('class'))
    'class_'
    >>> str(normalize_name('a-name'))
    'a_name'
    >>> str(normalize_name('a n\u00e4me'))
    'a_name'
    >>> str(normalize_name('Name'))
    'Name'
    >>> str(normalize_name(''))
    '_'
    >>> str(normalize_name('1'))
    '_1'
    """
    s = s.replace('-', '_').replace('.', '_').replace(' ', '_')
    if s in keyword.kwlist:
        return s + '_'
    s = '_'.join(slug(ss, lowercase=False) for ss in s.split('_'))
    if not s:
        s = '_'
    if s[0] not in string.ascii_letters + '_':
        s = '_' + s
    return s


def slug(s, remove_whitespace=True, lowercase=True):
    """Condensed version of s, containing only lowercase alphanumeric characters.

    >>> str(slug('A B. \u00e4C'))
    'abac'
    """
    res = ''.join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn')
    if lowercase:
        res = res.lower()
    for c in string.punctuation:
        res = res.replace(c, '')
    res = re.sub(r'\s+', '' if remove_whitespace else ' ', res)
    res = res.encode('ascii', 'ignore').decode('ascii')
    assert re.match('[ A-Za-z0-9]*$', res)
    return res
