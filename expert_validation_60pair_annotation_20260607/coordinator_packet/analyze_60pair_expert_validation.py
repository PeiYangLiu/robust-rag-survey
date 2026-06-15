#!/usr/bin/env python3
"""Analyze 60-pair expert-validation annotations.
Requires real participant and gold CSV files; emits no placeholder results.
"""
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path

def read(path):
    with open(path,encoding='utf-8',newline='') as f: return list(csv.DictReader(f))
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--responses', required=True, help='combined participant responses CSV')
    ap.add_argument('--gold', required=True, help='gold adjudication CSV with pair_id and gold verdict')
    ap.add_argument('--out-prefix', default='expert_validation_60pair')
    args=ap.parse_args()
    responses=read(args.responses); gold_rows=read(args.gold)
    if not responses or not gold_rows:
        raise SystemExit('Missing real responses or gold labels; refusing to emit placeholder validation numbers.')
    gold={r['pair_id']:(r.get('gold_verdict_valid_partial_invalid_underspecified') or r.get('gold_verdict') or '').strip() for r in gold_rows}
    if not all(gold.values()): raise SystemExit('Gold verdicts are incomplete.')
    by_cond=defaultdict(list)
    errors=defaultdict(Counter)
    for r in responses:
        cond=(r.get('condition') or r.get('group') or '').strip() or 'unknown'
        pair=r['pair_id']; v=(r.get('verdict_valid_partial_invalid_underspecified') or r.get('verdict') or '').strip()
        if not v: continue
        g=gold.get(pair,'')
        by_cond[cond].append((v,g,pair,r.get('breaking_coordinates_optional','')))
        if g and v!=g:
            errors[cond][r.get('breaking_coordinates_optional') or f'{v}_vs_{g}']+=1
    summary={}
    for cond,vals in by_cond.items():
        n=len(vals); agree=sum(1 for v,g,_,__ in vals if v==g)
        summary[cond]={'n':n,'gold_agreement':agree/n if n else None,'verdict_counts':dict(Counter(v for v,_,__,___ in vals)),'error_taxonomy':dict(errors[cond])}
    Path(args.out_prefix+'_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
