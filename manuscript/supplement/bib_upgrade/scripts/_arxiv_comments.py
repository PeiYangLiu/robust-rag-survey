import re, json, time, urllib.request
from pathlib import Path
RAW = Path("supplement/bib_upgrade/raw")
# key -> arxiv id
ax = {"rrag112":"2404.16032","rrag115":"2403.10131","rrag007":"2601.11004",
      "rrag013":"2501.00879","rrag015":"2506.04390","rrag044":"2311.08377",
      "rrag049":"2508.18652","rrag127":"2508.04276","rrag023":"2505.12574",
      "rrag175":"2512.14448"}
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"robust-rag-bib-upgrade/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r: return r.read().decode("utf-8","replace")
for k,aid in ax.items():
    try:
        html=get(f"https://arxiv.org/abs/{aid}")
    except Exception as e:
        print(f"{k} ({aid}): ERROR {e}"); continue
    (RAW/f"{k}_arxiv.html").write_text(html,encoding="utf-8")
    # comments
    m=re.search(r'<td class="tablecell comments[^"]*">(.*?)</td>', html, re.S|re.I)
    comment=re.sub(r"<[^>]+>","",m.group(1)).strip() if m else ""
    # citation_conference_title / journal_title meta
    conf=re.findall(r'<meta name="citation_(?:conference|journal)_title" content="([^"]*)"', html, re.I)
    doi=re.findall(r'<meta name="citation_doi" content="([^"]*)"', html, re.I)
    print(f"{k} ({aid}): COMMENT='{comment[:160]}'  conf/journal={conf} doi={doi}")
    time.sleep(2)
