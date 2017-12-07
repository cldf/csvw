from __future__ import unicode_literals

import decimal
import datetime

import pytest

from csvw import Datatype


def test_string():
    t = Datatype.fromvalue({'base': 'string', 'format': '[0-9]+[a-z]+'})
    assert t.read('1a') == '1a'
    with pytest.raises(ValueError):
        t.read('abc')
    with pytest.raises(ValueError):
        t.read('1a.')


def test_anyURI():
    t = Datatype.fromvalue('anyURI')
    uri = t.parse('/a/b?d=5')
    assert uri.resolve_with('http://example.org').unsplit() == \
           'http://example.org/a/b?d=5'
    assert t.formatted(uri) == '/a/b?d=5'


def test_number():
    t = Datatype.fromvalue('integer')
    assert t.parse('5') == 5

    t = Datatype.fromvalue({'base': 'integer', 'minimum': 5, 'maximum': 10})
    v = t.parse('3')
    with pytest.raises(ValueError):
        t.validate(v)
    assert t.formatted(v) == '3'
    with pytest.raises(ValueError):
        t.validate(12)

    t = Datatype.fromvalue(
        {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}})
    assert t.parse('INF') == decimal.Decimal('Infinity')
    assert t.formatted(decimal.Decimal('NaN')) == 'NaN'
    assert t.parse('1.234,567') == decimal.Decimal('1234.567')
    assert t.formatted(decimal.Decimal('1234.567')) == '1.234,567'
    with pytest.raises(ValueError):
        t.parse(' ')

    t = Datatype.fromvalue('float')
    with pytest.raises(ValueError):
        t.parse(' ')


def test_object():
    t = Datatype.fromvalue({'base': 'string', 'length': 5, '@id': 'x', 'dc:type': ''})
    assert t.validate('abcde') == 'abcde'
    with pytest.raises(ValueError):
        t.validate('abc')


def test_errors():
    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'string', 'length': 5, 'minLength': 6})

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'string', 'length': 5, 'maxLength': 4})

    with pytest.raises(ValueError):
        dt = Datatype.fromvalue({'base': 'string', 'minLength': 4})
        dt.validate('abc')

    with pytest.raises(ValueError):
        dt = Datatype.fromvalue({'base': 'string', 'maxLength': 4})
        dt.validate('abcdefg')

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'string', 'maxLength': 5, 'minLength': 6})

    with pytest.raises(ValueError):
        Datatype.fromvalue(5)


def test_date():
    t = Datatype.fromvalue('date')
    assert t.formatted(t.parse('2012-12-01')) == '2012-12-01'

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'date', 'format': '2012+12+12'})

    t = Datatype.fromvalue('datetime')
    assert t.formatted(t.parse('2012-12-01T12:12:12')) == '2012-12-01T12:12:12'

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SGS'})

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.S XxX'})

    t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm'})
    assert t.formatted(t.parse('22.3.2015 22:05')) == '22.3.2015 22:05'

    t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SSS'})
    assert t.formatted(t.parse('22.3.2015 22:05:55.012')) == '22.3.2015 22:05:55.012'
    assert t.formatted(datetime.datetime(2012, 12, 12, 12, 12, 12, microsecond=12345)) == \
           '12.12.2012 12:12:12.012'

    t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm X'})
    assert t.formatted(t.parse('22.3.2015 22:05 +03')) == '22.3.2015 22:05 +03'

    t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm XXX'})
    assert t.formatted(t.parse('22.3.2015 22:05 +03:30')) == '22.3.2015 22:05 +03:30'

    t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm X'})
    assert t.formatted(t.parse('22.3.2015 22:05 +0330')) == '22.3.2015 22:05 +0330'
    assert t.parse('22.3.2015 23:05 +0430') == t.parse('22.3.2015 22:05 +0330')

    t = Datatype.fromvalue({'base': 'time', 'format': 'HH:mm X'})
    assert t.parse('23:05 +0430') == t.parse('22:05 +0330')
    assert t.formatted(t.parse('23:05 +0430')) == '23:05 +0430'

    t = Datatype.fromvalue({'base': 'time'})
    assert t.parse('23:05:22') == t.parse('23:05:22')

    # "d.M.yyyy",  # e.g., 22.3.2015
    t = Datatype.fromvalue({'base': 'date', 'format': "d.M.yyyy"})
    assert t.formatted(t.parse('22.3.2015')) == '22.3.2015'

    t = Datatype.fromvalue({'base': 'dateTimeStamp'})
    with pytest.raises(ValueError):
        t.parse('22.3.2015 22:05')
    assert t.formatted(t.parse('2012-12-01T12:12:12.123456+05:30')) == \
           '2012-12-01T12:12:12.123456+05:30'

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'dateTimeStamp', 'format': 'd.M.yyyy HH:mm:ss.SSS'})

    t = Datatype.fromvalue({'base': 'duration'})
    assert t.formatted(t.parse('P1Y1D')) == 'P1Y1D'

    t = Datatype.fromvalue({'base': 'duration'})
    assert t.formatted(t.parse('PT2H30M')) == 'PT2H30M'

    t = Datatype.fromvalue({'base': 'duration', 'format': 'P[1-5]Y'})
    with pytest.raises(ValueError):
        t.parse('P8Y')


def test_misc():
    t = Datatype.fromvalue({'base': 'any'})
    assert t.formatted(None) == 'None'

    t = Datatype.fromvalue({'base': 'float'})
    assert t.parse('3.5') == pytest.approx(3.5)
    assert t.formatted(3.5) == '3.5'

    t = Datatype.fromvalue({'base': 'number'})
    assert t.parse('3.123456789') == pytest.approx(3.123456789)
    assert t.formatted(3.123456789) == '3.123456789'

    t = Datatype.fromvalue({'base': 'json'})
    assert t.parse('{"a": 5}') == {'a': 5}
    assert t.formatted({'a': 5}) == '{"a": 5}'

    t = Datatype.fromvalue({'base': 'boolean'})
    with pytest.raises(ValueError):
        t.parse('J')

    t = Datatype.fromvalue({'base': 'boolean'})
    assert '{}'.format(t.basetype()) == 'boolean'
    assert t.parse(False) is False
    assert t.parse('false') is False
    assert t.formatted(True) == 'true'

    t = Datatype.fromvalue({'base': 'boolean', 'format': 'J|N'})
    assert t.parse('J') is True
    assert t.formatted(True) == 'J'

    t = Datatype.fromvalue({'base': 'binary'})
    assert t.formatted(t.parse('aGVsbG8gd29ybGQ=')) == 'aGVsbG8gd29ybGQ='
    with pytest.raises(ValueError):
        t.parse('sp\u00e4m')
    with pytest.raises(ValueError):
        t.parse('aGVsbG8gd29ybGQ')

    t = Datatype.fromvalue({'base': 'hexBinary'})
    assert t.formatted(t.parse('abcdef12')) == 'abcdef12'
    with pytest.raises(ValueError):
        t.parse('sp\u00e4m')
    with pytest.raises(ValueError):
        t.parse('spam')
