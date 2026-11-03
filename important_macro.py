"""Recurring, free calendar results. No official-source or live-price claim."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import time
from zoneinfo import ZoneInfo
import requests
from macro_watch import write_json, timestamp, parse_time, retry_delay, HTTPResult, EXPECTED_BOT

UTC=timezone.utc
WEEK='https://nfs.faireconomy.media/ff_calendar_thisweek.json'
STATE=Path('macro_events.json')
# Exact numeric releases only. Speeches, votes, statements and elections remain news.
RULES={}
def rule(names, label, family, countries):
    for name in names:
        RULES[name]=(label, family, frozenset(countries.split()))
rule(['CPI m/m','CPI y/y'], 'Inflation CPI', 'inflation','USD EUR GBP CHF')
rule(['Core CPI m/m','Core CPI y/y'], 'Inflation CPI hors énergie/alimentation','inflation','USD EUR GBP')
rule(['Core PCE Price Index m/m','PCE Price Index m/m'], 'Inflation PCE','inflation','USD')
rule(['PPI m/m','Core PPI m/m'], 'Prix à la production','inflation','USD')
rule(['Average Hourly Earnings m/m'], 'Salaires horaires','inflation','USD')
rule(['Non-Farm Employment Change','ADP Non-Farm Employment Change'], 'Créations d’emplois','growth','USD')
rule(['Unemployment Rate','Unemployment Claims','Claimant Count Change'], 'Chômage','unemployment','USD GBP EUR CHF')
rule(['JOLTS Job Openings'], 'Offres d’emploi JOLTS','growth','USD')
rule(['Advance GDP q/q','Prelim GDP q/q','Final GDP q/q','GDP m/m','GDP q/q','GDP y/y','German Prelim GDP q/q'], 'Croissance PIB','growth','USD EUR GBP')
rule(['Retail Sales m/m','Core Retail Sales m/m'], 'Ventes au détail','growth','USD GBP')
rule(['ISM Manufacturing PMI','ISM Services PMI','Chicago PMI'], 'Enquête d’activité PMI','growth','USD')
rule(['Flash Manufacturing PMI','Flash Services PMI','German Flash Manufacturing PMI','German Flash Services PMI','French Flash Manufacturing PMI','French Flash Services PMI'], 'Enquête d’activité PMI','growth','USD EUR GBP')
rule(['Prelim UoM Consumer Sentiment','CB Consumer Confidence'], 'Confiance des ménages','growth','USD')
rule(['CPI Flash Estimate y/y','Core CPI Flash Estimate y/y','German Prelim CPI m/m'], 'Inflation européenne','inflation','EUR')
rule(['Federal Funds Rate','Main Refinancing Rate','Deposit Facility Rate','Official Bank Rate','SNB Policy Rate'], 'Décision de taux','rate','USD EUR GBP CHF')
# Correct a title's country, rather than allowing the same title for any bank.
for name,country in [('Federal Funds Rate','USD'),('Main Refinancing Rate','EUR'),('Deposit Facility Rate','EUR'),('Official Bank Rate','GBP'),('SNB Policy Rate','CHF')]:
    label,family,_=RULES[name];RULES[name]=(label,family,frozenset([country]))


def number(raw):
    if not isinstance(raw,str):raise ValueError('Valeur absente')
    m=re.fullmatch(r'([+-]?\d+(?:\.\d+)?)(%|K|M|B)?',raw.strip())
    if not m:raise ValueError('Unité non reconnue')
    value=Decimal(m[1]);unit=m[2] or ''
    if unit in ('K','M','B'):value*=Decimal({'K':1000,'M':1000000,'B':1000000000}[unit]);unit='count'
    return value,unit


def day_url(at):
    # Numeric month map avoids locale-dependent strftime abbreviations.
    return 'https://www.forexfactory.com/calendar?day='+('jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec')[at.month-1]+str(at.day)+'.'+str(at.year)


def fetch(url):
    if url!=WEEK and not re.fullmatch(r'https://www\.forexfactory\.com/calendar\?day=[a-z]{3}\d{1,2}\.\d{4}',url):raise ValueError('Source refusée')
    try:
        with requests.get(url,timeout=(3,8),stream=True,allow_redirects=False,headers={'User-Agent':'FundamentalNewsBot/Calendar','Cache-Control':'no-cache'}) as r:
            body=bytearray()
            if r.status_code==200:
                for chunk in r.iter_content(65536):
                    body.extend(chunk)
                    if len(body)>3_000_000:raise ValueError('Réponse trop volumineuse')
            return HTTPResult(r.status_code,body.decode('utf-8',errors='replace'),dict(r.headers))
    except requests.RequestException:raise ValueError('Source indisponible') from None


def page_events(body):
    # Parse JSON data, never execute the site's JavaScript.
    matches=list(re.finditer(r'\bdays:\s*(?=\[)',body))
    if len(matches)!=1:raise ValueError('Calendrier ambigu')
    days=json.JSONDecoder().raw_decode(body[matches[0].end():])[0]
    events=[];seen=set()
    for day in days:
        for e in day.get('events',[]):
            if type(e.get('id')) is not int or e['id'] in seen:raise ValueError('Identifiant ambigu')
            seen.add(e['id']);events.append(e)
    return events


def selected(title,country):
    return title in RULES and country in RULES[title][2]


def upcoming(body,now):
    rows=json.loads(body)
    if not isinstance(rows,list):raise ValueError('Semaine illisible')
    result=[];seen=set()
    for e in rows:
        if not isinstance(e,dict) or not selected(e.get('title'),e.get('country')):continue
        try:at=parse_time(e['date'])
        except (ValueError,KeyError,TypeError):continue
        if at.date()!=now.date() or not 15<=(at-now).total_seconds()<=600:continue
        key=(e['title'],e['country'],timestamp(at))
        if key in seen:raise ValueError('Annonce ambiguë')
        seen.add(key);result.append((at,e))
    return sorted(result,key=lambda x:x[0])


def match_event(events,title,currency,at,event_id=None):
    rows=[e for e in events if e.get('name')==title and e.get('currency')==currency
          and type(e.get('dateline')) is int and e['dateline']==int(at.timestamp())
          and e.get('timeMasked') is False and (event_id is None or e.get('id')==event_id)]
    if len(rows)!=1:raise ValueError('Annonce exacte absente ou ambiguë')
    return rows[0]


def comparison(actual,forecast):
    a,ua=number(actual);f,uf=number(forecast)
    if ua!=uf:raise ValueError('Unités différentes')
    return a-f,ua


def fr(raw):return raw.replace('.',',') if isinstance(raw,str) and raw else 'indisponible'


def format_result(items,at,observed):
    currencies=set(i['currency'] for i in items)
    lines=['📊 RÉSULTATS ÉCONOMIQUES — '+ ' / '.join(sorted(currencies))]
    scores=[];families=set()
    for i in items:
        title=i['title'];label,family,_=RULES[title];families.add(family)
        # The exact English metric distinguishes headline/core and m/m vs y/y.
        lines.extend(['',label+' — '+title,'Publié : '+fr(i['actual']), 'Attendu : '+fr(i.get('forecast')), 'Précédent : '+fr(i.get('previous'))])
        try:
            diff,unit=comparison(i['actual'],i.get('forecast'))
        except ValueError:
            lines.append('Surprise : non calculée, attentes absentes ou unités incompatibles.');continue
        sign=(diff>0)-(diff<0)
        scores.append(-sign if family=='unemployment' else sign)
        suffix=' point de %' if unit=='%' else ' emplois' if unit=='count' else ' point'
        d=('+' if diff>0 else '')+format(diff,'f').replace('.',',')
        lines.append('Surprise : '+d+suffix)
    nonzero=set(s for s in scores if s)
    if len(scores)<len(items):conclusion='Comparaison incomplète : aucune direction déduite.'
    elif not scores:conclusion='Attentes indisponibles : aucune direction déduite.'
    elif len(nonzero)>1:conclusion='Résultats MIXTES : les chiffres donnent des indications opposées.'
    elif not nonzero:conclusion='Résultats conformes aux attentes : aucune surprise chiffrée.'
    else:
        hot=next(iter(nonzero))>0
        wording='Inflation plus forte' if families=={'inflation'} and hot else 'Inflation plus faible' if families=={'inflation'} else 'Taux plus élevé' if families=={'rate'} and hot else 'Taux plus faible' if families=={'rate'} else 'Activité/emploi plus solide' if hot else 'Activité/emploi plus faible'
        conclusion=wording+' qu’attendu.'
        if currencies=={'USD'}:
            lines.extend(['','🎯 Scénarios possibles',
                ('EUR/USD ↓ ; GBP/USD ↓ ; USD/CHF ↑ possibles' if hot else 'EUR/USD ↑ ; GBP/USD ↑ ; USD/CHF ↓ possibles'),
                'si les taux US attendus '+('montent' if hot else 'baissent')+' par rapport aux taux européens, britanniques et suisses. Le refuge CHF peut modifier USD/CHF.'])
            if families<= {'inflation','rate'}:
                lines.append('SP500 / NAS100 / US30 : '+('pression' if hot else 'soutien')+' possible si les taux US '+('montent' if hot else 'baissent')+', surtout NAS100. GER30 : effet indirect via les taux mondiaux.')
            else:
                lines.append('SP500 / NAS100 / US30 : effets opposés possibles entre bénéfices et taux. Une activité plus forte soutient les bénéfices ; une hausse des taux pèse surtout sur NAS100. GER30 : effet indirect via croissance mondiale et taux.')
        elif len(currencies)==1:
            c=next(iter(currencies));pair={'EUR':'EUR/USD','GBP':'GBP/USD','CHF':'USD/CHF'}[c]
            arrow=('↑' if hot else '↓') if c!='CHF' else ('↓' if hot else '↑')
            lines.extend(['','🎯 '+pair+' '+arrow+' possible si la surprise '+('relève' if hot else 'abaisse')+' les taux attendus '+{'EUR':'de la zone euro','GBP':'britanniques','CHF':'suisses'}[c]+' par rapport aux taux US.'])
            if c=='EUR':lines.append('GER30 : coût du financement et perspectives de croissance peuvent produire des effets opposés.')
    lines.insert(1,conclusion)
    if 'rate' in families:lines.append('Cette lecture porte sur le taux publié ; le communiqué et la conférence peuvent changer l’interprétation.')
    p=ZoneInfo('Europe/Paris');delay=(observed-at).total_seconds()
    lines.extend(['',f'Prévu : {at.astimezone(p):%d/%m %H:%M} Paris • détecté : {observed.astimezone(p):%H:%M:%S} (+{delay:.1f} s)'.replace('.',','), 'Attentes enregistrées avant annonce. Source : calendrier Forex Factory.',day_url(at)])
    return '\n'.join(lines)


def state_read(path=STATE):
    if not path.exists():return {'events':{}}
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or not isinstance(data.get('events'),dict):raise ValueError('État illisible')
    return data


def checkpoint():
    for cmd in (['git','add','--',str(STATE)],):
        if subprocess.run(cmd,capture_output=True).returncode:raise ValueError('Sauvegarde refusée')
    diff=subprocess.run(['git','diff','--cached','--quiet','--',str(STATE)],capture_output=True).returncode
    if diff not in (0,1):raise ValueError('Sauvegarde refusée')
    if diff and subprocess.run(['git','commit','-m','Save economic release state [skip ci]','--',str(STATE)],capture_output=True).returncode:raise ValueError('Sauvegarde refusée')
    for cmd in (['git','pull','--rebase','origin','main'],['git','push','origin','HEAD:main']):
        if subprocess.run(cmd,capture_output=True).returncode:raise ValueError('Sauvegarde refusée')


def watch(*,now=lambda:datetime.now(UTC),sleep=time.sleep,get=fetch,save=checkpoint,send=None,verify=None,path=STATE):
    data=state_read(path);r=get(WEEK)
    if r.status!=200:raise ValueError('Calendrier indisponible')
    candidates=upcoming(r.text,now())
    # Resume a durable pre-release snapshot after a runner interruption.
    armed=[(parse_time(k),v) for k,v in data['events'].items()
           if v.get('status')=='armed' and parse_time(k)-timedelta(seconds=600)<=now()<=parse_time(k)+timedelta(seconds=180)]
    if armed:
        at,record=min(armed,key=lambda x:x[0]);key=timestamp(at)
        if parse_time(record['forecast_at'])>=at:raise ValueError('Capture tardive')
        frozen=record['items']
    else:
        candidates=[(t,e) for t,e in candidates if timestamp(t) not in data['events']]
        if not candidates:return 'outside_window'
        at=candidates[0][0];key=timestamp(at)
        group=[e for t,e in candidates if t==at]
        response=get(day_url(at))
        if response.status!=200:raise ValueError('Source résultat indisponible')
        page=page_events(response.text);frozen=[]
        for e in group:
            source=match_event(page,e['title'],e['country'],at)
            if source.get('actual'):raise ValueError('Résultat déjà publié avant capture')
            raw=source.get('forecast','')
            if raw:number(raw)
            frozen.append({'title':e['title'],'currency':e['country'],'id':source['id'],'forecast':raw,'previous':source.get('previous','')})
        if now()>=at:return 'late_no_snapshot'
        record={'status':'armed','scheduled_at':key,'forecast_at':timestamp(now()),'items':frozen}
    if verify is None:
        from bot import verify_telegram_token
        verify=verify_telegram_token
    identity=verify()
    if identity.get('is_bot') is not True or identity.get('username','').lower()!=EXPECTED_BOT.lower():raise ValueError('Identité Telegram incorrecte')
    data['events'][key]=record;write_json(path,data);save()
    while now()<at:sleep(min(30,(at-now()).total_seconds()))
    deadline=at+timedelta(seconds=180);valid=None
    while now()<=deadline:
        try:response=get(day_url(at))
        except ValueError:response=HTTPResult(0)
        seen=now()
        if seen>deadline:break
        if response.status in (401,403):break
        delay=10
        if response.status in (429,503):delay=max(10,retry_delay(response,seen,10))
        elif response.status==200:
            try:
                entries=page_events(response.text);results=[]
                for item in frozen:
                    row=match_event(entries,item['title'],item['currency'],at,item['id'])
                    number(row.get('actual'))
                    results.append({**item,'actual':row['actual']})
                valid=(results,seen);break
            except (ValueError,KeyError,TypeError):pass
        remaining=(deadline-now()).total_seconds()
        if remaining<=0 or delay>remaining:break
        sleep(min(delay,remaining))
    message=format_result(valid[0],at,valid[1]) if valid else ('⚠️ Résultats indisponibles — '+', '.join(i['title'] for i in frozen)+'\nAucun résultat confirmé sous trois minutes. Aucune direction déduite.\n'+day_url(at))
    record.update(status='send_pending',reserved_at=timestamp(now()))
    if valid:record.update(items=valid[0],first_seen_at=timestamp(valid[1]))
    write_json(path,data);save()  # Remote intent before the sole POST.
    if now()>deadline+timedelta(seconds=120) or (valid and now()>deadline):return 'deadline_no_send'
    if send is None:
        from bot import send_telegram
        send=send_telegram
    try:send(message)
    except Exception:
        record['status']='send_uncertain';write_json(path,data);save();return 'send_uncertain'
    record.update(status='completed' if valid else 'unavailable',telegram_accepted_at=timestamp(now()))
    write_json(path,data);save();return record['status']


def dispatch(now=None,get=fetch,post=requests.post):
    now=now or datetime.now(UTC);r=get(WEEK)
    if r.status!=200:raise ValueError('Calendrier indisponible')
    due=upcoming(r.text,now)
    data=state_read()
    if not any(timestamp(at) not in data['events'] or data['events'][timestamp(at)].get('status')=='armed' for at,_ in due):return 'outside_window_or_reserved'
    token=os.environ.get('GH_TOKEN','')
    if not token or '\n' in token or '\r' in token:raise ValueError('Autorisation absente')
    try:
        r=post('https://api.github.com/repos/maxell666/fundamental-news-bot/actions/workflows/important-macro.yml/dispatches',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},json={'ref':'main'},timeout=(3,8),allow_redirects=False)
    except requests.RequestException:raise ValueError('Déclenchement non confirmé') from None
    if r.status_code!=204:raise ValueError('Déclenchement refusé')
    return 'dispatch_accepted'


def main():
    p=argparse.ArgumentParser();p.add_argument('--dispatch',action='store_true');p.add_argument('--watch',action='store_true');p.add_argument('--check',action='store_true');args=p.parse_args()
    try:
        if args.dispatch:print(dispatch())
        elif args.watch:print(watch())
        elif args.check:
            r=fetch(WEEK)
            if r.status!=200:raise ValueError('Calendrier indisponible')
            rows=json.loads(r.text)
            upcoming_rows=[e for e in rows if selected(e.get('title'),e.get('country'))]
            print(json.dumps(upcoming_rows,ensure_ascii=False,indent=2))
            current=datetime.now(UTC)
            future=[e for e in upcoming_rows if parse_time(e['date'])>current]
            pages={}
            for e in future:
                at=parse_time(e['date']);url=day_url(at)
                if url not in pages:
                    response=fetch(url)
                    if response.status!=200:raise ValueError('Source indisponible')
                    pages[url]=page_events(response.text)
                match_event(pages[url],e['title'],e['country'],at)
            print('Annonces futures vérifiées par identifiant et horaire :',len(future))
        else:p.error('Choisir --dispatch, --watch ou --check')
        return 0
    except (ValueError,OSError,TypeError,KeyError):
        print('Macro : source, calendrier, état ou sauvegarde non confirmé. Aucun résultat inventé.');return 1
if __name__=='__main__':raise SystemExit(main())
