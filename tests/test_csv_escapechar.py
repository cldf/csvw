# test_csv_escapechar.py - https://bugs.python.org/issue12178

import io
import csv
import sys

import pytest


def make_io():
    return io.StringIO(newline='')


def roundtrip(value, dialect):
    with make_io() as f:
        writer = csv.writer(f, dialect=dialect)
        writer.writerow([value])
        out = f.getvalue()
        f.seek(0)
        reader = csv.reader(f, dialect=dialect)
        cell = next(reader)[0]
    return out, cell


class EscapeDialect(csv.excel):

    escapechar = '/'


class QuoteNone(EscapeDialect):

    quoting = csv.QUOTE_NONE


class EscapeQuote(EscapeDialect):

    doublequote = False


@pytest.mark.parametrize('dialect', [QuoteNone, EscapeQuote])
def test_quotechar(dialect):
    value = 'spam %s eggs' % dialect.quotechar
    out, cell = roundtrip(value, dialect)
    assert cell == value


@pytest.mark.parametrize('dialect', [
    QuoteNone,
    pytest.param(EscapeQuote, marks=pytest.mark.xfail(
        sys.version_info < (3, 10), reason='does not escape escapechar'),
    ),
])
def test_escapechar(dialect):
    value = 'spam %s eggs' % dialect.escapechar
    out, cell = roundtrip(value, dialect)
    assert cell == value


@pytest.mark.parametrize('dialect', [
    QuoteNone,
    pytest.param(EscapeQuote, marks=pytest.mark.xfail(
        sys.version_info < (3, 10), reason='does not escape escapechar')),
])
def test_escapecharquotechar(dialect):
    value = 'spam %s%s eggs' % (dialect.escapechar, dialect.quotechar)
    out, cell = roundtrip(value, dialect)
    assert cell == value


@pytest.mark.xfail(sys.version_info >= (3, 10), reason="https://bugs.python.org/issue44861")
def test_escapequote_escapecharquotechar_final(dialect=EscapeQuote):
    value = 'spam %s%s' % (dialect.escapechar, dialect.quotechar)
    out, cell = roundtrip(value, dialect)
    assert out.strip() == '"spam //""'  # why does this not raise on reading?
    assert cell == value  # pragma: no cover
