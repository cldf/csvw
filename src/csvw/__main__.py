import sys
import json
import argparse

from colorama import init, Fore, Style

from csvw import CSVW


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


def csvw2json():  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="""convert CSVW to JSON, see https://w3c.github.io/csvw/csv2json/""")
    parser.add_argument('url', help='URL or local path to CSV or JSON metadata file.')

    args = parser.parse_args()
    csvw = CSVW(args.url)
    print(json.dumps(csvw.to_json(), indent=4))


if __name__ == '__main__':  # pragma: no cover
    sys.exit(csvw2json() or 0)
