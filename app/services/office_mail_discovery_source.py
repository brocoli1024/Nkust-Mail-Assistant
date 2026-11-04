"""Extract public URL candidates only; mail content is never archived here."""
import re
from datetime import timezone
from email.utils import getaddresses
from bs4 import BeautifulSoup
from app.services.office_mail_source import normalize_office_url
from app.services.public_source import PublicSourceError

def discovery_query(start,end):
 if start.tzinfo is None or end.tzinfo is None or start>=end:raise ValueError('OFFICE_DISCOVERY_WINDOW')
 return f'from:mailoffice@nkust.edu.tw after:{int(start.timestamp())} before:{int(end.timestamp())}'

def extract_office_urls(email):
 addresses=getaddresses([email.sender])
 if len(addresses)!=1 or addresses[0][1].lower()!='mailoffice@nkust.edu.tw':return ()
 values=[]
 if email.html_body:
  soup=BeautifulSoup(email.html_body,'html.parser')
  for n in soup.select('script,style,iframe,form'):n.decompose()
  values.extend(a.get('href','') for a in soup.select('a[href]'))
  text=soup.get_text(' ')
 else:text=''
 text+=' '+(email.text_body or '')
 values.extend(re.findall(r'https://[^\s<>"\']+',text))
 result=[]
 for value in values:
  try:url=normalize_office_url(value.rstrip('.,，。;；)]}）】'))
  except PublicSourceError:continue
  if url not in result:result.append(url)
 return tuple(result)
