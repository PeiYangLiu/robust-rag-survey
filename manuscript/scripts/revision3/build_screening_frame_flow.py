#!/usr/bin/env python3
"""Document the sampling frame the census is computed over.

Every composition figure in the paper is conditioned on 259 locally extracted
full texts, and the submitted version never said how those 259 were obtained.
Appendix A conceded that the initial search logs are incomplete.  For a paper
whose contribution is labelled a census, the provenance of the corpus is the
object of study, not a detail.

This script reconstructs, from released artifacts alone, every stage from
retrieval to the screened corpus, emits a PRISMA-style flow record, and -- this
is the part that matters -- separates what is *reproducible* from what is only
*documented*.  Stages whose logs are incomplete are labelled as such in the
output and in the figure, so a reader can see exactly which edge of the flow is
weak instead of discovering it in an appendix sentence.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MANUSCRIPT = REPO / "manuscript"
SUPPLEMENT = MANUSCRIPT / "supplement"
TEXT_DIR = MANUSCRIPT / "citation_audit" / "expanded_texts"


def arxiv_id(url: str) -> str | None:
    m = re.search(r"(\d{2})(\d{2})\.(\d{4,5})", url or "")
    return m.group(0) if m else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=SUPPLEMENT / "screening_frame_flow.json"
    )
    parser.add_argument(
        "--tex", type=Path, default=MANUSCRIPT / "figures" / "screening_frame_flow.tex"
    )
    args = parser.parse_args()

    protocol = json.loads((SUPPLEMENT / "search_protocol.json").read_text(encoding="utf-8"))
    provenance = list(csv.DictReader((SUPPLEMENT / "screening_provenance.csv").open(encoding="utf-8")))
    ledger = list(csv.DictReader((SUPPLEMENT / "search_source_ledger.csv").open(encoding="utf-8")))
    manifest = list(
        csv.DictReader(
            (MANUSCRIPT / "citation_audit" / "expanded_audit_manifest.csv").open(encoding="utf-8")
        )
    )
    reviewed = list(
        csv.DictReader((SUPPLEMENT / "all_reviewed_deduped.csv").open(encoding="utf-8"))
    )
    frame_summary = json.loads(
        (SUPPLEMENT / "cross_paper_frame_summary.json").read_text(encoding="utf-8")
    )

    on_disk = sorted(p.stem for p in TEXT_DIR.glob("*.txt"))
    manifest_keys = sorted(r["key"] for r in manifest)
    assert set(on_disk) == set(manifest_keys), "manifest and extracted texts disagree"

    years = Counter()
    for row in manifest:
        aid = arxiv_id(row["url"])
        if aid:
            years[2000 + int(aid[:2])] += 1
    n_with_arxiv = sum(years.values())

    decisions = Counter(r.get("decision", "") for r in reviewed)
    n_included = sum(v for k, v in decisions.items() if k.strip().lower() in {"include", "core", "yes"})

    stages = []
    for row in provenance:
        stages.append(
            {
                "stage": row["stage"],
                "input_n": int(row["input_n"]) if row["input_n"].strip() else None,
                "output_n": int(row["output_n"]) if row["output_n"].strip() else None,
                "actor": row["screening_actor"],
                "evidence": row["evidence"],
                "limitation": row["status_and_limit"],
            }
        )
    # The stage the submitted version never documented: from the screened
    # literature to the extracted full texts the census actually ran over.
    stages.append(
        {
            "stage": "Full-text extraction for the census frame",
            "input_n": stages[3]["output_n"] if len(stages) > 3 else None,
            "output_n": len(on_disk),
            "actor": "Deterministic PDF-to-text extraction with a per-file readiness check",
            "evidence": "citation_audit/expanded_audit_manifest.csv (status=ready) and citation_audit/expanded_texts/",
            "limitation": (
                "A paper enters the census frame only if an open PDF was "
                "retrievable and extracted to text with a usable line "
                "structure. Papers behind a paywall, PDFs whose two-column "
                "tables did not linearise, and non-English texts are absent. "
                "This is an access filter, not a relevance judgment, and it is "
                "the reason every composition figure is stated for the frame."
            ),
        }
    )
    stages.append(
        {
            "stage": "Deterministic screen over extracted texts",
            "input_n": len(on_disk),
            "output_n": frame_summary.get("n_candidates"),
            "actor": "build_cross_paper_frame.py, released gazetteer and cue lists",
            "evidence": "supplement/cross_paper_frame_candidates.jsonl and cross_paper_frame_summary.json",
            "limitation": (
                "Fully reproducible from the released texts: re-running the "
                "script reproduces the candidate set byte for byte."
            ),
        }
    )

    reproducible = {
        "fully_reproducible_from_release": [
            "Full-text extraction for the census frame",
            "Deterministic screen over extracted texts",
            "Title normalization and deduplication",
            "Open-PDF filtering",
        ],
        "documented_but_not_re_executable": [
            "Initial retrieval (arXiv API, ACL Anthology, OpenReview, USENIX, "
            "AAAI/ACM, curated lists): the query set is released and the "
            "snapshot date is fixed, but per-query hit counts were not logged "
            "and live indices drift, so a rerun returns a different ordering "
            "and a different tail."
        ],
        "consequence": (
            "The frame is reconstructible by a third party from the release, "
            "because the 259 extracted texts and the screen are both released "
            "and the screen is deterministic over them. What is not "
            "reconstructible is the population those 259 were drawn from, so "
            "the frame supports composition statements about itself and about "
            "the re-weighted window universe, and supports no statement about "
            "the robust-RAG literature as a whole."
        ),
    }

    payload = {
        "schema_version": 1,
        "snapshot_date": protocol.get("snapshot_date"),
        "sources": protocol.get("sources"),
        "n_arxiv_queries": len(protocol.get("arxiv_queries", [])),
        "arxiv_queries": protocol.get("arxiv_queries"),
        "venue_followup": [
            r for r in ledger if r["stage"].lower().startswith("venue")
        ],
        "stages": stages,
        "screened_corpus": {
            "n_full_texts": len(on_disk),
            "n_with_arxiv_identifier": n_with_arxiv,
            "arxiv_year_distribution": dict(sorted(years.items())),
            "n_core_designated": sum(1 for r in manifest if r.get("is_core100") == "True"),
            "median_text_kb": sorted(
                (TEXT_DIR / f"{k}.txt").stat().st_size for k in on_disk
            )[len(on_disk) // 2]
            / 1024,
        },
        "inclusion_criteria": [
            "topic: retrieval-augmented generation with a robustness, security, "
            "conflict, calibration, abstention or faithfulness dimension, as "
            "matched by the released query set",
            "an open PDF retrievable at the snapshot date",
            "English full text",
            "PDF-to-text extraction yielding a usable line structure, which is "
            "what the window screen indexes",
        ],
        "exclusion_criteria": [
            "no open PDF at the snapshot date",
            "extraction failure or unusable line structure",
            "duplicate title or identifier after normalisation",
            "screened out as off-topic in the released relevance pass",
        ],
        "deduplication_rule": (
            "normalised title plus arXiv or DOI identifier; the first retained "
            "record wins and the rule is released with all_reviewed_deduped.csv"
        ),
        "reproducibility": reproducible,
        "relevance_screen_decisions": dict(decisions),
        "n_reviewed_deduplicated": len(reviewed),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ---- PRISMA-style figure -------------------------------------------------
    s = {row["stage"]: row for row in stages}
    retrieved = s["Initial retrieval"]["output_n"]
    open_pdf = s["Open-PDF filtering"]["output_n"]
    dedup = s["Title normalization and deduplication"]["output_n"]
    screened = s["Broad relevance screening"]["output_n"]
    texts = len(on_disk)
    cands = frame_summary.get("n_candidates")
    files = frame_summary.get("n_files_with_candidates") or frame_summary.get("n_papers")

    tex = rf"""% Generated by scripts/revision3/build_screening_frame_flow.py -- do not edit.
