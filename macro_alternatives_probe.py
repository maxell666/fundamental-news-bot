"""Sonde unique de sources publiques macro : aucun secret ni envoi."""
import json
import re
from pathlib import Path
from macro_probe import get_public

SOURCES = {
 "ism_september": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/september/",
 "ism_october": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/october/",
 "chicago": "https://chicago.ismworld.org/news-publications/reports/research-survey/",
 "census": "https://www.census.gov/construction/c30/current/index.html",
 "calendar_next": "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
}
def main():
 directory = Path("macro_audit")
 directory.mkdir(exist_ok=True)
 for name,url in SOURCES.items():
  try:
   status,body,timing = get_public(url)
   text=body.decode("utf-8",errors="replace")
   (directory/(name+".txt")).write_text(text,encoding="utf-8")
   plain=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",text))
   patterns=("Manufacturing PMI", "Chicago Business", "Business Barometer", "Construction Spending", "ISM Manufacturing")
   snippets=[]
   for pattern in patterns:
    matches=list(re.finditer(re.escape(pattern),plain,re.I))[:3]
    snippets.extend(plain[max(0,m.start()-100):m.start()+500] for m in matches)
   if name=="calendar_next" and status==200:
    snippets=[x for x in json.loads(text) if x.get("country")=="USD" and "ISM" in x.get("title","")]
   print(json.dumps({"source":name,"http_status":status,**timing,"snippets":snippets},ensure_ascii=False))
  except Exception as error:
   print(json.dumps({"source":name,"error":type(error).__name__}))
 return 0
if __name__=="__main__":
 raise SystemExit(main())
