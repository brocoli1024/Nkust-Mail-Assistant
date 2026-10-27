from datetime import datetime, timezone
from sqlalchemy import select,func
import pytest
from tests.test_multi_user_database import database
from tests.test_public_source import feed,item
from app.services.public_source import parse_listing, PublicSourceError
from app.services.public_sync import backfill_history,sync_recent
from app.models.public_announcements import PublicAnnouncement as P,PublicSourceState as S


def listing(page=1,total=3,url='https://osa.nkust.edu.tw/a'):
    return f'''<html><div id="pageptlist"><div class="d-item"><div class="mtitle"><i class="mdate">2026-10-27</i><a href="{url}">合成公告</a></div></div></div><nav class="mpgbar"><ul class="pagination"><li class="active"><a>{page}</a></li></ul><span class="pg-txt">共<span>{total}</span>頁</span></nav></html>'''.encode()


def test_listing_checks_active_page_and_explicit_last_page():
    assert parse_listing(listing(),page_number=1).has_next
    assert not parse_listing(listing(3),page_number=3).has_next
    for raw in (b'<html>login</html>',listing(2),listing(url='https://evil.invalid/')):
        with pytest.raises(PublicSourceError): parse_listing(raw,page_number=1)


def test_backfill_resumes_only_after_committed_page(database):
    db,_=database
    calls=[]
    def interrupted(page):
        calls.append(page)
        if page==2: raise PublicSourceError('PUBLIC_SOURCE_UNAVAILABLE')
        return listing(page,url=f'https://osa.nkust.edu.tw/{page}')
    r=backfill_history(db,source=interrupted,sleep=lambda _:None)
    assert r.status=='failed' and r.added==1 and calls==[1,2]
    with db.transaction() as s:
        assert s.get(S,'nkust-latest').next_history_page==2
        assert s.get(S,'nkust-latest').history_status=='incomplete'
    r=backfill_history(db,source=lambda n:listing(n,url=f'https://osa.nkust.edu.tw/{n}'),sleep=lambda _:None)
    assert r.status=='success' and r.added==2
    with db.transaction() as s:
        assert s.get(S,'nkust-latest').history_status=='complete'
        assert s.scalar(select(func.count()).select_from(P))==3


def test_repeated_page_and_malformed_end_do_not_mark_complete(database):
    db,_=database
    r=backfill_history(db,source=lambda n:listing(n),sleep=lambda _:None)
    assert r.status=='failed' and r.added==1
    with db.transaction() as s:
        assert s.get(S,'nkust-latest').next_history_page==2
        assert s.get(S,'nkust-latest').history_status=='incomplete'


@pytest.mark.parametrize('split',[False,True])
def test_nonadjacent_repeated_last_page_is_rejected_across_batches(database,split):
    db,_=database
    def source(n): return listing(n,url='https://osa.nkust.edu.tw/'+('a' if n in (1,3) else 'b'))
    if split:
        assert backfill_history(db,max_pages=2,source=source,sleep=lambda _:None).status=='success'
    result=backfill_history(db,source=source,sleep=lambda _:None)
    assert result.status=='failed'
    with db.transaction() as s:
        assert s.get(S,'nkust-latest').history_status=='incomplete'
        assert s.get(S,'nkust-latest').next_history_page==3


def test_page_budget_preserves_richer_rss_and_can_resume(database):
    db,_=database
    sync_recent(db,source=lambda:feed(item()))
    r=backfill_history(db,max_pages=1,source=lambda n:listing(n,url='https://osa.nkust.edu.tw/p/404-1.php'),sleep=lambda _:None)
    assert r.status=='success'
    with db.transaction() as s:
        row=s.scalar(select(P))
        assert row.excerpt=='學生申請'
        assert row.published_at.replace(tzinfo=timezone.utc)==datetime(2026,10,27,7,tzinfo=timezone.utc)
        assert s.get(S,'nkust-latest').next_history_page==2
        assert s.get(S,'nkust-latest').history_status=='incomplete'


@pytest.mark.parametrize('budget',[0,21,-1])
def test_history_rejects_unbounded_page_budget(database,budget):
    with pytest.raises(ValueError): backfill_history(database[0],max_pages=budget)
