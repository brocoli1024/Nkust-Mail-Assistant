"""Display only verified calendar dates; never infer event end or ticket eligibility."""
from datetime import date,datetime
from app.services.public_source import TAIPEI


def reading_dates(card, *, now):
    if now.tzinfo is None:raise ValueError('Aware display time required')
    today=now.astimezone(TAIPEI).date().isoformat()
    dates=[];notices=[]
    article=card.source.metadata.get('article') or {}
    for key,label in (('deadline','截止'),('event_date','活動')):
        field=card.fields[key]
        if (article.get('stale') or article.get('error')) and field.origin!='user':continue
        if field.state not in ('supported','user_confirmed') or not field.value:continue
        try:
            if date.fromisoformat(field.value).isoformat()!=field.value:continue
        except (ValueError,TypeError):continue
        dates.append({'key':key,'label':label,'value':field.value})
        if field.value<today:
            notices.append('截止日期已過，其他流程請核對來源。' if key=='deadline' else '活動日期已過，是否仍可辦理請核對來源。')
        elif key=='deadline' and field.value==today:notices.append('今日截止，確切時間請核對原文。')
    return {'dates':dates,'notices':notices,'pending':'來源待更新，日期請重新核對' if article.get('stale') or article.get('error') else '日期待確認'}
