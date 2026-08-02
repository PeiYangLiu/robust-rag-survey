import json, time, urllib.request, re
from pathlib import Path
RAW = Path("supplement/bib_upgrade/raw")
def get(url, accept="*/*"):
    req=urllib.request.Request(url,headers={"User-Agent":"robust-rag-bib-upgrade/1.0","Accept":accept})
    with urllib.request.urlopen(req,timeout=30) as r: return r.read().decode("utf-8","replace")

# ACL Anthology bibs: key -> anthology id
anth = {"rrag032":"2026.acl-long.1151","rrag034":"2025.acl-long.319","rrag035":"2024.emnlp-main.96",
        "rrag058":"2026.eacl-long.391","rrag110":"2024.findings-emnlp.593","rrag111":"2025.acl-long.415",
        "rrag132":"2026.acl-long.1357","rrag141":"2026.findings-acl.503","rrag206":"2025.emnlp-main.549",
        "rrag006":"2026.eacl-long.361"}
print("### ACL ANTHOLOGY BIBS ###")
for k,aid in anth.items():
    try:
        bib=get(f"https://aclanthology.org/{aid}.bib")
        (RAW/f"{k}_aclanthology.bib").write_text(bib,encoding="utf-8")
        bt=re.search(r'booktitle\s*=\s*"([^"]+)"',bib,re.S)
        yr=re.search(r'year\s*=\s*"([^"]+)"',bib)
        ttl=re.search(r'title\s*=\s*"((?:[^"\\]|\\.)*)"',bib,re.S)
        print(f"{k} [{aid}]: booktitle={ (bt.group(1).strip() if bt else '??') }")
        print(f"        year={yr.group(1) if yr else '?'}  title={re.sub(chr(92)+'s+',' ',ttl.group(1)) if ttl else '?'}")
    except Exception as e:
        print(f"{k} [{aid}]: ERROR {type(e).__name__}: {e}")
    time.sleep(1.5)

# Crossref for IEEE/ACM DOIs
print("\n### CROSSREF (IEEE/ACM) ###")
cr = {"rrag051":"10.1109/SP63933.2026.00070","rrag057":"10.1145/3750555.3811900","rrag091":"10.1145/3767695.3769518"}
for k,doi in cr.items():
    try:
        raw=get(f"https://api.crossref.org/works/{urllib.parse.quote(doi,safe='') if False else doi}")
        (RAW/f"{k}_crossref.json").write_text(raw,encoding="utf-8")
        m=json.loads(raw).get("message",{})
        ct=m.get("container-title") or []
        ev=m.get("event",{})
        print(f"{k} [{doi}]: container-title={ct} event={ev.get('name','')} year={ (m.get('published',{}).get('date-parts') or [['?']])[0][0] }")
        print(f"        crossref-title={m.get('title')}")
    except Exception as e:
        print(f"{k} [{doi}]: ERROR {type(e).__name__}: {e}")
    time.sleep(1.5)

# rrag006 arxiv comment
print("\n### rrag006 arXiv comment (2601.05503) ###")
try:
    html=get("https://arxiv.org/abs/2601.05503")
    (RAW/"rrag006_arxiv.html").write_text(html,encoding="utf-8")
    m=re.search(r'<td class="tablecell comments[^"]*">(.*?)</td>', html, re.S|re.I)
    print("COMMENT:", re.sub(r"<[^>]+>","",m.group(1)).strip() if m else "(none)")
    tt=re.search(r'<meta name="citation_title" content="([^"]*)"',html)
    print("arxiv citation_title:", tt.group(1) if tt else "?")
except Exception as e:
    print("ERROR",e)
