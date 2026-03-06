import json
import pathlib
import warnings
import contextlib
import dataclasses
import urllib.parse
import urllib.request
from typing import Optional, Literal

import pytest

from csvw.metadata import CSVW
from csvw.utils import get_json, LinkHeader, GetResponse


def pytest_addoption(parser):
    parser.addoption("--number", type=int, help="csvw json test number", default=None)


def csvw_tests_url(path) -> str:
    return f'http://www.w3.org/2013/csvw/tests/{path}'


def csvw_tests_path(path) -> pathlib.Path:
    return pathlib.Path(__file__).parent / 'fixtures' / 'csvw' / 'tests' / path


def unorder(o):
    if isinstance(o, dict):
        return {k: unorder(v) for k, v in o.items()}
    if isinstance(o, list):
        return [unorder(i) for i in o]
    return o


@dataclasses.dataclass
class CSWVTest:
    id: str
    type: Literal[
        'csvt:NegativeJsonTest',
        'csvt:ToJsonTest',
        'csvt:ToJsonTestWithWarnings',
        'csvt:PositiveValidationTest',
        'csvt:NegativeValidationTest',
        'csvt:WarningValidationTest']
    name: str
    comment: str
    approval: str
    option: dict
    action: str
    result: Optional[str] = None
    implicit: str = None
    httpLink: str = None
    contentType: str = None

    def __post_init__(self):
        self.id = self.id.split('#')[-1]
        self.option = {
            k: csvw_tests_url(v) if k == 'metadata' else v for k, v in self.option.items()}
        self.action = csvw_tests_url(self.action)
        self.result = csvw_tests_url(self.result) if self.result else None

    @property
    def is_json_test(self):
        return 'Json' in self.type

    @property
    def is_validation_test(self):
        return 'Validation' in self.type

    @property
    def number(self):  # pragma: no cover
        return int(self.id.replace('test', ''))

    def request_head(self, _):
        if self.contentType:
            return self.contentType, []
        if self.httpLink:
            return '', [LinkHeader.from_string(self.httpLink)]
        return '', []

    @staticmethod
    def request_get(url):
        url = urllib.parse.urlparse(url)
        if url.netloc == 'www.w3.org':
            if url.path.startswith('/2013/csvw/tests/'):
                p = csvw_tests_path(url.path.replace('/2013/csvw/tests/', ''))
                if p.exists():
                    return GetResponse(content=p.read_bytes())
            elif url.path == '/.well-known/csvm':
                return GetResponse(
                    text="""{+url}-metadata.json
    csv-metadata.json
    {+url}.json
    csvm.json
    """)
            return GetResponse(status_code=404)
        raise ValueError(url)  # pragma: no cover

    def _run(self):
        with contextlib.ExitStack() as stack:
            if self.type == "csvt:ToJsonTestWithWarnings":
                stack.enter_context(pytest.warns(UserWarning))
            elif self.type == "csvt:ToJsonTest":
                stack.enter_context(warnings.catch_warnings())
                warnings.simplefilter('error')
            elif self.type == "csvt:NegativeJsonTest":
                stack.enter_context(warnings.catch_warnings())
                warnings.simplefilter('ignore')
                stack.enter_context(pytest.raises(ValueError))

            elif self.type == "csvt:PositiveValidationTest":
                # Turn warnings into exceptions!
                stack.enter_context(warnings.catch_warnings())
                warnings.simplefilter('error')
            elif self.type == "csvt:NegativeValidationTest":
                # Warnings count as negative validatio, too!
                stack.enter_context(pytest.raises(ValueError))
                #stack.enter_context(warnings.catch_warnings())
                #warnings.simplefilter('error')
            elif self.type == "csvt:WarningValidationTest":
                stack.enter_context(pytest.warns(UserWarning))

            ds = CSVW(
                self.action, md_url=self.option.get('metadata'), validate=self.is_validation_test)
            if self.is_validation_test:
                if self.type == 'csvt:PositiveValidationTest':
                    assert ds.is_valid
                elif self.type == 'csvt:WarningValidationTest':
                    if not ds.is_valid:
                        warnings.warn('invalid')
                else:
                    if not ds.is_valid:
                        raise ValueError('invalid')

            elif self.is_json_test:
                assert unorder(ds.to_json(minimal=self.option.get('minimal'))) == \
                       unorder(get_json(self.result)), \
                    '{}: {}'.format(self.id, self.name)

    def run(self, mocker):
        mocker.patch('csvw.metadata.utils.request_head', self.request_head)
        mocker.patch('csvw.metadata.utils.request_get', self.request_get)
        mocker.patch('csvw.utils.request_get', self.request_get)
        self._run()


def pytest_generate_tests(metafunc):
    if "csvwjsontest" in metafunc.fixturenames:
        xfail = {
            193: "Why do we have to format durations with particular comps, e.g. PT130M and not "
                 "PT2H10M?",
        }
        number = metafunc.config.getoption("number")
        tests = json.loads(csvw_tests_path('manifest-json.jsonld').read_text(encoding='utf8'))
        metafunc.parametrize(
            "csvwjsontest",
            [pytest.param(test, marks=pytest.mark.xfail) if test.number in xfail else test
             for test in [CSWVTest(**t) for t in tests['entries']]
             if number is None or number == test.number])

    if "csvwnonnormtest" in metafunc.fixturenames:
        xfail = {
            20: "Don't understand the test.",
            21: "Don't understand the test. If not trimming makes reading the data impossible, "
                "where's the point?",
            22: "Don't understand the test.",
            24: "Hm.",
            56: "Dunno, I'm skipping initial space, but it fails?",
            57: "Again, the trimming seems to not be expected?",
            58: "Again, the trimming seems to not be expected?",
            59: "Again, the trimming seems to not be expected?",
        }
        tests = json.loads(csvw_tests_path('manifest-nonnorm.jsonld').read_text(encoding='utf8'))
        metafunc.parametrize(
            "csvwnonnormtest",
            [pytest.param(test, marks=pytest.mark.xfail) if test.number in xfail else test
             for test in [CSWVTest(**t) for t in tests['entries']] if 'Json' in test.type])

    if "csvwvalidationtest" in metafunc.fixturenames:
        xfail = {
            92: "Can't detect malformed JSON if we don't know whether we are fed a metadata or a "
                "CSV file to begin with!",
            124: "Hm. Didn't we have this as ToJson test with warnings?",
        }
        number = metafunc.config.getoption("number")
        tests = json.loads(csvw_tests_path('manifest-validation.jsonld').read_text(encoding='utf8'))
        metafunc.parametrize(
            "csvwvalidationtest",
            [pytest.param(test, marks=pytest.mark.xfail) if test.number in xfail else test
             for test in [CSWVTest(**t) for t in tests['entries']]
             if number is None or number == test.number])
