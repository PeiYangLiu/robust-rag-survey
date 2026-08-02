import csv, re, itertools
from collections import defaultdict

MAP = "manuscript/human_coding/human_round2_evidence274_results/evidence_map_round2_adjudicated.csv"
rows = [r for r in csv.DictReader(open(MAP)) if r.get('cite_key') and r.get('title')]

ASSUMP = {
 'adversarial_corruption':'attacker-created evidence',
 'knowledge_conflict':'naturally conflicting sources',
 'calibration_control':'benign uncertainty',
 'evaluation_benchmark':'benchmark-constructed stressor',
 'noisy_retrieval':'benign retrieval noise',
 'distraction':'benign distractor',
 'survey_related':'n/a',
}
def metric_bucket(s):
    s=(s or '').lower()
    if 'asr' in s or 'attack success' in s or 'retrieval failure rate' in s: return 'attack_success'
    if 'ece' in s or 'auroc' in s or 'coverage' in s or 'risk' in s or 'abstention' in s or 'reject' in s or 'selective' in s or 'conformal' in s or 'lac' in s: return 'calibration/selective_risk'
    if 'em' in s or 'f1' in s or 'accuracy' in s or 'acc' in s or 'rouge' in s or 'exact' in s: return 'answer_correctness'
    return 'other'
def action_of(mf, iv):
    mf=(mf or '').lower(); iv=(iv or '').lower()
    if 'attack' in mf: return 'answer'
    if 'system control' in iv: return 'abstain/re-retrieve'
    if 'analysis' in mf: return 'U'
    if 'control/calibration' in mf and 'system control' not in iv: return 'U'
    if 'benchmark' in mf or 'evaluation' in mf: return 'measure(eval-only)'
    if 'defense' in mf or 'mitigation' in mf:
        if 'corpus' in iv or 'retriever' in iv: return 'filter/quarantine'
        if 'context assembly' in iv: return 'filter'
        return 'answer'
    return 'U'

def sig(r):
    f=r['failure_or_risk_type'].strip()
    return dict(key=r['cite_key'].strip(), title=r['title'].strip(),
               failure=f, assumption=ASSUMP.get(f,f),
               intervention=r['intervention_point'].strip(),
               metric=metric_bucket(r['metrics_reported_or_relevant']),
               action=action_of(r['method_family'], r['intervention_point']),
               mf=r['method_family'].strip(), bench=(r['benchmark_or_task'] or '').strip())
S=[sig(r) for r in rows]
# dedupe by key
seen={}; P=[]
for s in S:
    if s['key'] not in seen: seen[s['key']]=1; P.append(s)

def verdict(a,b):
    if a['action']=='U' or b['action']=='U' or a['metric']=='other' or b['metric']=='other':
        # treat genuinely missing/unclassifiable required coord as under-specified only if action U
        if a['action']=='U' or b['action']=='U': return 'under-specified'
    if a['failure']!=b['failure'] or a['assumption']!=b['assumption']: return 'invalid'
    if a['intervention']==b['intervention'] and a['metric']==b['metric'] and a['action']==b['action']: return 'valid'
    return 'partial'

used=defaultdict(int)
def take(cond, target, exclude_same_key=True, prefer=None):
    out=[]
    cand=[p for p in P if used[p['key']]<2]
    pairs=[]
    for a,b in itertools.combinations(cand,2):
        if a['key']==b['key']: continue
        if cond(a,b): pairs.append((a,b))
    # greedy, spread by failure type, avoid reusing
    pairs.sort(key=lambda ab: used[ab[0]['key']]+used[ab[1]['key']])
    for a,b in pairs:
        if len(out)>=target: break
        if used[a['key']]>=2 or used[b['key']]>=2: continue
        out.append((a,b)); used[a['key']]+=1; used[b['key']]+=1
    return out

valid = take(lambda a,b: a['action']!='U' and b['action']!='U' and a['mf']==b['mf'] and a['failure']==b['failure'] and a['intervention']==b['intervention'] and a['metric']==b['metric'] and a['action']==b['action'] and a['metric']!='other', 12)
partial= take(lambda a,b: a['action']!='U' and b['action']!='U' and a['failure']==b['failure'] and a['assumption']==b['assumption'] and (a['intervention']!=b['intervention'] or a['action']!=b['action']) and not(a['intervention']==b['intervention'] and a['metric']==b['metric'] and a['action']==b['action']), 12)
invalid= take(lambda a,b: a['action']!='U' and b['action']!='U' and a['failure']!=b['failure'], 12)
underspec= take(lambda a,b: ((a['action']=='U') ^ (b['action']=='U')) and a['failure']==b['failure'] and a['assumption']==b['assumption'], 12)  # one missing action, otherwise same game

cats=[('valid',valid),('partial',partial),('invalid',invalid),('under-specified',underspec)]
pair_rows=[]; key_rows=[]; i=0
for name,lst in cats:
    for a,b in lst:
        i+=1; pid=f"R2C-{i:03d}"
        # ensure A is the one with U for under-specified
        if name=='under-specified' and b['action']=='U' and a['action']!='U': a,b=b,a
        v=verdict(a,b)
        pair_rows.append(dict(pair_id=pid, area=a['failure'], paper_a_key=a['key'], paper_a_title=a['title'], paper_b_key=b['key'], paper_b_title=b['title']))
        key_rows.append(dict(pair_id=pid, expected_verdict=name, mechanical_check=v,
            a_failure=a['failure'], a_assumption=a['assumption'], a_intervention=a['intervention'], a_metric=a['metric'], a_action=a['action'],
            b_failure=b['failure'], b_assumption=b['assumption'], b_intervention=b['intervention'], b_metric=b['metric'], b_action=b['action'],
            note=f"{name}: rule-applied on map-inferred coords; VERIFY against papers (esp. valid={a['bench'][:25]} vs {b['bench'][:25]})"))
print("counts:", {n:len(l) for n,l in cats})
print("mechanical_check matches expected:", sum(1 for k in key_rows if k['mechanical_check']==k['expected_verdict']),"/",len(key_rows))
with open('round2_candidate_pairs_20260616/r2_candidate_pairs_for_annotation.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(pair_rows[0].keys())); w.writeheader(); w.writerows(pair_rows)
with open('round2_candidate_pairs_20260616/r2_coordinator_hidden_pair_key.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(key_rows[0].keys())); w.writeheader(); w.writerows(key_rows)
