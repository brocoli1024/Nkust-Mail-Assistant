import base64
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.announcement_parser import (
    AnnouncementParseError, parse_announcements, parse_email, source_fingerprint,
)
from app.services.email_parser import decode_message

FIXTURES = Path(__file__).parent / 'fixtures'
RECEIVED = datetime(2026, 9, 19, tzinfo=timezone.utc)


def fixture(extension):
    return (FIXTURES / f'nkust_mail_sample.{extension}').read_text(encoding='utf-8')


@pytest.mark.parametrize('use_html', [True, False])
def test_required_examples_and_three_announcements(use_html):
    result = parse_announcements(html=fixture('html') if use_html else None,
                                plain_text=fixture('txt'), received_at=RECEIVED)
    assert len(result.announcements) == 3
    a, b, c = result.announcements
    assert (a.department, a.source_category, a.deadline) == ('體育室', '獎學金', '2026-10-08')
    assert a.event_date is None
    assert (b.department, b.source_category, b.event_date) == ('校友中心', '其他', '2026-10-21')
    assert b.date_evidence[0].year_inferred is True
    assert b.deadline is None
    assert c.event_date is c.deadline is None
    assert [item.source_index for item in result.announcements] == [0, 1, 2]
    assert '【運動績優獎勵金申請】\n本校' in a.original_text
    assert '自即日起受理申請至115年10月08日止' in a.original_text
    assert len(a.source_fingerprint) == 64


@pytest.mark.parametrize('html', ['', '<p>不是公告表格</p>', '<table><tr><td>未知欄位</td></tr></table>'])
def test_bad_html_never_silently_falls_back(html):
    with pytest.raises(AnnouncementParseError, match='TABLE_NOT_FOUND'):
        parse_announcements(html=html, plain_text=fixture('txt'), received_at=RECEIVED)


def test_plain_mime_to_announcements():
    text = fixture('txt')
    email = decode_message({'id': 'synthetic', 'internalDate': '1789776000000',
                            'payload': {'mimeType': 'text/plain', 'body': {
                                'data': base64.urlsafe_b64encode(text.encode()).decode()}}})
    result = parse_email(email)
    assert len(result.announcements) == 3
    assert result.warnings == ['PLAIN_TEXT_FALLBACK: parsed labelled plain-text blocks']


def test_fingerprint_independent_of_position_and_formatting():
    result = parse_announcements(html=fixture('html'), received_at=RECEIVED)
    a = result.announcements[0]
    assert a.source_fingerprint == source_fingerprint(a.department, a.source_category, a.title)
    assert source_fingerprint('體育室', '獎學金', 'Ａ  B') == source_fingerprint('體育室', '獎學金', 'A\nB')
    assert a.source_fingerprint != source_fingerprint(a.department, '其他', a.title)


def test_nested_layout_does_not_duplicate_rows():
    result = parse_announcements(html='<table><tr><td>' + fixture('html') + '</td></tr></table>')
    assert len(result.announcements) == 3


@pytest.mark.parametrize('row, error', [
    ('', 'TABLE_EMPTY'),
    ('<tr><td>體育室</td></tr>', 'TABLE_ROW_INVALID'),
    ('<tr><td>體育室</td><td>獎學金</td><td></td></tr>', 'EMPTY_FIELD'),
    ('<tr><td colspan="3">合併列</td></tr>', 'SPAN_UNSUPPORTED'),
])
def test_invalid_rows_error(row, error):
    html = '<table><tr><td>寄件單位</td><td>郵件性質</td><td>主旨</td></tr>' + row + '</table>'
    with pytest.raises(AnnouncementParseError, match=error):
        parse_announcements(html=html)


def test_plain_missing_labels_error():
    with pytest.raises(AnnouncementParseError, match='PLAIN_BLOCK_INVALID'):
        parse_announcements(html=None, plain_text='寄件單位：體育室\n主旨：資訊')


def test_received_year_is_taipei_year():
    result = parse_announcements(html=None, plain_text='寄件單位：校友中心\n郵件性質：其他\n主旨：1/02企業徵才說明會',
                                 received_at=datetime(2025, 12, 31, 17, tzinfo=timezone.utc))
    assert result.announcements[0].event_date == '2026-01-02'


def test_fingerprint_does_not_remove_repeated_announcements():
    result = parse_announcements(html=fixture('html') + fixture('html'), received_at=RECEIVED)
    assert len(result.announcements) == 6
    assert result.announcements[0].source_fingerprint == result.announcements[3].source_fingerprint
    assert result.announcements[0].source_index != result.announcements[3].source_index
