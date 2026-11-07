import pytest
from datetime import datetime,timezone
from sqlalchemy import select,event
from tests.test_sessions import web,oauth,login,csrf
from app.core.office_discovery import DiscoverySettings
from app.services.office_mail_discovery import DiscoveryResult
SECRET='synthetic-trigger-secret-'+'x'*32

def enabled(app):
 app.state.discovery_settings=DiscoverySettings(True,'google-a',SECRET)
 app.state.discovery_runner=lambda:DiscoveryResult(published=2)

def test_trigger_disabled_and_cookie_is_not_authorization(web):
 c,app,_,_=web
 assert c.post('/internal/office-discovery/run').status_code==404
 enabled(app);login(c)
 assert c.post('/internal/office-discovery/run').status_code==401
 r=c.post('/internal/office-discovery/run',headers={'Authorization':'Bearer '+SECRET})
 assert r.status_code==200 and r.json()['published']==2 and SECRET not in r.text

@pytest.mark.parametrize('suffix,body,status',[('?owner=other',b'',422),('',b'{}',422),('',b'x'*1025,413)])
def test_trigger_rejects_arbitrary_parameters(web,suffix,body,status):
 c,app,_,_=web;enabled(app)
 assert c.post('/internal/office-discovery/run'+suffix,content=body,headers={'Authorization':'Bearer '+SECRET}).status_code==status

def test_owner_page_and_csrf_are_required(web):
 c,app,google,_=web;enabled(app);login(c)
 r=c.get('/settings/office-discovery');assert r.status_code==200 and SECRET not in r.text and 'google-a' not in r.text
 assert r.headers['referrer-policy']=='same-origin'
 assert 'href="/auth/google"' in r.text
 assert c.post('/settings/office-discovery/run',data={'csrf_token':'wrong'}).status_code==403
 assert c.post('/settings/office-discovery/run',data={'csrf_token':csrf(c)}).status_code==200
 app.state.discovery_settings=DiscoverySettings(True,'other-sub',SECRET)
 assert c.get('/settings/office-discovery').status_code==403
 assert c.post('/settings/office-discovery/run',data={'csrf_token':csrf(c)}).status_code==403

def test_public_discovery_failure_cannot_be_hidden_by_successful_reread(web):
 from app.models.public_announcements import PublicSourceState,PublicSyncRun
 c,app,_,_=web;now=datetime.now(timezone.utc)
 with app.state.database.transaction() as s:
  s.add(PublicSourceState(source_key='nkust-office-mail',last_success_at=now))
  s.add(PublicSourceState(source_key='nkust-office-discovery',history_status='incomplete'))
  s.add(PublicSyncRun(source_key='nkust-office-discovery',mode='recent',status='failed',started_at=now,finished_at=now,error_code='GMAIL_REAUTHORIZE'))
 queries=[]
 def capture(conn,cursor,statement,*args):queries.append(statement.lower())
 event.listen(app.state.database.engine,'before_cursor_execute',capture)
 try:r=c.get('/public/office-mail')
 finally:event.remove(app.state.database.engine,'before_cursor_execute',capture)
 assert '新公告收錄暫停' in r.text and '內容最後成功重讀' in r.text
 assert not any('office_discovery_' in q or ' users' in q for q in queries)
 assert '返回公務公告' in c.get('/public/office-mail/999').text


def test_public_scope_shows_all_collected_publication_dates(web):
 from dataclasses import replace
 from tests.test_office_discovery_state import URL
 from tests.test_office_mail_sync import document
 from app.services.office_mail_sync import import_office_mail
 c,app,_,_=web
 for day in (1,5):
  u=URL[:-1]+str(day)
  import_office_mail(app.state.database,[u],source=lambda url,day=day:replace(document(url),published_at=datetime(2026,11,day,tzinfo=timezone.utc)))
 text=c.get('/public/office-mail?q=no-match').text
 assert '收錄公告發布日期' in text and '2026-11-01' in text and '2026-11-05' in text
