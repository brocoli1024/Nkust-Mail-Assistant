"""Minimal in-page calendar information; no persistence or external requests."""
from app.schemas.action_cards import ActionCard


def calendar_payload(card,*,snapshot=False):
    if not isinstance(card,ActionCard):card=ActionCard.model_validate(card)
    return {'schema_version':1,'source':{'kind':card.source.kind,'source_ref':card.source.source_ref,
        'title':card.source.title[:500],'url':card.source.url},'baseline_hash':card.baseline_hash,
        'summary':(card.fields['summary'].value or '')[:160],'action':(card.fields['action'].value or '')[:1200],
        'dates':{key:{'value':card.fields[key].value,'state':card.fields[key].state,
            'evidence':[e.quote[:2000] for e in card.fields[key].evidence[:5]]} for key in ('event_date','deadline')},
        'time_status':card.time_status,'context':'snapshot' if snapshot else 'current'}
