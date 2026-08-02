import json, re, unicodedata, difflib, csv
from pathlib import Path
RAW=Path("supplement/bib_upgrade/raw")
targets=json.load(open("supplement/bib_upgrade/targets.json"))
def norm(s):
    s=re.sub(r"\\[A-Za-z]+\s*"," ",s).replace("{","").replace("}","")
    s=unicodedata.normalize("NFKD",s); s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ",s.lower()).strip()
def ratio(a,b): return difflib.SequenceMatcher(None,norm(a),norm(b)).ratio()
def first_surname(a):
    f=a.split(" and ")[0].strip()
    return norm(f.split(",")[0]) if "," in f else (norm(f.split()[-1]) if f.split() else "")

# rebuild full dblp_results from cached raw
dblp={}
for k in targets:
    p=RAW/f"{k}_dblp.json"
    if not p.exists(): continue
    data=json.loads(p.read_text())
    t=targets[k]["fields"]["title"]; sn=first_surname(targets[k]["fields"].get("author",""))
    hits=data.get("result",{}).get("hits",{}).get("hit",[])
    if isinstance(hits,dict): hits=[hits]
    cand=[]
    for h in hits:
        info=h.get("info",{}); ht=info.get("title","")
        au=info.get("authors",{}).get("author",[]); au=[au] if isinstance(au,dict) else au
        anorm=norm(" ".join((a.get("text","") if isinstance(a,dict) else a) for a in au))
        v=info.get("venue",""); v=" / ".join(v) if isinstance(v,list) else v
        cand.append({"htitle":ht,"ratio":round(ratio(t,ht),3),"type":info.get("type",""),
                     "venue":v,"year":info.get("year",""),"doi":info.get("doi",""),
                     "surname_ok":bool(sn and sn in anorm)})
    dblp[k]={"bibtitle":t,"candidates":cand}
json.dump(dblp,open("supplement/bib_upgrade/dblp_results.json","w"),indent=2)
print("Rebuilt dblp_results.json with",len(dblp),"keys")

# decisions
spec=json.load(open("supplement/bib_upgrade/upgrade_spec.json"))
UPGRADED={k:v for k,v in spec.items()}
# reason for keeping misc
def best_dblp(k):
    cs=dblp[k]["candidates"]
    return cs
KEEP_REASON={
 "rrag001":"DBLP+S2: venue=arXiv.org/CoRR (preprint only); no peer-reviewed venue",
 "rrag002":"DBLP: CoRR (preprint only); no peer-reviewed venue",
 "rrag003":"DBLP: CoRR (preprint only); no peer-reviewed venue",
 "rrag004":"DBLP: CoRR (preprint only); no peer-reviewed venue",
 "rrag005":"DBLP: CoRR (preprint only); no peer-reviewed venue",
 "rrag007":"DBLP: no hits; arXiv: no acceptance comment; S2: no venue -> unverifiable",
 "rrag008":"DBLP: CoRR (preprint only); no peer-reviewed venue",
 "rrag013":"DBLP: no hits; arXiv: no acceptance comment -> unverifiable",
 "rrag044":"DBLP: CoRR (preprint only); arXiv: no acceptance comment",
 "rrag049":"DBLP: CoRR (preprint only); arXiv comment is page count only",
 "rrag093":"DBLP: CoRR (preprint only); no peer-reviewed venue",
 "rrag112":"DBLP: no hits (variant retry also 0); arXiv: no comment; S2: empty venue -> unverifiable",
 "rrag115":"DBLP: CoRR only (variant retry also CoRR); arXiv: no acceptance comment -> preprint per sources",
 "rrag127":"DBLP: CoRR (preprint only); arXiv: no acceptance comment",
 "rrag128":"DBLP: no hits; OpenReview API 403 challenge (cannot read venue) -> unverifiable",
 "rrag175":"DBLP: CoRR (preprint only); arXiv: no acceptance comment",
 "rrag017":"ALREADY @inproceedings (NeurIPS 2025); DBLP confirms; left unchanged",
}
rows=[]
allkeys="rrag001 rrag002 rrag003 rrag004 rrag005 rrag006 rrag007 rrag008 rrag013 rrag015 rrag017 rrag023 rrag032 rrag034 rrag035 rrag039 rrag044 rrag046 rrag049 rrag051 rrag057 rrag058 rrag091 rrag093 rrag110 rrag111 rrag112 rrag115 rrag127 rrag128 rrag132 rrag141 rrag175 rrag206".split()
for k in allkeys:
    if k in UPGRADED:
        m=UPGRADED[k]
        rows.append({"key":k,"decision":"upgraded->@inproceedings","venue":m["booktitle"],
                     "pub_year":m["year"],"doi":m.get("doi",""),"url":m["url"],"source":m["source"]})
    else:
        rows.append({"key":k,"decision":"kept @misc","venue":"","pub_year":"","doi":"","url":"","source":KEEP_REASON.get(k,"unverifiable")})
with open("supplement/bib_upgrade/upgrade_decisions.csv","w",newline="") as h:
    w=csv.DictWriter(h,fieldnames=["key","decision","venue","pub_year","doi","url","source"]); w.writeheader(); w.writerows(rows)
up=[r for r in rows if r["decision"].startswith("upgraded")]
print(f"decisions CSV written: {len(up)} upgraded, {len(rows)-len(up)} kept (incl rrag017 already-inproceedings)")
