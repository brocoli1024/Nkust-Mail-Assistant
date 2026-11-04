import pytest
from app.services.office_mail_source import OfficeDocument
URL='https://officemail.nkust.edu.tw/Mail/MailView/69929'
TRAINING='【合成AI整合實務班】\n培養AI工具整合能力。\n上課日期：2026/12/28－2027/02/22\n【合成數據人才班】\n培養數據分析能力。\n上課日期：2026/12/28－2027/03/03\n【合成永續培訓班】\n培養ESG應用能力。\n上課日期：2026/12/29－2027/02/22\n【參訓福利】\n政府補助訓練費（含自付1萬元）\n結訓後符合資格，可申請返還1萬元\n每月可領8,000元，最高16,000元\n【就業服務】\n企業參訪、履歷健檢、就業媒合\n【參訓資格】\n本國籍15－29歲待業青年\n應屆畢業生、進修部學生可參加\n非在學學生'

def doc(body=TRAINING,title='合成職涯培訓'):
    return OfficeDocument(URL,'69929',title,body,'合成單位',None)

def build(d):
    from app.services.office_mail_briefs import build_office_brief
    return build_office_brief(d)

def test_training_integrates_every_class_benefit_and_qualification_with_evidence():
    d=doc();b=build(d)
    assert b['kind']=='training' and '3' in b['headline']
    courses=next(s for s in b['sections'] if s['label']=='班別與課程')
    assert len(courses['items'])==3
    text='\n'.join(i['text'] for s in b['sections'] for i in s['items'])
    for v in ['合成AI整合實務班','合成數據人才班','合成永續培訓班','2027/03/03','符合資格','返還1萬元','最高16,000元','履歷健檢','進修部學生','非在學學生']:assert v in text
    assert '保證退費' not in text and b['warnings']
    for section in b['sections']:
        for item in section['items']:
            assert item['evidence']
            for e in item['evidence']:assert d.body[e['start']:e['end']]==e['quote']


def test_works_keeps_campus_time_scope_and_detour_associations():
    d=doc('建工校區11/5上午施工，西門封閉，請改走東門。\n楠梓校區11/6下午停水，圖書館停止供水。','兩校區施工及停水')
    b=build(d)
    assert b['kind']=='works' and b['campus_flags']['jiangong'] and b['campus_flags']['nanzih']
    text=' '.join(i['text'] for s in b['sections'] for i in s['items'])
    assert '建工校區11/5上午施工，西門封閉，請改走東門。' in text
    assert '楠梓校區11/6下午停水，圖書館停止供水。' in text
    assert '楠梓校區11/5' not in text


def test_footer_and_recipient_do_not_define_affected_campus():
    b=build(doc('受文者：全校學生\n聯絡地址：建工校區合成路1號\n聯絡人：第一校區窗口\n辦理線上活動。','合成線上活動'))
    assert not any(b['campus_flags'].values()) and not b['campus_global']
    global_brief=build(doc('本次全校各校區均停電，請先備份資料。','全校停電'))
    assert global_brief['campus_global']


def test_campus_evidence_from_title_or_body_is_exact():
    d=doc('11月5日停水。','旗津校區停水')
    b=build(d)
    assert b['campus_flags']['qijin']
    for e in b['campus_evidence']:
        text=d.title if e['source']=='title' else d.body
        assert text[e['start']:e['end']]==e['quote']


def test_missing_detour_and_long_negative_restriction_are_not_invented_or_cut():
    b=build(doc('建工校區施工，西門封閉。','施工通知'))
    assert any('替代動線' in w for w in b['warnings'])
    body='【合成培訓班】\n'+('合成課程介紹，'*40)+'但僅限教職員，學生不得報名。'
    b=build(doc(body))
    assert '學生不得報名' in str(b['sections'])


def test_campus_codes_are_validated_deduplicated_in_fixed_order():
    from app.services.office_mail_briefs import parse_campuses
    assert parse_campuses(['nanzih','jiangong','nanzih'])==('jiangong','nanzih')
    assert parse_campuses([])==()
    with pytest.raises(ValueError):parse_campuses(['invalid'])


def test_training_keeps_unheaded_and_unrecognized_heading_restrictions():
    d=doc('本方案僅限待業青年，在學學生不得報名。\n【AI課程班】\n培訓免費，另可申請補助。\n【重要提醒】\n補助只適用已就業三個月者，未就業不得申請。')
    b=build(d);text=' '.join(i['text'] for s in b['sections'] for i in s['items'])
    assert '在學學生不得報名' in text and '未就業不得申請' in text
    assert any(s['label']=='重要提醒' for s in b['sections'])
    for section in b['sections']:
        for item in section['items']:
            for e in item['evidence']:assert d.body[e['start']:e['end']]==e['quote']


def test_heading_only_restrictions_survive_training_and_general_briefs():
    restriction='僅限教職員，學生不得報名'
    for body in ['【'+restriction+'】\n【AI課程班】\n培訓免費。','【'+restriction+'】']:
        d=doc(body);b=build(d)
        text=' '.join(s['label']+' '+i['text'] for s in b['sections'] for i in s['items'])
        assert restriction in text
        evidence=[e['quote'] for s in b['sections'] for i in s['items'] for e in i['evidence']]
        assert '【'+restriction+'】' in evidence
