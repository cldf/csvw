import json
import warnings
import urllib.parse
import urllib.request

import pytest
import attr

from csvw.metadata import CSVW, get_json


def csvw_tests_url(path):
    return 'http://www.w3.org/2013/csvw/tests/{}'.format(path)


def unorder(o):
    if isinstance(o, dict):
        return {k: unorder(v) for k, v in o.items()}
    if isinstance(o, list):
        return [unorder(i) for i in o]
    return o


@attr.s
class CSWVTest:
    id = attr.ib(converter=lambda s: s.split('#')[-1])
    type = attr.ib()
    name = attr.ib()
    comment = attr.ib()
    approval = attr.ib()
    option = attr.ib(
        converter=lambda d: {k: csvw_tests_url(v) if k == 'metadata' else v for k, v in d.items()})
    action = attr.ib(converter=lambda s: csvw_tests_url(s))
    result = attr.ib(converter=lambda s: csvw_tests_url(s) if s else None, default=None)
    implicit = attr.ib(default=None)
    httpLink = attr.ib(default=None)

    def _run(self):
        #
        # FIXME: also check for expected warnings!
        #
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            if not self.result:
                with pytest.raises(ValueError):
                    ds = CSVW(self.action, md_url=self.option.get('metadata'))
            else:
                ds = CSVW(self.action, md_url=self.option.get('metadata'))
                assert unorder(ds.to_json(minimal=self.option.get('minimal'))) == unorder(get_json(self.result)), \
                    '{}: {}'.format(self.id, self.name)

    def run(self):
        import requests_mock

        if self.httpLink:
            with requests_mock.Mocker(real_http=True) as mock:
                print('---', self.action)
                mock.head(self.action, text='', headers={'Link': self.httpLink})
                self._run()
        else:
            self._run()


def pytest_generate_tests(metafunc):
    if "csvwjsontest" in metafunc.fixturenames:
        with urllib.request.urlopen(csvw_tests_url('manifest-json.jsonld')) as u:
            tests = json.loads(u.read().decode('utf8'))
            metafunc.parametrize("csvwjsontest", [CSWVTest(**t) for t in tests['entries']])
