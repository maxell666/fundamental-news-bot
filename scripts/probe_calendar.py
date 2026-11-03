"""Read-only checks of the public calendar used for release alerts."""
from pathlib import Path
import json
import requests
p=Path("calendar_probe");p.mkdir(exist_ok=True)
for name,url in (("week","https://nfs.faireconomy.media/ff_calendar_thisweek.json"),
                 ("calendar","https://www.forexfactory.com/calendar?day=nov3.2026")):
    try:
        r=requests.get(url,timeout=(3,15),allow_redirects=False,headers={"User-Agent":"FundamentalNewsBot/Calendar","Cache-Control":"no-cache"})
        print(name,r.status_code,len(r.content))
        if r.status_code==200 and len(r.content)<3000000:
            (p/(name+".txt")).write_text(r.text)
    except requests.RequestException:
        print(name,"unavailable")
