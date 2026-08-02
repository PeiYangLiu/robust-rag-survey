import re, json
from pathlib import Path

RAW = Path("supplement/bib_upgrade/raw")

def anth_booktitle(key):
    bib = (RAW/f"{key}_aclanthology.bib").read_text(encoding="utf-8")
    m = re.search(r'booktitle\s*=\s*"([^"]+)"', bib, re.S)
    return re.sub(r"\s+"," ", m.group(1)).strip()

def crossref_ct(key):
    d = json.loads((RAW/f"{key}_crossref.json").read_text(encoding="utf-8"))
    return d["message"]["container-title"][0]

# Per-key upgrade metadata. type: inproceedings for all here.
# fields to add (besides preserved title/author): booktitle, year, doi(optional), url
UP = {}
# ACL Anthology confirmed (DBLP + anthology)
for key, aid in {
    "rrag006":"2026.eacl-long.361","rrag032":"2026.acl-long.1151","rrag034":"2025.acl-long.319",
    "rrag035":"2024.emnlp-main.96","rrag058":"2026.eacl-long.391","rrag110":"2024.findings-emnlp.593",
    "rrag111":"2025.acl-long.415","rrag132":"2026.acl-long.1357","rrag141":"2026.findings-acl.503",
    "rrag206":"2025.emnlp-main.549",
}.items():
    year = aid.split(".")[0]
    UP[key] = {"booktitle":anth_booktitle(key),"year":year,
               "doi":f"10.18653/v1/{aid}","url":f"https://aclanthology.org/{aid}/",
               "source":"DBLP + ACL Anthology .bib"}
# Crossref (IEEE/ACM)
UP["rrag051"] = {"booktitle":crossref_ct("rrag051"),"year":"2026","doi":"10.1109/SP63933.2026.00070",
                 "url":"https://doi.org/10.1109/SP63933.2026.00070","source":"DBLP + Crossref"}
UP["rrag057"] = {"booktitle":crossref_ct("rrag057"),"year":"2026","doi":"10.1145/3750555.3811900",
                 "url":"https://doi.org/10.1145/3750555.3811900","source":"DBLP + Crossref"}
UP["rrag091"] = {"booktitle":crossref_ct("rrag091"),"year":"2025","doi":"10.1145/3767695.3769518",
                 "url":"https://doi.org/10.1145/3767695.3769518","source":"DBLP + Crossref"}
# ICLR (DBLP + OpenReview, no DOI)
UP["rrag039"] = {"booktitle":"International Conference on Learning Representations (ICLR)","year":"2025",
                 "url":"https://openreview.net/forum?id=oU3tpaR8fm","source":"DBLP (ICLR, OpenReview)"}
UP["rrag046"] = {"booktitle":"International Conference on Learning Representations (ICLR)","year":"2024",
                 "url":"https://openreview.net/forum?id=auKAUJZMO6","source":"DBLP (ICLR, OpenReview)"}
# arXiv-comment confirmed acceptances (very recent; not yet indexed)
UP["rrag015"] = {"booktitle":"International Conference on Machine Learning (ICML)","year":"2026",
                 "url":"https://arxiv.org/abs/2506.04390","source":"arXiv comment: 'Accepted at ICML 2026'"}
UP["rrag023"] = {"booktitle":"ACM SIGKDD Conference on Knowledge Discovery and Data Mining (KDD)","year":"2026",
                 "url":"https://arxiv.org/abs/2505.12574","source":"arXiv comment: 'Accepted by KDD 2026'"}

# ---- Locate and parse existing misc blocks ----
text = Path("auto_references.bib").read_text(encoding="utf-8")

def find_block(key):
    m = re.search(r"@misc\{\s*"+re.escape(key)+r"\s*,", text)
    if not m: return None
    start = m.start(); depth=0; i=m.end()-1
    # find opening brace of entry
    # start scanning from '@' : the first '{' after key start
    ob = text.index("{", m.start())
    depth=1; i=ob+1
    while i < len(text) and depth:
        if text[i]=="{": depth+=1
        elif text[i]=="}": depth-=1
        i+=1
    return start, i  # [start, end) end just after closing brace

def parse_fields(body):
    # returns dict of field->raw value (brace/quote stripped), preserving inner text
    fields={}; fc=0
    while True:
        fm=re.search(r"(?m)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[fc:])
        if not fm: break
        name=fm.group(1).lower(); vs=fc+fm.end()
        # parse value
        while vs<len(body) and body[vs].isspace(): vs+=1
        if body[vs]=="{":
            depth=1; j=vs+1
            while j<len(body) and depth:
                if body[j]=="{": depth+=1
                elif body[j]=="}": depth-=1
                j+=1
            val=body[vs+1:j-1]; ve=j
        elif body[vs]=='"':
            j=vs+1
            while j<len(body) and not (body[j]=='"' and body[j-1]!="\\"): j+=1
            val=body[vs+1:j]; ve=j+1
        else:
            j=vs
            while j<len(body) and body[j] not in ",\n": j+=1
            val=body[vs:j]; ve=j
        fields[name]=val.strip()
        fc=ve
    return fields

previews={}
new_text = text
# apply replacements from the end to keep offsets valid
spans=[]
for key in UP:
    loc=find_block(key)
    if not loc:
        print("!! block not found:", key); continue
    s,e=loc
    block=text[s:e]
    ob=block.index("{"); body=block[ob+1: block.rfind("}")]
    f=parse_fields(body)
    title=f.get("title","").strip()
    author=f.get("author","").strip()
    meta=UP[key]
    lines=[f"@inproceedings{{{key},",
           f"  title = {{{title}}},",
           f"  author = {{{author}}},",
           f"  booktitle = {{{meta['booktitle']}}},",
           f"  year = {{{meta['year']}}},"]
    if meta.get("doi"): lines.append(f"  doi = {{{meta['doi']}}},")
    lines.append(f"  url = {{{meta['url']}}},}}")
    newblock="\n".join(lines)
    spans.append((s,e,newblock,key))
    previews[key]={"old":block,"new":newblock,"source":meta["source"]}

# write previews to a file for review
with open("supplement/bib_upgrade/upgrade_preview.txt","w",encoding="utf-8") as h:
    for key in UP:
        if key in previews:
            h.write(f"########## {key}  (source: {previews[key]['source']})\n")
            h.write("---- OLD ----\n"+previews[key]['old']+"\n")
            h.write("---- NEW ----\n"+previews[key]['new']+"\n\n")

# Apply (sorted by start desc)
for s,e,nb,key in sorted(spans, key=lambda x:-x[0]):
    new_text = new_text[:s]+nb+new_text[e:]

Path("supplement/bib_upgrade/_auto_references.candidate.bib").write_text(new_text, encoding="utf-8")
json.dump({k:UP[k] for k in UP}, open("supplement/bib_upgrade/upgrade_spec.json","w"), indent=2)
print("Prepared", len(spans), "upgrades. Preview -> supplement/bib_upgrade/upgrade_preview.txt")
print("Candidate bib -> supplement/bib_upgrade/_auto_references.candidate.bib")
print("KEYS:", sorted(k for *_,k in spans))
