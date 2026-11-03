"""Bounded company story deduplication, independent of sending and scoring."""
from datetime import datetime, timedelta
import hashlib
import json
import re
from filter import normalize_text

COMPANIES={
 'apple':('apple','aapl'),'microsoft':('microsoft','msft'),
 'nvidia':('nvidia','nvda'),'amazon':('amazon','amzn'),
 'alphabet':('alphabet','google','googl'),'meta':('meta','meta platforms'),
 'tesla':('tesla','tsla'),'palantir':('palantir','pltr'),
 'intel':('intel','intc'),'amd':('amd','advanced micro devices'),
}
def has(text,pattern):return re.search(pattern,text) is not None

def company_names(title):
 t=normalize_text(title)
 return tuple(name for name,aliases in COMPANIES.items() if any(has(t,r'\b'+re.escape(a)+r'\b') for a in aliases))

def is_company_preview(title):
 t=normalize_text(title)
 if has(t,r'\b(?:cuts?|raises?|forecasts?|warns?|announces?)\b') and has(t,r'\b(?:margin|revenue|sales|profit|guidance)\b'):return False
 return bool(company_names(t) and has(t,r'\b(?:earnings|results)\b') and (
  has(t,r'\b(?:preview|what to (?:watch|expect)|ahead of|key variable)\b') or
  has(t,r'\bearnings (?:outlook|expectations)\s*:')))

def signatures(title):
 t=normalize_text(title);companies=company_names(t)
 if not companies or is_company_preview(t):return []
 # Keep deals, regulation, product/supply news and personnel outside these families.
 if has(t,r'\b(?:acqui\w*|merger|fined|fines?|antitrust|lawsuit|recall\w*|resigns?|appointed|steps down|ceo quits)\b'):return []
 if has(t,r'\b(?:restate\w*|corrects?|corrected|revision|revises|revised)\b'):
  # Explicit corrections with new headline facts must remain visible.
  facts=re.findall(r'[-+]?\d+(?:[.,]\d+)?\s*(?:%|billion|million|bn|bps)?',t)
  if not facts:return []
  topic='correction';value={'facts': '|'.join(facts)}
 elif has(t,r'\b(?:shares?|stocks?)\b') and has(t,r'\b(?:slide\w*|slid|slump\w*|fall\w*|fell|drop\w*|sink\w*|sank|plunge\w*|tumble\w*|declin\w*|rise\w*|rose|ris\w*|jump\w*|surge\w*|rall\w*|gain\w*)\b'):
  if not has(t,r'\b(?:earnings|results|profit|revenue|margin|guidance|outlook|post.bell)\b'):return []
  down=has(t,r'\b(?:slide\w*|slid|slump\w*|fall\w*|fell|drop\w*|sink\w*|sank|plunge\w*|tumble\w*|declin\w*)\b')
  up=has(t,r'\b(?:rise\w*|rose|ris\w*|jump\w*|surge\w*|rall\w*|gain\w*)\b')
  # Mixed-direction multi-company headlines cannot be assigned to each ticker safely.
  if down and up:return []
  topic='reaction';value={'direction':'down' if down else 'up','milestone':0}
  # Attribute a percentage only to a single-company headline.
  if len(companies)==1:
   moves=[abs(float(v.replace(',','.'))) for v in re.findall(
    r'\b(?:shares?|stock)\s+(?:\w+\s+){0,2}(?:slump\w*|fall\w*|fell|drop\w*|plunge\w*|tumble\w*|slide\w*|slid|rise\w*|rose|jump\w*|surge\w*|rall\w*|gain\w*)'
    r'\s+(?:by\s+|as much as\s+|more than\s+|over\s+|nearly\s+)?([-+]?\d+(?:[.,]\d+)?)\s*%',t)]
   if moves:value['milestone']=max((b for b in (5,10,20,30) if max(moves)>=b),default=0)
 elif has(t,r'\b(?:forecast\w*|guidance|outlook|expects?|projects?)\b') and has(t,r'\b(?:raises?|raised|hikes?|higher|growth|strong\w*|upbeat|cuts?|lower\w*|drop\w*|declin\w*|weak\w*|downbeat|warn\w*)\b'):
  topic='guidance'
  up=has(t,r'\b(?:raises?|raised|hikes?|higher|growth|strong\w*|upbeat)\b')
  down=has(t,r'\b(?:cuts?|lower\w*|drop\w*|declin\w*|weak\w*|downbeat|warn\w*)\b')
  metric='margin' if 'margin' in t else 'revenue' if has(t,r'\b(?:revenue|sales)\b') else 'earnings' if has(t,r'\b(?:earnings|profit|eps)\b') else 'outlook'
  value={'direction':'mixed' if up and down else 'down' if down else 'up','metric':metric}
  # A newly announced change to a numeric forecast is a distinct update.
  if has(t,r'\b(?:cuts?|raises?|revis\w*)\b') and (m:=re.search(r'\bto\s+([$€£]?\s*\d+(?:[.,]\d+)?\s*(?:%|billion|million|bn)?)',t)):
   value['new_target']=m.group(1).strip()
 elif has(t,r'\b(?:earnings|results|quarterly|revenue|profit|eps)\b') and has(t,r'\b(?:reports?|reported|posts?|posted|beats?|beat|miss\w*|tops?|topped|exceeds?|stronger.than.expected|better.than.expected)\b'):
  topic='earnings'
  up=has(t,r'\b(?:beats?|beat|tops?|topped|exceeds?|stronger.than.expected|better.than.expected)\b')
  down=has(t,r'\b(?:miss\w*|below (?:estimates|expectations)|weaker.than.expected)\b')
  value={'direction':'mixed' if up and down else 'beat' if up else 'miss' if down else 'reported'}
 else:return []
 if m:=re.search(r'\bq([1-4])\b',t):value['quarter']=m.group(1)
 if m:=re.search(r'\b(20\d{2})\b',t):value['year']=m.group(1)
 return [(f'company:{name}:{topic}',dict(value)) for name in companies]

