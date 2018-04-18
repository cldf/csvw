"""Support for reading delimiter-separated value files.

This module contains unicode aware replacements for :func:`csv.reader`
and :func:`csv.writer`. It was stolen/extracted from the ``csvkit``
project to allow re-use when the whole ``csvkit`` package isn't
required.

The original implementations were largely copied from
`examples in the csv module documentation <http://docs.python.org/library/csv.html\
#examples>`_.

.. seealso:: http://en.wikipedia.org/wiki/Delimiter-separated_values
"""

from __future__ import unicode_literals

import csv
import codecs
import shutil
import tempfile
import collections

from ._compat import (pathlib, PY2, string_types, binary_type, text_type,
    BytesIO, StringIO, iteritems, Iterator, map, zip, fix_kw)

from . import utils
from .dsv_dialects import Dialect

__all__ = [
    'UnicodeWriter',
    'UnicodeReader', 'UnicodeReaderWithLineNumber', 'UnicodeDictReader', 'NamedTupleReader',
    'iterrows',
    'rewrite', 'add_rows', 'filter_rows_as_dict',
]


if PY2:
    class UTF8Recoder(object):
        """Iterator that reads an encoded stream and reencodes the input to UTF-8."""

        def __init__(self, f, encoding):
            self.reader = codecs.getreader(encoding)(f)

        def __iter__(self):
            return self

        def next(self):
            return self.reader.next().encode('utf-8')


class UnicodeWriter(object):
    """Write Unicode data to a csv file."""

    def __init__(self, f=None, dialect=None, **kw):
        self.f = f
        self.encoding = kw.pop('encoding', 'utf-8')
        if isinstance(dialect, Dialect):
            self.encoding = dialect.encoding
            self.kw = dialect.as_python_formatting_parameters()
            self.kw.update(kw)
        else:
            self.kw = kw
            if dialect:
                self.kw['dialect'] = dialect
        self.kw = fix_kw(self.kw)
        self.escapechar = self.kw.get('escapechar')
        self._close = False

    def __enter__(self):
        if isinstance(self.f, (string_types, pathlib.Path)):
            if isinstance(self.f, pathlib.Path):
                self.f = self.f.as_posix()

            if PY2:
                self.f = open(self.f, 'wb')
            else:  # pragma: no cover
                self.f = open(self.f, 'wt', encoding=self.encoding, newline='')
            self._close = True
        elif self.f is None:
            self.f = BytesIO() if PY2 else StringIO(newline='')

        self.writer = csv.writer(self.f, **self.kw)
        return self

    def read(self):
        if hasattr(self.f, 'seek'):
            self.f.seek(0)
        if hasattr(self.f, 'read'):
            res = self.f.read()
            if not PY2:  # pragma: no cover
                res = res.encode('utf-8')
            return res

    def __exit__(self, type, value, traceback):
        if self._close:
            self.f.close()

    def _escapedoubled(self, s):
        #
        # As per https://docs.python.org/3/library/csv.html#csv.Dialect.escapechar:
        # > On reading, the escapechar removes any special meaning from the following
        # > character.
        # Thus, to make roundtripping work, we must escape any literal occurrence of
        # escapechar in the data to be written.
        #
        if self.escapechar and isinstance(s, string_types):
            return s.replace(self.escapechar, 2 * self.escapechar)
        return s

    def writerow(self, row):
        row = [self._escapedoubled(s) for s in row]
        if PY2:
            row = [('%s' % s).encode(self.encoding) if s is not None else s for s in row]
        self.writer.writerow(row)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


