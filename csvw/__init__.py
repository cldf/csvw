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
__version__ = '0.0.dev0'
__author__ = ''
__license__ = 'Apache 2.0, see LICENSE'
__copyright__ = ''
