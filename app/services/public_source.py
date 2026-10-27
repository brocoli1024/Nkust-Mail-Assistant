"""Bounded, read-only NKUST public source adapters. Never fetch original links."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit, urlunsplit, urljoin
from xml.etree.ElementTree import ParseError

from bs4 import BeautifulSoup
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException

SOURCE_KEY = 'nkust-latest'
LISTING_URL = 'https://www.nkust.edu.tw/p/422-1000-1001.php'
FEED_URL = 'https://www.nkust.edu.tw/p/503-1000-1001.php'
MAX_BYTES = 2 * 1024 * 1024
TAIPEI = timezone(timedelta(hours=8))


class PublicSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicEntry:
    title: str
    url: str
    published_at: datetime | None
    excerpt: str = ''
    external_id: str | None = None


class ParsedEntries(list):
    """List interface plus explicit rejected-item count; partial is not success."""
    def __init__(self, entries=(), *, failed=0):
        super().__init__(entries)
        self.failed = failed


def normalize_public_url(value: str) -> str:
    try:
        if not value or len(value) > 4096 or '\\' in value or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError()
        p = urlsplit(value)
        host = p.hostname or ''
        if (p.scheme != 'https' or not (host == 'nkust.edu.tw' or host.endswith('.nkust.edu.tw'))
                or p.username is not None or p.password is not None or p.port not in (None, 443)):
            raise ValueError()
        return urlunsplit(('https', host, p.path or '/', p.query, ''))
    except (ValueError, TypeError):
        raise PublicSourceError('PUBLIC_SOURCE_URL') from None


def plain_text(value):
    soup = BeautifulSoup(value, 'html.parser')
    for tag in soup.select('script,style,iframe,noscript'):
        tag.decompose()
    return ' '.join(soup.get_text(' ', strip=True).split())


def source_date(value):
    if not value:
        return None
    try:
        try:
            result = datetime.fromisoformat(value.strip())
        except ValueError:
            result = parsedate_to_datetime(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=TAIPEI)
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_feed(data: bytes) -> ParsedEntries:
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise PublicSourceError('PUBLIC_SOURCE_SIZE')
    try:
        root = fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError):
        raise PublicSourceError('PUBLIC_SOURCE_XML') from None
    nodes = root.findall('./channel/item') if root.tag == 'rss' else []
    if not nodes or len(nodes) > 500:
        raise PublicSourceError('PUBLIC_SOURCE_ITEMS')
    entries = ParsedEntries()
    for node in nodes:
        try:
            title = (node.findtext('title') or '').strip()
            excerpt = node.findtext('description') or ''
            external = node.findtext('guid')
            if not title or len(title) > 2000 or len(excerpt) > 12000 or (external and len(external) > 4096):
                raise PublicSourceError('PUBLIC_SOURCE_FIELD')
            entries.append(PublicEntry(title, normalize_public_url((node.findtext('link') or '').strip()),
                                       source_date(node.findtext('pubDate')), plain_text(excerpt), external))
        except PublicSourceError:
            entries.failed += 1
    if not entries:
        raise PublicSourceError('PUBLIC_SOURCE_ITEMS')
    return entries


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the validated address, keep TLS SNI/verification on hostname."""
    def __init__(self, host, address, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _download(url, *, deadline, resolver=socket.getaddrinfo, connection_factory=_PinnedHTTPSConnection):
    try:
        host = urlsplit(url).hostname
        records = resolver(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({record[4][0] for record in records})
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise PublicSourceError('PUBLIC_SOURCE_ADDRESS')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PublicSourceError('PUBLIC_SOURCE_TIMEOUT')
        connection = connection_factory(host, addresses[0], min(5, remaining))
        try:
            p = urlsplit(url)
            connection.request('GET', p.path + ('?' + p.query if p.query else ''), headers={
                'User-Agent': 'NKUST-Mail-Assistant/1.0', 'Accept-Encoding': 'identity',
                'Accept': 'application/rss+xml, application/xml, text/xml, text/html'})
            if connection.sock:
                connection.sock.settimeout(max(.01, min(20, deadline - time.monotonic())))
            response = connection.getresponse()
            headers = {k.lower(): v for k, v in response.getheaders()}
            if headers.get('content-encoding', 'identity').lower() != 'identity':
                raise PublicSourceError('PUBLIC_SOURCE_ENCODING')
            body = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PublicSourceError('PUBLIC_SOURCE_TIMEOUT')
                if connection.sock:
                    connection.sock.settimeout(min(20, remaining))
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(body)))
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise PublicSourceError('PUBLIC_SOURCE_SIZE')
                if not chunk:
                    return response.status, headers, bytes(body)
        finally:
            connection.close()
    except PublicSourceError:
        raise
    except Exception:
        raise PublicSourceError('PUBLIC_SOURCE_UNAVAILABLE') from None


def fetch_feed(*, transport=None) -> bytes:
    url = FEED_URL
    deadline = time.monotonic() + 30
    for _ in range(4):
        status, headers, body = (transport(url) if transport else _download(url, deadline=deadline))
        if 300 <= status < 400:
            target = urljoin(url, headers.get('location', ''))
            try:
                valid = normalize_public_url(target) == target and urlsplit(target).hostname == 'www.nkust.edu.tw'
            except PublicSourceError:
                valid = False
            if not valid:
                raise PublicSourceError('PUBLIC_SOURCE_REDIRECT')
            url = target
            continue
        if status != 200:
            raise PublicSourceError('PUBLIC_SOURCE_HTTP')
        if len(body) > MAX_BYTES:
            raise PublicSourceError('PUBLIC_SOURCE_SIZE')
        return body  # known official endpoint serves valid XML as text/html
    raise PublicSourceError('PUBLIC_SOURCE_REDIRECT')
