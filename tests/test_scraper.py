from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.services.scraper import Scraper, ScrapeError, extract_text, validate_url

URL = 'https://officemail.nkust.edu.tw/Mail/View/1'
HTML = (Path(__file__).parent / 'fixtures/nkust_announcement_sample.html').read_bytes()


def resolver(*args, **kwargs):
    return [(2, 1, 6, '', ('140.127.1.1', 443))]


def page(status=200, content=HTML, mime='text/html'):
    return SimpleNamespace(status=status, body=content, headers={'Content-Type': mime})


def test_clean_content():
    text = extract_text(HTML)
    assert '115年10月08日' in text
    assert all(s not in text for s in ['登入', 'ignore', '隱藏文字', '頁尾'])


@pytest.mark.parametrize('url', ['http://officemail.nkust.edu.tw/', 'https://evil.example/',
    'https://officemail.nkust.edu.tw.evil.example/', 'https://user:pass@officemail.nkust.edu.tw/',
    'https://officemail.nkust.edu.tw:8000/', 'file:///etc/passwd', 'https://127.0.0.1/'])
def test_invalid_url(url):
    with pytest.raises(ScrapeError, match='URL_BLOCKED'):
        validate_url(url, Settings().scrape_allowed_hosts, resolver)


def test_private_dns_blocked_before_fetch():
    fetch = Mock()
    scrape = Scraper(Settings(), fetch=fetch, resolver=lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))])
    with pytest.raises(ScrapeError, match='ADDRESS_BLOCKED'):
        scrape.scrape(URL)
    fetch.assert_not_called()


def test_retry_is_bounded_and_redirect_is_not_followed():
    fetch = Mock(side_effect=[page(503), page()])
    scraper = Scraper(Settings(), fetch=fetch, resolver=resolver, sleep=lambda _: None)
    assert '校園測試活動' in scraper.scrape(URL)
    assert fetch.call_count == 2
    fetch.reset_mock(side_effect=True)
    fetch.return_value = page(302)
    with pytest.raises(ScrapeError, match='REDIRECT_BLOCKED'):
        scraper.scrape(URL)
    assert fetch.call_count == 1


def test_network_failure_sanitized():
    fetch = Mock(side_effect=RuntimeError('sensitive transport text'))
    with pytest.raises(ScrapeError, match='^SCRAPE_CONNECTION_FAILED$'):
        Scraper(Settings(), fetch=fetch, resolver=resolver, sleep=lambda _: None).scrape(URL)
    assert fetch.call_count == 2


def test_redirect_destination_is_validated():
    redirect = page(302)
    redirect.headers['Location'] = 'https://127.0.0.1/private'
    fetch = Mock(return_value=redirect)
    with pytest.raises(ScrapeError, match='URL_BLOCKED'):
        Scraper(Settings(), fetch=fetch, resolver=resolver).scrape(URL)
    assert fetch.call_count == 1
    redirect.headers['Location'] = '/Mail/MailView/1'
    fetch = Mock(side_effect=[redirect, page()])
    scraper = Scraper(Settings(), fetch=fetch, resolver=resolver)
    assert '校園測試活動' in scraper.scrape(URL)
    assert scraper.last_url.endswith('/Mail/MailView/1')


def test_real_transport_configuration_without_network():
    from unittest.mock import patch
    from curl_cffi import CurlOpt
    with patch('curl_cffi.requests.Session.request', autospec=True) as request, \
         patch('scrapling.engines.static.ResponseFactory.from_http_request', return_value=page()):
        Scraper._fetch(URL, 'officemail.nkust.edu.tw', ['140.127.1.1'])
        session = request.call_args.args[0]
        assert session.curl_options[CurlOpt.RESOLVE] == ['officemail.nkust.edu.tw:443:140.127.1.1']
        assert session.curl_options[CurlOpt.PROXY] == ''
        assert request.call_args.kwargs['verify'] is True
        assert request.call_args.kwargs['allow_redirects'] is False


def test_nkust_mailview_template():
    html = '<html><head><title>國立高雄科技大學 測試通知</title></head><body><div><p>主 旨：測試公告</p><p>說 明：</p><p>歡迎同學參與本次測試活動，報名至115年10月08日截止。</p><a href="https://mail.google.com/mail/">轉寄</a></div></body></html>'
    text = extract_text(html.encode())
    assert '轉寄' not in text and '115年10月08日' in text


def test_mailview_issue_date_is_not_event_date():
    from datetime import datetime
    from app.services.date_parser import parse_dates
    html = '<title>國立高雄科技大學 測試</title><body><div>日期：民國115年9月18日<p>主旨：校園座談會</p><p>說明：</p><p>校園座談會</p><p>日期：115年10月7日</p><p>登記截止日:115年10月2日</p></div></body>'
    text = extract_text(html)
    assert '115年9月18日' not in text
    dates = parse_dates(text, datetime(2026, 9, 21))
    assert dates.event_date == '2026-10-07'
    assert dates.deadline == '2026-10-02'


@pytest.mark.parametrize('response,error', [(page(mime='application/pdf'), 'HTML_REQUIRED'),
    (page(content=b'x'*2_000_001), 'PAGE_TOO_LARGE'), (page(403), 'ACCESS_DENIED'),
    (page(content=b'<main><input type="password"></main>'), 'LOGIN_REQUIRED'),
    (page(content=b'<div>unknown</div>'), 'CONTENT_NOT_FOUND'),
    (page(content=b'<main>short</main>'), 'CONTENT_TOO_SHORT')])
def test_unusable_pages_fail_explicitly(response, error):
    with pytest.raises(ScrapeError, match=error):
        Scraper(Settings(), fetch=lambda *args: response, resolver=resolver).scrape(URL)
