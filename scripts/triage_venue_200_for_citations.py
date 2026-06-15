#!/usr/bin/env python3
from __future__ import annotations
import csv, json, re, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'metadata/venue_200_published_manifest.csv'
OUT_ALL=ROOT/'metadata/venue_200_citation_triage.csv'
OUT_REC=ROOT/'metadata/venue_200_recommended_citations.csv'
BIBS=[ROOT/'manuscript/references.bib',ROOT/'manuscript/auto_references.bib',ROOT/'manuscript/venue_authoritative_references.bib',ROOT/'manuscript/venue_extra_references.bib']
AUX=ROOT/'manuscript/main.aux'

SECTIONS={
 'evidence_construction':['irrelevant','noise','noisy','distractor','retrieval','retriever','rerank','context','long context','compression','sufficiency','sufficient context','hard negative','lost in the middle','domain adaptation'],
 'model_evidence_use':['faithful','faithfulness','hallucination','attribution','citation','grounded','grounding','conflict','knowledge conflict','parametric','contextual','answer attribution'],
 'security_integrity':['poison','poisoning','attack','adversarial','prompt injection','backdoor','malicious','privacy','membership','traceback','corruption','jailbreak'],
 'action_control':['calibration','calibrated','uncertainty','selective','abstain','refuse','refusal','answerability','unanswerable','adaptive retrieval','corrective','decision','confidence','self-rag'],
 'evaluation':['benchmark','evaluation','evaluating','metric','dataset','ragas','rgb','ragtruth','beir','qa benchmark','negative rejection','counterfactual','diagnose','visualize'],
}
BOUNDARY=['graph','multimodal','vision','image','video','molecular','medical','biomedical','legal','climate','e-commerce','table','patent','vehicle','auctions']
EXCLUDE=['diffusion','video generation','molecular machine learning','vehicle routing','ad auctions']
FOUNDATION=['retrieval-augmented generation for knowledge-intensive','realm','dense passage retrieval','fid','beir','lost in the middle','calibration of modern neural networks','selective classification']

def norm(s):
    return re.sub(r'\s+',' ', re.sub(r'[^a-z0-9]+',' ', (s or '').lower())).strip()

def cited_titles():
    cited=set()
    if AUX.exists():
        for m in re.finditer(r'\\citation\{([^}]*)\}', AUX.read_text(errors='ignore')):
            cited.update(k.strip() for k in m.group(1).split(',') if k.strip())
    title_by_key={}
    for bib in BIBS:
        if not bib.exists(): continue
        text=bib.read_text(errors='ignore')
        for m in re.finditer(r'@\w+\{([^,]+),([\s\S]*?)(?=\n@|\Z)', text):
            key=m.group(1).strip(); block=m.group(2)
            tm=re.search(r'title\s*=\s*[\{\"]([\s\S]*?)[\}\"]\s*,', block, re.I)
            if tm: title_by_key[key]=norm(tm.group(1))
    return {title_by_key[k] for k in cited if k in title_by_key}

def extract_text(path: Path) -> str:
    try:
        out=subprocess.run(['pdftotext','-f','1','-l','3',str(path),'-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=False)
        return out.stdout.decode('utf-8','ignore')[:12000]
    except Exception:
        return ''

def score_row(row, cited_norms):
    title=row['title']; t=title.lower(); nt=norm(title)
    text=(title+' '+row.get('matched_terms','')+' '+row.get('venue','')).lower()
    pdf=ROOT/row['curated_pdf']
    full=extract_text(pdf).lower() if pdf.exists() else ''
    blob=text+' '+full[:6000]
    section_scores={}
    for sec,terms in SECTIONS.items():
        section_scores[sec]=sum(1 for term in terms if term in blob)
    best=max(section_scores, key=section_scores.get)
    score=0
    score += min(int(row.get('related_score') or 0), 90)
    score += section_scores[best]*6
    if any(x in t for x in FOUNDATION): score += 35
    if any(x in blob for x in ['retrieval augmented generation','retrieval-augmented generation',' rag ','rag,','rag.']): score += 20
    if any(x in blob for x in ['robust','faithful','faithfulness','hallucination','poison','attack','calibration','uncertainty','abstain','refuse','benchmark','evaluation']): score += 15
    if nt in cited_norms: score += 25
    if any(x in t for x in EXCLUDE): score -= 80
    boundary_hits=[x for x in BOUNDARY if x in t]
    if boundary_hits and best not in ['security_integrity','evaluation']: score -= 20
    if 'workshop' in row.get('venue','').lower(): score -= 8
    return score,best,section_scores,boundary_hits,nt in cited_norms

def decision(score,best,boundary_hits,title):
    low=title.lower()
    if score>=95 and not any(x in low for x in EXCLUDE): return 'main_cite'
    if score>=70: return 'appendix_or_case_study'
    if score>=45: return 'background_or_boundary'
    return 'exclude_or_not_relevant'

def main():
    cited_norms=cited_titles()
    rows=list(csv.DictReader(open(MANIFEST,newline='',encoding='utf-8')))
    out=[]
    for row in rows:
        score,best,section_scores,boundary_hits,already=score_row(row,cited_norms)
        dec=decision(score,best,boundary_hits,row['title'])
        reason=[]
        if already: reason.append('already_cited_or_title_match')
        if boundary_hits: reason.append('boundary:'+';'.join(boundary_hits[:3]))
        if any(x in row['title'].lower() for x in FOUNDATION): reason.append('foundation')
        if section_scores[best]: reason.append(f'{best}_signals={section_scores[best]}')
        out.append({**row,'triage_score':score,'recommended_section':best,'section_scores_json':json.dumps(section_scores,sort_keys=True),'boundary_terms':';'.join(boundary_hits),'already_cited_title_match':str(already).lower(),'citation_decision':dec,'triage_reason':' | '.join(reason)})
    out.sort(key=lambda r:(['main_cite','appendix_or_case_study','background_or_boundary','exclude_or_not_relevant'].index(r['citation_decision']),-int(r['triage_score']),r['title']))
    fields=list(out[0].keys())
    with open(OUT_ALL,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
    rec=[r for r in out if r['citation_decision'] in {'main_cite','appendix_or_case_study'}]
    with open(OUT_REC,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rec)
    from collections import Counter
    print('total',len(out),'recommended',len(rec))
    print('decisions',Counter(r['citation_decision'] for r in out))
    print('sections',Counter(r['recommended_section'] for r in rec))
    for r in rec[:40]:
        print(r['citation_decision'], r['triage_score'], r['recommended_section'], r['year'], r['venue'][:18], '-', r['title'][:100])
if __name__=='__main__': main()
