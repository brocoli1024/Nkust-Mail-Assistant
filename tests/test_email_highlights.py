import pytest
from bs4 import BeautifulSoup
from sqlalchemy import select, func
from app.schemas.action_cards import SourceDocument, SourceSegment, CorrectionPatch
from app.services.action_cards import build_action_card, apply_patch
from tests.test_sessions import web, login, csrf
from tests.test_auth import oauth
from tests.test_action_card_corrections import seed, A
from app.models.multi_user import Announcement
from app.models.action_cards import PrivateActionSnapshot, PrivateActionRevision
from app.services.action_card_corrections import load_private_view, save_private_correction

BODY = "各位同學您好：\n" + "敬祝學習順利。\n" * 25 + "本校舉辦履歷健檢工作坊，協助同學改善求職履歷。\n請於2026年11月20日前完成報名，逾期不受理。\n參加對象為本校學生，須自備履歷；不需繳費。\n承辦人：合成窗口\n電話：000-0000000"


def card(text=BODY):
    return build_action_card(SourceDocument(kind='private',source_ref='synthetic',title='合成履歷工作坊',segments=(SourceSegment(kind='original',text=text),)))


def highlights(c):
    from app.services.email_highlights import email_highlights
    return email_highlights(c)


def test_highlights_select_substance_after_greetings_with_exact_evidence():
    c=card();before=c.model_dump()
    result=highlights(c)
    assert result['kind']=='extracted'
    assert [p['text'] for p in result['points']]==[
        '本校舉辦履歷健檢工作坊，協助同學改善求職履歷。',
        '請於2026年11月20日前完成報名，逾期不受理。',
        '參加對象為本校學生，須自備履歷；不需繳費。']
    for p in result['points']:
        assert c.source.segments[p['segment']].text[p['start']:p['end']]==p['quote']
    assert c.model_dump()==before


def test_repeated_sentences_are_deduplicated_and_at_most_three_in_source_order():
    result=highlights(card('歡迎參加合成講座。\n歡迎參加合成講座。\n活動日期：2026年12月1日。\n報名截止：2026年11月20日。\n請攜帶學生證。'))
    points=result['points']
    assert len(points)==3 and len({p['text'] for p in points})==3
    assert [p['start'] for p in points]==sorted(p['start'] for p in points)
    assert all('符合資格' not in p['text'] for p in points)


def test_no_unpublished_dates_or_materials_are_added():
    result=highlights(card('本校舉辦合成音樂會。歡迎有興趣的同學參加。'))
    assert [p['text'] for p in result['points']]==['本校舉辦合成音樂會。','歡迎有興趣的同學參加。']
    assert all(p['text'] in '本校舉辦合成音樂會。歡迎有興趣的同學參加。' for p in result['points'])


@pytest.mark.parametrize('mode,value,kind',[('value','我自己的摘要','personal'),('pending',None,'pending')])
def test_personal_summary_and_explicit_pending_take_precedence(mode,value,kind):
    patch={'mode':mode}
    if value:patch['value']=value
    c=apply_patch(card(),CorrectionPatch.model_validate({'fields':{'summary':patch}}))
    result=highlights(c)
    assert result['kind']==kind and result['value']==value and result['points']==[]


def test_empty_contacts_and_long_content_have_honest_fallbacks():
    assert highlights(card('   '))['kind']=='empty'
    assert highlights(card('承辦人：合成窗口\n電話：000-0000000\nhttps://example.invalid/a'))['kind']=='empty'
    text='本校舉辦'+('合成說明'*150)+'。'
    p=highlights(card(text))['points'][0]
    assert p['text']==text
    assert p['quote']==text and text[p['start']:p['end']]==p['quote']


def test_private_detail_shows_summary_first_collapses_original_and_does_not_write(web):
    c,app,google,_=web;login(c);db=app.state.database;aid=seed(db)
    with db.transaction() as s:s.get(Announcement,aid).original_text=BODY+'\n<script>PRIVATE-XSS</script>'
    before=load_private_view(db,A,aid).base.baseline_hash
    response=c.get(f'/announcements/{aid}')
    assert response.status_code==200
    soup=BeautifulSoup(response.text,'html.parser');summary=soup.select_one('[aria-label="郵件公告重點摘要"]')
    assert summary and len(summary.select('[data-email-highlight]'))==3
    assert response.text.index('郵件公告重點摘要')<response.text.index('公告行動資訊卡')
    original=soup.select_one('details.private-original')
    assert original and not original.has_attr('open') and 'PRIVATE-XSS' in original.text
    assert '<script>PRIVATE-XSS</script>' not in response.text
    for p in summary.select('[data-email-highlight]'):assert p.find('details')
    assert not soup.select('[data-card-field="summary"]')
    assert 'no-store' in response.headers['cache-control']
    assert load_private_view(db,A,aid).base.baseline_hash==before
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(PrivateActionSnapshot))==0
        assert s.scalar(select(func.count()).select_from(PrivateActionRevision))==0
    c.post('/logout',data={'csrf_token':csrf(c)})
    google.claims={'sub':'google-b','email':'b@example.invalid','name':'B'};login(c)
    denied=c.get(f'/announcements/{aid}')
    assert denied.status_code==404 and '履歷健檢' not in denied.text
    assert '履歷健檢' not in c.get('/public/announcements').text


def test_saved_summary_stays_visible_without_replacing_it_with_extracted_text(web):
    c,app,_,_=web;login(c);db=app.state.database;aid=seed(db)
    v=load_private_view(db,A,aid)
    patch=CorrectionPatch.model_validate({'fields':{'summary':{'mode':'value','value':'我自己的摘要'}}})
    save_private_correction(db,A,aid,expected_revision=0,baseline_hash=v.base.baseline_hash,operation='save',patch=patch)
    response=c.get(f'/announcements/{aid}')
    summary=BeautifulSoup(response.text,'html.parser').select_one('[aria-label="郵件公告重點摘要"]')
    assert summary and '我自己的摘要' in summary.text and '個人修正' in summary.text
    assert not summary.select('[data-email-highlight]')
    assert load_private_view(db,A,aid).effective.fields['summary'].value=='我自己的摘要'


def test_courtesy_with_instruction_is_not_discarded():
    text='謝謝同學配合，請於11月20日前繳交申請表。'
    assert [p['text'] for p in highlights(card(text))['points']]==[text]


def test_long_sentence_keeps_trailing_eligibility_and_negation_visible():
    text='本校舉辦工作坊，'+('合成課程說明，'*45)+'但僅限教職員，學生不得報名。'
    result=highlights(card(text))
    assert result['points'][0]['text']==text
    assert '學生不得報名' in result['points'][0]['text']
