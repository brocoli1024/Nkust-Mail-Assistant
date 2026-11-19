from types import SimpleNamespace
import pytest
from app.services.source_history import official_identity,public_snapshot,private_snapshot,snapshot_changes

URL='https://www.nkust.edu.tw/p/406-1000-12345.php?Lang=zh-tw'

def test_official_article_identity_is_exact_and_conservative():
    assert official_identity(URL+'#section')==URL
    assert official_identity(URL.replace('www.nkust','WWW.NKUST'))==URL
    assert official_identity(URL+'2')!=official_identity(URL)
    assert official_identity(URL.replace('/406-','/404-'))!=official_identity(URL)
    assert official_identity(URL.replace('www.nkust','nkust'))!=official_identity(URL)
    for raw in ['https://www.nkust.edu.tw/','https://www.nkust.edu.tw/p/422-1000-1001.php','https://www.nkust.edu.tw/p/503-1000-1001.php','https://evil.invalid/p/406-1000-12345.php',URL.replace('https:','http:'),None,'javascript:alert(1)']:
        assert official_identity(raw) is None


def snapshot(text,version='v1'):
    row=SimpleNamespace(email_id=1,user_id=1,source_index=0,source_fingerprint='a'*64,title='合成公告',original_text=text,original_html='<p>'+text+'</p>',url=URL,event_date=None,deadline=None,date_evidence=[],source_category='活動')
    email=SimpleNamespace(user_id=1,received_at=None,parser_version=version)
    return private_snapshot(row,email)


def test_snapshot_retains_raw_evidence_and_distinguishes_source_and_parser_change():
    old=snapshot('報名截止：2026年11月10日');new=snapshot('報名截止：2026年11月12日')
    changes=snapshot_changes(old,new)
    assert any('2026-11-10' in s and '2026-11-12' in s for s in changes)
    assert new['html']=='<p>報名截止：2026年11月12日</p>'
    pending=snapshot('報名截止尚待公告')
    assert any('待確認' in s for s in snapshot_changes(old,pending))
    assert any('解析' in s for s in snapshot_changes(old,snapshot('報名截止：2026年11月10日','v2')))
    assert snapshot_changes(old,old)==[]
