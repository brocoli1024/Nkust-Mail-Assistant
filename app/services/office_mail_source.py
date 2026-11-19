"""Anonymous reads of explicitly supplied official public mail URLs only."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
from html import escape
from urllib.parse import urlsplit, urljoin
from bs4 import BeautifulSoup
from app.services.public_source import PublicSourceError, MAX_BYTES, TAIPEI, _download

OFFICE_SOURCE_KEY='nkust-office-mail'
_PATH=re.compile(r'/Mail/MailView/[1-9][0-9]{0,17}')
_RESTRICTED=re.compile(r'僅限內部|禁止公開|不得公開|機密文件|密件|限閱|內部文件')


def normalize_office_url(value: str) -> str:
    try:
        if not isinstance(value,str) or len(value)>4096 or '\\' in value or any(c.isspace() or ord(c)<32 for c in value):raise ValueError()
        p=urlsplit(value)
        if p.scheme!='https' or p.hostname!='officemail.nkust.edu.tw' or p.port not in (None,443) or p.username is not None or p.password is not None or p.query or p.fragment or not _PATH.fullmatch(p.path):raise ValueError()
        return 'https://officemail.nkust.edu.tw'+p.path
    except (TypeError,ValueError):raise PublicSourceError('OFFICE_MAIL_URL') from None


@dataclass(frozen=True)
class OfficeDocument:
    url:str
    external_id:str
    title:str
    body:str
    department:str
    published_at:datetime|None


def parse_office_mail(data:bytes,url:str)->OfficeDocument:
    url=normalize_office_url(url)
    if not isinstance(data,bytes) or len(data)>MAX_BYTES:raise PublicSourceError('OFFICE_MAIL_SIZE')
    try:soup=BeautifulSoup(data.decode('utf-8-sig'),'html.parser')
    except UnicodeError:raise PublicSourceError('OFFICE_MAIL_ENCODING') from None
    if soup.select('input[type="password"]'):raise PublicSourceError('OFFICE_MAIL_NOT_PUBLIC')
    headings=[n for n in soup.select('h3') if re.fullmatch(r'國立高雄科技大學\s+.+?\s+通知',n.get_text(' ',strip=True))]
    if len(headings)!=1:raise PublicSourceError('OFFICE_MAIL_STRUCTURE')
    header=headings[0];root=header.parent
    fields={};description=None
    for n in root.find_all('p',recursive=False):
        text=n.get_text(' ',strip=True)
        m=re.match(r'^(受文者|副\s*本|日\s*期|文\s*號|主\s*旨|說\s*明)\s*[：:]\s*(.*)$',text,re.S)
        if m:
            key=re.sub(r'\s','',m[1]);fields[key]=m[2].strip()
            if key=='說明':description=n;break
    recipient=fields.get('受文者','')
    groups=re.split(r'[、，,;；]',recipient)
    if not groups or any(not re.fullmatch(r'(?:全校|全體|本校)[^@<>\n]{0,50}(?:學生|師生|教職員工|教職員|教師|職員|同仁|人員)',g.strip()) for g in groups):raise PublicSourceError('OFFICE_MAIL_NOT_PUBLIC')
    title=fields.get('主旨','')
    if not description or not title or len(title)>2000:raise PublicSourceError('OFFICE_MAIL_STRUCTURE')
    if _RESTRICTED.search('\n'.join([header.get_text(' ',strip=True),*fields.values()])):raise PublicSourceError('OFFICE_MAIL_NOT_PUBLIC')
    inline=BeautifulSoup(str(description),'html.parser')
    for n in inline.select('script,style,form,input,textarea,select,button,iframe,noscript'):n.decompose()
    for n in inline.select('br'):n.replace_with('\n')
    inline_text=re.sub(r'^\s*說\s*明\s*[：:]\s*','',inline.get_text(' '))
    body_nodes=[escape(inline_text)+'\n']
    # Only siblings after the explicit 說明 marker, before the platform signature.
    for n in description.next_siblings:
        if getattr(n,'name',None):
            text=n.get_text(' ',strip=True)
            if re.search(r'敬啟\s*$|^聯絡人[：:]|^分機[：:]|^e-mail[：:]|^※此為系統',text,re.I):break
        body_nodes.append(str(n))
    body_soup=BeautifulSoup(''.join(body_nodes),'html.parser')
    for n in body_soup.select('script,style,form,input,textarea,select,button,iframe,noscript,nav,footer'):n.decompose()
    for n in body_soup.select('br'):n.replace_with('\n')
    for n in body_soup.select('p,div,li,tr,h1,h2,h3,h4'):n.insert_after('\n')
    lines=[' '.join(line.split()).strip('\u200b') for line in body_soup.get_text(' ').splitlines()]
    body='\n'.join(line for line in lines if line).strip()
    if not body or len(body)>40000:raise PublicSourceError('OFFICE_MAIL_BODY')
    if _RESTRICTED.search(body):raise PublicSourceError('OFFICE_MAIL_NOT_PUBLIC')
    published=None
    date=re.fullmatch(r'民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',fields.get('日期',''))
    if date:
        try:published=datetime(int(date[1])+1911,int(date[2]),int(date[3]),tzinfo=TAIPEI).astimezone(timezone.utc)
        except ValueError:pass
    department=re.sub(r'^國立高雄科技大學\s*|\s*通知$','',header.get_text(' ',strip=True)).strip()
    return OfficeDocument(url,url.rsplit('/',1)[1],title,body,department,published)


def fetch_office_mail(url:str,*,transport=None)->OfficeDocument:
    original=normalize_office_url(url);current=original;deadline=time.monotonic()+15
    for _ in range(4):
        status,headers,body=transport(current) if transport else _download(current,deadline=deadline)
        if 300<=status<400:
            current=normalize_office_url(urljoin(current,headers.get('location','')))
            if current!=original:raise PublicSourceError('OFFICE_MAIL_REDIRECT')
            continue
        if status==404:raise PublicSourceError('OFFICE_MAIL_HTTP_404')
        if status!=200 or 'html' not in headers.get('content-type','').lower():raise PublicSourceError('OFFICE_MAIL_RESPONSE')
        return parse_office_mail(body,original)
    raise PublicSourceError('OFFICE_MAIL_REDIRECT')
