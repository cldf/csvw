from __future__ import unicode_literals

import shutil

from csvw._compat import PY2, pathlib, BytesIO, StringIO, to_binary

import pytest

from csvw.dsv import (reader, UnicodeReader, UnicodeWriter, rewrite,
    Dialect, add_rows, filter_rows_as_dict)

FIXTURES = pathlib.Path(__file__).parent


def test_reader():
    with pytest.raises(ValueError, match=r'either namedtuples or dicts'):
        next(reader([], namedtuples=True, dicts=True))

    lines = ['first\tline', 's\u00fccond\tl\u00e4ne\u00df']
    encoded_lines = [l.encode('utf-8') for l in lines]
    csv_lines = [l.replace('\t', ',') for l in lines]

    def check(r):
        res = list(r)
        assert len(res) == 2
        assert res[1][1] == 'l\u00e4ne\u00df'

    check(reader(lines, delimiter='\t'))
    for lt in ['\n', '\r\n', '\r']:
        if PY2:  # pragma: no cover
            # Simulate file opened in binary mode:
            fp = BytesIO(to_binary(lt).join(encoded_lines))
        else:
            # Simulate file opened in text mode:
            fp = StringIO(lt.join(lines), newline='')
        check(reader(fp, delimiter='\t'))
    check(reader(FIXTURES / 'csv.txt'))

    res = list(reader(FIXTURES / 'tsv.txt', namedtuples=True, delimiter='\t'))
    assert res[0].a_name == 'b'
    # Missing column values should be set to None:
    assert res[2].a_name is None

    r = list(reader(lines, dicts=True, delimiter='\t'))
    assert len(r) == 1 and r[0]['first'] == 's\u00fccond'
    r = list(reader(lines, namedtuples=True, delimiter='\t'))
    assert len(r) == 1 and r[0].first == 's\u00fccond'
    r = list(reader(csv_lines, namedtuples=True))
    assert len(r) == 1 and r[0].first == 's\u00fccond'
    
    assert list(reader([], dicts=True, delimiter='\t')) == []
    assert list(reader([''], dicts=True, fieldnames=['a', 'b'], delimiter='\t')) == \
           []
    assert list(reader(['a,b', ''], dicts=True, delimiter='\t')) == []

    r = reader(
        ['a,b', '1,2,3,4', '1'], dicts=True, restkey='x', restval='y', delimiter=',')
    assert list(r) == [{'a': '1', 'b': '2', 'x': ['3', '4']}, {'a': '1', 'b': 'y'}]


@pytest.mark.parametrize('row, expected', [
    ([None, 0, 1.2, '\u00e4\u00f6\u00fc'], b',0,1.2,\xc3\xa4\xc3\xb6\xc3\xbc\r\n'),
])
def test_writer(tmpdir, row, expected):
    with UnicodeWriter() as writer:
        writer.writerows([row])
    assert writer.read() == expected

    tmp = tmpdir / 'test'
    with UnicodeWriter(str(tmp)) as writer:
        writer.writerow(row)
    assert tmp.read_binary() == expected


def test_rewrite(tmpdir):
    tmp = tmpdir / 'test'
    shutil.copy(str(FIXTURES / 'tsv.txt'), str(tmp))
    rewrite(str(tmp), lambda i, row: [len(row)], delimiter='\t')
    assert list(reader(str(tmp)))[0] ==  ['2']

    shutil.copy(str(FIXTURES / 'csv.txt'), str(tmp))
    rewrite(str(tmp), lambda i, row: row)
    assert list(reader(str(tmp))) == list(reader(str(FIXTURES / 'csv.txt')))


def test_add_delete_rows(tmpdir):
    csv_path = tmpdir / 'test.csv'
    add_rows(str(csv_path), ['a', 'b'], [1, 2], [3, 4])
    assert len(list(reader(str(csv_path), dicts=True))) == 2

    filter_rows_as_dict(str(csv_path), lambda item: item['a'] == '1')
    assert len(list(reader(str(csv_path), dicts=True))) == 1

    add_rows(str(csv_path), [2, 2], [2, 4])
    assert len(list(reader(str(csv_path), dicts=True))) == 3

    res = filter_rows_as_dict(str(csv_path), lambda item: item['a'] == '1')
    assert res == 2


def test_reader_with_keyword_dialect(tmpdir):
    data = [['1', 'y'], ['  "1 ', '3\t4']]
    with UnicodeWriter(str(tmpdir / 'test'), dialect='excel') as w:
        w.writerows(data)
    assert list(reader(str(tmpdir / 'test'), dialect='excel')) == data


def test_reader_with_comments():
    d = Dialect(commentPrefix='*', header=False, trim=True)
    with UnicodeReader(['1,x,y', ' *1,a,b', 'a,b,c', '*1,1,2'], dialect=d) as r:
        # Comment markers must appear at the very start of a row, without any trimming
        assert len(list(r)) == 3
        assert r.comments[0] == (3, '1,1,2')


def test_reader_with_dialect():
    d = Dialect(trim=True, skipRows=1, skipColumns=1, skipBlankRows=True)
    r = list(reader(['1,x,y', ' #1,a,b', '#1,1,2', ',,', '1,3, 4\t '], dialect=d))

    # make sure comment lines are stripped:
    assert len(r) == 2

    # make sure cells are trimmmed:
    assert r[1][1] == '4'

    r = list(reader(
        ['1,x,y', ' #1,a,b', '#1,1,2', ',,', '1,3, 4\t '],
        dialect=d.updated(skipRows=0, skipColumns=0)))

    assert r[2][2] == '4'

    d = Dialect(doubleQuote=False, quoteChar=None)
    r = list(reader(['1,"x""y",x'], dialect=d))
    assert r[0][1] == '"x""y"'

    d = Dialect(doubleQuote=True)
    r = list(reader(['1,"x""y",y\\,x'], dialect=d))
    assert r[0][1] == 'x"y'
    assert r[0][2] == 'y,x'

    d = Dialect(commentPrefix=None)
    r = list(reader(['#x,y'], dialect=d))
    assert r[0][0] == '#x'
