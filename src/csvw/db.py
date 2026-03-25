"""
SQLite as alternative storage backend for a TableGroup's data.

For the most part, translation of a TableGroup's tableSchema to SQL works as expected:

- each table is converted to a `CREATE TABLE` statement
- each column specifies a column in the corresponding `CREATE TABLE` statement
- `foreignKey` constraints are added according to the corresponding `tableSchema` property.

List-valued foreignKeys are supported as follows: For each pair of tables related through a
list-valued foreign key, an association table is created. To make it possible to distinguish
multiple list-valued foreign keys between the same two tables, the association table has
a column `context`, which stores the name of the foreign key column from which a row in the
assocation table was created.

Other list-valued columns work in two different ways: If the atomic datatype is `string`, the
specified separator is used to create a concatenated string representation in the database field.
Otherwise, the list of values is serialized as JSON.

SQL table and column names can be customized by passing a translator callable when instantiating
a :class:`Database`.

SQLite support has the following limitations:

- regex constraints on strings (as specified via a :class:`csvw.Datatype`'s format attribute) are
  not enforced by the database.
"""
import json
from typing import Optional, Union, Protocol, Callable, Any
import decimal
import pathlib
import sqlite3
import functools
import contextlib
import collections
from collections.abc import Sequence, Iterator
import dataclasses

import csvw
from csvw.datatypes import DATATYPES
from csvw.metadata import TableGroup, Datatype
from .utils import optcast


def identity(s):  # pylint: disable=C0116
    return s


@dataclasses.dataclass
class DBType:
    """A DB datatype together with read/write converters."""
    name: str
    convert: Callable[[Any], Any] = identity
    read: Callable[[Any], Any] = identity


TYPE_MAP = {
    'string': DBType('TEXT'),
    'integer': DBType('INTEGER'),
    'boolean': DBType('INTEGER', optcast(int), optcast(bool)),
    'decimal': DBType('REAL', optcast(float), optcast(decimal.Decimal)),
    'hexBinary': DBType('BLOB'),
}


class SchemaTranslator(Protocol):  # pylint: disable=R0903,C0115
    def __call__(self, table: str, column: Optional[str] = None) -> str:
        ...  # pragma: no cover


class ColumnTranslator(Protocol):  # pylint: disable=R0903,C0115
    def __call__(self, column: str) -> str:
        ...  # pragma: no cover


def quoted(*names: str) -> str:
    """Returns a comma-separated list of quoted schema object names."""
    return ','.join(f'`{name}`' for name in names)


def insert(db: sqlite3.Connection,
           translate: SchemaTranslator,
           table: str,
           keys: Sequence[str],
           *rows: list,
           single: Optional[bool] = False):
    """
    Insert a sequence of rows into a table.

    :param db: Database connection.
    :param translate: Callable translating table and column names to proper schema object names.
    :param table: Untranslated table name.
    :param keys: Untranslated column names.
    :param rows: Sequence of rows to insert.
    :param single: Flag signaling whether to insert all rows at once using `executemany` or one at \
    a time, allowing for more focused debugging output in case of errors.
    """
    if rows:
        cols = quoted(*[translate(table, k) for k in keys])
        vals = ','.join(['?' for _ in keys])
        sql = f"INSERT INTO {quoted(translate(table))} ({cols}) VALUES ({vals})"
        try:
            db.executemany(sql, rows)
        except:  # noqa: E722 - this is purely for debugging.  pylint: disable=bare-except
            if not single:
                for row in rows:
                    insert(db, translate, table, keys, row, single=True)
            else:
                print(sql)
                print(rows)
                raise


def select(db: sqlite3.Connection, table: str) -> tuple[list[str], Sequence]:
    """Shortcut to construct and execute simple SELECT statements."""
    cu = db.execute(f"SELECT * FROM {quoted(table)}")
    cols = [d[0] for d in cu.description]
    return cols, list(cu.fetchall())


