import decimal
import datetime
import warnings
from urllib.parse import urlparse

import pytest

from csvw import Datatype
from csvw.datatypes import NumberPattern


@pytest.mark.parametrize(
    'datatype,val,obj,roundtrip',
    [
        ({'base': 'string', 'format': '[0-9]+[a-z]+'}, '1a', '1a', True),
        ('anyURI', '/a/b?d=5', None, True),
        ('integer', '5', 5, True),
        ('decimal', '0.00000001', decimal.Decimal((0, (1,), -8)), True),
        ('decimal', '1000000000000', decimal.Decimal('1e12'), True),
        ('integer', '-5', -5, True),
        ('date', '2012-12-01', None, True),
        ('datetime', '2012-12-01T12:12:12', None, True),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm'}, '22.3.2015 22:05', None, True),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SSS'}, '22.3.2015 22:05:55.012', None, True),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm X'}, '22.3.2015 22:05 +03', None, True),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm XXX'}, '22.3.2015 22:05 +03:30', None, True),
        ({'base': 'date', 'format': "d.M.yyyy"}, '22.3.2015', None, True),
        ({'base': "date", 'format': 'M/d/yyyy'}, '10/18/2010', None, True),
        ({'base': 'duration'}, 'P1Y1D', None, True),
        ({'base': 'duration'}, 'PT2H30M', None, True),
        ({'base': 'time', 'format': 'HH:mm X'}, '23:05 +0430', None, True),
        ('time', '11:11:11', None, True),
        ('binary', 'aGVsbG8gd29ybGQ=', b'hello world', True),
        ('hexBinary', 'ABCDEF12', None, True),
        ({'base': 'decimal', 'format': '#,##0.##'}, '1,234.57', None, True),
        ({'base': 'decimal', 'format': {'pattern': '#,##0.##', 'groupChar': ' '}}, '1 234.57', None, True),
        ('json', '{"a": 5}', {'a': 5}, True),
        ('float', '3.5', 3.5, True),
        ('number', '3.123456789', 3.123456789, True),
        ({'base': 'boolean', 'format': 'J|N'}, 'J', True, True),
        ({'base': 'nonNegativeInteger'}, '0', 0, True),
        ({'base': 'positiveInteger'}, '1', 1, True),
        ({'base': "json", "format": '{"type":"object","required":["a"]}'}, '{"a": 1}', {'a': 1}, True),
        ({'base': "json", "format": '{"type":"object"}'}, '{"x": 1}', dict(x=1), True),
        ({'base': "json", "format": 'x'}, '{"x": 1}', dict(x=1), True),
        (
                {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}},
                '1.234,567',
                decimal.Decimal('1234.567'),
                True),
        (
                {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}},
                '20%',
                decimal.Decimal('0.2'),
                False),
        # From https://www.w3.org/TR/2015/REC-tabular-data-model-20151217/#parsing-cells
        # For example, the string value "-25%" must be interpreted as -0.25 and the string value
        # "1E6" as 1000000.
        (
                {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}},
                '-25%',
                decimal.Decimal('-0.25'),
                False),
        (
                {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}},
                '20‰',
                decimal.Decimal('0.02'),
                False),
        ({'base': 'string', 'length': 5, '@id': 'x', 'dc:type': ''}, 'abcde', 'abcde', True),
]
)
def test_roundtrip(datatype, val, obj, roundtrip):
    t = Datatype.fromvalue(datatype)
    o = t.parse(val)
    if obj:
        if isinstance(obj, float):
            assert o == pytest.approx(obj)
        else:
            assert o == obj
    if roundtrip:
        assert t.formatted(o) == val


@pytest.mark.parametrize(
    'datatype,val',
    [
        ({'base': 'nonNegativeInteger'}, '-1'),
        ({'base': 'positiveInteger'}, '0'),
        ({'base': 'double', 'minimum': 10}, '3.1'),
        ({'base': 'string', 'format': '[0-9]+[a-z]+'}, 'abc'),
        ({'base': 'string', 'format': '[0-9]+[a-z]+'}, '1a.'),
        ("NMTOKEN", 'bold,brash'),
        ({'base': "json", "format": '{"type":"object","required":["a"]}'}, '{"x": 1}'),
        ({'base': 'boolean'}, 'J'),
        ('float', ' '),
        ({'base': 'string', 'length': 5, '@id': 'x', 'dc:type': ''}, 'abc'),
        ({'base': 'binary'}, 'sp\u00e4m'),
        ({'base': 'binary'}, 'aGVsbG8gd29ybGQ'),
        ({'base': 'hexBinary'}, 'sp\u00e4m'),
        ({'base': 'hexBinary'}, 'spam'),
    ]
)
def test_invalid(datatype, val):
    t = Datatype.fromvalue(datatype)
    with pytest.raises(ValueError):
        t.read(val)


