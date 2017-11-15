# csvw - https://w3c.github.io/csvw/primer/

from .metadata import (TableGroup, Table, Column, ForeignKey,
    Link, NaturalLanguage, Datatype)

__all__ = [
    'TableGroup',
    'Table', 'Column', 'ForeignKey',
    'Link', 'NaturalLanguage',
    'Datatype',
]

__title__ = 'csvw'
__version__ = '0.1'
__author__ = 'Robert Forkel'
__license__ = 'Apache 2.0, see LICENSE'
__copyright__ = 'Copyright (c) 2017 Robert Forkel'
