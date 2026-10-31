"""Bounded official article refresh into the existing public version archive."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from sqlalchemy import select, func
from app.models.public_announcements import PublicAnnouncement as P
from app.models.source_history import PublicSourceVersion as V
from app.services.public_source import PublicSourceError, _download, MAX_BYTES, normalize_public_url
from app.services.public_sync import SourceLease, aware
from app.services.source_history import official_identity, record_public_version


def parse_article(data):
    if not isinstance(data,bytes) or len(data)>MAX_BYTES:raise PublicSourceError('PUBLIC_ARTICLE_SIZE')
    try:soup=BeautifulSoup(data.decode('utf-8-sig'),'html.parser')
    except UnicodeError:raise PublicSourceError('PUBLIC_ARTICLE_ENCODING') from None
    bodies=soup.select('.mpgdetail .meditor')
    if len(bodies)!=1:raise PublicSourceError('PUBLIC_ARTICLE_BODY')
    body=bodies[0]
    for tag in body.select('script,style,iframe,noscript,nav,footer,form'):tag.decompose()
    # Keep explicit breaks and blocks: date roles must not bleed across paragraphs.
    for br in body.select('br'):br.replace_with('\n')
    for block in body.select('p,li,div,tr,h1,h2,h3,h4'):block.insert_after('\n')
    text='\n'.join(' '.join(line.split()) for line in body.get_text(' ').splitlines() if line.strip()).strip()
    if not text or len(text)>40000:raise PublicSourceError('PUBLIC_ARTICLE_BODY')
    return text


def fetch_article(url, *, transport=None):
    original=official_identity(url)
    if not original:raise PublicSourceError('PUBLIC_ARTICLE_URL')
    current=original;deadline=time.monotonic()+15
    for _ in range(4):
        status,headers,body=transport(current) if transport else _download(current,deadline=deadline)
        if 300<=status<400:
            target=official_identity(urljoin(current,headers.get('location','')))
            if not target or (urlsplit(target).hostname,urlsplit(target).path)!=(urlsplit(original).hostname,urlsplit(original).path):raise PublicSourceError('PUBLIC_ARTICLE_REDIRECT')
            current=target;continue
        if status!=200 or 'html' not in headers.get('content-type','').lower():raise PublicSourceError('PUBLIC_ARTICLE_RESPONSE')
        return parse_article(body)
    raise PublicSourceError('PUBLIC_ARTICLE_REDIRECT')


def latest_article(session,row):
    latest=session.scalar(select(V).where(V.source_key==row.source_key,V.canonical_url==row.canonical_url).order_by(V.id.desc()).limit(1))
    return latest.snapshot.get('metadata',{}).get('article') if latest else None


@dataclass
class ArticleResult:
    updated:int=0
    failed:int=0
    status:str='success'


def refresh_articles(database, *, source=fetch_article, limit=8, now=None, sleep=time.sleep):
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20:raise ValueError('limit must be 1..20')
    lease=SourceLease(database,now=now);lease.acquire();result=ArticleResult();deadline=time.monotonic()+90
    try:
        with database.transaction() as session:
            lease.verify(session)
            rows=session.scalars(select(P).where(P.source_key=='nkust-latest').order_by(P.last_seen_at.desc(),P.published_at.desc(),P.id.desc()).limit(200)).all()
            latest_ids=select(func.max(V.id)).where(V.source_key=='nkust-latest',V.canonical_url.in_([r.canonical_url for r in rows])).group_by(V.canonical_url)
            previous={v.canonical_url:v.snapshot.get('metadata',{}).get('article') for v in session.scalars(select(V).where(V.id.in_(latest_ids)))}
            candidates=[]
            for row in rows:
                if not official_identity(row.canonical_url):continue
                old=previous.get(row.canonical_url) or {}
                checked=datetime.fromisoformat(old['checked_at']) if old.get('checked_at') else None
                if checked and old.get('rss_hash')==row.content_hash and lease.clock()-aware(checked)<timedelta(hours=1 if old.get('error') else 24):continue
                candidates.append((row.id,row.canonical_url,old))
        # Untouched pages go first; ties retain recent-feed order.
        candidates.sort(key=lambda c:c[2].get('checked_at',''))
        for index,(pid,url,old) in enumerate(candidates[:limit]):
            if time.monotonic()>=deadline:break
            if index:sleep(2)
            article=dict(old,checked_at=lease.clock().isoformat())
            try:
                body=source(url)
                if not isinstance(body,str) or not body.strip() or len(body)>40000:raise PublicSourceError('PUBLIC_ARTICLE_BODY')
                article.update(text=body,fetched_at=lease.clock().isoformat(),error=None)
            except Exception:
                article['error']='PUBLIC_ARTICLE_UNAVAILABLE'
                result.failed+=1;result.status='partial'
            with database.transaction() as session:
                lease.verify(session)
                row=session.get(P,pid)
                if row and row.canonical_url==url:
                    if not article['error']:article['rss_hash']=row.content_hash
                    record_public_version(session,row,lease.clock(),article=article)
                    if not article['error']:result.updated+=1
    finally:lease.release()
    return result
