import io
import csv
import sys
import shutil
import pathlib
from collections import OrderedDict

import pytest

from csvw.dsv import (iterrows, UnicodeReader, UnicodeDictReader, UnicodeWriter, rewrite,
    Dialect, add_rows, filter_rows_as_dict, UnicodeReaderWithLineNumber)

TESTDIR = pathlib.Path(__file__).parent / 'fixtures'

QUOTING = ['QUOTE_ALL', 'QUOTE_MINIMAL', 'QUOTE_NONNUMERIC', 'QUOTE_NONE']


def test_iterrows_invalid():
    with pytest.raises(ValueError, match=r'either namedtuples or dicts'):
        next(iterrows([], namedtuples=True, dicts=True))


def test_iterrows(rows=[['first', 'line'], ['s\u00fccond', 'l\u00e4ne\u00df']]):
    assert list(iterrows(TESTDIR / 'csv.txt')) == rows

    lines = ['\t'.join(r) for r in rows]
    assert list(iterrows(lines, delimiter='\t')) == rows

    for lt in ['\n', '\r\n', '\r']:
        # Simulate file opened in text mode:
        fp = io.StringIO(lt.join(lines), newline='')
        assert list(iterrows(fp, delimiter='\t')) == rows

    assert list(iterrows(lines, dicts=True, delimiter='\t')) == [OrderedDict(zip(*rows))]

    r = list(iterrows(lines, namedtuples=True, delimiter='\t'))
    assert len(r) == 1 and r[0].first == 's\u00fccond'

    r = list(iterrows([l.replace('\t', ',') for l in lines], namedtuples=True))
    assert len(r) == 1 and r[0].first == 's\u00fccond'


def test_iterrows_empty():
    assert list(iterrows([], dicts=True, delimiter='\t')) == []
    assert list(iterrows([''], dicts=True, fieldnames=['a', 'b'], delimiter='\t')) == \
           []
    assert list(iterrows(['a,b', ''], dicts=True, delimiter='\t')) == []


def test_iterrows_tsv(filename=str(TESTDIR / 'tsv.txt')):
    res = list(iterrows(filename, namedtuples=True, delimiter='\t'))
    assert res[0].a_name == 'b'
    # Missing column values should be set to None:
    assert res[2].a_name is None


def test_iterrows_restkey(lines=['a,b', '1,2,3,4', '1']):
    result = iterrows(lines, dicts=True, restkey='x', restval='y', delimiter=',')
    assert list(result) == [{'a': '1', 'b': '2', 'x': ['3', '4']}, {'a': '1', 'b': 'y'}]


@pytest.mark.parametrize('row, expected', [
    ([None, 0, 1.2, '\u00e4\u00f6\u00fc'], b',0,1.2,\xc3\xa4\xc3\xb6\xc3\xbc\r\n'),
])
def test_UnicodeWriter(tmp_path, row, expected):
    with UnicodeWriter() as writer:
        writer.writerows([row])
    assert writer.read() == expected

    filepath = tmp_path / 'test.csv'
    with UnicodeWriter(filepath) as writer:
        writer.writerow(row)
    assert filepath.read_bytes() == expected


@pytest.mark.parametrize(
    'quoting',
    [
        pytest.param(
            csv.QUOTE_ALL,
            marks=pytest.mark.xfail(
                sys.version_info >= (3, 10), reason="https://bugs.python.org/issue44861")),
        pytest.param(
            csv.QUOTE_MINIMAL,
            marks=pytest.mark.xfail(
                sys.version_info >= (3, 10), reason="https://bugs.python.org/issue44861")),
        pytest.param(
            csv.QUOTE_NONNUMERIC,
            marks=pytest.mark.xfail(
                sys.version_info >= (3, 10), reason="https://bugs.python.org/issue44861")),
        csv.QUOTE_NONE,
    ],
    ids=QUOTING)
def test_roundtrip_escapechar(tmp_path, quoting, escapechar='\\', row=['\\spam', 'eggs']):
    filename = tmp_path / 'spam.csv'
    kwargs = {'escapechar': escapechar, 'quoting': quoting}
    with UnicodeWriter(filename, **kwargs) as writer:
        writer.writerow(row)
    with UnicodeReader(filename, **kwargs) as reader:
        result = next(reader)
    assert result == row


@pytest.mark.parametrize('encoding', ['utf-16', 'utf-8-sig', 'utf-8'])
def test_roundtrip_multibyte(tmp_path, encoding, row=['spam', 'eggs'], expected='spam,eggs\r\n', n=2):
    filepath = tmp_path / 'spam.csv'
    kwargs = {'encoding': encoding}
    with UnicodeWriter(filepath, **kwargs) as writer:
        writer.writerows([row] * n)
    with UnicodeReader(filepath, **kwargs) as reader:
        result = next(reader)
    assert result == row
    assert filepath.read_bytes() == (expected * n).encode(encoding)


