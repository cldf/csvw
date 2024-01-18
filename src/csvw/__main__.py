import sys
import json
import shutil
import pathlib
import argparse
import subprocess

from colorama import init, Fore, Style

from csvw import CSVW, TableGroup
from csvw.db import Database


def parsed_args(desc, args, *argspecs):
    if args is None:  # pragma: no cover
        parser = argparse.ArgumentParser(description=desc)
        for kw, kwargs in argspecs:
            parser.add_argument(*kw, **kwargs)
        return parser.parse_args()
    return args


def exit(ret, test=False):
    if test:
        return ret
    sys.exit(ret)  # pragma: no cover


def csvwdescribe(args=None, test=False):
    frictionless = shutil.which('frictionless')
    if not frictionless:  # pragma: no cover
        raise ValueError('The frictionless command must be installed for this functionality!\n'
                         'Run `pip install frictionless` and try again.')

    args = parsed_args(
        "Describe a (set of) CSV file(s) with basic CSVW metadata.",
        args,
        (['--delimiter'], dict(default=None)),
        (['csv'], dict(nargs='+', help="CSV files to describe as CSVW TableGroup")),
    )
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
    return exit(0, test=test)


def csvwvalidate(args=None, test=False):
    init()
    args = parsed_args(
        "Validate a (set of) CSV file(s) described by CSVW metadata.",
        args,
        (['url'], dict(help='URL or local path to CSV or JSON metadata file.')),
        (['-v', '--verbose'], dict(action='store_true', default=False)),
    )
    ret = 0
    try:
        csvw = CSVW(args.url, validate=True)
        if csvw.is_valid:
            print(Style.BRIGHT + Fore.GREEN + 'OK')
        else:
            ret = 1
            print(Style.BRIGHT + Fore.RED + 'FAIL')
            if args.verbose:
                for w in csvw.warnings:
                    print(Style.DIM + str(w.message))
    except ValueError as e:
        ret = 2
        print(Style.BRIGHT + Fore.RED + 'FAIL')
        if args.verbose:
            print(Style.DIM + Fore.BLUE + str(e))
    return exit(ret, test=test)


def csvw2datasette(args=None, test=False):
    args = parsed_args(
        "Convert CSVW to data for datasette (https://datasette.io/).",
        args,
        (['url'], dict(help='URL or local path to CSV or JSON metadata file.')),
        (['-o', '--outdir'], dict(type=pathlib.Path, default=pathlib.Path('.'))),
    )
    dbname, mdname = 'datasette.db', 'datasette-metadata.json'
    csvw = CSVW(args.url)
    db = Database(csvw.tablegroup, fname=args.outdir / dbname)
    db.write_from_tg()
    md = {}
    for k in ['title', 'description', 'license']:
        if 'dc:{}'.format(k) in csvw.common_props:
            md[k] = csvw.common_props['dc:{}'.format(k)]
    # FIXME: flesh out, see https://docs.datasette.io/en/stable/metadata.html
    args.outdir.joinpath(mdname).write_text(json.dumps(md, indent=4))
    print("""Run
    datasette {} --metadata {}
and open your browser at
    http://localhost:8001/
to browse the data.
""".format(args.outdir / dbname, args.outdir / mdname))
    return exit(0, test=test)


def csvw2json(args=None, test=False):
    args = parsed_args(
        "Convert CSVW to JSON, see https://w3c.github.io/csvw/csv2json/",
        args,
        (['url'], dict(help='URL or local path to CSV or JSON metadata file.')),
    )
    csvw = CSVW(args.url)
    print(json.dumps(csvw.to_json(), indent=4))
    return exit(0, test=test)


if __name__ == '__main__':  # pragma: no cover
    csvw2json()
