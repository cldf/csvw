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
        for rsc in self.json.get('resources', []):
            schema = rsc.get('schema')
            if schema and \
                    rsc.get('profile') == 'tabular-data-resource' and \
                    rsc.get('scheme') == 'file' and \
                    rsc.get('format') == 'csv':
                # Table Schema:
                md.setdefault('tables', [])
                table = dict(
                    url=rsc['path'],
                    tableSchema=dict(columns=[
                        {"name": f['name'], "datatype": f['type']}
                        for f in schema['fields']
                    ]),
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
