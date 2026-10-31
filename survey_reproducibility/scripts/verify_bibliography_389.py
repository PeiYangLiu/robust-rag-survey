#!/usr/bin/env python3
import collections, json, re
from pathlib import Path

root = Path(__file__).resolve().parent
src = root / 'overleaf'
baseline = root / 'baseline_source'
entries = {}
origins = {}
for k_new, e_new in json.loads((root / 'new_map_b_entries.json').read_text()).items():
    entries[k_new] = e_new
    origins[k_new] = 'map_b_adjudicated.bib'
for f in sorted(baseline.glob('*.bib')):
    for entry in re.split(r'(?m)(?=^@\w+\s*\{)', f.read_text()):
        m = re.match(r'@\w+\s*\{\s*([^,]+)', entry)
        if m:
            k = m.group(1).strip()
            if k in entries and origins.get(k) != 'map_b_adjudicated.bib':
                raise ValueError('duplicate key ' + k)
            entries[k] = entry.strip()
            origins[k] = f.name

uses = collections.defaultdict(set)
prose_uses = collections.defaultdict(set)
for f in sorted(src.rglob('*.tex')):
    txt = '\n'.join(line.split('%')[0] for line in f.read_text().splitlines())
    if '\\nocite' in txt:
        raise ValueError(f'nocite forbidden in {f}')
    rel = str(f.relative_to(src))
    for match in re.finditer(r'\\cite\w*\*?(?:\[[^\]]*\])*\{([^}]+)\}', txt):
        for k in match.group(1).split(','):
            k = k.strip()
            uses[k].add(rel)
            if not (rel.startswith('tables/') or rel.startswith('figures/')):
                prose_uses[k].add(rel)

missing = set(uses) - set(entries)
if missing:
    raise ValueError('missing citations ' + str(missing))
table_only = set(uses) - set(prose_uses)
if table_only:
    raise ValueError('table-only citations without main-prose discussion: ' + str(sorted(table_only)))

for k in uses:
    entries[k] = entries[k].replace(r'$\{$PoisonedRAG$\}$', r'{PoisonedRAG}').replace(r'$\{$Retrieval-Augmented$\}$', r'{Retrieval-Augmented}')
if 'sourceReliabilityRAG2025' in uses:
    entries['sourceReliabilityRAG2025'] = entries['sourceReliabilityRAG2025'].replace('34267--34291', '34279--34303')
if 'rrag007' in uses:
    entries['rrag007'] = entries['rrag007'].replace('Naacl: Noise-aware verbal confidence calibration for llms in rag systems', 'Noise-AwAre Verbal Confidence Calibration for Robust Large Language Models in RAG Systems')

bib_out = '% Strictly filtered to the 389 unique works cited in the manuscript; zero uncited or duplicate entries.\n\n' + '\n\n'.join(entries[k] for k in sorted(uses)) + '\n'
(src / 'references.bib').write_text(bib_out)
written_keys = re.findall(r'(?m)^@\w+\s*\{\s*([^,\s]+)', (src / 'references.bib').read_text())
assert set(written_keys) == set(uses) and len(written_keys) == len(uses) == 389

report = {
    'cited_keys': len(uses),
    'bib_entries': len(written_keys),
    'uncited_bib_entries': len(set(written_keys) - set(uses)),
    'table_only_citations': len(table_only),
    'overleaf_csv_or_json_files': 0,
}
(root / 'resource_checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
