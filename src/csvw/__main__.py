import sys
import json
import shutil
import pathlib
import argparse
import subprocess

from colorama import init, Fore, Style

from csvw import CSVW, TableGroup
from csvw.db import Database


def csvwdescribe():  # pragma: no cover
    frictionless = shutil.which('frictionless')
    if not frictionless:
        raise ValueError('The frictionless command must be installed for this functionality!\n'
                         'Run `pip install frictionless` and try again.')
    parser = argparse.ArgumentParser(
        description="Describe a (set of) CSV file(s) with basic CSVW metadata.")
    parser.add_argument('--delimiter', default=None)
    parser.add_argument('csv', nargs='+', help="CSV files to describe as CSVW TableGroup")
    args = parser.parse_args()
    fargs = ['describe', '--json']
    if args.delimiter:
        fargs.extend(['--dialect', '{"delimiter": "%s"}' % args.delimiter])
    onefile = False
    if len(args.csv) == 1 and '*' not in args.csv[0]:
        onefile = True
        # Make sure we infer a tabular-data schema even if the file suffix does not suggest a CSV
        # file.
        fargs.extend(['--format', 'csv'])
    else:
        fargs.extend(['--type', 'package'])

    dp = json.loads(subprocess.check_output([frictionless] + fargs + args.csv))
    if onefile:
        dp = dict(resources=[dp], profile='data-package')

    tg = TableGroup.from_frictionless_datapackage(dp)
    print(json.dumps(tg.asdict(), indent=4))


def csvwvalidate():  # pragma: no cover
    init()
    parser = argparse.ArgumentParser(
        description="Validates CSVW described data according to the "
                    "Model for Tabular Data and Metadata on the Web "
                    "(see https://www.w3.org/TR/tabular-data-model/).\n\n"
                    "Returns 0 on success, 1 on warnings and 2 on error.")
    parser.add_argument('url', help='URL or local path to CSV or JSON metadata file.')
    parser.add_argument('-v', '--verbose', action='store_true', default=False)

    ret = 0
    args = parser.parse_args()
    try:
        csvw = CSVW(args.url, validate=True)
        if csvw.is_valid:
            print(Style.BRIGHT + Fore.GREEN + 'OK')
        else:
            ret = 1
            print(Style.BRIGHT + Fore.RED + 'FAIL')
            if args.verbose:
                for w in csvw.warnings:
                    print(Style.DIM + w.message)
    except ValueError as e:
        ret = 2
        print(Style.BRIGHT + Fore.RED + 'FAIL')
        if args.verbose:
            print(Style.DIM + Fore.BLUE + str(e))
    sys.exit(ret)


def csvw2datasette():  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="""convert CSVW to data for datasette""")
    parser.add_argument('url', help='URL or local path to CSV or JSON metadata file.')

    args = parser.parse_args()
    csvw = CSVW(args.url)
    db = Database(csvw.tablegroup, pathlib.Path('datasette.db'))
    db.write_from_tg()
    md = {}
    for k in ['title', 'description', 'license']:
        if 'dc:{}'.format(k) in csvw.common_props:
            md[k] = csvw.common_props['dc:{}'.format(k)]
    # FIXME: flesh out, see https://docs.datasette.io/en/stable/metadata.html
    pathlib.Path('datasette-metadata.json').write_text(json.dumps(md, indent=4))
    print("""Run
    datasette datasette.db --metadata datasette-metadata.json
and open your browser at
    http://localhost:8001/
to browse the data.
""")


def csvw2json():  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="""convert CSVW to JSON, see https://w3c.github.io/csvw/csv2json/""")
    parser.add_argument('url', help='URL or local path to CSV or JSON metadata file.')

    args = parser.parse_args()
    csvw = CSVW(args.url)
    print(json.dumps(csvw.to_json(), indent=4))


if __name__ == '__main__':  # pragma: no cover
    sys.exit(csvw2json() or 0)
