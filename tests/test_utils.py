import contextlib

import pytest

from csvw import utils


@pytest.mark.parametrize(
    's,check',
    [
        ('<url>', lambda lh: lh.params == {} and lh.url == 'url'),
        ('<url>; p=5', lambda lh: lh.params['p'] == '5'),
    ]
)
def test_LinkHeader(s, check):
    assert check(utils.LinkHeader.from_string(s))


def test_LinkHeader_mult():
    res = list(utils.LinkHeader.iter_links('<url1>, <url2>'))
    assert len(res) == 2
    assert res[0].url == 'url1' and res[1].url == 'url2'


def test_request_get(mocker):
    @contextlib.contextmanager
    def urlopen(url, **_):
        yield mocker.Mock(
            read=lambda: '"äöü"'.encode('latin1'),
            status=201,
            headers=mocker.Mock(get_content_charset=lambda: 'latin1')
        )

    mocker.patch('csvw.utils.urllib.request.urlopen', urlopen)
    res = utils.request_get('url')
    assert res.text == '"äöü"'
    assert res.json() == "äöü"


def test_request_head(mocker):
    class HTTPMessage:
        @staticmethod
        def info():
            return mocker.Mock(
                get_all=lambda _: ['<a>', '<b>'],
                get_content_type=lambda: 'text/html')

    @contextlib.contextmanager
    def urlopen(url, **_):
        yield HTTPMessage()

    mocker.patch('csvw.utils.urllib.request.Request', mocker.Mock())
    mocker.patch('csvw.utils.urllib.request.urlopen', urlopen)
    content_type, links = utils.request_head('url')
    assert content_type == 'text/html'
    assert len(links) == 2


def test_normalize_name():
    assert utils.normalize_name('') == '_'
    assert utils.normalize_name('0') == '_0'


def test_slug():
    assert utils.slug('ABC') == 'abc'