@dataclasses.dataclass
class ColSpec:
    """
    A `ColSpec` captures sufficient information about a :class:`csvw.Column` for the DB schema.
    """
    name: str
    csvw_type: str = 'string'
    separator: str = None
    db_type: DBType = None
    required: bool = False
    csvw: Datatype = None

    def __post_init__(self):
        self.csvw_type = self.csvw_type or 'string'
        if self.csvw_type in TYPE_MAP:
            self.db_type = TYPE_MAP[self.csvw_type]
        else:
            self.db_type = DBType(
                'TEXT', DATATYPES[self.csvw_type].to_string, DATATYPES[self.csvw_type].to_python)
        if self.separator and self.db_type != 'TEXT':
            self.db_type = DBType('TEXT', self.db_type.convert, self.db_type.read)

    def check(self, translate: ColumnTranslator) -> Optional[str]:
        """
        We try to convert as many data constraints as possible into SQLite CHECK constraints.

        :param translate: Callable to translate column names between CSVW metadata and DB schema.
        :return: A string suitable as argument of an SQL CHECK constraint.
        """
        if not self.csvw:
            return None
        c, cname = self.csvw, translate(self.name)
        constraints = []
        if (c.minimum is not None) or (c.maximum is not None):
            func = {
                'date': 'date',
                'datetime': 'datetime',
            }.get(self.csvw_type)
            if c.minimum is not None:
                if func:
                    constraints.append(f"{func}(`{cname}`) >= {func}('{c.minimum}')")
                else:
                    constraints.append(f'`{cname}` >= {c.minimum}')
            if c.maximum is not None:
                if func:
                    constraints.append(f"{func}(`{cname}`) <= {func}('{c.maximum}')")
                else:
                    constraints.append(f'`{cname}` <= {c.maximum}')
        elif any(cc is not None for cc in [c.length, c.minLength, c.maxLength]):
            if c.length:
                constraints.append(f'length(`{cname}`) = {c.length}')
            if c.minLength:
                constraints.append(f'length(`{cname}`) >= {c.minLength}')
            if c.maxLength:
                constraints.append(f'length(`{cname}`) <= {c.maxLength}')
        return ' AND '.join(constraints)

    def sql(self, translate: ColumnTranslator) -> str:
        """Format the column metadata suitable for inclusion in a CREATE TABLE statement."""
        _check = self.check(translate)
        null_constraint = ' NOT NULL' if self.required else ''
        check_constraint = f' CHECK ({_check})' if _check else ''
        return f'`{translate(self.name)}` {self.db_type.name}{null_constraint}{check_constraint}'


@dataclasses.dataclass
class TableSpec:
    """
    A `TableSpec` captures sufficient information about a :class:`csvw.Table` for the DB schema.

    .. note::

        We support "light-weight" many-to-many relationships by allowing list-valued foreign key
        columns in CSVW. In the database these columns are turned into an associative table, adding
        the name of the column as value a `context` column. Thus, multiple columns in a table my be
        specified as targets of many-to-many relations with the same table.

        .. seealso:: `<https://en.wikipedia.org/wiki/Associative_entity>`_
    """
    name: str
    columns: list[ColSpec] = dataclasses.field(default_factory=list)
    foreign_keys: list = dataclasses.field(default_factory=list)
    many_to_many: collections.OrderedDict = dataclasses.field(
        default_factory=collections.OrderedDict)
    primary_key: Optional[list[str]] = None

    @classmethod
    def from_table_metadata(cls,
                            table: csvw.Table,
                            drop_self_referential_fks: Optional[bool] = True) -> 'TableSpec':
        """
        Create a `TableSpec` from the schema description of a `csvw.metadata.Table`.

        :param table: `csvw.metadata.Table` instance.
        :param drop_self_referential_fks: Flag signaling whether to drop self-referential foreign \
        keys. This may be necessary, if the order of rows in a CSVW table does not guarantee \
        referential integrity when inserted in order (e.g. an eralier row refering to a later one).
        :return: `TableSpec` instance.
        """
        spec = cls(name=table.local_name, primary_key=table.tableSchema.primaryKey)
        list_valued = {c.header for c in table.tableSchema.columns if c.separator}
        for fk in table.tableSchema.foreignKeys:
            # We only support Foreign Key references between tables!
            if not fk.reference.schemaReference:
                if len(fk.columnReference) == 1 and fk.columnReference[0] in list_valued:
                    # List-valued foreign keys are turned into a many-to-many relation!
                    assert len(fk.reference.columnReference) == 1, \
                        (f'Composite key {fk.reference.columnReference} in table '
                         f'{fk.reference.resource} referenced')
                    assert spec.primary_key and len(spec.primary_key) == 1, \
                        (f'Table {spec.name} referenced by list-valued foreign key must have '
                         f'non-composite primary key')
                    spec.many_to_many[fk.columnReference[0]] = TableSpec.association_table(
                        spec.name,
                        spec.primary_key[0],
                        fk.reference.resource.string,
                        fk.reference.columnReference[0],
                    )
                elif not (drop_self_referential_fks and fk.reference.resource.string == spec.name):
                    spec.foreign_keys.append((
                        sorted(fk.columnReference),
                        fk.reference.resource.string,
                        sorted(fk.reference.columnReference),
                    ))
        for c in table.tableSchema.columns:
            if c.header not in spec.many_to_many:
                datatype = c.inherit('datatype')
                spec.columns.append(ColSpec(
                    name=c.header,
                    csvw_type=datatype.base if datatype else datatype,
                    separator=c.inherit('separator'),
                    required=c.inherit('required'),
                    csvw=c.inherit('datatype'),
                ))
        return spec

    @classmethod
    def association_table(cls, atable, apk, btable, bpk) -> 'TableSpec':
        """
        List-valued foreignKeys are supported as follows: For each pair of tables related through a
        list-valued foreign key, an association table is created. To make it possible to distinguish
        multiple list-valued foreign keys between the same two tables, the association table has
        a column `context`, which stores the name of the foreign key column from which a row in the
        assocation table was created.
        """
        afk = ColSpec(f'{atable}_{apk}')
        bfk = ColSpec(f'{btable}_{bpk}')
        if afk.name == bfk.name:
            afk.name += '_1'
            bfk.name += '_2'
        return cls(
            name=f'{atable}_{btable}',
            columns=[afk, bfk, ColSpec('context')],
            foreign_keys=[
                ([afk.name], atable, [apk]),
                ([bfk.name], btable, [bpk]),
            ]
        )

    def sql(self, translate: SchemaTranslator) -> str:
        """
        :param translate:
        :return: The SQL statement to create the table.
        """
        col_translate = functools.partial(translate, self.name)
        # Assemble the column specifications:
        clauses = [col.sql(col_translate) for col in self.columns]
        # Then add the constraints:
        if self.primary_key:
            qcols = quoted(*[col_translate(c) for c in self.primary_key])
            clauses.append(f'PRIMARY KEY({qcols})')
        for fk, ref, refcols in self.foreign_keys:
            fkcols = quoted(*[col_translate(c) for c in fk])
            rtable = quoted(translate(ref))
            pkcols = quoted(*[translate(ref, c) for c in refcols])
            clauses.append(f'FOREIGN KEY({fkcols}) REFERENCES {rtable}({pkcols}) ON DELETE CASCADE')

        clauses = ',\n    '.join(clauses)
        return '\n'.join([
            f"CREATE TABLE IF NOT EXISTS `{translate(self.name)}` (", f"{clauses}", ")"])


