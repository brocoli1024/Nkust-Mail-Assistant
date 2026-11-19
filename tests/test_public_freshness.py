from datetime import datetime,timedelta,timezone
from tests.test_multi_user_database import database
from app.api.public_announcements import status_data
from app.models.public_announcements import PublicSourceState

def test_hourly_refresh_warns_when_over_two_hours_old(database):
    db,_=database;updated=datetime(2026,10,31,2,tzinfo=timezone.utc)
    with db.transaction() as s:
        s.add(PublicSourceState(source_key='nkust-latest',last_success_at=updated))
    with db.transaction() as s:
        assert not status_data(s,now=updated+timedelta(hours=1))['is_stale']
        assert not status_data(s,now=updated+timedelta(hours=2))['is_stale']
        assert status_data(s,now=updated+timedelta(hours=2,seconds=1))['is_stale']
