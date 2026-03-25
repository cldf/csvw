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
import contextlib
import collections
import dataclasses
import unicodedata
import urllib.request
from typing import Callable, Any, Union, Optional, Literal

HTTP_REQUEST_TIMEOUT = 10


@dataclasses.dataclass
class LinkHeader:
    """
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Link
    """
    url: str
    params: dict[str, str]

    @classmethod
    def from_string(cls, s):
        """
        <uri-reference>; param1=value1; param2="value2"
        """
        comps = re.split(r'>\s*;\s*', s.strip(), maxsplit=1)
        if len(comps) == 2:
            url, sparams = comps
            url += '>'
        else:
            url, sparams = comps[0], ''
        assert url.startswith('<') and url.endswith('>')
        url = url[1:-1].strip()
        params = {}
        if sparams:
            for sparam in sparams.split(';'):
                key, _, value = sparam.strip().partition('=')
                key, value = key.strip(), (value or '').strip()
                if value.startswith('"'):
                    assert value.endswith('"')
                    value = value[1:-1].strip()
                params[key] = value or None
        return cls(url=url, params=params)

    @classmethod
    def iter_links(cls, s):
        """
        A Link header might contain multiple links separated by comma.
        """
        for i, single in enumerate(re.split(r',\s*<', s)):
            yield cls.from_string(single if i == 0 else '<' + single)


@contextlib.contextmanager
def urlopen(
        url,
        method: Optional[Literal['HEAD', 'GET']] = 'GET',
        timeout=HTTP_REQUEST_TIMEOUT,
):
    """
    Open URLs
    - without raising an exception on HTTP errors,
    - passing a specific User-Agent header,
    - specifying a timeout.
    """
    class NonRaisingHTTPErrorProcessor(urllib.request.HTTPErrorProcessor):
        """Don't raise exceptions on HTTP errors."""
        http_response = https_response = lambda self, req, res: res  # pylint: disable=C3001

    opener = urllib.request.build_opener(NonRaisingHTTPErrorProcessor)
    opener.addheaders = [('User-agent', 'csvw/4.0.0')]
    yield opener.open(urllib.request.Request(url, method=method), timeout=timeout)


def request_head(url) -> tuple[str, list[LinkHeader]]:
    """Makes a HEAD request and returns the relevant response data."""
    with urlopen(url) as response:
        links = []
        for mult in response.info().get_all('Link') or []:
            links.extend(LinkHeader.iter_links(mult))
        return response.info().get_content_type() or '', links


@dataclasses.dataclass
class GetResponse:
    """Relevant data from an HTTP GET response."""
    status_code: int = 200
    content: bytes = None
    text: str = None

    def __post_init__(self):
        if self.content and not self.text:
            self.text = self.content.decode('utf8')
        if self.text and not self.content:
            self.content = self.text.encode('utf8')

    @classmethod
    def from_response(cls, response) -> 'GetResponse':
        """Initialize instance with data from a urllib response."""
        content = response.read()
        text = content.decode(response.headers.get_content_charset() or 'utf-8')
        return cls(status_code=response.status, content=content, text=text)

    def json(self) -> Any:
        """The content of the repsonse parsed as JSON."""
        return json.loads(self.text, object_pairs_hook=collections.OrderedDict)


def request_get(url: str) -> GetResponse:
    """Makes a GET request."""
    with urlopen(url) as response:
        return GetResponse.from_response(response)


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
        return request_get(fname).json()
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
