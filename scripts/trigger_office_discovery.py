"""Fixed-purpose scheduler client. Never print credentials or raw response bodies."""
import json
import os
import time
import requests
ENDPOINT='https://nkust-mail-assistant.onrender.com/internal/office-discovery/run'
CODES={'GMAIL_REAUTHORIZE','GMAIL_CREDENTIALS_UNAVAILABLE','GMAIL_DISCOVERY_UNAVAILABLE','GMAIL_RESPONSE_INVALID','GMAIL_DISCOVERY_PAGE_TOKEN','OFFICE_DISCOVERY_BUSY','OFFICE_DISCOVERY_COOLDOWN','OFFICE_DISCOVERY_LEASE','OFFICE_DISCOVERY_IDENTITY','OFFICE_DISCOVERY_PENDING','OFFICE_DISCOVERY_SOURCE_UNAVAILABLE','OFFICE_DISCOVERY_OWNER_UNAVAILABLE','OFFICE_DISCOVERY_DISABLED','OFFICE_DISCOVERY_UNAVAILABLE'}
FIELDS={'status','scanned','discovered','published','rejected','pending','error_code'}
def failure(code):return {'status':'failed','error_code':code},1

def trigger(secret,*,post=requests.post,sleep=time.sleep):
 if not secret:return {'status':'skipped','error_code':'OFFICE_DISCOVERY_NOT_CONFIGURED'},0
 if not isinstance(secret,str) or not 32<=len(secret)<=256 or any(not 33<=ord(c)<=126 for c in secret):return failure('OFFICE_DISCOVERY_TRIGGER_CONFIG')
 unknown=False
 for attempt in range(2):
  response=None
  try:
   response=post(ENDPOINT,headers={'Authorization':'Bearer '+secret,'Accept':'application/json'},data=b'',allow_redirects=False,timeout=(10,110),stream=True)
   status=response.status_code
   if status in (409,429):
    if unknown:return failure('OFFICE_DISCOVERY_TRIGGER_UNCONFIRMED')
    return {'status':'busy','error_code':'OFFICE_DISCOVERY_BUSY'},0
   if status in (401,403):return failure('OFFICE_DISCOVERY_TRIGGER_AUTH')
   if 300<=status<400 or status not in (200,503):return failure('OFFICE_DISCOVERY_TRIGGER_HTTP')
   raw=bytearray()
   for chunk in response.iter_content(1024):
    raw.extend(chunk)
    if len(raw)>8192:return failure('OFFICE_DISCOVERY_TRIGGER_RESPONSE')
   try:
    result=json.loads(raw)
    valid=isinstance(result,dict) and set(result)==FIELDS and all(type(result[k]) is int and result[k]>=0 for k in ('scanned','discovered','published','rejected','pending')) and result['error_code'] in CODES|{None}
   except (ValueError,TypeError):valid=False
   if not valid:
    if status==503 and not attempt:unknown=True;sleep(2);continue
    return failure('OFFICE_DISCOVERY_TRIGGER_RESPONSE')
   if status==200 and result['status']=='success' and result['error_code'] is None and result['pending']==0:return result,0
   if status==200 and result['status']=='partial' and result['error_code']=='OFFICE_DISCOVERY_PENDING':return result,0
   if status==503 and result['status'] in ('failed','partial') and result['error_code'] in CODES:return result,1
   return failure('OFFICE_DISCOVERY_TRIGGER_RESPONSE')
  except requests.RequestException:
   unknown=True
   if not attempt:sleep(2);continue
   return failure('OFFICE_DISCOVERY_TRIGGER_UNCONFIRMED')
  finally:
   if response is not None:response.close()
 return failure('OFFICE_DISCOVERY_TRIGGER_UNCONFIRMED')

def main():
 result,code=trigger(os.environ.get('NKUST_OFFICE_DISCOVERY_TRIGGER_SECRET',''))
 print(json.dumps(result),flush=True)
 if result['status'] in ('partial','busy'):print('::warning::Office discovery has unfinished work; see maintenance results.',flush=True)
 return code
if __name__=='__main__':raise SystemExit(main())