class UnicodeReader(Iterator):
    """Read Unicode data from a csv file."""

    def __init__(self, f, dialect=None, **kw):
        self.f = f
        self.encoding = kw.pop('encoding', 'utf-8')
        self.newline = kw.pop('lineterminator', None)
        self.dialect = dialect if isinstance(dialect, Dialect) else None
        if self.dialect:
            self.encoding = self.dialect.encoding
            self.kw = dialect.as_python_formatting_parameters()
            self.kw.update(kw)
        else:
            self.kw = kw
            if dialect:
                self.kw['dialect'] = dialect
        self.kw = fix_kw(self.kw)
        self._close = False
        self.comments = []

    def __enter__(self):
        if isinstance(self.f, (string_types, pathlib.Path)):
            if isinstance(self.f, pathlib.Path):
                self.f = self.f.as_posix()

            if PY2:
                self.f = open(self.f, mode='rU')
            else:  # pragma: no cover
                self.f = open(
                    self.f, mode='rt', encoding=self.encoding, newline=self.newline or '')
            self._close = True
        elif hasattr(self.f, 'read'):
            if PY2:
                self.f = UTF8Recoder(self.f, self.encoding)
        else:
            lines = []
            for line in self.f:
                if PY2 and isinstance(line, text_type):
                    line = line.encode(self.encoding)
                elif not PY2 and isinstance(line, binary_type):  # pragma: no cover
                    line = line.decode(self.encoding)
                lines.append(line)
            self.f = lines
        self.reader = csv.reader(self.f, **self.kw)
        self.lineno = -1
        return self

    def _next_row(self):
        self.lineno += 1
        return [
            s if isinstance(s, text_type) else s.decode(self.encoding)
            for s in next(self.reader)]

    def __next__(self):
        row = self._next_row()
        if self.dialect:
            while (row and self.dialect.commentPrefix and
                   row[0].startswith(self.dialect.commentPrefix)) or \
                    ((not row or set(row) == {''}) and self.dialect.skipBlankRows) or \
                    (self.lineno < self.dialect.skipRows):
                if row and self.dialect.commentPrefix and \
                        row[0].startswith(self.dialect.commentPrefix):
                    self.comments.append(
                        (self.lineno, self.dialect.delimiter.join(row)[1:].strip()))
                row = self._next_row()
            row = [self.dialect.trimmer(s) for s in row][self.dialect.skipColumns:]
        return row

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._close:
            self.f.close()

    def __iter__(self):
        return self


class UnicodeReaderWithLineNumber(UnicodeReader):

    def __next__(self):
        """

        :return: a pair (1-based line number in the input, row)
        """
        # Retrieve the row, thereby incrementing the line number:
        row = super(UnicodeReaderWithLineNumber, self).__next__()
        return self.lineno + 1, row


class UnicodeDictReader(UnicodeReader):
    """Read Unicode data represented as one (ordered) dictionary per row."""

    def __init__(self, f, fieldnames=None, restkey=None, restval=None, **kw):
        self._fieldnames = fieldnames   # list of keys for the dict
        self.restkey = restkey          # key to catch long rows
        self.restval = restval          # default value for short rows
        self.line_num = 0
        super(UnicodeDictReader, self).__init__(f, **kw)

    @property
    def fieldnames(self):
        if self._fieldnames is None:
            try:
                self._fieldnames = super(UnicodeDictReader, self).__next__()
            except StopIteration:
                pass
        self.line_num = self.reader.line_num
        return self._fieldnames

    def __next__(self):
        if self.line_num == 0:
            # Used only for its side effect.
            self.fieldnames
        row = super(UnicodeDictReader, self).__next__()
        self.line_num = self.reader.line_num

        # unlike the basic reader, we prefer not to return blanks,
        # because we will typically wind up with a dict full of None
        # values
        while row == []:
            row = super(UnicodeDictReader, self).__next__()
        return self.item(row)

    def item(self, row):
        d = collections.OrderedDict((k, v) for k, v in zip(self.fieldnames, row))
        lf = len(self.fieldnames)
        lr = len(row)
        if lf < lr:
            d[self.restkey] = row[lf:]
        elif lf > lr:
            for key in self.fieldnames[lr:]:
                d[key] = self.restval
        return d