def covered(base,value,prior):
 if base!=prior.get('base'):return False
 old=prior.get('value',{})
 if not isinstance(old,dict):return False
 for field in ('quarter','year'):
  if field in value and field in old and value[field]!=old[field]:return False
 if base.endswith(':reaction'):
  return old.get('direction')==value.get('direction') and old.get('milestone',0)>=value.get('milestone',0)
 if base.endswith(':earnings'):
  return value.get('direction')=='reported' or old.get('direction')==value.get('direction')
 if base.endswith(':guidance'):
  return (old.get('metric')==value.get('metric') and old.get('direction')==value.get('direction')
          and ('new_target' not in value or old.get('new_target')==value['new_target']))
 return old==value

def event_record(base,value):
 key=base+'|'+hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
 return {'key':key,'base':base,'value':value}

def deduplicate_company_stories(rows,seen_events,now):
 history=[]
 for record in (seen_events or {}).values():
  if not isinstance(record,dict):continue
  try:sent=datetime.fromisoformat(record['sent_at'].replace('Z','+00:00'))
  except (KeyError,TypeError,ValueError):continue
  if sent.tzinfo and timedelta(0)<=now-sent<timedelta(hours=24):history.append(record)
 selected=[]
 for row in rows:
  row['company_events']=[]
  facts=signatures(row['title']) if row.get('category')=='EQUITIES' else []
  if facts and all(any(covered(base,value,p) for p in history) for base,value in facts):
   row.update(decision='duplicate_company_story',reason='Même information sur la même entreprise déjà couverte depuis moins de 24 heures')
   continue
  row['company_events']=[event_record(base,value) for base,value in facts]
  history.extend(row['company_events']);selected.append(row)
 return selected
