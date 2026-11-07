from dataclasses import replace
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import pytest
from app.services.email_parser import DecodedEmail
from app.services.office_mail_discovery_source import extract_office_urls,discovery_query
from tests.test_user_gmail_service import FakeHttp,seed,web,oauth
from app.services.user_gmail_service import UserGmailFactory
from app.config import Settings
URL='https://officemail.nkust.edu.tw/Mail/MailView/70001'
NOW=datetime(2026,11,5,tzinfo=timezone.utc)
EMAIL=DecodedEmail('private-id','校方 <mailoffice@nkust.edu.tw>','PRIVATE-SUBJECT',NOW,None,URL+' PRIVATE-BODY')

def test_extract_only_canonical_office_urls_and_exact_sender():
 e=replace(EMAIL,html_body='<a href="'+URL+'">官方</a><a href="https://evil.invalid/?to='+URL+'">假</a>',text_body=URL.replace('.tw/','.tw:443/')+' '+URL+'?private=yes')
 assert extract_office_urls(e)==(URL,)
 for sender in ('mailoffice@evil.invalid','mailoffice@nkust.edu.tw <evil@invalid.test>','mailoffice@nkust.edu.tw, evil@invalid.test'):
  assert extract_office_urls(replace(e,sender=sender))==()

def test_source_query_uses_fixed_sender_and_epoch_seconds():
 q=discovery_query(NOW-timedelta(days=14),NOW)
 assert q=='from:mailoffice@nkust.edu.tw after:'+str(int((NOW-timedelta(days=14)).timestamp()))+' before:'+str(int(NOW.timestamp()))
 with pytest.raises(ValueError):discovery_query(NOW,NOW-timedelta(days=1))

def test_discovery_client_has_bounded_page_and_does_not_change_regular_query(web):
 _,app,google=web;a,_=seed(app,google);http=FakeHttp(lambda uri,auth:(200,{'messages':[{'id':'m1'}],'nextPageToken':'private-page'}))
 with patch('app.services.user_gmail_service.httplib2.Http',return_value=http):
  with UserGmailFactory(Settings(),app.state.tokens).discovery(a,timeout_seconds=5) as client:
   ids,token=client.list_discovery_page(NOW-timedelta(days=14),NOW)
   assert ids==('m1',) and token=='private-page'
 assert http.closed
 from urllib.parse import parse_qs,urlsplit
 q=parse_qs(urlsplit(http.requests[0][0]).query)
 assert q['maxResults']==['10'] and q['includeSpamTrash']==['false'] and q['q'][0].startswith('from:mailoffice@nkust.edu.tw ')


@pytest.mark.parametrize('payload',[{'messages':[{'id':'x'}]*2},{'messages':[{'id':'x'+str(i)} for i in range(11)]},{'messages':[{'id':'private\nvalue'}]},{'nextPageToken':'same'}])
def test_bad_discovery_pages_are_rejected_without_raw_response(web,payload):
 from app.services.gmail_service import GmailError
 _,app,google=web;a,_=seed(app,google);http=FakeHttp(lambda uri,auth:(200,payload))
 with patch('app.services.user_gmail_service.httplib2.Http',return_value=http):
  with UserGmailFactory(Settings(),app.state.tokens).discovery(a,timeout_seconds=2) as client:
   with pytest.raises(GmailError,match='GMAIL_DISCOVERY_PAGE_TOKEN' if payload.get('nextPageToken')=='same' else 'GMAIL_RESPONSE_INVALID'):client.list_discovery_page(NOW-timedelta(days=1),NOW,page_token='same')

def test_invalid_page_token_has_a_safe_recoverable_code(web):
 from app.services.gmail_service import GmailError
 _,app,google=web;a,_=seed(app,google);http=FakeHttp(lambda uri,auth:(400,{'error':{'message':'PRIVATE-ERROR'}}))
 with patch('app.services.user_gmail_service.httplib2.Http',return_value=http):
  with UserGmailFactory(Settings(),app.state.tokens).discovery(a,timeout_seconds=2) as client:
   with pytest.raises(GmailError,match='GMAIL_DISCOVERY_PAGE_TOKEN'):client.list_discovery_page(NOW-timedelta(days=1),NOW,page_token='expired')
 assert len(http.requests)==1 and http.closed


def inline_message(mid='m1',sender='mailoffice@nkust.edu.tw'):
 return {'id':mid,'internalDate':'1793836800000','payload':{'mimeType':'multipart/alternative','headers':[{'name':'From','value':sender}], 'parts':[{'mimeType':'text/plain','body':{'attachmentId':'plain'}},{'mimeType':'text/html','body':{'attachmentId':'html'}}]}}

def test_inline_body_transient_failure_is_not_a_permanent_mime_rejection(web):
 from app.services.gmail_service import GmailError
 _,app,google=web;a,_=seed(app,google)
 def respond(uri,auth):return (503,{'error':{'message':'PRIVATE'}}) if '/attachments/' in uri else (200,inline_message())
 http=FakeHttp(respond)
 with patch('app.services.user_gmail_service.httplib2.Http',return_value=http):
  with UserGmailFactory(Settings(),app.state.tokens).discovery(a,timeout_seconds=2) as client:
   with pytest.raises(GmailError):client.read_message('m1')

def test_sender_is_checked_before_loading_inline_bodies(web):
 from app.services.email_parser import EmailParseError
 _,app,google=web;a,_=seed(app,google);http=FakeHttp(lambda uri,auth:(200,inline_message(sender='other@example.invalid')))
 with patch('app.services.user_gmail_service.httplib2.Http',return_value=http):
  with UserGmailFactory(Settings(),app.state.tokens).discovery(a,timeout_seconds=2) as client:
   with pytest.raises(EmailParseError):client.read_message('m1')
 assert len(http.requests)==1

def test_deadline_checked_before_each_inline_body_request(web):
 import base64
 from app.services.gmail_service import GmailError
 _,app,google=web;a,_=seed(app,google)
 def respond(uri,auth):return (200,{'data':base64.urlsafe_b64encode(URL.encode()).decode()}) if '/attachments/' in uri else (200,inline_message())
 http=FakeHttp(respond);ticks=iter([0,0,9])
 with patch('app.services.user_gmail_service.httplib2.Http',return_value=http):
  with UserGmailFactory(Settings(),app.state.tokens).discovery(a,timeout_seconds=2,deadline=10,monotonic=lambda:next(ticks,9)) as client:
   with pytest.raises(GmailError,match='OFFICE_DISCOVERY_BUDGET'):client.read_message('m1')
 assert len(http.requests)==2
