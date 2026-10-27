"""Conservative browsing hints, never admission/eligibility decisions."""
from dataclasses import dataclass
import unicodedata

RULE_VERSION = 'nkust-student-rules-v1'


@dataclass(frozen=True)
class RelevanceResult:
    status: str
    reasons: tuple[str, ...]
    rule_version: str = RULE_VERSION


def classify_student_relevance(title: str, excerpt: str) -> RelevanceResult:
    title, excerpt = (''.join(unicodedata.normalize('NFKC', v).casefold().split())
                      for v in (title, excerpt))
    text = title + ' ' + excerpt
    mixed = ('全校師生', '教職員工生', '師生參加', '師生免費', '學生亦可')
    if any(word in text for word in mixed):
        return RelevanceResult('relevant', ('explicit_mixed_audience',))
    if any(word in title for word in ('教師專屬', '限教師', '限教職員', '僅限教師')):
        return RelevanceResult('not_student', ('explicit_staff_only_title',))
    words = ('獎學金', '獎助學金', '選課', '學生實習', '實習媒合', '交換學生',
             '學生報名', '全校學生', '同學參加', '新生健康檢查', '學生健檢', 'toeic', '多益報名')
    if any(word in text for word in words):
        return RelevanceResult('relevant', ('explicit_student_topic_or_audience',))
    return RelevanceResult('unknown', ())
