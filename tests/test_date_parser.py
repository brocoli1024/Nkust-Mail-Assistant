from datetime import datetime

import pytest

from app.services.date_parser import parse_dates

RECEIVED = datetime(2026, 9, 19)


@pytest.mark.parametrize(('text', 'expected'), [
    ('115年10月08日', '2026-10-08'),
    ('115年11月23日截止', '2026-11-23'),
    ('10/21', '2026-10-21'),
    ('11月29日', '2026-11-29'),
    ('2026-11-29', '2026-11-29'),
    ('2026/10/21', '2026-10-21'),
])
def test_dates(text, expected):
    assert parse_dates(text, RECEIVED).evidence[0].iso_date == expected


@pytest.mark.parametrize('text', ['115-1學期', '115學年度第1學期'])
def test_semester_is_not_date(text):
    assert parse_dates(text, RECEIVED).evidence == []


def test_deadline_and_event_are_separate():
    result = parse_dates('10/21 大立光電企業徵才說明會，報名至115年10月08日止', RECEIVED)
    assert result.event_date == '2026-10-21'
    assert result.deadline == '2026-10-08'
    assert result.evidence[0].year_inferred is True
    assert result.evidence[1].year_inferred is False


def test_application_deadline():
    assert parse_dates('申請至115年10月08日止').deadline == '2026-10-08'
    assert parse_dates('115年11月23日截止').deadline == '2026-11-23'


@pytest.mark.parametrize('text', ['115年02月30日截止', '明年10/21舉行講座'])
def test_invalid_or_ambiguous_dates_are_preserved(text):
    result = parse_dates(text, RECEIVED)
    assert result.evidence[0].iso_date is None
    assert result.warnings


def test_unknown_year_and_multiple_events():
    assert parse_dates('10/21').evidence[0].iso_date is None
    result = parse_dates('10/21講座，11/29活動', RECEIVED)
    assert result.event_date is None
    assert len(result.evidence) == 2
    assert result.warnings


def test_unlabelled_date_does_not_invent_role():
    result = parse_dates('115年10月08日')
    assert result.event_date is result.deadline is None
