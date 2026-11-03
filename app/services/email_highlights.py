"""Read-only, extractive highlights of one owned email announcement.

Presentation only: no AI/network calls, database writes, or changes to action-card
baselines. Quotes and offsets always refer to the original private segment.
"""
import re

_SENTENCE = re.compile(r'[^\n。！？!?]+[。！？!?]*')
_PURPOSE = re.compile(r'舉辦|辦理|招募|徵求|徵件|開放|提供|工作坊|講座|說明會|研討會')
_ACTION = re.compile(r'請|報名|申請|繳交|繳件|填寫|攜帶|自備|不需|無須|不得|不受理')
_FACT = re.compile(r'截止|期限|活動日期|活動時間|地點|對象|資格|材料|費用|免費|繳費')
_NOISE = re.compile(r'^(?:各位.*(?:您好|大家好)[：:，,。！!]*|(?:敬祝|順頌|謝謝|感謝您的閱讀|此為系統|退訂).*|(?:承辦人|聯絡人|聯絡電話|電話|分機|電子郵件|E-?mail)\s*[：:].*|https?://\S+)$',re.I)


def email_highlights(card):
    """Select at most three useful original sentences, retaining source order."""
    summary=card.fields['summary']
    if summary.origin=='user':
        return {'kind':'personal' if summary.value else 'pending',
                'value':summary.value,'points':[]}
    candidates=[]
    seen=set()
    for segment_index,segment in enumerate(card.source.segments):
        if segment.kind!='original':continue
        for match in _SENTENCE.finditer(segment.text):
            raw=match.group();quote=raw.strip()
            if not quote:continue
            score=4*bool(_PURPOSE.search(quote))+3*bool(_ACTION.search(quote))+2*bool(_FACT.search(quote))
            if _NOISE.fullmatch(quote) and not score:continue
            # Formatting is ignored for deduplication only; displayed quotes are
            # never rewritten, and negations/conditions remain in the sentence.
            key=re.sub(r'^[\s\d一二三四五六七八九十、.．)）(（•·-]+','',quote)
            if key in seen:continue
            seen.add(key)
            start=match.start()+len(raw)-len(raw.lstrip())
            candidates.append({'segment':segment_index,'start':start,'end':start+len(quote),
                               'quote':quote,'text':quote,
                               'score':score})
    selected=sorted(candidates,key=lambda p:(-p['score'],p['segment'],p['start']))[:3]
    selected.sort(key=lambda p:(p['segment'],p['start']))
    return {'kind':'extracted' if selected else 'empty','value':None,
            'points':[{k:v for k,v in p.items() if k!='score'} for p in selected]}
