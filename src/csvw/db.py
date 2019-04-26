"""
SQLite as alternative storage backend for a TableGroup's data.

SQLite support has the following limitations:
- lists as values (as specified via the separator attribute of a Column) are only supported for
  string types.
- regex constraints on strings (as specified via a Datatype's format attribute) are not enforced
  by the database.
"""
from __future__ import unicode_literals
import sqlite3
from contextlib import closing
from collections import OrderedDict, defaultdict
from functools import partial
from decimal import Decimal

import attr

from csvw.datatypes import DATATYPES
from csvw._compat import pathlib


def identity(s):
    return s


TYPE_MAP = {
    'string': (
        'TEXT',
        identity,
        identity),
    'integer': (
        'INTEGER',
        identity,
        identity),
    'boolean': (
        'INTEGER',
        lambda s: s if s is None else int(s),
        lambda s: s if s is None else bool(s)),
    'decimal': (
        'REAL',
        lambda s: s if s is None else float(s),
        lambda s: s if s is None else Decimal(s)),
    'hexBinary': (
        'BLOB',
        identity,
        identity),
}


def quoted(*names):
    return ','.join('`{0}`'.format(name) for name in names)


def insert(db, translate, table, keys, *rows, **kw):
    if rows:
        sql = "INSERT INTO {0} ({1}) VALUES ({2})".format(
            quoted(translate(table)),
            quoted(*[translate(table, k) for k in keys]),
            ','.join(['?' for _ in keys]))
        try:
            db.executemany(sql, rows)
        except:  # noqa: E722 - this is purely for debugging.
            if 'single' not in kw:
                for row in rows:
                    insert(db, translate, table, keys, row, single=True)
            else:
                print(sql)
                print(rows)
                raise


def select(db, table):
    cu = db.execute("SELECT * FROM {0}".format(quoted(table)))
    cols = [d[0] for d in cu.description]
    return cols, list(cu.fetchall())


@attr.s
class ColSpec(object):
    """
    A `ColSpec` captures sufficient information about a `Column` for the DB schema.
    """
    name = attr.ib()
    csvw_type = attr.ib(default='string', converter=lambda s: s if s else 'string')
    separator = attr.ib(default=None)
    db_type = attr.ib(default=None)
    convert = attr.ib(default=None)
    read = attr.ib(default=None)
    required = attr.ib(default=False)
    csvw = attr.ib(default=None)

    def __attrs_post_init__(self):
        if self.csvw_type in TYPE_MAP:
            self.db_type, self.convert, self.read = TYPE_MAP[self.csvw_type]
        else:
            self.db_type = 'TEXT'
            self.convert = DATATYPES[self.csvw_type].to_string
            self.read = DATATYPES[self.csvw_type].to_python
        if self.separator and self.db_type != 'TEXT':
            raise ValueError('list-valued fields are only supported for string types')

    def check(self, translate):
        """
        We try to convert as many data constraints as possible into SQLite CHECK constraints.

        :param translate:
        :return:
        """
        if not self.csvw:
            return
        c, cname = self.csvw, translate(self.name)
        constraints = []
        if (c.minimum is not None) or (c.maximum is not None):
            func = {
                'date': 'date',
                'datetime': 'datetime',
            }.get(self.csvw_type)
            if c.minimum is not None:
                if func:
                    constraints.append("{2}(`{0}`) >= {2}('{1}')".format(cname, c.minimum, func))
                else:
                    constraints.append('`{0}` >= {1}'.format(cname, c.minimum))
            if c.maximum is not None:
                if func:
                    constraints.append("{2}(`{0}`) <= {2}('{1}')".format(cname, c.maximum, func))
                else:
                    constraints.append('`{0}` <= {1}'.format(cname, c.maximum))
        elif any(cc is not None for cc in [c.length, c.minLength, c.maxLength]):
            if c.length:
                constraints.append('length(`{0}`) = {1}'.format(cname, c.length))
            if c.minLength:
                constraints.append('length(`{0}`) >= {1}'.format(cname, c.minLength))
            if c.maxLength:
                constraints.append('length(`{0}`) <= {1}'.format(cname, c.maxLength))
        return ' AND '.join(constraints)

    def sql(self, translate):
        _check = self.check(translate)
        return '`{0}` {1}{2}{3}'.format(
            translate(self.name),
            self.db_type,
            ' NOT NULL' if self.required else '',
            ' CHECK ({0})'.format(_check) if _check else '')