\begin{{figure}}[t]
\centering
\scriptsize
\begin{{tikzpicture}}[
    node distance=0.30cm,
    box/.style={{draw, rounded corners, align=center, inner sep=2.5pt,
                text width=3.15cm, minimum height=0.52cm}},
    weak/.style={{box, fill=red!6, dashed}},
    strong/.style={{box, fill=blue!6}},
    final/.style={{box, fill=orange!14, very thick}},
    note/.style={{align=left, text width=3.5cm, font=\tiny}},
    arrow/.style={{-{{Latex[length=1.6mm]}}, thick}}
]
\node[weak] (r) {{{retrieved:,} records retrieved\\{{\tiny {payload['n_arxiv_queries']} arXiv queries + 5 venue sources, {payload['snapshot_date']}}}}};
\node[strong, below=of r] (p) {{{open_pdf:,} with an open PDF}};
\node[strong, below=of p] (d) {{{dedup:,} after de-duplication}};
\node[strong, below=of d] (s) {{{screened:,} retained by the relevance screen}};
\node[strong, below=of s] (t) {{{texts} extracted full texts\\{{\tiny the census frame's corpus}}}};
\node[final, below=of t] (c) {{{cands:,} candidate windows\\{{\tiny in {files} papers}}}};

\draw[arrow] (r) -- node[right, note] {{$-${retrieved - open_pdf:,} no open PDF}} (p);
\draw[arrow] (p) -- node[right, note] {{$-${open_pdf - dedup:,} duplicate title or identifier}} (d);
\draw[arrow] (d) -- node[right, note] {{$-${dedup - screened:,} screened out as off-topic}} (s);
\draw[arrow] (s) -- node[right, note] {{$-${screened - texts} not extractable to a usable\\line structure at the snapshot}} (t);
\draw[arrow] (t) -- node[right, note] {{deterministic screen:\\gazetteer, two result-formatted\\values, three declared strata}} (c);
\end{{tikzpicture}}
\caption{{Sampling frame for the census. Solid boxes are stages a third party
can re-execute from the release; the dashed box is documented but not
re-executable, because per-query hit counts were not logged at the snapshot date
and live indices drift. The frame is therefore reconstructible from the
{texts} released texts downward, and the population those texts were drawn from
is not. Every composition figure in this paper is stated for the frame or for
the re-weighted window universe, never for the literature.}}
\label{{fig:screening-frame-flow}}
\end{{figure}}
"""
    args.tex.write_text(tex, encoding="utf-8")
    print(
        json.dumps(
            {
                "stages": [(x["stage"], x["input_n"], x["output_n"]) for x in stages],
                "n_full_texts": texts,
                "arxiv_years": payload["screened_corpus"]["arxiv_year_distribution"],
                "n_queries": payload["n_arxiv_queries"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
