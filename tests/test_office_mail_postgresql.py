from sqlalchemy import select,func
import pytest
from tests.test_postgresql import database
from tests.test_office_mail_pages import seed_office
from app.services.office_mail_views import list_office_mail
from app.services.public_sync import SourceLease
from app.services.public_source import PublicSourceError
from app.services.office_mail_source import OFFICE_SOURCE_KEY


def test_postgres_json_priority_precedes_pagination(database):
    db,_=database;values=seed_office(db,24)
    a=list_office_mail(db,campuses=('jiangong',),mode='priority')
    b=list_office_mail(db,campuses=('jiangong',),mode='priority',page_number=2)
    assert [x['id'] for x in a['items'][:3]]==[values[1],values[0],values[2]]
    assert a['total']==24 and len(b['items'])==4
    assert len({x['id'] for x in a['items']+b['items']})==24
    all_rows=list_office_mail(db,campuses=('jiangong',),mode='all')
    assert [x['id'] for x in all_rows['items']]==list(reversed(values))[:20]


def test_postgres_office_lease_blocks_same_source_but_not_rss(database):
    db,_=database;a=SourceLease(db,source_key=OFFICE_SOURCE_KEY);other=SourceLease(db,source_key=OFFICE_SOURCE_KEY);rss=SourceLease(db)
    a.acquire()
    try:
        with pytest.raises(PublicSourceError,match='PUBLIC_SYNC_BUSY'):other.acquire()
        rss.acquire();rss.release()
    finally:a.release()
    other.acquire();other.release()