@attr.s
class TableSpec(object):
    """
    A `TableSpec` captures sufficient information about a `Table` for the DB schema.

    Note: We support "light-weight" many-to-many relationships by allowing list-valued foreign key
    columns in CSVW. In the database these columns are turned into an associative table, adding
    the name of the column as value a "context" column. Thus, multiple columns in a table my be
    specified as targets of many-to-many relations with the same table.

    See also https://en.wikipedia.org/wiki/Associative_entity
    """
    name = attr.ib()
    columns = attr.ib(default=attr.Factory(list))
    foreign_keys = attr.ib(default=attr.Factory(list))
    many_to_many = attr.ib(default=attr.Factory(OrderedDict))
    primary_key = attr.ib(default=None)

    @classmethod
    def from_table_metadata(cls, table):
        spec = cls(name=table.local_name, primary_key=table.tableSchema.primaryKey)
        list_valued = {c.header for c in table.tableSchema.columns if c.separator}
        for fk in table.tableSchema.foreignKeys:
            # We only support Foreign Key references between tables!
            if not fk.reference.schemaReference:
                if len(fk.columnReference) == 1 and fk.columnReference[0] in list_valued:
                    # List-valued foreign keys are turned into a many-to-many relation!
                    assert len(fk.reference.columnReference) == 1
                    assert spec.primary_key and len(spec.primary_key) == 1
                    spec.many_to_many[fk.columnReference[0]] = TableSpec.association_table(
                        spec.name,
                        spec.primary_key[0],
                        fk.reference.resource.string,
                        fk.reference.columnReference[0],
                    )
                else:
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
    def association_table(cls, atable, apk, btable, bpk):
        afk = ColSpec('{0}_{1}'.format(atable, apk))
        bfk = ColSpec('{0}_{1}'.format(btable, bpk))
        if afk.name == bfk.name:
            afk.name += '_1'
            bfk.name += '_2'
        return cls(
            name='{0}_{1}'.format(atable, btable),
            columns=[afk, bfk, ColSpec('context')],
            foreign_keys=[
                ([afk.name], atable, [apk]),
                ([bfk.name], btable, [bpk]),
            ]
        )

    def sql(self, translate):
        """
        :param translate:
        :return: The SQL statement to create the table.
        """
        col_translate = partial(translate, self.name)
        clauses = [col.sql(col_translate) for col in self.columns]
        if self.primary_key:
            clauses.append('PRIMARY KEY({0})'.format(quoted(
                *[col_translate(c) for c in self.primary_key])))
        for fk, ref, refcols in self.foreign_keys:
            clauses.append('FOREIGN KEY({0}) REFERENCES {1}({2}) ON DELETE CASCADE'.format(
                quoted(*[col_translate(c) for c in fk]),
                quoted(translate(ref)),
                quoted(*[translate(ref, c) for c in refcols])))
        return "CREATE TABLE IF NOT EXISTS `{0}` (\n    {1}\n)".format(
            translate(self.name), ',\n    '.join(clauses))


def schema(tg):
    """
    Convert the table and column descriptions of a `TableGroup` into specifications for the
    DB schema.

    :param ds:
    :return: A pair (tables, reference_tables).
    """
    tables = {}
    for tname, table in tg.tabledict.items():
        t = TableSpec.from_table_metadata(table)
        tables[t.name] = t
        for at in t.many_to_many.values():
            tables[at.name] = at

    # We must determine the order in which tables must be created!
    ordered = OrderedDict()
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