def test_iterrows_with_bom(tmp_path):
    filepath = tmp_path / 'spam.csv'
    filepath.write_text('\ufeffcol1,col2\nval1,val2', encoding='utf8')
    rows = list(iterrows(filepath))
    assert rows[0] == ['col1', 'col2']


def test_rewrite(tmp_path, tsvname=str(TESTDIR / 'tsv.txt'), csvname=str(TESTDIR / 'csv.txt')):
    filename = tmp_path / 'test.txt'
    shutil.copy(tsvname, filename)
    rewrite(filename, lambda i, row: [len(row)], delimiter='\t')
    assert next(iterrows(filename)) == ['2']

    shutil.copy(csvname, filename)
    rewrite(filename, lambda i, row: row)
    assert list(iterrows(filename)) == list(iterrows(csvname))


def test_add_delete_rows(tmp_path):
    filename = tmp_path / 'test.csv'
    add_rows(filename, ['a', 'b'], [1, 2], [3, 4])
    assert len(list(iterrows(filename, dicts=True))) == 2

    filter_rows_as_dict(filename, lambda item: item['a'] == '1')
    assert len(list(iterrows(filename, dicts=True))) == 1

    add_rows(filename, [2, 2], [2, 4])
    assert len(list(iterrows(filename, dicts=True))) == 3

    nremoved = filter_rows_as_dict(filename, lambda item: item['a'] == '1')
    assert nremoved == 2


def test_roundtrip_with_keyword_dialect(
        tmp_path, rows=[['1', 'y'], ['  "1 ', '3\t4']], dialect='excel'):
    filename = tmp_path / 'test.csv'
    with UnicodeWriter(filename, dialect=dialect) as w:
        w.writerows(rows)
    assert list(iterrows(filename, dialect=dialect)) == rows


def test_UnicodeReader_comments(lines=['1,x,y', ' *1,a,b', 'a,b,c', '*1,1,2']):
    dialect = Dialect(commentPrefix='*', header=False, trim=True)
    # Comment markers must appear at the very start of a row, without any trimming
    with UnicodeReader(lines, dialect=dialect) as reader:
        assert len(list(reader)) == 3
    assert reader.comments[0] == (3, '1,1,2')


def test_iterrows_iterable():
    def lines():
        for _ in range(10):
            yield 'a,b,c'
    res = list(iterrows(lines()))
    assert len(res) == 10
    assert res[-1] == ['a', 'b', 'c']


def test_iterrows_dialect(lines=['1,x,y', ' #1,a,b', '#1,1,2', ',,', '1,3, 4\t ']):
    dialect = Dialect(trim=True, skipRows=1, skipColumns=1, skipBlankRows=True)
    r = list(iterrows(lines, dialect=dialect))
    # make sure comment lines are stripped:
    assert len(r) == 2
    # make sure cells are trimmmed:
    assert r[1][1] == '4'

    r = list(iterrows(lines, dialect=dialect.updated(skipRows=0, skipColumns=0)))
    assert r[2][2] == '4'


@pytest.mark.parametrize('dialect, lines, expected', [
    (Dialect(doubleQuote=False, quoteChar=None), ['1,"x""y",x'], [['1', '"x""y"', 'x']]),
    (Dialect(doubleQuote=True), ['1,"x""y",y\\,x'], [['1', 'x"y', 'y\\', 'x']]),
    (Dialect(doubleQuote=False), ['1,x\\"y,y\\,x'], [['1', 'x"y', 'y,x']]),
    (Dialect(commentPrefix=None), ['#x,y'], [['#x', 'y']]),
])
def test_iterrows_quote_comment(dialect, lines, expected):
    assert list(iterrows(lines, dialect=dialect)) == expected


def test_UnicodeDictReader_duplicate_columns():
    with pytest.warns(UserWarning, match='uplicate'):
        with UnicodeDictReader(['a,a,b', '1,2,3']) as r:
            assert list(r)[0]['a'] == '2'  # last value wins


def test_UnicodeReaderWithLineNumber(tmp_path):
    p = tmp_path / 'test.csv'
    p.write_text('col1,col2\n"a\n\nb",c')
    with UnicodeReaderWithLineNumber(p) as reader:
        linenos = [item[0] for item in reader]
        assert linenos == [1, 4]


def test_UnicodeReader_R_encodings(tmp_path):
    p = tmp_path / 'test.csv'
    p.write_bytes(b'\xef\xbb\xbfcol1,col2\nval1,val2')
    with UnicodeDictReader(p) as r:
        row = next(r)
        assert 'col1' in row

    with UnicodeDictReader(p, dialect=Dialect(encoding='UTF-8-BOM')) as r:
        row = next(r)
        assert 'col1' in row

    with UnicodeWriter(p, dialect=Dialect(encoding='UTF-8-BOM')) as w:
        w.writerows([['col1', 'col2'], ['val1', 'val2']])
    assert p.read_bytes()[:4] == b'\xef\xbb\xbfc'
