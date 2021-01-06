"""
Functionality to convert tabular data in Frictionless Data Packages to CSVW.

We translate [table schemas](https://specs.frictionlessdata.io/table-schema/) defined
for [data resources](https://specs.frictionlessdata.io/data-resource/) in a
[data package](https://specs.frictionlessdata.io/data-package/) to a CVSW TableGroup.

This functionality can be used together with the `frictionless describe` command to add
CSVW metadata to "raw" CSV tables.
"""
import json
import pathlib
import urllib.parse


def convert_column_spec(spec):
    """
    https://specs.frictionlessdata.io/table-schema/#field-descriptors

    :param spec:
    :return:
    """
    # name, title, description, type, format
    # type string -> format: default, email, uri, binary (base64), uuid
    # type number -> additional props decimalChar, groupChar, bareNumber
    # format: integer -> add. props: bareNumber
    # format: boolean -> add. props: trueValues, falseValues
    # format: object / arrays, JSON
    # format: date
    # time
    # datetime
    # year
    # yearmonth
    # duration
    # geopoint
    # geojson

    # rdfType -> propertyUrl

    # constraints: required, unique, minLength, maxLength, minimum, maximum, pattern, enum
    from csvw import Column

    name, titles = spec['name'], [spec.get('title')]
    try:
        Column(name=name)
    except ValueError:
        titles.append(name)
        name = urllib.parse.quote(name)
        Column(name=name)

    titles = [t for t in titles if t]

    res = dict(name=name)
    if ('type' in spec) and spec['type'] in [
        'string', 'number', 'integer', 'boolean', 'date', 'time'
    ]:
        res['datatype'] = spec['type']
    if titles:
        res['titles'] = titles
    if 'description' in spec:
        res['dc:description'] = [spec['description']]
    return res


def convert_foreignKey(rsc_name, fk, resource_map):
    """
    https://specs.frictionlessdata.io/table-schema/#foreign-keys
    """
    # Rename "fields" to "columnReference" and map resource name to url (resolving self-referential
    # foreign keys).
    return dict(
        columnReference=fk['fields'],
        reference=dict(
            columnReference=fk['reference']['fields'],
            resource=resource_map[fk['reference']['resource'] or rsc_name],
        )
    )


def convert_table_schema(rsc_name, schema, resource_map):
    """
    :param rsc_name: `name` property of the resource the schema belongs to. Needed to resolve \
    self-referential foreign keys.
    :param schema: `dict` parsed from JSON representing a frictionless Table Schema object.
    :param resource_map: `dict` mapping resource names to resource paths, needed to convert foreign\
    key constraints.
    :return: `dict` suitable for instantiating a `csvw.metadata.Schema` object.
    """
    res = dict(
        columns=[convert_column_spec(f) for f in schema['fields']],
    )
    for prop in [
        ('missingValues', 'null'),
        'primaryKey',
        'foreignKeys',
    ]:
        if isinstance(prop, tuple):
            prop, toprop = prop
        else:
            toprop = prop
        if prop in schema:
            res[toprop] = schema[prop]
            if prop == 'foreignKeys':
                res[toprop] = [convert_foreignKey(fk, rsc_name, resource_map) for fk in res[toprop]]
    return res


class DataPackage:
    def __init__(self, spec, directory=None):
        if isinstance(spec, dict):
            # already a parsed JSON object
            self.dir = pathlib.Path(directory or '.')
        elif isinstance(spec, pathlib.Path):
            self.dir = directory or spec.parent
            spec = json.loads(spec.read_text(encoding='utf8'))
        else:  # assume a JSON formatted string
            spec = json.loads(spec)
            self.dir = pathlib.Path(directory or '.')

        self.json = spec

    def to_tablegroup(self, cls=None):
        from csvw import TableGroup

        md = {}
        # Package metadata:
        md['dc:source'] = json.dumps(self.json)

        # Data Resource metadata:
        resources = [rsc for rsc in self.json.get('resources', []) if 'path' in rsc]
        resource_map = {rsc['name']: rsc['path'] for rsc in resources}
        for rsc in resources:
            schema = rsc.get('schema')
            if schema and \
                    rsc.get('profile') == 'tabular-data-resource' and \
                    rsc.get('scheme') == 'file' and \
                    rsc.get('format') == 'csv':
                # Table Schema:
                md.setdefault('tables', [])
                table = dict(
                    url=rsc['path'],
                    tableSchema=convert_table_schema(rsc['name'], schema, resource_map),
                    dialect=dict(),
                )
                if rsc.get('dialect', {}).get('delimiter'):
                    table['dialect']['delimiter'] = rsc['dialect']['delimiter']
                if rsc.get('encoding'):
                    table['dialect']['encoding'] = rsc['encoding']
                md['tables'].append(table)

        cls = cls or TableGroup
        res = cls.fromvalue(md)
        res._fname = self.dir / 'csvw-metadata.json'
        return res
