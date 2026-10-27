import pytest
from sqlalchemy import select
from tests.test_multi_user_database import database
from tests.test_public_source import feed,item
from app.models.public_announcements import PublicAnnouncement as P
from app.services.public_sync import sync_recent, reclassify
from app.services.student_relevance import classify_student_relevance


@pytest.mark.parametrize('title,excerpt,status', [
    ('獎助學金申請','','relevant'),
    ('教師專屬研習：課程設計','','not_student'),
    ('研究計畫說明會','','unknown'),
    ('科技講座','歡迎全校師生參加','relevant'),
    ('講座','','unknown'),
    ('一般徵才公告','','unknown'),
    ('教師專屬研習','本次研習提供獎學金案例教材','not_student'),
    ('多益報名說明會','本活動僅限教師參加','not_student'),
    ('教師研習：協助學生申請獎學金','','not_student'),
    ('學生實習媒合','','relevant'),
    ('ＴＯＥＩＣ 多益報名','','relevant'),
    ('','','unknown'),
])
def test_conservative_student_relevance(title,excerpt,status):
    result=classify_student_relevance(title,excerpt)
    assert result.status==status
    assert result.rule_version and (result.reasons or status=='unknown')


def test_rules_recorded_on_sync_and_can_reclassify_without_network(database):
    db,_=database
    sync_recent(db,source=lambda:feed(item()))
    with db.transaction() as s:
        row=s.scalar(select(P))
        assert row.student_relevance=='relevant' and row.category=='獎學金'
        row.title='教師專屬研習'
        row.excerpt=''
    assert reclassify(db).updated==1
    with db.transaction() as s:
        row=s.scalar(select(P))
        assert row.student_relevance=='not_student' and row.student_rule_version