def schema(tg: csvw.TableGroup,
           drop_self_referential_fks: Optional[bool] = True) -> list[TableSpec]:
    """
    Convert the table and column descriptions of a `TableGroup` into specifications for the
    DB schema.

    :param tg: CSVW TableGroup.
    :param drop_self_referential_fks: Flag signaling whether to drop self-referential foreign \
    keys. This may be necessary, if the order of rows in a CSVW table does not guarantee \
    referential integrity when inserted in order (e.g. an eralier row refering to a later one).
    :return: A pair (tables, reference_tables).
    """
    tables = {}
    for table in tg.tabledict.values():
        t = TableSpec.from_table_metadata(
            table, drop_self_referential_fks=drop_self_referential_fks)
        tables[t.name] = t
        for at in t.many_to_many.values():
            tables[at.name] = at

    # We must determine the order in which tables must be created!
    ordered = collections.OrderedDict()
    i = 0

    # We loop through the tables repeatedly, and whenever we find one, which has all
    # referenced tables already in ordered, we move it from tables to ordered.
    while tables and i < 100:
        i += 1
        for table in list(tables.keys()):
            if all((ref[1] in ordered) or ref[1] == table for ref in tables[table].foreign_keys):
                # All referenced tables are already created (or self-referential).
                ordered[table] = tables.pop(table)
                break
    if tables:  # pragma: no cover
        raise ValueError('there seem to be cyclic dependencies between the tables')

    return list(ordered.values())


