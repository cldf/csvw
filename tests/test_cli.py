import os
import json
import shutil
import pathlib
import argparse

import pytest

from csvw.__main__ import csvw2json, csvw2datasette, csvwdescribe, csvwvalidate, csvw2markdown


def relpath(fname):
    return str(pathlib.Path(__file__).parent.joinpath('fixtures', fname).relative_to(os.getcwd()))


@pytest.fixture
def csvname():
    return relpath('csv.txt')


@pytest.fixture
def tsvname():
    return relpath('test.tsv')


@pytest.fixture
def mdname():
    return relpath('csv.txt-metadata.json')


@pytest.fixture
def multitable_mdname():
    return relpath('multitable/metadata.json')


def run(func, **kw):
    return func(argparse.Namespace(**kw), test=True)


def test_csvw2json(csvname, mdname, capsys):
    run(csvw2json, url=csvname)
    out, _ = capsys.readouterr()
    assert json.loads(out)
    run(csvw2json, url=mdname)
    out, _ = capsys.readouterr()
    assert json.loads(out)
    run(csvw2json, url=relpath('no-metadata.csv'))
    out, _ = capsys.readouterr()
    assert json.loads(out)


def test_csvw2markdown(mdname, multitable_mdname, capsys):
    assert run(csvw2markdown, url=mdname) == 0
    out, _ = capsys.readouterr()
    assert 'Described by' in out

    assert run(csvw2markdown, url=multitable_mdname) == 0
    out, _ = capsys.readouterr()
    assert 'References' in out


def test_csvwvalidate(mdname, tmp_path):
    assert run(csvwvalidate, url=mdname) == 0
    p = tmp_path / 'md.json'
    p.write_text(pathlib.Path(mdname).read_text(encoding='utf8').replace('@context', 'context'))
    assert run(csvwvalidate, url=str(p), verbose=True) == 2

    p.write_text(pathlib.Path(mdname).read_text(encoding='utf8').replace('"en"', '1'))
    assert run(csvwvalidate, url=str(p), verbose=True) == 1


def test_csvwdescribe(csvname, tsvname, capsys):
    run(csvwdescribe, csv=[csvname], delimiter=',')
    out, _ = capsys.readouterr()
    assert json.loads(out)

    run(csvwdescribe, csv=[tsvname, csvname], delimiter=None)
    out, _ = capsys.readouterr()
    assert json.loads(out)


def test_csvw2datasette(tmp_path, mdname):
    run(csvw2datasette, url=mdname, outdir=tmp_path)
    assert tmp_path.joinpath('datasette.db').exists()
