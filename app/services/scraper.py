"""One approved public URL per request. No login, browser automation or link crawling."""
import ipaddress
import socket
import time
import re
from urllib.parse import urlsplit, urljoin

from bs4 import BeautifulSoup


class ScrapeError(RuntimeError):
    pass


def validate_url(url, allowed_hosts, resolver=socket.getaddrinfo):
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if (parts.scheme != 'https' or host not in allowed_hosts or parts.username or parts.password
                or parts.port not in (None, 443) or parts.fragment or '\\' in url
                or any(ord(c) < 33 for c in url)):
            raise ScrapeError('SCRAPE_URL_BLOCKED')
        records = resolver(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({r[4][0] for r in records})
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise ScrapeError('SCRAPE_ADDRESS_BLOCKED')
        return host, addresses
    except (ValueError, TypeError):
        raise ScrapeError('SCRAPE_URL_BLOCKED') from None
    except OSError:
        raise ScrapeError('SCRAPE_DNS_FAILED') from None


def extract_text(html):
    mailview = False
    soup = BeautifulSoup(html, 'html.parser', from_encoding='utf-8' if isinstance(html, bytes) else None)
    if soup.select_one('input[type="password"]'):
        raise ScrapeError('SCRAPE_LOGIN_REQUIRED')
    for element in soup.select('script, style, nav, header, footer, noscript, iframe, form, [hidden], [aria-hidden="true"]'):
        element.decompose()
    for element in soup.select('[style]'):
        style = element.get('style', '').replace(' ', '').lower()
        if 'display:none' in style or 'visibility:hidden' in style:
            element.decompose()
    # Prefer known content containers; never treat an arbitrary login/error page as an announcement.
    root = soup.select_one('.mail-content, .mail-body, .ck-content, .mcont, article, main, [role="main"]')
    if root is None and soup.title and '高雄科技大學' in soup.title.get_text():
        candidate = soup.select_one('body > div')
        labels = re.sub(r'\s+', '', candidate.get_text() if candidate else '')
        if '主旨：' in labels and '說明：' in labels:
            root = candidate
            mailview = True
            for link in root.select('a[href*="mail.google.com/mail/"]'):
                link.decompose()
    if root is None:
        raise ScrapeError('SCRAPE_CONTENT_NOT_FOUND')
    text = '\n'.join(line.strip() for line in root.get_text('\n').splitlines() if line.strip())
    if mailview:
        # Remove document metadata (especially the issue date) before the announcement subject.
        subject = re.search(r'主\s*旨[：:]', text)
        text = text[subject.start():] if subject else text
    if len(text) < 30:
        raise ScrapeError('SCRAPE_CONTENT_TOO_SHORT')
    if len(text) > 12000:
        raise ScrapeError('SCRAPE_CONTENT_TOO_LONG')
    return text


class Scraper:
    def __init__(self, settings, *, fetch=None, resolver=socket.getaddrinfo, sleep=time.sleep):
        self.allowed_hosts = settings.scrape_allowed_hosts
        self.fetch = fetch or self._fetch
        self.resolver, self.sleep = resolver, sleep

    @staticmethod
    def _fetch(url, host, addresses):
        from curl_cffi import CurlOpt
        from scrapling.fetchers import FetcherSession
        # Pin the public DNS answer to prevent a second lookup from reaching a private address.
        addresses = ','.join('[' + a + ']' if ':' in a else a for a in addresses)
        with FetcherSession(impersonate=None, stealthy_headers=False) as session:
            # Scrapling 0.4.15 does not expose curl session options publicly.
            # Keep this adapter covered by a transport test when upgrading Scrapling.
            session._curl_session.curl_options.update({
                CurlOpt.RESOLVE: [f'{host}:443:{addresses}'],
                CurlOpt.PROXY: '', CurlOpt.MAXFILESIZE_LARGE: 2_000_000,
            })
            session._curl_session.trust_env = False
            return session.get(url, timeout=20, retries=1, follow_redirects=False,
                               stealthy_headers=False, impersonate=None, verify=True,
                               headers={'User-Agent': 'NKUST-Mail-Assistant/1.0', 'Accept': 'text/html'},
                               max_recv_speed=250000)

    def scrape(self, url):
        return self._scrape(url, 0)

    def _scrape(self, url, redirects):
        host, addresses = validate_url(url, self.allowed_hosts, self.resolver)
        for attempt in range(2):
            try:
                page = self.fetch(url, host, addresses)
            except Exception as exc:
                if getattr(exc, 'code', None) == 60:
                    raise ScrapeError('SCRAPE_TLS_ERROR') from None
                if not attempt:
                    self.sleep(1)
                    continue
                raise ScrapeError('SCRAPE_CONNECTION_FAILED') from None
            if page.status in (429, 502, 503, 504) and not attempt:
                self.sleep(1)
                continue
            if 300 <= page.status < 400:
                location = next((str(v) for k, v in page.headers.items() if str(k).lower() == 'location'), None)
                if redirects >= 3 or not location:
                    raise ScrapeError('SCRAPE_REDIRECT_BLOCKED')
                return self._scrape(urljoin(url, location), redirects + 1)
            if page.status in (401, 403):
                raise ScrapeError('SCRAPE_ACCESS_DENIED')
            if page.status != 200:
                raise ScrapeError('SCRAPE_HTTP_ERROR')
            headers = {str(k).lower(): str(v).lower() for k, v in page.headers.items()}
            if 'text/html' not in headers.get('content-type', ''):
                raise ScrapeError('SCRAPE_HTML_REQUIRED')
            if len(page.body) > 2_000_000:
                raise ScrapeError('SCRAPE_PAGE_TOO_LARGE')
            text = extract_text(page.body)
            self.last_url = url
            return text
