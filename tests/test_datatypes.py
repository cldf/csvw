import decimal
import datetime
import warnings
from urllib.parse import urlparse

import pytest

from csvw import Datatype
from csvw.datatypes import NumberPattern


@pytest.mark.parametrize(
    'datatype,val,obj',
    [
        ({'base': 'string', 'format': '[0-9]+[a-z]+'}, '1a', '1a'),
        ('anyURI', '/a/b?d=5', None),
        ('integer', '5', 5),
        ('integer', '-5', -5),
        ('date', '2012-12-01', None),
        ('datetime', '2012-12-01T12:12:12', None),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm'}, '22.3.2015 22:05', None),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm:ss.SSS'}, '22.3.2015 22:05:55.012', None),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm X'}, '22.3.2015 22:05 +03', None),
        ({'base': 'datetime', 'format': 'd.M.yyyy HH:mm XXX'}, '22.3.2015 22:05 +03:30', None),
        ({'base': 'date', 'format': "d.M.yyyy"}, '22.3.2015', None),
        ({'base': "date", 'format': 'M/d/yyyy'}, '10/18/2010', None),
        ({'base': 'duration'}, 'P1Y1D', None),
        ({'base': 'duration'}, 'PT2H30M', None),
        ({'base': 'time', 'format': 'HH:mm X'}, '23:05 +0430', None),
        ('time', '11:11:11', None),
        ('binary', 'aGVsbG8gd29ybGQ=', b'hello world'),
        ('hexBinary', 'ABCDEF12', None),
        ({'base': 'decimal', 'format': '#,##0.##'}, '1,234.57', None),
        ({'base': 'decimal', 'format': {'pattern': '#,##0.##', 'groupChar': ' '}}, '1 234.57', None),
        ('json', '{"a": 5}', {'a': 5}),
        ('float', '3.5', 3.5),
        ('number', '3.123456789', 3.123456789),
        ({'base': 'boolean', 'format': 'J|N'}, 'J', True),
    ]
)
def test_roundtrip(datatype, val, obj):
    t = Datatype.fromvalue(datatype)
    o = t.parse(val)
    if obj:
        if isinstance(obj, float):
            assert o == pytest.approx(obj)
        else:
            assert o == obj
    assert t.formatted(o) == val


def test_double():
    t = Datatype.fromvalue({'base': 'double', 'minimum': 10})
    v = t.parse('3.1')
    with pytest.raises(ValueError):
        t.validate(v)


def test_string():
    t = Datatype.fromvalue({'base': 'string', 'format': '[0-9]+[a-z]+'})
    with pytest.raises(ValueError):
        t.read('abc')
    with pytest.raises(ValueError):
        t.read('1a.')

    with pytest.raises(ValueError):
        Datatype.fromvalue('NMTOKEN').read("bold,brash")


def test_json():
    t = Datatype.fromvalue({'base': "json", "format": '{"type":"object"}'})
    t = Datatype.fromvalue({'base': "json", "format": '{"type":"object","required":["a"]}'})
    assert t.read('{"a": 1}') == dict(a=1)
    with pytest.raises(ValueError):
        t.read('{"x": 1}')
    t = Datatype.fromvalue({'base': "json", "format": '{"type":"object"}'})
    t.read('{"x": 1}')
    t = Datatype.fromvalue({'base': "json", "format": 'x'})
    t.read('{"x": 1}')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        t = Datatype.fromvalue({'base': "json", "format": '{"type":"obj"}'})
        t.read('{"x": 1}')


def test_anyURI():
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
    
    t = Datatype.fromvalue({'base': 'nonNegativeInteger'})
    with pytest.raises(ValueError):
        v = t.parse('-3')

    t = Datatype.fromvalue(
        {'base': 'decimal', 'format': {'groupChar': '.', 'decimalChar': ','}})
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        assert t.parse('INF') == decimal.Decimal('Infinity')
        assert t.formatted(decimal.Decimal('NaN')) == 'NaN'
    assert t.parse('1.234,567') == decimal.Decimal('1234.567')
    assert t.parse('20%') == decimal.Decimal('0.2')
    # From https://www.w3.org/TR/2015/REC-tabular-data-model-20151217/#parsing-cells
    # For example, the string value "-25%" must be interpreted as -0.25 and the string value "1E6"
    # as 1000000.
    assert t.parse('-25%') == decimal.Decimal('-0.25')
    assert t.parse('20‰') == decimal.Decimal('0.02')
    assert t.formatted(decimal.Decimal('1234.567')) == '1.234,567'
    with pytest.raises(ValueError):
        t.parse(' ')

    t = Datatype.fromvalue({'base': 'decimal', 'format': '0.00;0.00-'})
    assert t.formatted(decimal.Decimal('-3.1415')) == '3.14-'

    t = Datatype.fromvalue(
        {'base': 'decimal', 'format': {'pattern': '0.00;0.00-', 'decimalChar': ','}})
    assert t.formatted(decimal.Decimal('-3.1415')) == '3,14-'

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
    with pytest.raises(ValueError):
        t.parse('J')

    t = Datatype.fromvalue({'base': 'boolean'})
    assert '{}'.format(t.basetype()) == 'boolean'
    assert t.parse(False) is False
    assert t.parse('false') is False
    assert t.formatted(True) == 'true'

    t = Datatype.fromvalue({'base': 'binary'})
    with pytest.raises(ValueError):
        t.parse('sp\u00e4m')
    with pytest.raises(ValueError):
        t.parse('aGVsbG8gd29ybGQ')

    t = Datatype.fromvalue({'base': 'hexBinary'})
    with pytest.raises(ValueError):
        t.parse('sp\u00e4m')
    with pytest.raises(ValueError):
        t.parse('spam')


def test_NumberPattern():
    np = NumberPattern('0.0E#,##0 #')
    assert np.exponent_digits == 4

    assert not NumberPattern('#,##,##0').is_valid('234,567')
