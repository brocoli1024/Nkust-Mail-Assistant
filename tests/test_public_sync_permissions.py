"""Opt-in least-privilege contract on disposable PostgreSQL only."""
import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from tests.test_postgresql import database
from tests.test_public_source import feed,item
from app.database.multi_user import MultiUserDatabase
from app.services.public_sync import sync_recent

def test_scheduled_role_can_sync_but_not_read_private_or_delete(database,monkeypatch):
    raw=os.environ.get('NKUST_TEST_PUBLIC_SYNC_URL')
    if not raw:pytest.skip('independent restricted PostgreSQL role absent')
    db,_=database
    with db.transaction() as s:
        schema=s.scalar(text('select current_schema()'))
        assert schema.startswith('nkust_test_')
        s.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO nkust_public_sync'))
        grant=Path('scripts/sql/public_sync_grants.sql').read_text(encoding='utf-8-sig')
        for statement in grant.split(';'):
            if 'GRANT SELECT ON public.alembic_version' in statement or 'GRANT SELECT, INSERT' in statement or 'GRANT USAGE, SELECT' in statement:
                s.execute(text(statement.replace('public.',f'"{schema}".')))
    limited=MultiUserDatabase(make_url(raw).update_query_dict({'options':f'-csearch_path={schema}'}))
    try:
        assert sync_recent(limited,source=lambda:feed(item(url='https://ord.nkust.edu.tw/p/404-1009-108001.php'))).status=='success'
        with limited.transaction() as s:assert s.scalar(text('select count(*) from public_source_versions'))==1
        from app.services.public_articles import refresh_articles
        from app.services.linked_registration import parse_form
        form_url='https://docs.google.com/forms/d/e/synthetic-form/viewform'
        form=parse_form(b'<form><div role="heading" aria-level="1">Synthetic 2026</div><div role="heading" aria-level="3">Name <span aria-label="Required question">*</span></div><input value="PRIVATE-ANSWER"></form>',form_url)
        monkeypatch.setattr('app.services.linked_registration.fetch_registration',lambda url:dict(form,initial_url=url))
        assert refresh_articles(limited,source=lambda url:{'text':'活動日期：2026年10月31日','links':[form_url]},sleep=lambda _:None).updated==1
        with limited.transaction() as s:
            from app.models.source_history import PublicSourceVersion
            snapshot=s.scalar(select(PublicSourceVersion).order_by(PublicSourceVersion.id.desc())).snapshot
            assert snapshot['card']['fields']['materials']['value']=='填表資料：Name'
            assert 'PRIVATE-ANSWER' not in str(snapshot)

        for query in ['select * from emails','select * from users','select * from private_todos',
            'select * from private_action_snapshots','select * from private_source_versions',
            'delete from public_announcements','create table forbidden(id int)']:
            with pytest.raises(DBAPIError):
                with limited.transaction() as s:s.execute(text(query))
    finally:limited.close()
