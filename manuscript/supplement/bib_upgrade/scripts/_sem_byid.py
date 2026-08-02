import json, time, urllib.request
from pathlib import Path
RAW = Path("supplement/bib_upgrade/raw")
ids = {"rrag015":"2506.04390","rrag023":"2505.12574","rrag112":"2404.16032",
       "rrag115":"2403.10131","rrag007":"2601.11004","rrag013":"2501.00879"}
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"robust-rag-bib-upgrade/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as r: return r.read().decode("utf-8","replace")
for k,aid in ids.items():
    url=f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{aid}?fields=title,venue,year,externalIds,publicationVenue,publicationTypes"
    raw=None
    for att in range(3):
        try:
            raw=get(url)
            if '"code": "429"' in raw or 'Too Many Requests' in raw:
                time.sleep(12); raw=None; continue
            break
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(12); continue
            raw=json.dumps({"error":f"HTTP{e.code}"}); break
        except Exception as e:
            raw=json.dumps({"error":str(e)}); break
    if raw is None: raw=json.dumps({"error":"429"})
    (RAW/f"{k}_semscholar_byid.json").write_text(raw,encoding="utf-8")
    try:
        d=json.loads(raw)
        pv=d.get("publicationVenue") or {}
        print(f"{k} ({aid}): venue='{d.get('venue')}' pubVenue='{pv.get('name') if isinstance(pv,dict) else pv}' yr={d.get('year')} types={d.get('publicationTypes')} title='{(d.get('title') or '')[:50]}'")
    except Exception as e:
        print(f"{k}: {raw[:80]}")
    time.sleep(8)