class Database(object):
    def __init__(self, tg, fname=None, translate=None):
        self.translate = translate or Database.name_translator
        self.fname = pathlib.Path(fname) if fname else None
        self.init_schema(tg)
        self._connection = None  # For in-memory dbs we need to keep the connection!

    def init_schema(self, tg):
        self.tg = tg
        self.tables = schema(self.tg) if self.tg else []

    @property
    def tdict(self):
        return {t.name: t for t in self.tables}

    @staticmethod
    def name_translator(table, column=None):
        """
        A callable with this signature can be passed into DB creation to control the names
        of the schema objects.

        :param table: Name of the table before translation
        :param column: Name of a column of `table` before translation
        :return: Translated table name if `column is None` else translated column name
        """
        # By default, no translation is done:
        return column or table

    def connection(self):
        if self.fname:
            return closing(sqlite3.connect(str(self.fname)))
        if not self._connection:
            self._connection = sqlite3.connect(':memory:')
        return self._connection

    def select_many_to_many(self, db, table, context):
        cu = db.execute(
            "SELECT {0}, group_concat({1}, ' ') FROM {2} WHERE context = '{3}' GROUP BY {0}".format(
                quoted(table.columns[0].name),
                quoted(table.columns[1].name),
                quoted(self.translate(table.name)),
                context))
        return {r[0]: r[1].split() for r in cu.fetchall()}

    def read(self):
        res = defaultdict(list)
        with self.connection() as conn:
            for tname in self.tg.tabledict:
                #
                # FIXME: how much do we want to use DB types? Probably as much as possible!
                # Thus we need tp convert on write **and** read!
                #
                convert, seps, refs = {}, {}, defaultdict(dict)
                table = self.tdict[tname]  # The TableSpec object.

                # Assemble the conversion dictionary:
                for col in table.columns:
                    convert[self.translate(tname, col.name)] = [col.name, identity]
                    if col.csvw_type in TYPE_MAP:
                        convert[self.translate(tname, col.name)][1] = TYPE_MAP[col.csvw_type][2]
                    else:
                        convert[self.translate(tname, col.name)][1] = \
                            DATATYPES[col.csvw_type].to_python
                    if col.separator:
                        seps[self.translate(tname, col.name)] = col.separator

                # Retrieve the many-to-many relations:
                for col, at in table.many_to_many.items():
                    for pk, v in self.select_many_to_many(conn, at, col).items():
                        refs[pk][self.translate(tname, col)] = v

                cols, rows = select(conn, self.translate(tname))
                for row in rows:
                    d = OrderedDict()
                    for k, v in zip(cols, row):
                        if k in seps:
                            if not v:
                                d[k] = []
                            else:
                                d[k] = [convert[k][1](v_) for v_ in (v or '').split(seps[k])]
                        else:
                            d[k] = convert[k][1](v) if v is not None else None
                    pk = d[self.translate(tname, table.primary_key[0])] \
                        if table.primary_key and len(table.primary_key) == 1 else None
                    d.update({k: [] for k in table.many_to_many})
                    d.update(refs.get(pk, {}))
                    res[self.translate(tname)].append(d)
        return res

    def association_table_context(self, table, column, fkey):
        """
        Context for association tables is created calling this method.

        :param table:
        :param column:
        :param fkey:
        :return: a pair (foreign key, context)
        """
        # The default implementation takes the column name as context:
        return fkey, column

    def write_from_tg(self, _force=False, _exists_ok=False):
        return self.write(_force=_force, _exists_ok=_exists_ok, **self.tg.read())

    def write(self, _force=False, _exists_ok=False, **items):
        """
        Creates a db file with the core schema.

        :param force: If `True` an existing db file will be overwritten.
        """
        if self.fname and self.fname.exists():
            raise ValueError('db file already exists, use force=True to overwrite')

        with self.connection() as db:
            for table in self.tables:
                db.execute(table.sql(translate=self.translate))

            db.execute('PRAGMA foreign_keys = ON;')
            db.commit()

            refs = defaultdict(list)  # collects rows in association tables.
            for t in self.tables:
                if t.name not in items:
                    continue
                rows, keys = [], []
                cols = {c.name: c for c in t.columns}
                for i, row in enumerate(items[t.name]):
                    pk = row[t.primary_key[0]] \
                        if t.primary_key and len(t.primary_key) == 1 else None
                    values = []
                    for k, v in row.items():
                        if k in t.many_to_many:
                            assert pk
                            at = t.many_to_many[k]
                            atkey = tuple([at.name] + [c.name for c in at.columns])
                            for vv in v:
                                fkey, context = self.association_table_context(t, k, vv)
                                refs[atkey].append((pk, fkey, context))
                        else:
                            col = cols[k]
                            if isinstance(v, list):
                                # Note: This assumes list-valued columns are of datatype string!
                                v = (col.separator or ';').join(
                                    col.convert(vv) for vv in v)
                            else:
                                v = col.convert(v) if v is not None else None
                            if i == 0:
                                keys.append(col.name)
                            values.append(v)
                    rows.append(tuple(values))
                insert(db, self.translate, t.name, keys, *rows)

            for atkey, rows in refs.items():
                insert(db, self.translate, atkey[0], atkey[1:], *rows)

            db.commit()
