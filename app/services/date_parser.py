"""Conservative date extraction with source evidence; never use today's year."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime

DATE_PATTERN = re.compile(
    r"(?<![\d/.-])(?:(?P<year>\d{2,4})\s*年\s*)?"
    r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日"
    r"|(?<![\d/.-])(?:(?P<slash_year>\d{3,4})/)?"
    r"(?P<slash_month>\d{1,2})/(?P<slash_day>\d{1,2})(?![\d/])"
    r"|(?<![\d-])(?P<iso_year>\d{4})-(?P<iso_month>\d{2})-(?P<iso_day>\d{2})(?!\d)"
)
EVENT = re.compile(r"活動|說明會|座談會|講座|研習|競賽|比賽|舉行|舉辦|上課|開課|考試|典禮")
DEADLINE_BEFORE = re.compile(r"截止(?:日期|時間|日)?\s*[:：]?\s*$|(?:申請|報名|受理|繳交|繳件|收件|即日起).{0,20}(?:至|到|於)\s*$")
DEADLINE_AFTER = re.compile(r"^\s*(?:截止|止|前(?:完成|提出|申請|報名|繳交|繳件))")


@dataclass(frozen=True)
class DateEvidence:
    original_text: str
    iso_date: str | None
    role: str | None
    year_inferred: bool
    start: int
    end: int


@dataclass
class DateResult:
    event_date: str | None = None
    deadline: str | None = None
    evidence: list[DateEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_dates(text: str, received_at: date | datetime | None = None) -> DateResult:
    result = DateResult()
    matches = list(DATE_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        groups = match.groupdict()
        year = groups['year'] or groups['slash_year'] or groups['iso_year']
        month = groups['month'] or groups['slash_month'] or groups['iso_month']
        day = groups['day'] or groups['slash_day'] or groups['iso_day']
        inferred = year is None
        previous_end = matches[index - 1].end() if index else 0
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        before = re.split(r"[，,。；;\n]", text[previous_end:match.start()])[-1]
        after = re.split(r"[，,。；;\n]", text[match.end():next_start])[0]
        if DEADLINE_BEFORE.search(before) or DEADLINE_AFTER.search(after):
            role = 'deadline'
        elif (EVENT.search(before + after) or (len(matches) == 1 and EVENT.search(text))
              or (re.fullmatch(r'\s*日期\s*[:：]\s*', before)
                  and EVENT.search(text[:match.start()].splitlines()[-2] if len(text[:match.start()].splitlines()) > 1 else ''))):
            role = 'event_date'
        else:
            role = None
        value = None
        try:
            if inferred:
                if received_at is None or re.search(r"明年|翌年|次年|跨年|去年", text):
                    raise ValueError('Missing or ambiguous year')
                numeric_year = received_at.year
            else:
                numeric_year = int(year)
                if numeric_year < 1911:
                    # Only short years are ROC years; do not reinterpret four-digit years.
                    numeric_year = numeric_year + 1911 if len(year) <= 3 else numeric_year
            value = date(numeric_year, int(month), int(day)).isoformat()
        except ValueError:
            result.warnings.append(f"DATE_UNRESOLVED: {match.group()}")
        result.evidence.append(DateEvidence(match.group(), value, role, inferred,
                                            match.start(), match.end()))
    for role in ('event_date', 'deadline'):
        relevant = [item for item in result.evidence if item.role == role]
        values = {item.iso_date for item in relevant if item.iso_date}
        if len(values) == 1 and all(item.iso_date for item in relevant):
            setattr(result, role, values.pop())
        elif relevant:
            result.warnings.append(f"DATE_AMBIGUOUS: {role}")
    return result
