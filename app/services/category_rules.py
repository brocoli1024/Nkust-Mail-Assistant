"""Conservative rules for the shared multi-user announcement categories."""
import unicodedata


CATEGORIES = ('課程', '選課', '獎學金', '競賽', '講座', '活動', '證照', 'TOEIC',
              '實習', '徵才', '交換學生', '行政通知', '其他')
RULE_VERSION = 'nkust-category-rules-v1'
FILTER_WORDS = {
    '課程': ('課程', '開課', '微學分'), '選課': ('選課',), '獎學金': ('獎學金', '獎助學金', '獎勵金'),
    '競賽': ('競賽', '比賽'), '講座': ('講座', '演講'), '活動': ('活動',),
    '證照': ('證照', '證輔導', '考證'), 'TOEIC': ('TOEIC', '多益'),
    '實習': ('實習',), '徵才': ('徵才', '徵聘'), '交換學生': ('交換學生',),
    '行政通知': ('行政通知',), '其他': ('其他',),
}


def _normalize(value):
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def _matches(value):
    normalized = _normalize(value)
    return {category for category, words in FILTER_WORDS.items() if category != '其他'
            and any(_normalize(word) in normalized for word in words)}


def classify_category(source_category: str, title: str) -> str | None:
    """Prefer a clear source label; fall back to one unambiguous title match."""
    source = _normalize(source_category)
    for category in CATEGORIES:
        if category == '其他':
            continue
        if source == _normalize(category):
            return category
    source_matches = _matches(source_category)
    if len(source_matches) == 1:
        return source_matches.pop()
    title_matches = _matches(title)
    if len(title_matches) == 1:
        title_category = title_matches.pop()
        if not source_matches or title_category in source_matches:
            return title_category
    return None
