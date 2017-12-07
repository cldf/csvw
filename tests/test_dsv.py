# coding: utf8

from __future__ import unicode_literals

import shutil

from six import PY3, BytesIO, StringIO

import clldutils
from clldutils.misc import to_binary
from clldutils.path import Path
from clldutils.testing import WithTempDir


FIXTURES = Path(__file__).parent


class Tests(WithTempDir):

    def test_reader(self):
        from csvw.dsv import reader

        lines = ['first\tline', 'sücond\tläneß']
        encoded_lines = [l.encode('utf8') for l in lines]
        csv_lines = [l.replace('\t', ',') for l in lines]

        def check(r):
            res = list(r)
            assert len(res) == 2
            assert res[1][1] == 'läneß'

        check(reader(lines, delimiter='\t'))
        for lt in ['\n', '\r\n', '\r']:
            if PY3:  # pragma: no cover
                # Simulate file opened in text mode:
                fp = StringIO(lt.join(lines), newline='')
            else:
                # Simulate file opened in binary mode:
                fp = BytesIO(to_binary(lt).join(encoded_lines))
            check(reader(fp, delimiter='\t'))
        check(reader(FIXTURES.joinpath('csv.txt')))

        res = list(reader(FIXTURES.joinpath('tsv.txt'), namedtuples=True, delimiter='\t'))
        assert res[0].a_name == 'b'
        # Missing column values should be set to None:
        assert res[2].a_name is None

        r = list(reader(lines, dicts=True, delimiter='\t'))
        assert len(r) == 1 and r[0]['first'] == 'sücond'
        r = list(reader(lines, namedtuples=True, delimiter='\t'))
        assert len(r) == 1 and r[0].first == 'sücond'
        r = list(reader(csv_lines, namedtuples=True))
        assert len(r) == 1 and r[0].first == 'sücond'
        self.assertEqual(list(reader([], dicts=True, delimiter='\t')), [])
        self.assertEqual(
            list(reader([''], dicts=True, fieldnames=['a', 'b'], delimiter='\t')), [])
        self.assertEqual(list(reader(['a,b', ''], dicts=True, delimiter='\t')), [])

        r = reader(
            ['a,b', '1,2,3,4', '1'], dicts=True, restkey='x', restval='y', delimiter=',')
        self.assertEqual(list(r), [dict(a='1', b='2', x=['3', '4']), dict(a='1', b='y')])

    def test_writer(self):
        from csvw.dsv import UnicodeWriter

        row = [None, 0, 1.2, 'äöü']
        as_csv = ',0,1.2,äöü'

        with UnicodeWriter() as writer:
            writer.writerows([row])
        self.assertEqual(writer.read().splitlines()[0].decode('utf8'), as_csv)

        tmp = self.tmp_path('test')
        with UnicodeWriter(tmp) as writer:
            writer.writerow(row)
        with tmp.open(encoding='utf8') as fp:
            res = fp.read().splitlines()[0]
        self.assertEqual(res, as_csv)

    def test_rewrite(self):
        from csvw.dsv import reader, rewrite

        tmp = self.tmp_path('test')
        shutil.copy(FIXTURES.joinpath('tsv.txt').as_posix(), tmp.as_posix())
        rewrite(tmp.as_posix(), lambda i, row: [len(row)], delimiter='\t')
        self.assertEquals(list(reader(tmp))[0], ['2'])

        shutil.copy(FIXTURES.joinpath('csv.txt').as_posix(), tmp.as_posix())
        rewrite(tmp, lambda i, row: row)
        self.assertEquals(list(reader(tmp)), list(reader(FIXTURES.joinpath('csv.txt'))))

    def test_add_delete_rows(self):
        from csvw.dsv import add_rows, filter_rows_as_dict, reader

        csv_path = self.tmp_path('test.csv')
        add_rows(csv_path, ['a', 'b'], [1, 2], [3, 4])
        self.assertEqual(len(list(reader(csv_path, dicts=True))), 2)
        filter_rows_as_dict(csv_path, lambda item: item['a'] == '1')
        self.assertEqual(len(list(reader(csv_path, dicts=True))), 1)
        add_rows(csv_path, [2, 2], [2, 4])
        self.assertEqual(len(list(reader(csv_path, dicts=True))), 3)
        res = filter_rows_as_dict(csv_path, lambda item: item['a'] == '1')
        self.assertEqual(res, 2)

    def test_reader_with_keyword_dialect(self):
        from csvw.dsv import reader, UnicodeWriter

        data = [['1', 'y'], ['  "1 ', '3\t4']]
        with UnicodeWriter(self.tmp_path('test'), dialect='excel') as w:
            w.writerows(data)
        self.assertEqual(list(reader(self.tmp_path('test'), dialect='excel')), data)

    def test_reader_with_comments(self):
        from csvw.dsv import UnicodeReader, Dialect

        d = Dialect(commentPrefix='*', header=False, trim=True)
        with UnicodeReader(['1,x,y', ' *1,a,b', 'a,b,c', '*1,1,2'], dialect=d) as r:
            # Comment markers must appear at the very start of a row, without any trimming
            self.assertEqual(len(list(r)), 3)
            self.assertEqual(r.comments[0], (3, '1,1,2'))

    def test_reader_with_dialect(self):
        from csvw.dsv import reader, Dialect

        d = Dialect(trim=True, skipRows=1, skipColumns=1, skipBlankRows=True)
        r = list(reader(['1,x,y', ' #1,a,b', '#1,1,2', ',,', '1,3, 4\t '], dialect=d))

        # make sure comment lines are stripped:
        self.assertEqual(len(r), 2)

        # make sure cells are trimmmed:
        self.assertEqual(r[1][1], '4')

        r = list(reader(
            ['1,x,y', ' #1,a,b', '#1,1,2', ',,', '1,3, 4\t '],
            dialect=d.updated(skipRows=0, skipColumns=0)))

        self.assertEqual(r[2][2], '4')

        d = Dialect(doubleQuote=False, quoteChar=None)
        r = list(reader(['1,"x""y",x'], dialect=d))
        self.assertEqual(r[0][1], '"x""y"')

        d = Dialect(doubleQuote=True)
        r = list(reader(['1,"x""y",y\\,x'], dialect=d))
        self.assertEqual(r[0][1], 'x"y')
        self.assertEqual(r[0][2], 'y,x')

        d = Dialect(commentPrefix=None)
        r = list(reader(['#x,y'], dialect=d))
        self.assertEqual(r[0][0], '#x')
