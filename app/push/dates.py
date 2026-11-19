"""Confirmed deadline windows; no AI or guessed end-of-day timestamp."""
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from .contracts import ReminderWindow
from .security import PushError
TAIPEI=ZoneInfo('Asia/Taipei')
def validate_window(deadline,remind_at,now):
    try:
        if not deadline or not deadline.confirmed or now.tzinfo is None:raise ValueError()
        if deadline.kind=='date':
            day=date.fromisoformat(deadline.value)
            expiry=datetime.combine(day,time.min,TAIPEI)
            default=datetime.combine(day-timedelta(days=1),time(9),TAIPEI)
        else:
            expiry=datetime.fromisoformat(deadline.value)
            if expiry.tzinfo is None:raise ValueError()
            default=expiry-timedelta(hours=24)
        remind=remind_at if remind_at is not None else default
        if remind.tzinfo is None or not now<remind<expiry or expiry>now+timedelta(days=366):raise ValueError()
        return ReminderWindow(remind.astimezone(timezone.utc),expiry.astimezone(timezone.utc))
    except (ValueError,TypeError,OverflowError):raise PushError('PUSH_DATE_CONFIRMATION_REQUIRED') from None
