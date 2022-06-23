# csvw - https://w3c.github.io/csvw/primer/

from .metadata import (
    TableGroup, Table, Column, ForeignKey, Link, NaturalLanguage, Datatype, URITemplate, CSVW
)

from .dsv import (UnicodeWriter,
    UnicodeReader, UnicodeReaderWithLineNumber, UnicodeDictReader, NamedTupleReader,
    iterrows, rewrite)

__all__ = [
    'TableGroup',
    'Table', 'Column', 'ForeignKey',
    'Link', 'NaturalLanguage',
    'Datatype',
    'URITemplate',
    'UnicodeWriter',
    'UnicodeReader', 'UnicodeReaderWithLineNumber', 'UnicodeDictReader', 'NamedTupleReader',
    'iterrows', 'rewrite',
    'CSVW',
]

__title__ = 'csvw'
__version__ = '2.0.1.dev0'
__author__ = 'Robert Forkel'
__license__ = 'Apache 2.0, see LICENSE'
__copyright__ = 'Copyright (c) 2022 Robert Forkel'
