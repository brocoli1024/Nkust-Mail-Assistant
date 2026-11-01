from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from app.services.linked_registration import normalize_registration_url,fetch_registration,parse_form,parse_tickets,registration_context
from app.services.public_source import PublicSourceError
from app.services.action_cards import build_action_card,public_source,field_display

FORM='https://docs.google.com/forms/d/e/synthetic-form/viewform'
TICKETS='https://example.kktix.cc/events/synthetic-event'
BASE='https://ord.nkust.edu.tw/p/404-1009-108001.php'
FORM_HTML=b'<form><div role="heading" aria-level="1">EDUCATION</div><div role="heading" aria-level="3">Name <span aria-label="Required question">*</span></div><input value="PRIVATE-MARKER"><div role="heading" aria-level="3">Email <span aria-label="Required question">*</span></div><textarea>PRIVATE-ANSWER</textarea><button>Submit</button></form>'
def tickets():
 return '<h1>合成2026活動票券</h1><table><tr><th>票種</th><th>販售時間</th><th>售價</th></tr><tr><td>教育推廣票</td><td>2026/09/04 00:00(+0800) ~ 2026/10/31 00:00(+0800)</td><td>免費</td></tr><tr><td>學生票</td><td>2026/09/04 00:00(+0800) ~ 2026/10/29 00:00(+0800)</td><td>99</td></tr></table>'

def test_form_only_reads_public_question_labels_never_answers():
 doc=parse_form(FORM_HTML,FORM)
 assert doc['required_fields']==['Name','Email']
 assert 'PRIVATE' not in str(doc)
 assert doc['kind']=='form'


def test_ticket_deadlines_stay_with_their_ticket_type():
 doc=parse_tickets(tickets().encode(),TICKETS)
 assert [t['name'] for t in doc['tickets']]==['教育推廣票','學生票']
 assert doc['tickets'][0]['ends_at']=='2026-10-31T00:00:00+08:00'
 form=parse_form(FORM_HTML,FORM);form['title']='合成2026高科大教育推廣票券兌換'
 context=registration_context([form,doc])
 assert context['selected_ticket']['name']=='教育推廣票'
 form['title']='合成報名表'
 assert registration_context([form,doc])['selected_ticket'] is None

@pytest.mark.parametrize('url',['http://docs.google.com/forms/d/e/a/viewform','https://docs.google.com/evil','https://example.kktix.cc:444/events/a','https://evil.invalid/events/a','https://u:p@example.kktix.cc/events/a'])
def test_linked_sources_are_strictly_allowlisted(url):
 with pytest.raises(PublicSourceError):normalize_registration_url(url)


def test_shortlink_target_is_validated_without_running_scripts():
 calls=[]
 def transport(url):
  calls.append(url)
  if url=='https://reurl.cc/Ab1234':return 200,{'content-type':'text/html'},('<input id="target" value="'+FORM+'"><script>NEVER EXECUTE</script>').encode()
  return 200,{'content-type':'text/html'},FORM_HTML
 doc=fetch_registration('https://reurl.cc/Ab1234',transport=transport)
 assert doc['url']==FORM and calls==['https://reurl.cc/Ab1234',FORM]
 with pytest.raises(PublicSourceError):fetch_registration('https://reurl.cc/Ab1234',transport=lambda u:(302,{'location':'http://127.0.0.1/private'},b''))


def test_materials_are_form_inputs_and_ticket_sale_is_not_form_deadline():
 form=parse_form(FORM_HTML,FORM);form['title']='合成2026教育推廣票券兌換'
 doc=parse_tickets(tickets().encode(),TICKETS)
 row=SimpleNamespace(source_key='nkust-latest',canonical_url=BASE,title='合成公告',excerpt='短摘要')
 card=build_action_card(public_source(row,article={'text':'活動日期：2026年10月31日','related':[form,doc]}))
 assert 'Name' in card.fields['materials'].value and '填表' in card.fields['materials'].value
 assert card.fields['deadline'].value is None
 assert '2026-10-31 00:00' in field_display(card,'deadline')['value']
 assert '學生票' not in field_display(card,'deadline')['value']
 assert '票券販售' in field_display(card,'deadline')['state']
 for e in card.fields['materials'].evidence:assert card.source.segments[e.segment].text[e.start:e.end]==e.quote


from tests.test_multi_user_database import database
from tests.test_public_source import feed,item
from tests.test_public_articles import NOW
from app.services.public_sync import sync_recent
from app.services.public_articles import refresh_articles,latest_article
from app.models.public_announcements import PublicAnnouncement as P
from sqlalchemy import select


def test_targeted_refresh_keeps_cached_registration_on_failure(database,monkeypatch):
 db,_=database;sync_recent(db,source=lambda:feed(item(url=BASE,excerpt='摘要')),now=NOW)
 form=parse_form(FORM_HTML,FORM);form['title']='合成2026教育推廣票券兌換'
 sources={FORM:form,TICKETS:parse_tickets(tickets().encode(),TICKETS)}
 monkeypatch.setattr('app.services.linked_registration.fetch_registration',lambda u:dict(sources[u],initial_url=u))
 source=lambda u:{'text':'活動日期：2026年10月31日','links':[FORM,TICKETS]}
 assert refresh_articles(db,source=source,now=NOW,sleep=lambda _:None).updated==1
 with db.transaction() as s:pid=s.scalar(select(P.id))
 def failed(u):raise RuntimeError('PRIVATE-ERROR')
 monkeypatch.setattr('app.services.linked_registration.fetch_registration',failed)
 result=refresh_articles(db,source=source,announcement_id=pid,now=NOW,sleep=lambda _:None)
 assert result.status=='partial' and result.failed==1
 with db.transaction() as s:
  row=s.get(P,pid);a=latest_article(s,row);card=build_action_card(public_source(row,article=a))
  assert 'Name' in card.fields['materials'].value and card.fields['materials'].state=='stale'
  assert 'PRIVATE-ERROR' not in str(a) and 'PRIVATE-MARKER' not in str(a)
  assert card.fields['deadline'].value is None


