from __future__ import unicode_literals

import re
import collections

import attr


def attr_defaults(cls):
    res = collections.OrderedDict()
    for field in attr.fields(cls):
        default = field.default
        if isinstance(default, attr.Factory):
            default = default.factory()
        res[field.name] = default
    return res


def attr_asdict(obj, omit_defaults=True, omit_private=True):
    defs = attr_defaults(obj.__class__)
    res = collections.OrderedDict()
    for field in attr.fields(obj.__class__):
        if not (omit_private and field.name.startswith('_')):
            value = getattr(obj, field.name)
            if not (omit_defaults and value == defs[field.name]):
                if hasattr(value, 'asdict'):
                    value = value.asdict(omit_defaults=True)
                res[field.name] = value
    return res


def attr_valid_re(regex_or_pattern, nullable=False):
    if hasattr(regex_or_pattern, 'match'):
        pattern = regex_or_pattern
    else:
        pattern = re.compile(regex_or_pattern)

    msg = '{0} is not a valid {1}'

    if nullable:
        def valid_re(instance, attribute, value):
            if value is not None and pattern.match(value) is None:
                raise ValueError(msg.format(value, attribute.name))
    else:
        def valid_re(instance, attribute, value):
            if pattern.match(value) is None:
                raise ValueError(msg.format(value, attribute.name))

    return valid_re


def attr_valid_range(min_, max_, nullable=False):
    assert any(x is not None for x in (min_, max_))

    msg = '{0} is not a valid {1}'

    if nullable:
        def valid_range(instance, attribute, value):
            if value is None:
                pass
            elif (min_ is not None and value < min_) or (max_ is not None and value > max_):
                raise ValueError(msg.format(value, attribute.name))
    else:
        def valid_range(instance, attribute, value):
            if (min_ is not None and value < min_) or (max_ is not None and value > max_):
                raise ValueError(msg.format(value, attribute.name))

    return valid_range
