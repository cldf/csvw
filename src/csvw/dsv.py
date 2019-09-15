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
import io
import csv
import codecs
import shutil
import tempfile
import collections

from ._compat import pathlib

from . import utils
from .dsv_dialects import Dialect

__all__ = [
    'UnicodeWriter',
    'UnicodeReader', 'UnicodeReaderWithLineNumber', 'UnicodeDictReader', 'NamedTupleReader',
    'iterrows',
    'rewrite', 'add_rows', 'filter_rows_as_dict',
]


def normalize_encoding(encoding):
    return codecs.lookup(encoding).name


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
        self.encoding = normalize_encoding(self.encoding)
        self.escapechar = self.kw.get('escapechar')
        if self.escapechar and self.kw.get('quoting') != csv.QUOTE_NONE:
            # work around https://bugs.python.org/issue12178
            # (csv.writer doesn't escape escapechar while csv.reader expects it)
            def _escapedoubled(row,
                               _type=str,
                               _old=self.escapechar,
                               _new=2 * self.escapechar):
                return [s.replace(_old, _new) if isinstance(s, _type) else s for s in row]
        else:
            def _escapedoubled(row):
                return row
        self._escapedoubled = _escapedoubled
        self._close = False

    def __enter__(self):
        if isinstance(self.f, (str, pathlib.Path)):
            if isinstance(self.f, pathlib.Path):
                self.f = str(self.f)

            self.f = io.open(self.f, 'wt', encoding=self.encoding, newline='')
            self._close = True
        elif self.f is None:
            self.f = io.StringIO(newline='')

        self.writer = csv.writer(self.f, **self.kw)
        return self

    def read(self):
        if hasattr(self.f, 'seek'):
            self.f.seek(0)
        if hasattr(self.f, 'read'):
            return self.f.read().encode('utf-8')

    def __exit__(self, type, value, traceback):
        if self._close:
            self.f.close()

    def writerow(self, row):
        self.writer.writerow(self._escapedoubled(row))

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


class UnicodeReader(object):
    """Read Unicode data from a csv file."""

    def __init__(self, f, dialect=None, **kw):
        self.f = f
        self.encoding = normalize_encoding(kw.pop('encoding', 'utf-8-sig'))
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
        self._close = False
        self.comments = []

        # We potentially screw people with valid CSV files where the content - presumably the
        # header - starts with 0xfeff. But the chance of irritating people trying to read Excel
        # exported CSV with the defaults seems way bigger - and anyone with CSV column names
        # starting with 0xfeff will run into more trouble down the line anyway ...
        if self.encoding == 'utf-8':
            self.encoding = 'utf-8-sig'

        # encoding of self.reader rows: differs from source encoding
        # where we need to recode from non-8bit clean source encoding
        # to utf-8 first to feed into the (byte-based) PY2 csv.reader
        self._reader_encoding = self.encoding

    def __enter__(self):
        if isinstance(self.f, (str, pathlib.Path)):
            if isinstance(self.f, pathlib.Path):
                self.f = str(self.f)

            self.f = io.open(self.f, mode='rt', encoding=self.encoding, newline=self.newline or '')
            self._close = True
        elif not hasattr(self.f, 'read'):
            lines = []
            for line in self.f:
                if isinstance(line, bytes):
                    line = line.decode(self.encoding)
                lines.append(line)
            self.f = lines
        self.reader = csv.reader(self.f, **self.kw)
        self.lineno = -1
        return self

    def _next_row(self):
        self.lineno += 1
        return [
            s if isinstance(s, str) else s.decode(self._reader_encoding)
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
            **{self._normalize_fieldname(k): v for k, v in d.items() if k in self.fieldnames})


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

    with _reader(lines_or_file, encoding=encoding, **kw) as r:
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
        assert isinstance(fname, str)
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
        assert isinstance(fname, str)
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
