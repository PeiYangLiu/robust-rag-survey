import json, re, time, unicodedata, urllib.parse, urllib.request, difflib, sys
from pathlib import Path

RAW = Path("supplement/bib_upgrade/raw")
RAW.mkdir(parents=True, exist_ok=True)
targets = json.load(open("supplement/bib_upgrade/targets.json"))

def norm(s):
    s = re.sub(r"\\[A-Za-z]+\s*", " ", s)
    s = s.replace("{","").replace("}","")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ", s.lower()).strip()

def ratio(a,b): return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()

def first_author_surname(author_field):
    # author_field is "First Last and First Last" OR "Last, First and ..."
    first = author_field.split(" and ")[0].strip()
    if "," in first:
        return norm(first.split(",")[0])
    return norm(first.split()[-1]) if first.split() else ""

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"robust-rag-bib-upgrade/1.0 (mailto:research@example.org)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8","replace")

results = {}
keys = sys.argv[1:] if len(sys.argv)>1 else list(targets.keys())
for k in keys:
    t = targets[k]["fields"]["title"]
    au = targets[k]["fields"].get("author","")
    surname = first_author_surname(au)
    q = urllib.parse.quote(t)
    url = f"https://dblp.org/search/publ/api?q={q}&format=json&h=5"
    try:
        raw = get(url)
    except Exception as e:
        print(f"{k}: DBLP ERROR {type(e).__name__}: {e}")
        results[k]={"error":str(e)}
        time.sleep(2.5); continue
    (RAW/f"{k}_dblp.json").write_text(raw, encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"{k}: JSON parse error {e}"); time.sleep(2.5); continue
    hits = data.get("result",{}).get("hits",{}).get("hit",[])
    if isinstance(hits, dict): hits=[hits]
    cand = []
    for h in hits:
        info = h.get("info",{})
        htitle = info.get("title","")
        r = ratio(t, htitle)
        # authors
        au_field = info.get("authors",{}).get("author",[])
        if isinstance(au_field, dict): au_field=[au_field]
        anames = [ (a.get("text","") if isinstance(a,dict) else a) for a in au_field ]
        anorm = norm(" ".join(anames))
        surname_ok = surname and surname in anorm
        venue = info.get("venue","")
        if isinstance(venue, list): venue = " / ".join(venue)
        cand.append({
            "htitle": htitle, "ratio": round(r,3), "type": info.get("type",""),
            "venue": venue, "year": info.get("year",""), "doi": info.get("doi",""),
            "ee": info.get("ee",""), "url": info.get("url",""),
            "surname_ok": bool(surname_ok), "authors": anames,
        })
    results[k]={"bibtitle":t,"surname":surname,"candidates":cand}
    # print concise
    print(f"=== {k}: {t[:70]}")
    for c in cand:
        flag = "OK" if (c["ratio"]>=0.90 and c["surname_ok"]) else "  "
        print(f"   [{flag}] r={c['ratio']} type='{c['type']}' venue='{c['venue']}' yr={c['year']} doi={c['doi']}")
    if not cand: print("   (no hits)")
    time.sleep(2.5)

json.dump(results, open("supplement/bib_upgrade/dblp_results.json","w"), indent=2)
print("\nDONE", len(keys), "keys")
