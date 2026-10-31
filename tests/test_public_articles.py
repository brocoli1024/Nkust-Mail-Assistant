from datetime import datetime, timedelta, timezone
from sqlalchemy import select
import pytest
from tests.test_multi_user_database import database
from tests.test_public_source import feed, item
from app.models.public_announcements import PublicAnnouncement as P
from app.models.source_history import PublicSourceVersion as V
from app.services.public_sync import sync_recent
from app.services.public_source import PublicSourceError
from app.services.public_articles import parse_article, fetch_article, refresh_articles, latest_article
from app.services.action_cards import build_action_card, public_source, field_display

URL='https://ord.nkust.edu.tw/p/404-1009-108001.php'
NOW=datetime(2026,10,31,12,tzinfo=timezone.utc)
TEXT='本校師生可索取專屬邀請碼，再使用邀請碼完成活動報名。\n活動日期：2026 年 10 月 31 日（六）'
def html(text=TEXT):
    return ('<html><h2 class="m-title">合成活動</h2><nav>報名截止：2030年1月1日</nav><div class="mpgdetail"><div class="meditor">'+text.replace('\n','<br>')+'<script>bad()</script></div></div><footer>應備文件：假的文件</footer></html>').encode()

def test_article_only_extracts_main_body_and_preserves_lines():
    body=parse_article(html())
    assert '2026 年 10 月 31 日' in body and '\n' in body
    assert '2030' not in body and '假的文件' not in body and 'bad()' not in body
    for raw in (b'<h1>Not found</h1>',html(''),html('x'*40001)):
        with pytest.raises(PublicSourceError):parse_article(raw)

@pytest.mark.parametrize('url',['https://evil.invalid/p/404-1009-1.php','https://ord.nkust.edu.tw/admin','https://ord.nkust.edu.tw:444/p/404-1009-1.php'])
def test_article_rejects_non_official_articles_before_network(url):
    calls=[]
    with pytest.raises(PublicSourceError):fetch_article(url,transport=lambda u:calls.append(u))
    assert not calls

def test_redirect_to_outside_or_private_path_is_rejected():
    for location in ('https://evil.invalid/x','https://ord.nkust.edu.tw/admin','https://ord.nkust.edu.tw/p/404-1009-999.php'):
        calls=[]
        def transport(url):calls.append(url);return 302,{'location':location},b''
        with pytest.raises(PublicSourceError):fetch_article(URL,transport=transport)
        assert calls==[URL]

def test_body_supports_actions_dates_and_distinct_missing_reasons(database):
    db,_=database
    sync_recent(db,source=lambda:feed(item(url=URL,excerpt='截短摘要')),now=NOW)
    result=refresh_articles(db,source=lambda url:parse_article(html()),now=NOW,sleep=lambda _:None)
    assert result.updated==1 and result.failed==0
    with db.transaction() as s:
        row=s.scalar(select(P));article=latest_article(s,row)
        card=build_action_card(public_source(row,article=article))
        assert row.excerpt=='截短摘要'
        assert card.fields['event_date'].value=='2026-10-31'
        assert card.fields['action'].value and card.fields['audience'].value=='本校師生'
        assert card.fields['deadline'].value is None
        assert field_display(card,'deadline')['value']=='本文未找到截止說明'
        for f in card.fields.values():
            for e in f.evidence:assert card.source.segments[e.segment].text[e.start:e.end]==e.quote
        count=len(s.scalars(select(V)).all())
    calls=[]
    refresh_articles(db,source=lambda url:calls.append(url),now=NOW+timedelta(hours=1),sleep=lambda _:None)
    assert not calls
    def fail(url):raise RuntimeError('PRIVATE SECRET')
    assert refresh_articles(db,source=fail,now=NOW+timedelta(hours=25),sleep=lambda _:None).failed==1
    with db.transaction() as s:
        row=s.scalar(select(P));a=latest_article(s,row)
        assert a['text']==TEXT and a['error']=='PUBLIC_ARTICLE_UNAVAILABLE'
        assert len(s.scalars(select(V)).all())>count
        assert 'PRIVATE SECRET' not in str(a)
    sync_recent(db,source=lambda:feed(item(url=URL,excerpt='新的RSS摘要')),now=NOW+timedelta(hours=26))
    with db.transaction() as s:
        row=s.scalar(select(P));article=latest_article(s,row)
        assert article['text']==TEXT
        assert build_action_card(public_source(row,article=article)).fields['event_date'].state=='stale'

def test_without_body_explains_source_limit(database):
    db,_=database;sync_recent(db,source=lambda:feed(item(url=URL)),now=NOW)
    with db.transaction() as s:
        card=build_action_card(public_source(s.scalar(select(P))))
        assert field_display(card,'deadline')['value']=='尚待讀取完整原文'


def test_fetch_failure_does_not_invalidate_same_body_corrections():
    from types import SimpleNamespace
    row=SimpleNamespace(source_key='nkust-latest',canonical_url=URL,title='合成活動',excerpt='摘要')
    a=build_action_card(public_source(row,article={'text':TEXT,'error':None,'fetched_at':NOW.isoformat()}))
    b=build_action_card(public_source(row,article={'text':TEXT,'error':'PUBLIC_ARTICLE_UNAVAILABLE'}))
    assert a.baseline_hash==b.baseline_hash


def test_completed_registration_is_not_an_instruction():
    from tests.test_action_cards import source
    assert build_action_card(source('已完成報名的同學請等待通知')).requires_action is None


from tests.test_sessions import web
from tests.test_auth import oauth

def test_public_page_uses_saved_body_and_get_never_fetches(web,monkeypatch):
    c,app,_,_=web;db=app.state.database
    sync_recent(db,source=lambda:feed(item(url=URL,excerpt='短摘要')),now=NOW)
    refresh_articles(db,source=lambda url:TEXT,now=NOW,sleep=lambda _:None)
    with db.transaction() as s:pid=s.scalar(select(P.id).where(P.canonical_url==URL))
    def forbidden(*a,**kw):raise AssertionError('GET must not fetch sources')
    monkeypatch.setattr('app.services.public_articles._download',forbidden)
    r=c.get('/public/announcements/'+str(pid))
    assert r.status_code==200
    assert '2026-10-31' in r.text and '官方公告本文' in r.text
    assert '本文未找到截止說明' in r.text and '尚待讀取完整原文' not in r.text
    assert '展開已讀取本文' in r.text


def test_full_body_does_not_discard_rss_evidence_or_hide_conflicts():
    from types import SimpleNamespace
    row=SimpleNamespace(source_key='nkust-latest',canonical_url=URL,title='合成活動',excerpt='報名截止：2026年11月1日；活動日期：2026年10月30日')
    card=build_action_card(public_source(row,article={'text':TEXT}))
    assert card.fields['deadline'].value=='2026-11-01'
    assert card.fields['event_date'].state=='pending'
    assert {card.source.segments[e.segment].kind for e in card.fields['event_date'].evidence}=={'excerpt','official_text'}