class NamedTupleReader(UnicodeDictReader):
    """Read namedtuple objects from a csv file."""

    _normalize_fieldname = staticmethod(utils.normalize_name)

    @utils.lazyproperty
    def cls(self):
        fieldnames = list(map(self._normalize_fieldname, self.fieldnames))
        return collections.namedtuple('Row', fieldnames)

    def item(self, row):
        d = UnicodeDictReader.item(self, row)
        for name in self.fieldnames:
            d.setdefault(name, None)
        return self.cls(
            **{self._normalize_fieldname(k): v for k, v in iteritems(d) if k in self.fieldnames})


def iterrows(lines_or_file, namedtuples=False, dicts=False, encoding='utf-8', **kw):
    """Convenience factory function for csv reader.

    :param lines_or_file: Content to be read. Either a file handle, a file path or a list\
    of strings.
    :param namedtuples: Yield namedtuples.
    :param dicts: Yield dicts.
    :param encoding: Encoding of the content.
    :param kw: Keyword parameters are passed through to csv.reader.
    :return: A generator over the rows.
    """
    if namedtuples and dicts:
        raise ValueError('either namedtuples or dicts can be chosen as output format')
    elif namedtuples:
        _reader = NamedTupleReader
    elif dicts:
        _reader = UnicodeDictReader
    else:
        _reader = UnicodeReader

    with _reader(lines_or_file, encoding=encoding, **fix_kw(kw)) as r:
        for item in r:
            yield item


reader = iterrows


def rewrite(fname, visitor, **kw):
    """Utility function to rewrite rows in tsv files.

    :param fname: Path of the dsv file to operate on.
    :param visitor: A callable that takes a line-number and a row as input and returns a \
    (modified) row or None to filter out the row.
    :param kw: Keyword parameters are passed through to csv.reader/csv.writer.
    """
    if not isinstance(fname, pathlib.Path):
        assert isinstance(fname, string_types)
        fname = pathlib.Path(fname)

    assert fname.is_file()
    with tempfile.NamedTemporaryFile(delete=False) as fp:
        tmp = pathlib.Path(fp.name)

    with UnicodeReader(fname, **kw) as reader_:
        with UnicodeWriter(tmp, **kw) as writer:
            for i, row in enumerate(reader_):
                row = visitor(i, row)
                if row is not None:
                    writer.writerow(row)
    shutil.move(str(tmp), str(fname))  # Path.replace is Python 3.3+


def add_rows(fname, *rows):
    with tempfile.NamedTemporaryFile(delete=False) as fp:
        tmp = pathlib.Path(fp.name)

    if not isinstance(fname, pathlib.Path):
        assert isinstance(fname, string_types)
        fname = pathlib.Path(fname)
    with UnicodeWriter(tmp) as writer:
        if fname.exists():
            with UnicodeReader(fname) as reader_:
                for row in reader_:
                    writer.writerow(row)
        writer.writerows(rows)
    shutil.move(str(tmp), str(fname))  # Path.replace is Python 3.3+


def filter_rows_as_dict(fname, filter_, **kw):
    """Rewrite a dsv file, filtering the rows.

    :param fname: Path to dsv file
    :param filter_: callable which accepts a `dict` with a row's data as single argument\
    returning a `Boolean` indicating whether to keep the row (`True`) or to discard it \
    `False`.
    :param kw: Keyword arguments to be passed `UnicodeReader` and `UnicodeWriter`.
    :return: The number of rows that have been removed.
    """
    filter_ = DictFilter(filter_)
    rewrite(fname, filter_, **kw)
    return filter_.removed


class DictFilter(object):

    def __init__(self, filter_):
        self.header = None
        self.filter = filter_
        self.removed = 0

    def __call__(self, i, row):
        if i == 0:
            self.header = row
            return row
        if row:
            item = dict(zip(self.header, row))
            if self.filter(item):
                return row
            else:
                self.removed += 1