def test_json():
    """
    If the format annotation is JSON but **not** a valid JSON Schema, emit a warning.
    """
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        t = Datatype.fromvalue({'base': "json", "format": '{"type":"obj"}'})
        t.read('{"x": 1}')


def test_anyURI():
    """
    Writing anyURI will perform some normalization.
    """
    t = Datatype.fromvalue('anyURI')
    assert t.formatted('Http://example.org') == 'http://example.org'
    assert t.formatted(urlparse('Http://example.org')) == 'http://example.org'


def test_number():
    t = Datatype.fromvalue({'base': 'integer', 'minimum': 5, 'maximum': 10})
    v = t.parse('3')
    with pytest.raises(ValueError):
        t.validate(v)
    assert t.formatted(v) == '3'
    with pytest.raises(ValueError):
        t.validate(12)
    
    t = Datatype.fromvalue(
        {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}})
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        assert t.parse('INF') == decimal.Decimal('Infinity')
        assert t.formatted(decimal.Decimal('NaN')) == 'NaN'
    assert t.formatted(decimal.Decimal('1234.567')) == '1.234,567'
    with pytest.raises(ValueError):
        t.parse(' ')

    t = Datatype.fromvalue({'base': 'decimal', 'format': '0.00;0.00-'})
    assert t.formatted(decimal.Decimal('-3.1415')) == '3.14-'

    t = Datatype.fromvalue(
        {'base': 'decimal', 'format': {'pattern': '0.00;0.00-', 'decimalChar': ','}})
    assert t.formatted(decimal.Decimal('-3.1415')) == '3,14-'


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
    with pytest.warns(UserWarning):
        Datatype.fromvalue({'base': 'date', 'format': '2012+12+12'})

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SGS'})

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.S XxX'})

    t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SSS'})
    assert t.formatted(datetime.datetime(2012, 12, 12, 12, 12, 12, microsecond=12345)) == \
           '12.12.2012 12:12:12.012'

    t = Datatype.fromvalue({'base': 'datetime', 'format': 'd.M.yyyy HH:mm X'})
    assert t.parse('22.3.2015 23:05 +0430') == t.parse('22.3.2015 22:05 +0330')

    t = Datatype.fromvalue({'base': 'time', 'format': 'HH:mm X'})
    assert t.parse('23:05 +0430') == t.parse('22:05 +0330')

    t = Datatype.fromvalue({'base': 'time'})
    assert t.parse('23:05:22') == t.parse('23:05:22')

    t = Datatype.fromvalue({'base': 'dateTimeStamp'})
    with pytest.raises(ValueError):
        t.parse('22.3.2015 22:05')
    assert t.formatted(t.parse('2012-12-01T12:12:12.123456+05:30')) == \
           '2012-12-01T12:12:12.123456+05:30'

    with pytest.raises(ValueError):
        Datatype.fromvalue({'base': 'dateTimeStamp', 'format': 'd.M.yyyy HH:mm:ss.SSS'})

    t = Datatype.fromvalue({'base': 'duration', 'format': 'P[1-5]Y'})
    with pytest.raises(ValueError):
        t.parse('P8Y')


def test_misc():
    t = Datatype.fromvalue({'base': 'any'})
    assert t.formatted(None) == 'None'

    t = Datatype.fromvalue({'base': 'boolean'})
    assert '{}'.format(t.basetype()) == 'boolean'
    assert t.parse(False) is False
    assert t.parse('false') is False
    assert t.formatted(True) == 'true'

    t = Datatype.fromvalue('decimal')
    assert t.formatted('1e6') == '100000.0'


def test_NumberPattern():
    np = NumberPattern('0.0E#,##0 #')
    assert np.exponent_digits == 4
    assert not NumberPattern('#,##,##0').is_valid('234,567')
