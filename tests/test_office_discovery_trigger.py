import json
import requests
import pytest
from scripts.trigger_office_discovery import trigger,ENDPOINT
SECRET='synthetic-only-trigger-'+'x'*32
GOOD={'status':'success','scanned':3,'discovered':2,'published':2,'rejected':0,'pending':0,'error_code':None}
class Response:
 def __init__(self,payload,status=200):self.raw=json.dumps(payload).encode();self.status_code=status;self.closed=False
 def iter_content(self,size):yield self.raw
 def close(self):self.closed=True

def test_fixed_trigger_sends_only_empty_post_and_header():
 response=Response(GOOD);calls=[]
 def post(url,**kw):calls.append((url,kw));return response
 result,code=trigger(SECRET,post=post,sleep=lambda _:None)
 assert code==0 and result==GOOD and response.closed
 assert calls[0][0]==ENDPOINT and calls[0][1]['data']==b'' and not calls[0][1]['allow_redirects']
 assert calls[0][1]['headers']['Authorization']=='Bearer '+SECRET

def test_missing_secret_is_explicitly_skipped():
 result,code=trigger('',post=lambda *a,**kw:pytest.fail('must not call network'))
 assert code==0 and result['status']=='skipped'

@pytest.mark.parametrize('payload',[dict(GOOD,scanned=True),dict(GOOD,private='PRIVATE'),dict(GOOD,pending=-1),dict(GOOD,error_code='PRIVATE_ERROR'),dict(GOOD,status='partial')])
def test_malformed_or_private_response_is_not_printed(payload):
 result,code=trigger(SECRET,post=lambda *a,**kw:Response(payload),sleep=lambda _:None)
 assert code==1 and 'PRIVATE' not in json.dumps(result)

def test_redirect_and_auth_failure_are_safe():
 for status in (302,401):
  result,code=trigger(SECRET,post=lambda *a,**kw:Response({'PRIVATE':SECRET},status),sleep=lambda _:None)
  assert code==1 and SECRET not in json.dumps(result)

def test_pending_backfill_and_unknown_timed_out_execution_are_distinct():
 partial=dict(GOOD,status='partial',pending=3,error_code='OFFICE_DISCOVERY_PENDING')
 assert trigger(SECRET,post=lambda *a,**kw:Response(partial),sleep=lambda _:None)[1]==0
 calls=[]
 def timeout_then_busy(*a,**kw):
  calls.append(1)
  if len(calls)==1:raise requests.Timeout('PRIVATE')
  return Response({},429)
 result,code=trigger(SECRET,post=timeout_then_busy,sleep=lambda _:None)
 assert code==1 and result['error_code']=='OFFICE_DISCOVERY_TRIGGER_UNCONFIRMED' and len(calls)==2
