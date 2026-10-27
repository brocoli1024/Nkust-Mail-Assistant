from datetime import datetime, timezone
import pytest

from app.services.public_source import PublicSourceError, parse_feed, normalize_public_url, fetch_feed


def feed(*items):
    return ('<?xml version="1.0"?><rss version="2.0"><channel>' + ''.join(items) + '</channel></rss>').encode()


def item(title='合成獎學金申請', url='https://osa.nkust.edu.tw/p/404-1.php',
         published='2026-10-27 15:00:00', excerpt='&lt;p&gt;學生申請&lt;/p&gt;'):
    return f'<item><title>{title}</title><link>{url}</link><description>{excerpt}</description><pubDate>{published}</pubDate></item>'


def test_rss_extracts_title_date_link_and_plain_excerpt():
    rows = parse_feed(feed(item()))
    assert len(rows) == 1 and rows.failed == 0
    assert rows[0].title == '合成獎學金申請'
    assert rows[0].url == 'https://osa.nkust.edu.tw/p/404-1.php'
    assert rows[0].excerpt == '學生申請'
    assert rows[0].published_at == datetime(2026, 10, 27, 7, tzinfo=timezone.utc)


@pytest.mark.parametrize('value,want', [('Tue, 27 Oct 2026 10:00:00 +0900', datetime(2026,10,27,1,tzinfo=timezone.utc)),
                                     ('not-a-date', None), ('', None)])
def test_dates_never_substitute_fetch_time(value, want):
    assert parse_feed(feed(item(published=value)))[0].published_at == want


@pytest.mark.parametrize('raw', [b'<html>error</html>', feed(), b'<rss><channel>',
                               b'<!DOCTYPE rss [<!ENTITY secret SYSTEM "file:///private">]><rss>&secret;</rss>',
                               b'x' * (2 * 1024 * 1024 + 1)], ids=['html', 'empty', 'truncated', 'entity', 'oversize'])
def test_malformed_empty_unsafe_or_oversized_feed_is_not_success(raw):
    with pytest.raises(PublicSourceError):
        parse_feed(raw)


def test_invalid_item_is_reported_without_hiding_valid_items():
    rows = parse_feed(feed(item(), item(url='https://evil.invalid/a')))
    assert len(rows) == 1 and rows.failed == 1
    with pytest.raises(PublicSourceError):
        parse_feed(feed(item(url='javascript:alert(1)')))


@pytest.mark.parametrize('url', ['http://osa.nkust.edu.tw/a', 'https://nkust.edu.tw.evil.invalid/a',
                               'https://user:pass@osa.nkust.edu.tw/a', 'https://osa.nkust.edu.tw:444/a',
                               'https://osa.nkust.edu.tw/a\n', 'https://osa.nkust.edu.tw\\@evil.invalid/a'])
def test_original_link_rejects_unsafe_urls(url):
    with pytest.raises(PublicSourceError):
        normalize_public_url(url)


def test_url_normalization_preserves_query_semantics():
    assert normalize_public_url('https://OSA.NKUST.EDU.TW:443/a?b=2&a=1#x') == 'https://osa.nkust.edu.tw/a?b=2&a=1'


def test_text_limits_and_script_removal():
    assert parse_feed(feed(item(excerpt='&lt;script&gt;private()&lt;/script&gt;可讀文字')))[0].excerpt == '可讀文字'
    with pytest.raises(PublicSourceError):
        parse_feed(feed(item(title='a' * 2001)))
    with pytest.raises(PublicSourceError):
        parse_feed(feed(*(item() for _ in range(501))))


def test_fetch_uses_fixed_source_and_accepts_xml_served_as_html():
    def transport(url):
        assert url == 'https://www.nkust.edu.tw/p/503-1000-1001.php'
        return 200, {'content-type': 'text/html; charset=UTF-8'}, feed(item())
    assert len(parse_feed(fetch_feed(transport=transport))) == 1


def test_fetch_does_not_follow_external_redirect():
    with pytest.raises(PublicSourceError, match='PUBLIC_SOURCE_REDIRECT'):
        fetch_feed(transport=lambda _: (302, {'location': 'https://evil.invalid/'}, b''))


def test_downloader_rejects_nonpublic_dns_before_connecting():
    import time
    from app.services.public_source import _download
    def resolve(*args,**kwargs): return [(None,None,None,None,('127.0.0.1',443))]
    with pytest.raises(PublicSourceError,match='PUBLIC_SOURCE_ADDRESS'):
        _download('https://www.nkust.edu.tw/',deadline=time.monotonic()+30,resolver=resolve)


def test_tls_connects_to_validated_ip_with_original_hostname(monkeypatch):
    from app.services.public_source import _PinnedHTTPSConnection
    observed=[]
    class Sock:
        def close(self): pass
    class Context:
        def wrap_socket(self,sock,server_hostname):
            observed.append(server_hostname)
            return sock
    def connect(address,timeout):
        observed.append(address)
        return Sock()
    monkeypatch.setattr('app.services.public_source.socket.create_connection',connect)
    connection=_PinnedHTTPSConnection('www.nkust.edu.tw','140.127.1.1',5)
    connection._context=Context()
    connection.connect()
    assert observed==[('140.127.1.1',443),'www.nkust.edu.tw']
    connection.close()