class Database:
    """
    Represents a SQLite database associated with a :class:`csvw.TableGroup` instance.

    :param tg: `TableGroup` instance defining the schema of the database.
    :param fname: Path to which to write the database file.
    :param translate: Schema object name translator.
    :param drop_self_referential_fks: Flag signaling whether to drop or enforce self-referential \
    foreign-key constraints.

    .. warning::

        We write rows of a table to the database sequentially. Since CSVW does not require ordering
        rows in tables such that self-referential foreign-key constraints are satisfied at each row,
        we don't enforce self-referential foreign-keys by default in order to not trigger "false"
        integrity errors. If data in a CSVW Table is known to be ordered appropriately, `False`
        should be passed as `drop_self_referential_fks` keyword parameter to enforce
        self-referential foreign-keys.
    """
    def __init__(
            self,
            tg: TableGroup,
            fname: Optional[Union[pathlib.Path, str]] = None,
            translate: Optional[SchemaTranslator] = None,
            drop_self_referential_fks: Optional[bool] = True,
    ):
        self.translate = translate or Database.name_translator
        self.fname = pathlib.Path(fname) if fname else None
        self.init_schema(tg, drop_self_referential_fks=drop_self_referential_fks)
        self._connection = None  # For in-memory dbs we need to keep the connection!

    def init_schema(self, tg: TableGroup, drop_self_referential_fks: bool = True):
        """Inititialize the db schema, possibly ignoring self-referential foreign keys."""
        self.tg = tg
        self.tables = schema(
            self.tg, drop_self_referential_fks=drop_self_referential_fks) if self.tg else []

    @property
    def tdict(self) -> dict[str, TableSpec]:  # pylint: disable=C0116
        return {t.name: t for t in self.tables}

    @staticmethod
    def name_translator(table: str, column: Optional[str] = None) -> str:
        """
        A callable with this signature can be passed into DB creation to control the names
        of the schema objects.

        :param table: CSVW name of the table before translation
        :param column: CSVW name of a column of `table` before translation
        :return: Translated table name if `column is None` else translated column name
        """
        # By default, no translation is done:
        return column or table

    def connection(self) -> Union[sqlite3.Connection, contextlib.closing]:
        """DB connection to be used as context manager."""
        if self.fname:
            return contextlib.closing(sqlite3.connect(str(self.fname)))
        if not self._connection:
            self._connection = sqlite3.connect(':memory:')
        return self._connection

    def _qt(self, tname: str, cname: Optional[str] = None) -> str:
        """Translate and then quote a db schema object."""
        if cname:
            return quoted(self.translate(tname, cname))
        return quoted(self.translate(tname))

    def select_many_to_many(self, db, table, context) -> dict[str, Union[tuple[str, str], str]]:
        """Select data from an association table, grouped by first foreign key."""
        if context is not None:
            context_sql = f"WHERE context = '{context}'"
        else:
            context_sql = ''
        qt = functools.partial(self._qt, table.name)
        sql = (f"SELECT {qt(table.columns[0].name)}, "
               f"       group_concat({qt(table.columns[1].name)}, ' '), "
               f"       group_concat(COALESCE(context, ''), '||') "
               f"FROM {qt()} {context_sql} GROUP BY {qt(table.columns[0].name)}")
        cu = db.execute(sql)
        return {
            r[0]: [(k, v) if context is None else k
                   for k, v in zip(r[1].split(), r[2].split('||'))] for r in cu.fetchall()}

    def separator(self, tname: str, cname: str) -> Optional[str]:
        """
        :return: separator for the column specified by db schema names `tname` and `cname`.
        """
        for name in self.tdict:
            if self.translate(name) == tname:
                for col in self.tdict[name].columns:
                    if self.translate(name, col.name) == cname:
                        return col.separator
        return None  # pragma: no cover

    def split_value(self, tname: str, cname: str, value) -> Union[list[str], str, None]:
        """Split a value if a separator is defined for the column."""
        sep = self.separator(tname, cname)
        return (value or '').split(sep) if sep else value

    def read(self) -> dict[str, list[collections.OrderedDict]]:
        """
        :return: A `dict` where keys are SQL table names corresponding to CSVW tables and values \
        are lists of rows, represented as dicts where keys are the SQL column names.
        """
        res = collections.defaultdict(list)
        with self.connection() as conn:
            for tname in self.tg.tabledict:
                #
                # How much do we want to use DB types? Probably as much as possible!
                # Thus we'd need to convert on write **and** read!
                #
                spec = TableReadSpec(self.tdict[tname], tname, self.translate)
                # Retrieve the many-to-many relations:
                for col, at in spec.table.many_to_many.items():
                    for pk, v in self.select_many_to_many(conn, at, col).items():
                        spec.references[pk][self.translate(tname, col)] = v

                cols, rows = select(conn, self.translate(tname))
                for row in rows:
                    res[self.translate(tname)].append(spec.read_row(zip(cols, row)))
        return res

    def association_table_context(self, _, column, fkey):
        """
        Context for association tables is created calling this method.

        Note: If a custom value for the `context` column is created by overwriting this method,
        `select_many_to_many` must be adapted accordingly, to make sure the custom
        context is retrieved when reading the data from the db.

        :param table:
        :param column:
        :param fkey:
        :return: a pair (foreign key, context)
        """
        # The default implementation takes the column name as context:
        return fkey, column

    def write_from_tg(self, _force=False, _exists_ok=False, _skip_extra=False):
        """Write the data from the contained tablegroup to a db."""
        return self.write(
            force=_force,
            _exists_ok=_exists_ok,
            _skip_extra=_skip_extra,
            **self.tg.read())

    def _get_rows(self, t, items, refs, _skip_extra):
        rows, keys = [], []
        cols = {c.name: c for c in t.columns}
        for i, row in enumerate(items):
            pk = row[t.primary_key[0]] if t.primary_key and len(t.primary_key) == 1 else None
            values = []
            for k, v in row.items():
                if k in t.many_to_many:
                    assert pk
                    atkey = tuple([t.many_to_many[k].name] +  # noqa: W504
                                  [c.name for c in t.many_to_many[k].columns])
                    # We distinguish None - meaning NULL - and [] - meaning no items - as
                    # values of list-valued columns.
                    refs[atkey].extend([
                        tuple([pk] + list(self.association_table_context(t, k, vv)))
                        for vv in (v or [])])
                else:
                    if k not in cols:
                        if _skip_extra:
                            continue
                        raise ValueError(f'unspecified column {k} found in data')
                    col = cols[k]
                    if isinstance(v, list):
                        # Note: This assumes list-valued columns are of datatype string!
                        if col.csvw_type == 'string':
                            v = (col.separator or ';').join(
                                col.db_type.convert(vv) or '' for vv in v)
                        else:
                            v = json.dumps(v)
                    else:
                        v = col.db_type.convert(v) if v is not None else None
                    if i == 0:
                        keys.append(col.name)
                    values.append(v)
            rows.append(tuple(values))
        return rows, keys

    def write(self, *, force=False, _exists_ok=False, _skip_extra=False, **items):
        """
        Creates a db file with the core schema.

        :param force: If `True` an existing db file will be overwritten.
        """
        if self.fname and self.fname.exists():
            if not force:
                raise ValueError('db file already exists, use force=True to overwrite')
            self.fname.unlink()

        with self.connection() as db:
            for table in self.tables:
                db.execute(table.sql(translate=self.translate))

            db.execute('PRAGMA foreign_keys = ON;')
            db.commit()

            refs = collections.defaultdict(list)  # collects rows in association tables.
            for t in self.tables:
                if t.name not in items:
                    continue
                rows, keys = self._get_rows(t, items[t.name], refs, _skip_extra)
                insert(db, self.translate, t.name, keys, *rows)

            for atkey, rows in refs.items():
                insert(db, self.translate, atkey[0], atkey[1:], *rows)

            db.commit()


