"""Conservative clause evidence layered on the existing date candidate parser."""
import re
from datetime import timezone, timedelta
from app.schemas.action_cards import Evidence, CardField
from app.services.date_parser import parse_dates

CLAUSE = re.compile(r'[^，,。；;\n]+')
NEGATIVE = re.compile(r'無須|無需|不須|不需|不用|免(?:予)?(?:報名|申請)')
ACTION = re.compile(r'(?:請|應|須|需|開放|受理).{0,30}?(?:報名|申請|繳交|繳件|提交)')


def extract(source):
    dates = {'deadline':[], 'event_date':[]}
    candidates, actions, audience, materials, warnings = [], [], [], [], []
    anchor = source.anchor if source.kind == 'private' else None
    if anchor:
        anchor=(anchor.replace(tzinfo=timezone.utc) if anchor.tzinfo is None else anchor).astimezone(timezone(timedelta(hours=8)))
    for index, segment in enumerate(source.segments):
        text = segment.text
        result = parse_dates(text, anchor)
        warnings.extend(result.warnings)
        for c in CLAUSE.finditer(text):
            clause = c.group()
            def evidence(role=None, inferred=False):
                return Evidence(segment=index, quote=clause, start=c.start(), end=c.end(), role=role, year_inferred=inferred)
            if ACTION.search(clause) and not NEGATIVE.search(clause):
                actions.append(evidence('action'))
            for pattern, target, role in ((r'(?:申請對象|適用對象|參加對象|對象|申請資格)\s*[:：]\s*(.+)', audience,'audience'),
                (r'(?:應備文件|所需材料|應備資料|申請文件)\s*[:：]\s*(.+)',materials,'materials')):
                m = re.search(pattern, clause)
                if m:
                    start = c.start()+m.start(1)
                    target.append(Evidence(segment=index, quote=m[1], start=start, end=c.start()+m.end(1), role=role))
        for d in result.evidence:
            clause_match = next((c for c in CLAUSE.finditer(text) if c.start() <= d.start < c.end()),None)
            clause = clause_match.group() if clause_match else ''
            before = text[clause_match.start():d.start] if clause_match else ''
            after = text[d.end:clause_match.end()] if clause_match else ''
            role = None
            if not re.search(r'發布|發佈|收件|收到|更新|公告日期',before):
                if re.search(r'(?:報名|申請|繳件|繳交|收件)?截止(?:日期|時間|日)?\s*[:：]?\s*$|(?:報名|申請|受理|繳交|繳件).{0,15}(?:至|到)\s*$',before) or re.match(r'\s*(?:(?:報名|申請|繳件)?截止|止|前(?:完成|報名|申請|繳交))',after):
                    role='deadline'
                elif re.search(r'(?:活動|講座|說明會|研習|舉辦|舉行)(?:日期|時間)?\s*[:：]?\s*$',before) or re.match(r'\s*(?:舉辦|舉行)(?:活動|講座|說明會|研習)',after):
                    role='event_date'
            ev = Evidence(segment=index,quote=d.original_text,start=d.start,end=d.end,role=role,year_inferred=d.year_inferred)
            candidates.append(ev)
            if role:
                other = [x for x in result.evidence if clause_match and clause_match.start() <= x.start < clause_match.end()]
                ambiguous = len(other)>1 or bool(re.search(r'明年|去年|翌年|次年|跨年',clause))
                context_ev=Evidence(segment=index,quote=clause,start=clause_match.start(),end=clause_match.end(),role=role,year_inferred=d.year_inferred)
                dates[role].append((d.iso_date,context_ev,ambiguous))
    fields = {}
    for role, values in dates.items():
        valid = {v for v,e,a in values if v and not e.year_inferred and not a}
        confirmed = len(valid)==1 and all(v and not e.year_inferred and not a for v,e,a in values)
        fields[role]=CardField(value=next(iter(valid)) if confirmed else None,
            state='supported' if confirmed else 'pending',evidence=tuple(e for v,e,a in values),
            warnings=() if confirmed else ('日期或角色待確認',))
    for role, values in (('action',actions),('audience',audience),('materials',materials)):
        unique = tuple(dict.fromkeys(e.quote for e in values))
        fields[role]=CardField(value='；'.join(unique) if unique else None,
            state='supported' if unique else 'pending',evidence=tuple(values))
    return fields,tuple(candidates),tuple(dict.fromkeys(warnings))