def test_different_year_or_ambiguous_ticket_matches_are_not_selected():
 form=parse_form(FORM_HTML,FORM);form['title']='2026 教育推廣票券兌換'
 doc=parse_tickets(tickets().encode(),TICKETS);doc['title']='2025 活動票券'
 assert registration_context([form,doc])['selected_ticket'] is None
 doc['title']='2026 活動票券';doc['tickets'].append(dict(doc['tickets'][0]))
 assert registration_context([form,doc])['selected_ticket'] is None

from tests.test_sessions import web
from tests.test_auth import oauth

def test_page_shows_real_scopes_and_provenance_without_answers(web):
 c,app,_,_=web;db=app.state.database
 sync_recent(db,source=lambda:feed(item(url=BASE,excerpt='摘要')),now=NOW)
 form=parse_form(FORM_HTML,FORM);form['title']='合成2026教育推廣票券兌換'
 from app.services.source_history import record_public_version
 with db.transaction() as s:
  row=s.scalar(select(P));pid=row.id
  record_public_version(s,row,NOW,article={'text':'活動日期：2026年10月31日','rss_hash':row.content_hash,'related':[form,parse_tickets(tickets().encode(),TICKETS)]})
 r=c.get('/public/announcements/'+str(pid))
 assert r.status_code==200 and '教育推廣票販售截止：2026-10-31 00:00' in r.text
 assert '填表資料：Name、Email' in r.text and '報名與兌換核對' in r.text
 assert FORM in r.text and '公告連結的兌換表單' in r.text
 assert 'PRIVATE-MARKER' not in r.text and 'PRIVATE-ANSWER' not in r.text


def test_private_parser_version_is_not_changed_by_public_link_support():
 from tests.test_action_cards import source
 assert build_action_card(source('請報名參加','private')).parser_version=='action-card-v2'


def test_optional_question_with_literal_star_is_not_required():
 doc=parse_form(FORM_HTML.replace(b'</form>',b'<div role="heading" aria-level="3">Optional * question</div></form>'),FORM)
 assert doc['required_fields']==['Name','Email']
 assert normalize_registration_url(FORM+'?authuser=0&entry.1=PRIVATE')==FORM


def test_explicit_form_deadline_can_be_used_without_taking_ticket_deadline():
 raw=FORM_HTML.replace(b'</form>','<p>報名截止：2026年10月30日</p></form>'.encode())
 form=parse_form(raw,FORM);form['title']='合成2026教育推廣票券兌換'
 row=SimpleNamespace(source_key='nkust-latest',canonical_url=BASE,title='合成公告',excerpt='')
 card=build_action_card(public_source(row,article={'text':'活動日期：2026年10月31日','related':[form,parse_tickets(tickets().encode(),TICKETS)]}))
 assert card.fields['deadline'].value=='2026-10-30'
 assert card.fields['deadline'].origin=='linked_form'
 assert any('2026年10月30日' in e.quote for e in card.fields['deadline'].evidence)


def test_missing_or_multi_year_never_selects_ticket():
 form=parse_form(FORM_HTML,FORM);form['title']='合成教育推廣票券兌換'
 doc=parse_tickets(tickets().encode(),TICKETS)
 assert registration_context([form,doc])['selected_ticket'] is None
 form['title']='2025 2026 教育推廣票券兌換'
 assert registration_context([form,doc])['selected_ticket'] is None


def test_ticket_fetch_failure_keeps_same_source_hash_and_warns():
 from copy import deepcopy
 form=parse_form(FORM_HTML,FORM);form['title']='2026 教育推廣票券兌換'
 ticket=parse_tickets(tickets().encode(),TICKETS)
 row=SimpleNamespace(source_key='nkust-latest',canonical_url=BASE,title='2026活動',excerpt='摘要')
 good=build_action_card(public_source(row,article={'text':'活動日期：2026年10月31日','related':[form,ticket]}))
 failed=deepcopy(ticket);failed.update(error='REGISTRATION_UNAVAILABLE',checked_at='2026-11-01T01:00:00+00:00')
 cached=build_action_card(public_source(row,article={'text':'活動日期：2026年10月31日','related':[form,failed]}))
 assert cached.baseline_hash==good.baseline_hash and cached.source_hash==good.source_hash
 assert '上次' in field_display(cached,'deadline')['state']


def test_history_reports_linked_content_changes_but_not_poll_failure():
 from copy import deepcopy
 from app.services.source_history import public_snapshot,snapshot_changes
 row=P(source_key='nkust-latest',canonical_url=BASE,title='2026活動',excerpt='摘要',content_hash='synthetic')
 form=parse_form(FORM_HTML,FORM);form['title']='2026 教育推廣票券兌換'
 old=public_snapshot(row,article={'text':'活動日期：2026年10月31日','related':[form]})
 failed=deepcopy(form);failed.update(error='REGISTRATION_UNAVAILABLE',checked_at='2026-11-01T01:00:00+00:00')
 assert snapshot_changes(old,public_snapshot(row,article={'text':'活動日期：2026年10月31日','related':[failed]}))==[]
 changed=deepcopy(form);changed['text']+='\nCompany *';changed['required_fields'].append('Company')
 assert any('報名表單或票券' in x for x in snapshot_changes(old,public_snapshot(row,article={'text':'活動日期：2026年10月31日','related':[changed]})))
