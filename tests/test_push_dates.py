from datetime import datetime,timezone
import pytest
from app.push.contracts import Deadline
from app.push.dates import validate_window
from app.push.security import PushError
NOW=datetime.fromisoformat('2026-11-08T00:00:00+00:00')
def deadline(kind,value,confirmed=True):return Deadline(kind=kind,value=value,confirmed=confirmed,basis='official')
def test_date_only_previous_day_taipei_0900():
    r=validate_window(deadline('date','2026-11-10'),None,NOW)
    assert r.remind_at.isoformat()=='2026-11-09T01:00:00+00:00'
    assert r.expires_at.isoformat()=='2026-11-09T16:00:00+00:00'
def test_exact_minus_24h():
    r=validate_window(deadline('datetime','2026-11-10T15:00:00+08:00'),None,NOW)
    assert r.remind_at.isoformat()=='2026-11-09T07:00:00+00:00'
@pytest.mark.parametrize('d,remind',[(deadline('date','待確認'),None),(deadline('date','2026-11-10',False),None),(deadline('date','2026-11-08'),None),(deadline('datetime','2026-11-10T12:00:00'),None),(deadline('date','2028-11-10'),None),(deadline('date','2026-11-10'),datetime.fromisoformat('2026-11-10T00:00:00+08:00'))])
def test_unknown_or_elapsed_default_requires_confirmation(d,remind):
    with pytest.raises(PushError):validate_window(d,remind,NOW)
def test_user_date_requires_explicit_confirmation():
    r=validate_window(Deadline(kind='date',value='2026-11-10',confirmed=True,basis='user'),datetime.fromisoformat('2026-11-08T09:00:00+08:00'),NOW)
    assert r.remind_at>NOW

def test_elapsed_default_requires_explicit_new_time():
    from datetime import timedelta
    with pytest.raises(PushError):validate_window(deadline('date','2026-11-09'),None,NOW+timedelta(hours=2))
