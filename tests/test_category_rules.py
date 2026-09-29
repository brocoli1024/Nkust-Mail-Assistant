from app.services.category_rules import classify_category


def test_unique_title_disambiguates_multiple_source_labels():
    assert classify_category('活動／講座', '教學分享講座') == '講座'


def test_conflicting_or_multiple_matches_stay_unclassified():
    assert classify_category('活動／講座', '獎學金申請') is None
    assert classify_category('校園訊息', '實習與徵才資訊') is None


def test_source_category_takes_priority_and_normalizes_width():
    assert classify_category(' ＴＯＥＩＣ ', '獎學金說明') == 'TOEIC'


def test_generic_other_without_title_evidence_stays_unclassified():
    assert classify_category('其他', '校園最新消息') is None
