#!/usr/bin/env python3
import json, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]  # <repo>/manuscript
NS={'a':'http://www.w3.org/2005/Atom'}

def read_url(url, timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':'robust-rag-bib-enricher/0.1'})
    return urllib.request.urlopen(req,timeout=timeout).read()

def arxiv_meta(aid):
    q=urllib.parse.urlencode({'id_list':aid})
    data=read_url('http://export.arxiv.org/api/query?'+q,timeout=40)
    root=ET.fromstring(data)
    ent=root.find('a:entry',NS)
    if ent is None: return None
    authors=[a.findtext('a:name',default='',namespaces=NS).strip() for a in ent.findall('a:author',NS)]
    year=(ent.findtext('a:published',default='',namespaces=NS) or '')[:4]
    title=re.sub(r'\s+',' ',ent.findtext('a:title',default='',namespaces=NS)).strip()
    return {'authors':authors,'year':year,'title':title}

def openreview_meta(oid):
    data=json.loads(read_url(f'https://api2.openreview.net/notes?id={oid}',timeout=30))
    notes=data.get('notes') or []
    if not notes: return None
    c=notes[0].get('content',{})
    def val(x):
        if isinstance(x,dict): return x.get('value')
        return x
    authors=val(c.get('authors')) or []
    title=val(c.get('title')) or ''
    year=''
    # Try cdate/tmdate milliseconds
    for k in ['pdate','cdate','tmdate']:
        if notes[0].get(k):
            import datetime
            year=str(datetime.datetime.utcfromtimestamp(notes[0][k]/1000).year)
            break
    return {'authors':authors,'year':year,'title':title}

def acl_meta(pid):
    html=read_url(f'https://aclanthology.org/{pid}/',timeout=30).decode('utf-8','ignore')
    # Prefer BibTeX-ish citation line "Cite (ACL): Name. Year. Title"
    authors=[]; year=''
    m=re.search(r'Cite \(ACL\):\s*</[^>]+>\s*([^<]+?)\.\s*(\d{4})\.\s*', html, re.S)
    if not m:
        m=re.search(r'Cite \(ACL\):\s*([^<]+?)\.\s*(\d{4})\.\s*', html, re.S)
    if m:
        names=re.sub(r'\s+',' ',m.group(1)).strip()
        year=m.group(2)
        names=names.replace(', and ', ' and ').replace(' and ', '; ')
        # split on comma only for author list where safe-ish
        parts=[]
        if ';' in names:
            parts=[p.strip(' ,') for p in names.split(';')]
        else:
            # ACL informal line often comma-separated authors
            parts=[p.strip(' ,') for p in names.split(',')]
        authors=[p for p in parts if p]
    # fallback metadata authors from visible list
    if not authors:
        # rough parse author block list items
        authors=re.findall(r'<a href="/people/[^">]+/">([^<]+)</a>', html)[:20]
    if not year:
        ym=re.search(r'<dt>Year</dt>\s*<dd>(\d{4})</dd>', html)
        if ym: year=ym.group(1)
    return {'authors':authors,'year':year,'title':''}

def bib_author(authors):
    return ' and '.join(a.strip() for a in authors if a and a.strip())

def process_file(path):
    text=path.read_text(encoding='utf-8')
    out=[]; last=0; changed=0
    for m in re.finditer(r'@(\w+)\{([^,]+),(.*?)(?=\n@|\Z)', text, re.S):
        out.append(text[last:m.start()])
        typ,key,body=m.group(1),m.group(2),m.group(3)
        has_author=bool(re.search(r'\n\s*author\s*=', body, re.I))
        if not has_author:
            urlm=re.search(r'\n\s*url\s*=\s*\{(.*?)\}', body, re.S|re.I)
            url=urlm.group(1).strip() if urlm else ''
            meta=None
            try:
                if 'arxiv.org/abs/' in url:
                    aid=url.rstrip('/').split('/')[-1]
                    aid=re.sub(r'v\d+$','',aid)
                    meta=arxiv_meta(aid)
                    time.sleep(0.4)
                elif 'aclanthology.org/' in url:
                    pid=url.rstrip('/').split('/')[-1]
                    meta=acl_meta(pid)
                    time.sleep(0.2)
                elif 'openreview.net/forum' in url:
                    oid=urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('id',[''])[0]
                    if oid: meta=openreview_meta(oid)
                    time.sleep(0.2)
            except Exception as e:
                print('WARN meta failed', key, url, type(e).__name__, e)
            if meta and meta.get('authors'):
                body='\n  author = {'+bib_author(meta['authors'])+'},'+body
                changed+=1
            # Fill year if missing
            if meta and meta.get('year') and not re.search(r'\n\s*year\s*=', body, re.I):
                body=re.sub(r'(\n\s*title\s*=\s*\{.*?\}\s*,?)', r'\1\n  year = {'+meta['year']+'},', body, count=1, flags=re.S|re.I)
        out.append(f'@{typ}'+'{'+key+','+body)
        last=m.end()
    out.append(text[last:])
    path.write_text(''.join(out),encoding='utf-8')
    print(path.name, 'authors_added', changed)

for fname in ['references.bib','auto_references.bib']:
    process_file(ROOT/fname)
