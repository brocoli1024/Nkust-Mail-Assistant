"""NKUST table parser. Unknown layouts fail explicitly instead of losing mail."""
import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from app.services.date_parser import DateEvidence, parse_dates
from app.services.email_parser import DecodedEmail

HEADERS = ('寄件單位', '郵件性質', '主旨')
TAIPEI = timezone(timedelta(hours=8))


class AnnouncementParseError(ValueError):
    pass


@dataclass
class Announcement:
    department: str
    source_category: str
    title: str
    original_text: str
    source_index: int
    source_fingerprint: str
    event_date: str | None
    deadline: str | None
    date_evidence: list[DateEvidence]
    url: str | None = None
    original_html: str | None = None


@dataclass
class ParseResult:
    announcements: list[Announcement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _normalized(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def source_fingerprint(department: str, source_category: str, title: str) -> str:
    """v1: SHA-256 of a UTF-8 JSON array of NFKC/whitespace-normalized fields."""
    canonical = json.dumps([_normalized(v) for v in (department, source_category, title)],
                           ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _original_text(tag) -> str:
    clone = deepcopy(tag)
    for br in clone.find_all('br'):
        br.replace_with('\n')
    return clone.get_text(separator='', strip=False)


def _append(result, values, original_text, received_at, *, url=None, original_html=None):
    department, category, title = (_normalized(values[key]) for key in HEADERS)
    if not all((department, category, title)):
        raise AnnouncementParseError('ANNOUNCEMENT_EMPTY_FIELD: required field is empty')
    dates = parse_dates(values['主旨'], received_at)
    index = len(result.announcements)
    result.announcements.append(Announcement(
        department, category, title, original_text, index,
        source_fingerprint(department, category, title), dates.event_date,
        dates.deadline, dates.evidence, url, original_html,
    ))
    result.warnings.extend(f'announcement[{index}]: {warning}' for warning in dates.warnings)


def _html(html: str, received_at) -> ParseResult:
    soup = BeautifulSoup(html, 'html.parser')
    result = ParseResult()
    matched_tables = 0
    for table in soup.find_all('table'):
        mapping = None
        for row in table.find_all('tr'):
            if row.find_parent('table') is not table:
                continue
            cells = row.find_all(['td', 'th'], recursive=False)
            labels = [re.sub(r'[\s:：]', '', cell.get_text()) for cell in cells]
            if all(label in labels for label in HEADERS):
                if any(labels.count(label) != 1 for label in HEADERS):
                    raise AnnouncementParseError('TABLE_DUPLICATE_HEADER: ambiguous column names')
                if mapping is None:
                    matched_tables += 1
                mapping = {label: labels.index(label) for label in HEADERS}
                continue
            if mapping is None or not any(cell.get_text().strip() for cell in cells):
                continue
            if any(cell.get('rowspan', '1') != '1' or cell.get('colspan', '1') != '1' for cell in cells):
                raise AnnouncementParseError('TABLE_SPAN_UNSUPPORTED: merged data cells need a parser update')
            if not cells or max(mapping.values()) >= len(cells):
                raise AnnouncementParseError('TABLE_ROW_INVALID: announcement row is missing columns')
            values = {label: _original_text(cells[index]) for label, index in mapping.items()}
            links = cells[mapping['主旨']].find_all('a', href=True)
            url = next((a['href'] for a in links if _http_url(a['href'])), None)
            _append(result, values, '\n'.join(_original_text(c) for c in cells), received_at,
                    url=url, original_html=str(row))
    if not matched_tables:
        raise AnnouncementParseError('TABLE_NOT_FOUND: expected headers 寄件單位 / 郵件性質 / 主旨')
    if not result.announcements:
        raise AnnouncementParseError('TABLE_EMPTY: recognized table contains no announcements')
    return result


def _http_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return url.scheme in ('http', 'https') and bool(url.hostname)
    except ValueError:
        return False


def _plain(text: str, received_at) -> ParseResult:
    # Explicit labels delimit blocks; unsupported free-form layouts are not guessed.
    starts = list(re.finditer(r'^\s*寄件單位\s*[:：]', text, re.MULTILINE))
    if not starts:
        raise AnnouncementParseError('PLAIN_LAYOUT_UNKNOWN: expected labelled announcement blocks')
    result = ParseResult(warnings=['PLAIN_TEXT_FALLBACK: parsed labelled plain-text blocks'])
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[start.start():end]
        labels = list(re.finditer(r'^\s*(寄件單位|郵件性質|主旨)\s*[:：][ \t]*', block, re.MULTILINE))
        if [match[1] for match in labels] != list(HEADERS):
            raise AnnouncementParseError('PLAIN_BLOCK_INVALID: expected department, category, then title')
        values = {match[1]: block[match.end():labels[i + 1].start() if i + 1 < len(labels) else len(block)]
                  for i, match in enumerate(labels)}
        _append(result, values, block, received_at)
    return result


def parse_announcements(*, html: str | None, plain_text: str | None = None,
                        received_at: date | datetime | None = None) -> ParseResult:
    if isinstance(received_at, datetime) and received_at.tzinfo is not None:
        received_at = received_at.astimezone(TAIPEI)
    if html is not None:
        return _html(html, received_at)
    return _plain(plain_text or '', received_at)


def parse_email(email: DecodedEmail) -> ParseResult:
    return parse_announcements(html=email.html_body, plain_text=email.text_body,
                              received_at=email.received_at)
