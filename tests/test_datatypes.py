# coding: utf8

from __future__ import unicode_literals

from unittest import TestCase
from decimal import Decimal
import datetime

from csvw.metadata import Datatype


class DatatypeTests(TestCase):

    def test_string(self):
        t = Datatype.fromvalue({'base': 'string', 'format': '[0-9]+[a-z]+'})
        self.assertEqual(t.read('1a'), '1a')
        with self.assertRaises(ValueError):
            t.read('abc')
        with self.assertRaises(ValueError):
            t.read('1a.')

    def test_anyURI(self):
        t = Datatype.fromvalue('anyURI')
        uri = t.parse('/a/b?d=5')
        self.assertEqual(
            uri.resolve_with('http://example.org').unsplit(),
            'http://example.org/a/b?d=5')
        self.assertEqual(t.formatted(uri), '/a/b?d=5')

    def test_number(self):
        t = Datatype.fromvalue('integer')
        self.assertEqual(t.parse('5'), 5)

        t = Datatype.fromvalue({'base': 'integer', 'minimum': 5, 'maximum': 10})
        v = t.parse('3')
        with self.assertRaises(ValueError):
            t.validate(v)
        self.assertEqual(t.formatted(v), '3')
        with self.assertRaises(ValueError):
            t.validate(12)

        t = Datatype.fromvalue(
            {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}})
        self.assertEqual(t.parse('INF'), Decimal('Infinity'))
        self.assertEqual(t.formatted(Decimal('NaN')), 'NaN')
        self.assertEqual(t.parse('1.234,567'), Decimal('1234.567'))
        self.assertEqual(t.formatted(Decimal('1234.567')), '1.234,567')
        with self.assertRaises(ValueError):
            t.parse(' ')

        t = Datatype.fromvalue('float')
        with self.assertRaises(ValueError):
            t.parse(' ')

    def test_object(self):
        t = Datatype.fromvalue({'base': 'string', 'length': 5, '@id': 'x', 'dc:type': ''})
        self.assertEqual(t.validate('abcde'), 'abcde')
        with self.assertRaises(ValueError):
            t.validate('abc')

    def test_errors(self):
        with self.assertRaises(ValueError):
            Datatype.fromvalue({'base': 'string', 'length': 5, 'minLength': 6})

        with self.assertRaises(ValueError):
            Datatype.fromvalue({'base': 'string', 'length': 5, 'maxLength': 4})

        with self.assertRaises(ValueError):
            dt = Datatype.fromvalue({'base': 'string', 'minLength': 4})
            dt.validate('abc')

        with self.assertRaises(ValueError):
            dt = Datatype.fromvalue({'base': 'string', 'maxLength': 4})
            dt.validate('abcdefg')

        with self.assertRaises(ValueError):
            Datatype.fromvalue({'base': 'string', 'maxLength': 5, 'minLength': 6})

        with self.assertRaises(ValueError):
            Datatype.fromvalue(5)

    def test_date(self):
        t = Datatype.fromvalue('date')
        self.assertEqual(t.formatted(t.parse('2012-12-01')), '2012-12-01')

        with self.assertRaises(ValueError):
            Datatype.fromvalue({'base': 'date', 'format': '2012+12+12'})

        t = Datatype.fromvalue('datetime')
        self.assertEqual(
            t.formatted(t.parse('2012-12-01T12:12:12')), '2012-12-01T12:12:12')

        with self.assertRaises(ValueError):
            Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SGS'})

        with self.assertRaises(ValueError):
            Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.S XxX'})

        t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm'})
        self.assertEqual(
            t.formatted(t.parse('22.3.2015 22:05')), '22.3.2015 22:05')

        t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SSS'})
        self.assertEqual(
            t.formatted(t.parse('22.3.2015 22:05:55.012')), '22.3.2015 22:05:55.012')
        self.assertEqual(
            t.formatted(datetime.datetime(2012, 12, 12, 12, 12, 12, microsecond=12345)),
            '12.12.2012 12:12:12.012')

        t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm X'})
        self.assertEqual(
            t.formatted(t.parse('22.3.2015 22:05 +03')), '22.3.2015 22:05 +03')

        t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm XXX'})
        self.assertEqual(
            t.formatted(t.parse('22.3.2015 22:05 +03:30')), '22.3.2015 22:05 +03:30')

        t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm X'})
        self.assertEqual(
            t.formatted(t.parse('22.3.2015 22:05 +0330')), '22.3.2015 22:05 +0330')
        self.assertEqual(
            t.parse('22.3.2015 23:05 +0430'), t.parse('22.3.2015 22:05 +0330'))

        t = Datatype.fromvalue({'base': 'time', 'format': 'HH:mm X'})
        self.assertEqual(t.parse('23:05 +0430'), t.parse('22:05 +0330'))
        self.assertEqual(t.formatted(t.parse('23:05 +0430')), '23:05 +0430')

        t = Datatype.fromvalue({'base': 'time'})
        self.assertEqual(t.parse('23:05:22'), t.parse('23:05:22'))

        # "d.M.yyyy",  # e.g., 22.3.2015
        t = Datatype.fromvalue({'base': 'date', 'format': "d.M.yyyy"})
        self.assertEqual(t.formatted(t.parse('22.3.2015')), '22.3.2015')

        t = Datatype.fromvalue({'base': 'dateTimeStamp'})
        with self.assertRaises(ValueError):
            t.parse('22.3.2015 22:05')
        self.assertEqual(
            t.formatted(t.parse('2012-12-01T12:12:12.123456+05:30')),
            '2012-12-01T12:12:12.123456+05:30')

        with self.assertRaises(ValueError):
            Datatype.fromvalue({'base': 'dateTimeStamp', 'format': 'd.M.yyyy HH:mm:ss.SSS'})

        t = Datatype.fromvalue({'base': 'duration'})
        self.assertEqual(t.formatted(t.parse('P1Y1D')), 'P1Y1D')

        t = Datatype.fromvalue({'base': 'duration'})
        self.assertEqual(t.formatted(t.parse('PT2H30M')), 'PT2H30M')

        t = Datatype.fromvalue({'base': 'duration', 'format': 'P[1-5]Y'})
        with self.assertRaises(ValueError):
            t.parse('P8Y')

    def test_misc(self):
        t = Datatype.fromvalue({'base': 'any'})
        self.assertEqual(t.formatted(None), 'None')

        t = Datatype.fromvalue({'base': 'float'})
        self.assertAlmostEqual(t.parse('3.5'), 3.5)
        self.assertEqual(t.formatted(3.5), '3.5')

        t = Datatype.fromvalue({'base': 'number'})
        self.assertAlmostEqual(t.parse('3.123456789'), 3.123456789)
        self.assertEqual(t.formatted(3.123456789), '3.123456789')

        t = Datatype.fromvalue({'base': 'json'})
        self.assertEqual(t.parse('{"a": 5}'), dict(a=5))
        self.assertEqual(t.formatted(dict(a=5)), '{"a": 5}')

        t = Datatype.fromvalue({'base': 'boolean'})
        with self.assertRaises(ValueError):
            t.parse('J')

        t = Datatype.fromvalue({'base': 'boolean'})
        self.assertEqual('{0}'.format(t.basetype), 'boolean')
        self.assertEqual(t.parse(False), False)
        self.assertEqual(t.parse('false'), False)
        self.assertEqual(t.formatted(True), 'true')

        t = Datatype.fromvalue({'base': 'boolean', 'format': 'J|N'})
        self.assertEqual(t.parse('J'), True)
        self.assertEqual(t.formatted(True), 'J')

        t = Datatype.fromvalue({'base': 'binary'})
        self.assertEqual(t.formatted(t.parse('aGVsbG8gd29ybGQ=')), 'aGVsbG8gd29ybGQ=')
        with self.assertRaises(ValueError):
            t.parse('ä')
        with self.assertRaises(ValueError):
            t.parse('aGVsbG8gd29ybGQ')

        t = Datatype.fromvalue({'base': 'hexBinary'})
        self.assertEqual(t.formatted(t.parse('abcdef12')), 'abcdef12')
        with self.assertRaises(ValueError):
            t.parse('ä')
        with self.assertRaises(ValueError):
            t.parse('a')
