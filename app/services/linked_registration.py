"""Anonymous, bounded reads of registration links explicitly published in an article.
Never submit forms, read browser cookies, or combine different ticket scopes.
"""
import re
import time
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,urlunsplit,urljoin
from bs4 import BeautifulSoup
from app.services.public_source import PublicSourceError,_download,MAX_BYTES


def normalize_registration_url(value):
    try:
        if not value or len(value)>4096 or '\\' in value or any(c.isspace() or ord(c)<32 for c in value):raise ValueError()
        p=urlsplit(value);host=p.hostname or ''
        if p.scheme!='https' or p.username is not None or p.password is not None or p.port not in (None,443):raise ValueError()
        valid=(host=='reurl.cc' and re.fullmatch(r'/[A-Za-z0-9_-]{4,20}',p.path) or
            host=='docs.google.com' and re.fullmatch(r'/forms/d/e/[A-Za-z0-9_-]{3,300}/viewform',p.path) or
            host.endswith('.kktix.cc') and re.fullmatch(r'/events/[A-Za-z0-9_-]{1,200}',p.path))
        if not valid:raise ValueError()
        return urlunsplit(('https',host,p.path,'',''))
    except (ValueError,TypeError):raise PublicSourceError('REGISTRATION_URL') from None


def soup_for(data):
    if not isinstance(data,bytes) or len(data)>MAX_BYTES:raise PublicSourceError('REGISTRATION_SIZE')
    try:return BeautifulSoup(data.decode('utf-8-sig'),'html.parser')
    except UnicodeError:raise PublicSourceError('REGISTRATION_ENCODING') from None


def parse_form(data,url):
    soup=soup_for(data);title=soup.select_one('[role="heading"][aria-level="1"]');form=soup.select_one('form')
    if not title or not form:raise PublicSourceError('REGISTRATION_FORM')
    title=title.get_text(' ',strip=True)
    required=[]
    for h in form.select('[role="heading"][aria-level="3"]'):
        text=h.get_text(' ',strip=True)
        if any(re.search(r'必填|required',n.get('aria-label',''),re.I) for n in h.select('[aria-label]')):
            label=re.sub(r'\s*\*\s*$','',text).strip()
            if not label or len(label)>120:raise PublicSourceError('REGISTRATION_FORM')
            required.append(label)
    # Explicitly remove controls and response/default values before any archive.
    for n in form.select('script,style,input,textarea,select,button,iframe,svg'):n.decompose()
    text=form.get_text('\n',strip=True)
    if not title or len(title)>500 or not text or len(text)>16000 or len(required)>50:raise PublicSourceError('REGISTRATION_FORM')
    from app.schemas.action_cards import SourceDocument,SourceSegment
    from app.services.action_card_rules import extract
    fields,_,_=extract(SourceDocument(kind='public',source_ref=url,title=title,segments=(SourceSegment(kind='original',text=text),)))
    deadline=fields['deadline'].model_dump(mode='json')
    return {'deadline':deadline,'kind':'form','url':normalize_registration_url(url),'title':title,'text':text,'required_fields':list(dict.fromkeys(required))}


STAMP=re.compile(r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2})\s*\(\+08:?00\)')

def parse_tickets(data,url):
    soup=soup_for(data);tables=[t for t in soup.select('table') if all(x in t.get_text(' ',strip=True) for x in ('票種','販售時間'))]
    if len(tables)!=1:raise PublicSourceError('REGISTRATION_TICKETS')
    title=soup.select_one('h1');title=title.get_text(' ',strip=True) if title else '票券販售資訊'
    tickets=[]
    for row in tables[0].select('tr'):
        cells=row.select('td')
        if len(cells)<2:continue
        name=cells[0].get_text(' ',strip=True);period=cells[1].get_text(' ',strip=True);dates=STAMP.findall(period)
        if len(name)>300 or len(period)>1000:raise PublicSourceError('REGISTRATION_TICKETS')
        if len(dates)!=2:continue
        try:
            start,end=(datetime.strptime(v,'%Y/%m/%d %H:%M').replace(tzinfo=timezone(timedelta(hours=8))) for v in dates)
        except ValueError:continue
        if start>end:continue
        tickets.append({'name':name,'starts_at':start.isoformat(),'ends_at':end.isoformat(),'quote':period})
    if not tickets or len(tickets)>40:raise PublicSourceError('REGISTRATION_TICKETS')
    return {'kind':'tickets','url':normalize_registration_url(url),'title':title,'tickets':tickets}


def fetch_registration(url,*,transport=None):
    original=normalize_registration_url(url);current=original;deadline=time.monotonic()+15
    for _ in range(4):
        status,headers,body=transport(current) if transport else _download(current,deadline=deadline)
        if 300<=status<400:
            current=normalize_registration_url(urljoin(current,headers.get('location','')));continue
        if status!=200 or 'html' not in headers.get('content-type','').lower():raise PublicSourceError('REGISTRATION_RESPONSE')
        host=urlsplit(current).hostname
        if host=='reurl.cc':
            targets=soup_for(body).select('input#target[value]')
            if len(targets)!=1:raise PublicSourceError('REGISTRATION_REDIRECT')
            current=normalize_registration_url(targets[0]['value']);continue
        doc=parse_form(body,current) if host=='docs.google.com' else parse_tickets(body,current)
        return dict(doc,initial_url=original)
    raise PublicSourceError('REGISTRATION_REDIRECT')


def article_registration_links(data,base_url):
    soup=soup_for(data);body=soup.select_one('.mpgdetail .meditor')
    links=[]
    if body:
        for a in body.select('a[href]'):
            label=a.parent.get_text(' ',strip=True)[:200]
            if not re.search(r'報名|邀請|票券|申請|兌換',label):continue
            try:url=normalize_registration_url(urljoin(base_url,a['href']))
            except PublicSourceError:continue
            if url not in links:links.append(url)
    return links[:2]


def registration_context(docs):
    forms=[d for d in docs if d.get('kind')=='form' and d.get('required_fields')]
    form=forms[0] if len(forms)==1 else None
    matches=[]
    if form:
        normalized=lambda text:re.sub(r'[\s（）()!！]','',text).casefold()
        years=set(re.findall(r'(?<!\d)20\d{2}(?!\d)',form.get('title','')))
        for d in docs:
            if d.get('kind')!='tickets':continue
            other=set(re.findall(r'(?<!\d)20\d{2}(?!\d)',d.get('title','')))
            if len(years)!=1 or years!=other:continue
            for t in d.get('tickets',[]):
                if normalized(t['name']) in normalized(form['title']):matches.append(dict(t,source_url=d['url']))
    ticket=matches[0] if len(matches)==1 else None
    return {'form':form,'selected_ticket':ticket}


def display_ticket(ticket):
    return ticket['name']+'販售截止：'+datetime.fromisoformat(ticket['ends_at']).strftime('%Y-%m-%d %H:%M')+'（台灣時間）'
