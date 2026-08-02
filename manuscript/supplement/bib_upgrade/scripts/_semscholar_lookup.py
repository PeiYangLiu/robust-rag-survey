import json, re, time, unicodedata, urllib.parse, urllib.request, difflib, sys
from pathlib import Path

RAW = Path("supplement/bib_upgrade/raw")
targets = json.load(open("supplement/bib_upgrade/targets.json"))

def norm(s):
    s = re.sub(r"\\[A-Za-z]+\s*", " ", s); s = s.replace("{","").replace("}","")
    s = unicodedata.normalize("NFKD", s); s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ", s.lower()).strip()
def ratio(a,b): return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()
def first_surname(a):
    f=a.split(" and ")[0].strip()
    return norm(f.split(",")[0]) if "," in f else (norm(f.split()[-1]) if f.split() else "")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"robust-rag-bib-upgrade/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8","replace")

def fetch(k):
    t = targets[k]["fields"]["title"]
    q = urllib.parse.quote(t)
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={q}&fields=title,venue,year,externalIds,publicationVenue,publicationTypes&limit=3"
    for attempt in range(5):
        try:
            raw = get(url)
            if '"code": "429"' in raw or '"message": "Too Many Requests"' in raw:
                wait = 8*(attempt+1); print(f"{k}: 429, sleep {wait}"); time.sleep(wait); continue
            return raw
        except urllib.error.HTTPError as e:
            if e.code==429:
                wait=8*(attempt+1); print(f"{k}: HTTP429, sleep {wait}"); time.sleep(wait); continue
            return json.dumps({"error":f"HTTPError {e.code}"})
        except Exception as e:
            return json.dumps({"error":f"{type(e).__name__}: {e}"})
    return json.dumps({"error":"429_exhausted"})

keys = sys.argv[1:] if len(sys.argv)>1 else list(targets.keys())
summary={}
for k in keys:
    t = targets[k]["fields"]["title"]; sn=first_surname(targets[k]["fields"].get("author",""))
    raw = fetch(k)
    (RAW/f"{k}_semanticscholar.json").write_text(raw, encoding="utf-8")
    try: data=json.loads(raw)
    except: data={"error":"parse"}
    best=None
    if isinstance(data,dict) and "data" in data:
        for p in data.get("data",[]):
            r=ratio(t, p.get("title","") or "")
            pv=p.get("publicationVenue") or {}
            vn = (pv.get("name") if isinstance(pv,dict) else None) or p.get("venue","") or ""
            if best is None or r>best["r"]:
                best={"r":round(r,3),"venue":vn,"year":p.get("year"),"title":p.get("title",""),
                      "externalIds":p.get("externalIds",{}),"pubTypes":p.get("publicationTypes"),
                      "venue_raw":p.get("venue","")}
    summary[k]={"title":t,"best":best,"err":data.get("error") if isinstance(data,dict) else None}
    b=best
    if b: print(f"{k}: r={b['r']} venue='{b['venue']}' (raw='{b['venue_raw']}') yr={b['year']} types={b['pubTypes']} ids={b['externalIds']}")
    else: print(f"{k}: no data ({summary[k]['err']})")
    time.sleep(5)

json.dump(summary, open("supplement/bib_upgrade/semscholar_results.json","w"), indent=2)
print("DONE", len(keys))