@dataclasses.dataclass
class TableReadSpec:
    """Bundles data informing the reading of table rows."""
    table: TableSpec
    name: str
    translate: SchemaTranslator
    converters: dict[str, tuple[str, Callable]] = dataclasses.field(default_factory=dict)
    separators: dict[str, str] = dataclasses.field(default_factory=dict)
    references: dict = dataclasses.field(default_factory=lambda: collections.defaultdict(dict))

    def __post_init__(self):
        # Assemble the conversion dictionary:
        for col in self.table.columns:
            if col.csvw_type in TYPE_MAP:
                conv = TYPE_MAP[col.csvw_type].convert
            else:
                conv = DATATYPES[col.csvw_type].to_python
            self.converters[self.translate(self.name, col.name)] = (col.name, conv)
            if col.separator:
                if col.csvw_type == 'string':
                    self.separators[self.translate(self.name, col.name)] = col.separator
                else:
                    self.separators[self.translate(self.name, col.name)] = 'json'

    def read_row(self, row: Iterator[tuple[str, Any]]) -> collections.OrderedDict[str, Any]:
        """Read a table according to spec."""
        d = collections.OrderedDict()
        for k, v in row:
            if k in self.separators:
                if v is None:
                    d[k] = None
                elif not v:
                    d[k] = []
                elif self.separators[k] == 'json':
                    d[k] = json.loads(v)
                else:
                    d[k] = [self.converters[k][1](v_) for v_ in (v or '').split(self.separators[k])]
            else:
                d[k] = self.converters[k][1](v) if v is not None else None
        pk = d[self.translate(self.name, self.table.primary_key[0])] \
            if self.table.primary_key and len(self.table.primary_key) == 1 else None
        d.update({k: [] for k in self.table.many_to_many})
        d.update(self.references.get(pk, {}))
        return d
