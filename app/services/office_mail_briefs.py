"""Source-backed content sections and conservative campus relevance; no AI calls."""
import re
from app.services.office_mail_source import OfficeDocument

CAMPUS_LABELS={'jiangong':'建工','first':'第一','nanzih':'楠梓','yanchao':'燕巢','qijin':'旗津'}
_SKIP=re.compile(r'^(?:受文者|副本|聯絡地址|地址|聯絡人|承辦人|電話|分機|電子郵件|e-mail)[：:]|敬啟\s*$|^https?://|^[━─_=\s]+$',re.I)
_HEAD=re.compile(r'^【([^】]{1,120})】(.*)$')
_COURSE=re.compile(r'(?:班|班別|課程)[一二三四五六七八九十0-9]*$')


def parse_campuses(values:list[str])->tuple[str,...]:
    if not isinstance(values,(list,tuple)) or len(values)>5 or any(v not in CAMPUS_LABELS for v in values):raise ValueError('Invalid campus')
    return tuple(k for k in CAMPUS_LABELS if k in values)


def _lines(text):
    for m in re.finditer(r'[^\n]+',text):
        quote=m.group().strip()
        if not quote or _SKIP.search(quote):continue
        start=m.start()+len(m.group())-len(m.group().lstrip())
        yield {'quote':quote,'start':start,'end':start+len(quote)}


def _item(entries):
    return {'text':'\n'.join(e['quote'] for e in entries),'evidence':entries}


def _group_item(group):
    entries=([group['header']] if group['header'] else [])+group['lines']
    item=_item(entries)
    item['text']='\n'.join(e['quote'] for e in group['lines']) if group['lines'] else group['heading']
    return item


def build_office_brief(doc:OfficeDocument)->dict:
    lines=list(_lines(doc.body))
    flags={k:False for k in CAMPUS_LABELS};campus_evidence=[];global_scope=False
    for source,text in [('title',doc.title),('body',doc.body)]:
        for e in _lines(text):
            quote=e['quote']
            for key,name in CAMPUS_LABELS.items():
                if re.search(re.escape(name)+r'(?:校區|(?=停水|停電|施工|封閉|交通|課程|活動))',quote):
                    flags[key]=True;campus_evidence.append(dict(e,source=source,campus=key))
            if re.search(r'全校(?:各校區|均|皆|適用|性|停水|停電)|各校區(?:均|皆|適用)|適用(?:全校|所有校區)',quote) and not re.search(r'非全校|不是全校|不適用全校',quote):
                global_scope=True;campus_evidence.append(dict(e,source=source,campus='all'))
    groups=[{'heading':'','header':None,'lines':[]}]
    for e in lines:
        m=_HEAD.fullmatch(e['quote'])
        if m:
            groups.append({'heading':m[1],'header':e,'lines':[]})
            if m[2].strip():groups[-1]['lines'].append(e)
        else:groups[-1]['lines'].append(e)
    courses=[g for g in groups if _COURSE.search(g['heading'])]
    sections=[];warnings=[];headline=doc.title
    if courses:
        kind='training'
        benefits=[g for g in groups if re.search(r'福利|補助|獎勵|就業|優惠',g['heading']) and g not in courses]
        headline=f'{doc.department or "校方"}提供 {len(courses)} 種班別；'+('另有參訓福利與資格條件，請核對適用範圍。' if benefits else '課程內容與資格條件請見下方整理。')
        course_items=[]
        for g in courses:
            entries=[g['header']]+[e for e in g['lines'] if not re.search(r'https?://',e['quote']) or re.search(r'限|不得|資格|條件',e['quote'])]
            item=_item(entries)
            item['text']=g['heading']+'\n'+'\n'.join(e['quote'] for e in entries[1:])
            course_items.append(item)
        sections.append({'label':'班別與課程','items':course_items})
        for g in groups:
            if g in courses or not (g['lines'] or g['header']):continue
            # Unknown headings and preambles can contain controlling eligibility
            # or benefit conditions. Keep them instead of selecting only positives.
            sections.append({'label':g['heading'] or '其他說明與條件','items':[_group_item(g)]})
        warnings.append('福利與退費須符合原文條件；資格可能有身分限制或例外，不代表你已符合資格。')
    elif re.search(r'施工|停水|停電|封閉|道路|交通管制',doc.title+'\n'+doc.body):
        kind='works';buckets={'影響地點與時段':[],'封閉或停用範圍':[],'替代動線與處理方式':[]}
        for e in lines:
            q=e['quote']
            if re.search(r'建工|第一校區|楠梓|燕巢|旗津',q):label='影響地點與時段'
            elif re.search(r'改走|替代|繞道|改道|請改|因應|備水|備份',q):label='替代動線與處理方式'
            elif re.search(r'封閉|停用|停止|管制|暫停',q):label='封閉或停用範圍'
            else:label='影響地點與時段'
            buckets[label].append(e)
        sections=[{'label':label,'items':[_item([e]) for e in entries]} for label,entries in buckets.items() if entries]
        if not any(re.search(r'改走|替代|繞道|改道|請改',e['quote']) for e in lines):warnings.append('原文未明列替代動線，請核對官方原文或洽承辦單位。')
    else:
        kind='general'
        for g in groups:
            if g['lines'] or g['header']:sections.append({'label':g['heading'] or '公告內容','items':[_group_item(g)]})
        warnings.append('依原文段落整理；未能確認的重點與其他條件請核對完整原文。')
    return {'version':'office-brief-v1','kind':kind,'headline':headline,
            'headline_evidence':[g['header'] for g in courses],
            'campus_flags':flags,'campus_global':global_scope,'campus_evidence':campus_evidence,
            'sections':sections,'warnings':warnings}
