"""
Misc
"""
import io
import re
import json
import string
import keyword
import logging
import warnings
import collections
import unicodedata
from typing import Callable, Any, Union, Optional

import requests


def log_or_raise(
        msg: str,
        log: Optional[logging.Logger] = None,
        level: str = 'warning',
        exception_cls: type = ValueError):
    """
    Helper for error handling. In an inspection scenario, we want to list - i.e. log - all
    errors. In a validation scenario, we raise an exception at the first error.
    """
    if log:
        getattr(log, level)(msg)
    else:
        raise exception_cls(msg)


def json_open(filename, mode='r', encoding='utf-8'):
    """Open a text file suitable for reading JSON content, i.e. assuming it is utf-8 encoded."""
    assert encoding == 'utf-8'
    return io.open(filename, mode, encoding=encoding)


def get_json(fname) -> Union[list, dict]:
    """Retrieve JSON content from a local file or remote URL."""
    fname = str(fname)
    if is_url(fname):
        return requests.get(fname, timeout=10).json(object_pairs_hook=collections.OrderedDict)
    with json_open(fname) as f:
        return json.load(f, object_pairs_hook=collections.OrderedDict)


def optcast(type_: type) -> Callable[[Any], Any]:
    """Returns a callable that casts its argument to type_ unless it is None."""
    return lambda v: v if v is None else type_(v)


def is_url(s):  # pylint: disable=C0116
    return re.match(r'https?://', str(s))


def type_checker(  # pylint: disable=R0913,R0917
        type_: type,
        default: Optional[Any],
        v: Union[list[Any], Any],
        allow_none: bool = False,
        cond: Optional[Callable[[Any], bool]] = None,
        allow_list=True,
) -> Any:
    """Check if a value has a certain type (with bells and whistles), warn if not."""
    if allow_list and type_ != list and isinstance(v, list):
        # Convert a list of strings by applying the conversion to each not-None item.
        return [v for v in [type_checker(type_, None, vv, cond=cond) for vv in v] if v is not None]

    if allow_none and v is None:
        return v

    # Note: `bool` is a `subclass` of int in Python!
    if not isinstance(v, type_) or (type_ == int and isinstance(v, bool)) or (cond and not cond(v)):
        warnings.warn(f'Invalid value for property: {v}')
        return default
    return v


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
