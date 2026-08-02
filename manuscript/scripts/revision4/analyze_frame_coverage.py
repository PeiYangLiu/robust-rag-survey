#!/usr/bin/env python3
r"""Coverage of prior surveys' reference lists against our screening frame (R4).

A reviewer objected that "259 full texts from 1,904 records" looks thin for the
field, and asked us to justify the query set or report recall against a known
list -- specifically, against the reference lists of the six prior surveys the
manuscript compares to.  This script answers that objection with a number.

It reads the six surveys' bibliographies harvested by
``harvest_survey_references.py`` (cached under
``supplement/coverage_audit/raw/``) and, for each survey and for the pooled
deduplicated union, reports how many of its references land in each released
stage of our frame:

  * deduplicated release (1,399 records)   -- supplement/all_reviewed_deduped.csv
  * relevance-screened in (536)            -- decision in {core, include}
  * extracted full texts (259)             -- citation_audit/expanded_audit_manifest.csv
  * adjudicated Map B (342)                -- supplement/evidence_map_venue_expanded_adjudicated.csv

The 1,904 retrieved and 1,445 open-PDF stages are *count only* in the release
(search_protocol.json logs queries and totals, not a per-record list), so the
1,399 deduplicated release is the largest per-record superset and lower-bounds
recall against the 1,904.  This is stated in the output.

Not every reference of a prior survey is a robust-RAG paper (they cite datasets,
base LLMs, optimisers).  We therefore apply a transparent, deterministic
title-keyword screen -- a title must name a retrieval/RAG concept AND a
robustness/attack/conflict/noise/calibration/abstention concept -- and report
BOTH the unfiltered and the in-scope recall.  The keyword lists are released
verbatim in the JSON output and are derived from the manuscript's own query set
(screening_frame_flow.json) plus morphological variants, so the screen is not
cherry-picked.

References match our records by, in order, arXiv id (version-stripped), DOI,
ACL Anthology id, then normalised title (exact, token-sorted, and a
conservative Jaccard>=0.9 fallback).  The channel that produced each match is
recorded so a reader can judge the title-matching tail.

The script is deterministic and offline: it reads only the cached raw JSON and
the released frame CSVs.  Wilson score intervals give the 95% CIs.

Writes:
  * supplement/frame_coverage_audit.json
  * supplement/frame_coverage_matches.csv
  * tables/frame_coverage.tex
  * tables/coverage_macros.tex

Standard library only.  Re-run with::

    python3 manuscript/scripts/revision4/analyze_frame_coverage.py
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MAN = REPO / "manuscript"
SUP = MAN / "supplement"
TAB = MAN / "tables"
RAW = SUP / "coverage_audit" / "raw"

SNAPSHOT = "2026-06-03"
SNAPSHOT_YEAR = 2026
SAMPLE_SEED = 20260603
N_MISS_SAMPLE = 20

SURVEY_ORDER = [
    "ragSurvey2024",
    "ragEvaluationSurvey2024",
    "trustRAGCompass2024",
    "securityRAGSurvey2026",
    "xuKnowledgeConflicts2024",
    "wenAbstentionSurvey2025",
]

# Short labels + bib keys for the LaTeX table.
SURVEY_LABEL = {
    "ragSurvey2024": "RAG survey (Gao)",
    "ragEvaluationSurvey2024": "RAG evaluation (Yu)",
    "trustRAGCompass2024": "Trustworthy RAG (Zhou)",
    "securityRAGSurvey2026": "Securing RAG (Xu)",
    "xuKnowledgeConflicts2024": "Knowledge conflicts (Xu)",
    "wenAbstentionSurvey2025": "Abstention (Wen)",
}

# ---------------------------------------------------------------------------
# In-scope title-keyword screen.
# The robustness axis is the union of the robustness/attack/conflict/noise/
# calibration/abstention query terms in the manuscript's released query set
# (supplement/screening_frame_flow.json -> arxiv_queries), plus morphological
# variants so that titles inflecting those terms still match.  The retrieval
# axis is the retrieval/RAG query terms plus "rag" and "retriever".  A title is
# in scope iff it contains >=1 retrieval term AND >=1 robustness term.
# ---------------------------------------------------------------------------
RETRIEVAL_TERMS = [
    "retrieval", "retriever", "retrieve", "retrieved", "retrieving",
    "retrieval augmented", "retrieval augmented generation",
    "retrieval augmented language models", "rag",
    "open domain question answering", "open domain qa",
    "knowledge intensive", "dense passage", "passage retrieval",
    "document retrieval",
]

ROBUSTNESS_TERMS_QUERY_SET = [
    # verbatim robustness-axis terms from screening_frame_flow.json queries
    "robustness", "noisy", "irrelevant", "distractor", "knowledge conflict",
    "parametric knowledge", "adversarial", "poisoning", "prompt injection",
    "uncertainty", "calibration", "abstain", "adaptive retrieval",
    "faithfulness", "hallucination", "trustworthy", "security", "privacy",
    "noise robustness", "noisy context", "irrelevant context", "hard negative",
    "context conflict", "knowledge corruption", "data poisoning",
    "indirect prompt", "unanswerable", "selective generation",
    "confidence estimation", "uncertainty quantification", "trust calibration",
    "negative rejection", "information integration", "counterfactual robustness",
    "context faithfulness", "groundedness", "citation", "self correction",
    "verification", "fact checking", "abstention",
]
ROBUSTNESS_TERMS_VARIANTS = [
    # morphological / close forms of the same concepts, so inflected titles match
    "robust", "noise", "distraction", "conflict", "knowledge conflicts",
    "conflicting", "adversary", "attack", "attacks", "poison", "poisoned",
    "injection", "abstaining", "faithful", "unfaithful", "hallucinate",
    "hallucinated", "hallucinations", "trustworthiness", "secure", "grounded",
    "counterfactual", "corruption", "corrupted", "contradiction",
    "contradictory", "calibrated", "confidence", "selective prediction",
    "rejection", "factuality", "misinformation", "jailbreak", "backdoor",
]
ROBUSTNESS_TERMS = ROBUSTNESS_TERMS_QUERY_SET + ROBUSTNESS_TERMS_VARIANTS


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def norm_title(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def toks(text: str) -> list[str]:
    return [w for w in norm_title(text).split() if w]


def toksort(text: str) -> str:
    return " ".join(sorted(toks(text)))


def clean_arxiv(value: str):
    """Return a version-stripped arXiv id, or None."""
    if not value:
        return None
    s = str(value).strip().lower()
    m = re.search(r"(\d{4}\.\d{4,5})", s)
    if m:
        return m.group(1)
    m = re.search(r"([a-z][a-z\-]+/\d{7})", s)
    if m:
        return m.group(1)
    return None


def clean_doi(value: str):
    if not value:
        return None
    s = str(value).strip().lower()
    s = s.replace("https://doi.org/", "").replace("http://doi.org/", "")
    s = s.replace("doi:", "").strip().strip("/")
    return s if s.startswith("10.") else None


def record_ids(url: str, key: str):
    """Extract (arxiv_set, doi_set, acl_set) from a frame record, guarding by source."""
    url = (url or "").strip()
    key = (key or "").strip()
    ax, doi, acl = set(), set(), set()
    lu = url.lower()
    if "arxiv.org" in lu:
        a = clean_arxiv(lu)
        if a:
            ax.add(a)
    if "doi.org" in lu:
        d = clean_doi(lu)
        if d:
            doi.add(d)
    elif lu.startswith("10."):
        doi.add(lu.strip("/"))
    if "aclanthology.org" in lu:
        m = re.search(r"aclanthology\.org/([^/#?]+)", lu)
        if m:
            acl.add(m.group(1).lower().rstrip("/"))
    lk = key.lower()
    if lk.startswith("arxiv"):
        a = clean_arxiv(lk)
        if a:
            ax.add(a)
    return ax, doi, acl


# whole-word / phrase membership on a normalised title
def find_term(ntitle: str, terms) -> str | None:
    padded = " " + ntitle + " "
    for term in terms:
        if " " + term + " " in padded:
            return term
    return None


def in_scope(ntitle: str) -> bool:
    return (find_term(ntitle, RETRIEVAL_TERMS) is not None
            and find_term(ntitle, ROBUSTNESS_TERMS) is not None)


# ---------------------------------------------------------------------------
# Wilson score interval (house style, matches scripts/revision3)
# ---------------------------------------------------------------------------
def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    z, p = 1.959963985, k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - h) / d, (c + h) / d


# ---------------------------------------------------------------------------
# Frame index
# ---------------------------------------------------------------------------
class Frame:
    def __init__(self, name: str):
        self.name = name
        self.arxiv: set[str] = set()
        self.doi: set[str] = set()
        self.acl: set[str] = set()
        self.title_exact: set[str] = set()
        self.title_toksort: set[str] = set()
        self.title_token_sets: list[frozenset] = []
        self.n = 0

    def add(self, url: str, key: str, title: str) -> None:
        self.n += 1
        ax, doi, acl = record_ids(url, key)
        self.arxiv |= ax
        self.doi |= doi
        self.acl |= acl
        nt = norm_title(title)
        if nt:
            self.title_exact.add(nt)
            self.title_toksort.add(toksort(title))
            ts = frozenset(toks(title))
            if len(ts) >= 4:
                self.title_token_sets.append(ts)


def match_ref(ref: dict, frame: Frame) -> str | None:
    """Return the channel that matches ref to frame, or None."""
    if ref["arxiv"] and ref["arxiv"] in frame.arxiv:
        return "arxiv"
    if ref["doi"] and ref["doi"] in frame.doi:
        return "doi"
    if ref["acl"] and ref["acl"] in frame.acl:
        return "acl"
    if ref["ntitle"] and ref["ntitle"] in frame.title_exact:
        return "title_exact"
    if ref["toksort"] and ref["toksort"] in frame.title_toksort:
        return "title_tokensort"
    rset = ref["tokset"]
    if rset and len(rset) >= 4:
        for fset in frame.title_token_sets:
            inter = len(rset & fset)
            if not inter:
                continue
            if inter / len(rset | fset) >= 0.9:
                return "title_jaccard"
    return None


def in_any_frame(ref: dict, frames: dict) -> bool:
    """True if the reference is present in ANY released stage of the frame.

    Stages are matched independently rather than assumed nested: the 259
    extracted full texts include a few foundational/core-reading papers (e.g.
    Lewis 2020 RAG, Self-RAG, CRAG) that were added outside the arXiv-retrieval
    dedup frame, so a paper can be in the full texts without being in the 1,399
    deduplicated release.
    """
    return any(match_ref(ref, frames[stage]) is not None for stage in STAGE_ORDER)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_reference(cited: dict) -> dict:
    ext = cited.get("externalIds") or {}
    title = cited.get("title") or ""
    return {
        "title": title,
        "year": cited.get("year"),
        "arxiv": clean_arxiv(ext.get("ArXiv")),
        "doi": clean_doi(ext.get("DOI")),
        "acl": (str(ext.get("ACL")).lower() if ext.get("ACL") else None),
        "ntitle": norm_title(title),
        "toksort": toksort(title),
        "tokset": frozenset(toks(title)),
    }


def load_surveys() -> dict:
    out = {}
    for key in SURVEY_ORDER:
        path = RAW / f"{key}_references.json"
        if not path.exists():
            sys.stderr.write(
                f"ERROR: missing cache {path}. Run harvest_survey_references.py first.\n")
            raise SystemExit(2)
        rec = json.loads(path.read_text(encoding="utf-8"))
        refs = [load_reference(c) for c in rec.get("references", [])]
        out[key] = {
            "resolved_id": rec.get("resolved_id"),
            "status": rec.get("status"),
            "reference_count_reported": rec.get("reference_count_reported"),
            "title": rec.get("title"),
            "refs": refs,
        }
    return out


def build_frames():
    frames = {}

    # deduplicated release (1,399) and screened-in (536)
    dedup = Frame("deduplicated_1399")
    screened = Frame("screened_536")
    ded_path = SUP / "all_reviewed_deduped.csv"
    with ded_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            dedup.add(row.get("url", ""), row.get("key", ""), row.get("title", ""))
            if row.get("decision", "").strip() in ("core", "include"):
                screened.add(row.get("url", ""), row.get("key", ""), row.get("title", ""))
    frames["deduplicated_1399"] = dedup
    frames["screened_536"] = screened

    # extracted full texts (259)
    texts = Frame("full_texts_259")
    man_path = MAN / "citation_audit" / "expanded_audit_manifest.csv"
    with man_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("status", "").strip() == "ready":
                texts.add(row.get("url", ""), row.get("key", ""), row.get("title", ""))
    frames["full_texts_259"] = texts

    # adjudicated Map B (342)
    mapb = Frame("evidence_map_342")
    map_path = SUP / "evidence_map_venue_expanded_adjudicated.csv"
    with map_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            mapb.add(row.get("url", ""), row.get("cite_key", ""), row.get("title", ""))
    frames["evidence_map_342"] = mapb

    return frames


STAGE_ORDER = ["deduplicated_1399", "screened_536", "full_texts_259", "evidence_map_342"]
STAGE_DENOM = {
    "deduplicated_1399": 1399,
    "screened_536": 536,
    "full_texts_259": 259,
    "evidence_map_342": 342,
}


# ---------------------------------------------------------------------------
# Recall computation
# ---------------------------------------------------------------------------
def recall_block(refs: list[dict], frames: dict, restrict_in_scope: bool):
    """Return per-stage {n, n_matched, recall, wilson95, channels} over refs."""
    subset = [r for r in refs if (r["is_scope"] if restrict_in_scope else True)]
    n = len(subset)
    block = {"n": n, "stages": {}}
    for stage in STAGE_ORDER:
        frame = frames[stage]
        channels = Counter()
        n_match = 0
        for r in subset:
            ch = match_ref(r, frame)
            if ch:
                n_match += 1
                channels[ch] += 1
        lo, hi = wilson(n_match, n) if n else (float("nan"), float("nan"))
        block["stages"][stage] = {
            "n_matched": n_match,
            "recall": (n_match / n) if n else None,
            "wilson95": [round(lo, 4), round(hi, 4)] if n else [None, None],
            "match_channels": dict(channels),
        }
    return block


def pooled_dedup(surveys: dict):
    """Deduplicate references across surveys; return list of pooled ref dicts
    carrying the set of surveys that cite each."""
    canon = {}
    order = {}
    for si, key in enumerate(SURVEY_ORDER):
        for r in surveys[key]["refs"]:
            if r["arxiv"]:
                ck = "arxiv:" + r["arxiv"]
            elif r["doi"]:
                ck = "doi:" + r["doi"]
            elif r["acl"]:
                ck = "acl:" + r["acl"]
            elif r["toksort"]:
                ck = "title:" + r["toksort"]
            else:
                ck = "blank:" + str(id(r))
            if ck not in canon:
                canon[ck] = dict(r)
                canon[ck]["surveys"] = set()
                order[ck] = (si, len(order))
            canon[ck]["surveys"].add(key)
    # deterministic order
    return [canon[ck] for ck in sorted(canon, key=lambda c: order[c])]


def classify_year(year) -> str:
    if year is None:
        return "unknown_year"
    try:
        y = int(year)
    except (TypeError, ValueError):
        return "unknown_year"
    if y <= SNAPSHOT_YEAR - 1:
        return "before_snapshot"
    if y == SNAPSHOT_YEAR:
        return "snapshot_year_ambiguous"
    return "after_snapshot"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Frame coverage audit (offline).")
    ap.add_argument("--json-out", type=Path, default=SUP / "frame_coverage_audit.json")
    ap.add_argument("--csv-out", type=Path, default=SUP / "frame_coverage_matches.csv")
    ap.add_argument("--tex-out", type=Path, default=TAB / "frame_coverage.tex")
    ap.add_argument("--macro-out", type=Path, default=TAB / "coverage_macros.tex")
    args = ap.parse_args()

    surveys = load_surveys()
    frames = build_frames()

    # tag scope on every reference
    for key in SURVEY_ORDER:
        for r in surveys[key]["refs"]:
            r["is_scope"] = in_scope(r["ntitle"])

    # ---- per-survey ----
    per_survey = {}
    for key in SURVEY_ORDER:
        refs = surveys[key]["refs"]
        n_scope = sum(1 for r in refs if r["is_scope"])
        in_block = recall_block(refs, frames, restrict_in_scope=True)
        un_block = recall_block(refs, frames, restrict_in_scope=False)
        # out of frame = in-scope reference absent from every released stage
        n_out = 0
        for r in refs:
            if not r["is_scope"]:
                continue
            if not in_any_frame(r, frames):
                n_out += 1
        per_survey[key] = {
            "title": surveys[key]["title"],
            "resolved_id": surveys[key]["resolved_id"],
            "reference_count_reported": surveys[key]["reference_count_reported"],
            "n_references": len(refs),
            "n_in_scope": n_scope,
            "in_scope_recall": in_block,
            "unfiltered_recall": un_block,
            "n_out_of_frame": n_out,
        }

    # ---- pooled ----
    pooled = pooled_dedup(surveys)
    for r in pooled:
        r["is_scope"] = in_scope(r["ntitle"])
    n_pool_scope = sum(1 for r in pooled if r["is_scope"])
    pool_in = recall_block(pooled, frames, restrict_in_scope=True)
    pool_un = recall_block(pooled, frames, restrict_in_scope=False)

    # pooled misses (in-scope, absent from every released stage)
    misses = []
    for r in pooled:
        if not r["is_scope"]:
            continue
        if not in_any_frame(r, frames):
            misses.append(r)
    miss_by_year = Counter(str(r["year"]) for r in misses)
    miss_by_snapshot = Counter(classify_year(r["year"]) for r in misses)
    rng = random.Random(SAMPLE_SEED)
    misses_sorted = sorted(misses, key=lambda r: (r["toksort"], str(r["year"])))
    sample = rng.sample(misses_sorted, min(N_MISS_SAMPLE, len(misses_sorted)))
    sample_titles = sorted(
        ({"title": r["title"], "year": r["year"],
          "cited_by": sorted(r["surveys"])} for r in sample),
        key=lambda d: (str(d["year"]), d["title"]))

    # channel roll-up across surveys (in-scope) at each stage
    channel_rollup = {stage: Counter() for stage in STAGE_ORDER}
    for key in SURVEY_ORDER:
        for stage in STAGE_ORDER:
            channel_rollup[stage].update(
                per_survey[key]["in_scope_recall"]["stages"][stage]["match_channels"])

    # ---- harvest provenance ----
    harvest = {}
    for key in SURVEY_ORDER:
        harvest[key] = {
            "resolved_id": surveys[key]["resolved_id"],
            "status": surveys[key]["status"],
            "reference_count_reported": surveys[key]["reference_count_reported"],
            "n_harvested": len(surveys[key]["refs"]),
        }
    n_fail = sum(1 for k in SURVEY_ORDER if surveys[k]["status"] != "ok")

    audit = {
        "schema_version": "frame-coverage-audit-v1",
        "snapshot_date": SNAPSHOT,
        "reviewer_prompt": (
            "'259 full texts' from '1,904 records' will strike readers as thin; "
            "justify the query set or report recall against a known list (the "
            "reference lists of the six prior surveys compared to)."),
        "harvest": harvest,
        "harvest_total_references": sum(len(surveys[k]["refs"]) for k in SURVEY_ORDER),
        "harvest_failures": n_fail,
        "in_scope_filter": {
            "rule": "title contains >=1 retrieval term AND >=1 robustness term "
                    "(whole-word/phrase match on the punctuation-stripped, "
                    "lower-cased title)",
            "retrieval_terms": RETRIEVAL_TERMS,
            "robustness_terms_query_set": ROBUSTNESS_TERMS_QUERY_SET,
            "robustness_terms_variants": ROBUSTNESS_TERMS_VARIANTS,
            "derivation": (
                "The robustness axis is the union of the robustness/attack/"
                "conflict/noise/calibration/abstention query terms released in "
                "supplement/screening_frame_flow.json (arxiv_queries) plus "
                "morphological variants; the retrieval axis is the retrieval/RAG "
                "query terms plus 'rag' and 'retriever'. Applied to prior-survey "
                "reference titles, not to our frame."),
            "caveat": (
                "A title-keyword screen misses robust-RAG papers whose titles "
                "carry a named system but no scope keyword (e.g. 'Astute RAG'), "
                "so in-scope counts are conservative; unfiltered recall is "
                "reported alongside for exactly this reason."),
        },
        "frame_stages": {
            "retrieved_1904": {
                "n": 1904,
                "record_level_list_released": False,
                "note": "Count only (search_protocol.json logs queries and the "
                        "1,904 total, not a per-record list). The 1,399 "
                        "deduplicated release is the largest released per-record "
                        "superset, so recall against it lower-bounds recall "
                        "against the 1,904 retrieved records.",
            },
            "open_pdf_1445": {
                "n": 1445,
                "record_level_list_released": False,
                "note": "Count only; superset of the 1,399 deduplicated release.",
            },
            "deduplicated_1399": {
                "n": frames["deduplicated_1399"].n,
                "artifact": "supplement/all_reviewed_deduped.csv",
            },
            "screened_536": {
                "n": frames["screened_536"].n,
                "artifact": "supplement/all_reviewed_deduped.csv (decision in {core,include})",
            },
            "full_texts_259": {
                "n": frames["full_texts_259"].n,
                "artifact": "citation_audit/expanded_audit_manifest.csv (status=ready)",
            },
            "evidence_map_342": {
                "n": frames["evidence_map_342"].n,
                "artifact": "supplement/evidence_map_venue_expanded_adjudicated.csv",
            },
        },
        "matching": {
            "channels_in_order": ["arxiv", "doi", "acl", "title_exact",
                                  "title_tokensort", "title_jaccard"],
            "note": "arXiv ids are version-stripped; titles are lower-cased and "
                    "punctuation-stripped; Jaccard fallback requires >=0.9 token "
                    "overlap and >=4 tokens.",
            "pooled_in_scope_channel_rollup_by_stage": {
                stage: dict(channel_rollup[stage]) for stage in STAGE_ORDER},
        },
        "per_survey": per_survey,
        "pooled": {
            "n_unique_references": len(pooled),
            "dedup_rule": "canonical key = arXiv id, else DOI, else ACL id, else "
                          "token-sorted normalised title",
            "n_in_scope": n_pool_scope,
            "in_scope_recall": pool_in,
            "unfiltered_recall": pool_un,
            "n_out_of_frame": len(misses),
            "misses": {
                "definition": "in-scope pooled references absent from every "
                              "released stage (the 1,399 deduplicated release, "
                              "the 536 screened set, the 259 full texts, and the "
                              "342-row Map B)",
                "n": len(misses),
                "by_year": dict(sorted(miss_by_year.items())),
                "by_snapshot": dict(miss_by_snapshot),
                "sample_titles": sample_titles,
            },
        },
        "limitations": [
            "Reference lists are as resolved by Semantic Scholar's citation "
            "graph; S2 does not resolve every bibliography entry, so harvested "
            "counts are lower bounds on the true bibliographies. "
            "ragEvaluationSurvey2024 resolves to only 74 references, which is "
            "low for a survey and likely undercounts its bibliography.",
            "The 1,904 retrieved and 1,445 open-PDF stages have no released "
            "per-record list; recall is reported against the 1,399 deduplicated "
            "release, a lower bound on retrieval recall.",
            "Semantic Scholar year granularity is annual; papers dated 2026 "
            "cannot be split around the 2026-06-03 snapshot, so they are reported "
            "as a separate 'snapshot_year_ambiguous' bucket.",
            "The in-scope screen is title-only and deterministic; it neither "
            "reads abstracts nor resolves named systems, so it under-counts "
            "in-scope work (unfiltered recall is reported alongside).",
            "Frame stages are matched independently, not assumed nested: the 259 "
            "extracted full texts include a few foundational/core-reading papers "
            "(e.g. Lewis 2020 RAG, Self-RAG, CRAG) added outside the "
            "arXiv-retrieval dedup frame, so a reference can appear in the full "
            "texts without appearing in the 1,399 deduplicated release. 'Out of "
            "frame' therefore means absent from every released stage.",
        ],
    }

    args.json_out.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    # ---- per-reference CSV ----
    write_matches_csv(args.csv_out, surveys, frames)

    # ---- LaTeX table + macros ----
    write_table(args.tex_out, per_survey, pooled_summary(pool_in, pool_un,
                len(pooled), n_pool_scope, len(misses)))
    write_macros(args.macro_out, per_survey, pool_in, pool_un, len(pooled),
                 n_pool_scope, len(misses), miss_by_snapshot,
                 audit["harvest_total_references"], n_fail)

    # ---- stderr summary ----
    sys.stderr.write("\n=== frame coverage (pooled, in-scope) ===\n")
    sys.stderr.write(f"pooled unique refs: {len(pooled)}; in-scope: {n_pool_scope}\n")
    for stage in STAGE_ORDER:
        s = pool_in["stages"][stage]
        sys.stderr.write(
            f"  {stage:20s} recall {s['recall']:.3f} "
            f"[{s['wilson95'][0]:.3f}, {s['wilson95'][1]:.3f}] "
            f"({s['n_matched']}/{n_pool_scope})\n")
    sys.stderr.write(f"out of frame (in-scope): {len(misses)}\n")
    print(json.dumps({"pooled_in_scope": pool_in, "n_in_scope": n_pool_scope,
                      "n_out_of_frame": len(misses)}, indent=2))
    return 0


def pooled_summary(pool_in, pool_un, n_pool, n_scope, n_out):
    return {"n_pool": n_pool, "n_scope": n_scope, "n_out": n_out,
            "in": pool_in, "un": pool_un}


def write_matches_csv(path: Path, surveys: dict, frames: dict) -> None:
    cols = ["survey", "ref_title", "ref_year", "ref_arxiv", "ref_doi", "ref_acl",
            "in_scope", "match_deduplicated_1399", "match_screened_536",
            "match_full_texts_259", "match_evidence_map_342", "in_any_release"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for key in SURVEY_ORDER:
            for r in surveys[key]["refs"]:
                ch = {stage: match_ref(r, frames[stage]) for stage in STAGE_ORDER}
                in_any = any(ch[stage] is not None for stage in STAGE_ORDER)
                w.writerow([
                    key, r["title"], r["year"] if r["year"] is not None else "",
                    r["arxiv"] or "", r["doi"] or "", r["acl"] or "",
                    int(r["is_scope"]),
                    ch["deduplicated_1399"] or "", ch["screened_536"] or "",
                    ch["full_texts_259"] or "", ch["evidence_map_342"] or "",
                    int(in_any),
                ])


def fr(x) -> str:
    return "---" if x is None else f"{x:.2f}"


def ci(w) -> str:
    if not w or w[0] is None:
        return "---"
    return f"[{w[0]:.2f}, {w[1]:.2f}]"


def write_table(path: Path, per_survey: dict, pool) -> None:
    lines = [
        "% Generated by scripts/revision4/analyze_frame_coverage.py -- do not edit.",
        "\\begin{table}[t]",
        "\\centering\\scriptsize",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\resizebox{\\columnwidth}{!}{%",
        "\\begin{tabular}{@{}lrrrrrr@{}}",
        "\\toprule",
        "Prior survey & Refs & In-sc. & Ded. & Scr. & Text & Map \\\\",
        "\\midrule",
    ]
    for key in SURVEY_ORDER:
        p = per_survey[key]
        st = p["in_scope_recall"]["stages"]
        lines.append(
            f"{SURVEY_LABEL[key]} \\citep{{{key}}} & {p['n_references']} & "
            f"{p['n_in_scope']} & {fr(st['deduplicated_1399']['recall'])} & "
            f"{fr(st['screened_536']['recall'])} & "
            f"{fr(st['full_texts_259']['recall'])} & "
            f"{fr(st['evidence_map_342']['recall'])} \\\\")
    lines.append("\\midrule")
    pin = pool["in"]["stages"]
    lines.append(
        f"\\textbf{{Pooled}} & {pool['n_pool']} & {pool['n_scope']} & "
        f"{fr(pin['deduplicated_1399']['recall'])} & "
        f"{fr(pin['screened_536']['recall'])} & "
        f"{fr(pin['full_texts_259']['recall'])} & "
        f"{fr(pin['evidence_map_342']['recall'])} \\\\")
    lines.append("\\midrule")
    lines.append("\\multicolumn{7}{@{}l}{\\emph{Pooled in-scope recall, Wilson 95\\% CI}} \\\\")
    for stage, lab in (("deduplicated_1399", "Deduped (1,399)"),
                       ("full_texts_259", "Full texts (259)")):
        s = pin[stage]
        lines.append(
            f"{lab} & \\multicolumn{{6}}{{r}}{{{s['recall']:.2f} {ci(s['wilson95'])} "
            f"({s['n_matched']}/{pool['n_scope']})}} \\\\")
    lines += [
        "\\bottomrule",
        "\\end{tabular}}",
        "\\caption{Coverage of the six prior surveys' reference lists against our "
        "frame, the reviewer's requested recall-against-a-known-list check. "
        "\\emph{Refs} is the bibliography Semantic Scholar resolves for each "
        "survey; \\emph{In-sc.}\\ keeps titles naming both a retrieval and a "
        "robustness concept (keyword lists released in "
        "\\texttt{frame\\_coverage\\_audit.json}). The stage columns give the "
        "share of in-scope references present in the deduplicated release "
        "(1,399), the relevance-screened set (536), the extracted full texts "
        "(259) and the adjudicated Map~B (342); matching is by arXiv id, DOI, "
        "ACL id, then normalised title. The 1,904 retrieved and 1,445 open-PDF "
        "stages are count-only in the release, so the deduplicated column lower-"
        "bounds retrieval recall. Per-survey CIs and unfiltered recall are in "
        "the released JSON.}",
        "\\label{tab:frame-coverage}",
        "\\end{table}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def m(name: str, value) -> str:
    return f"\\newcommand{{\\{name}}}{{{value}}}"


def write_macros(path: Path, per_survey, pool_in, pool_un, n_pool, n_scope,
                 n_out, miss_snapshot, harvest_total, n_fail) -> None:
    def pct(x):
        return "??" if x is None else f"{x * 100:.0f}"

    def fr2(x):
        return "??" if x is None else f"{x:.2f}"

    ded = pool_in["stages"]["deduplicated_1399"]
    scr = pool_in["stages"]["screened_536"]
    txt = pool_in["stages"]["full_texts_259"]
    mpb = pool_in["stages"]["evidence_map_342"]
    ded_un = pool_un["stages"]["deduplicated_1399"]
    txt_un = pool_un["stages"]["full_texts_259"]

    lines = [
        "% Generated by scripts/revision4/analyze_frame_coverage.py -- do not edit by hand.",
        m("CovNSurveys", len(SURVEY_ORDER)),
        m("CovHarvestTotal", f"{harvest_total:,}"),
        m("CovHarvestFailures", n_fail),
        m("CovPooledRefs", f"{n_pool:,}"),
        m("CovPooledInScope", n_scope),
        m("CovPooledInScopePct", pct(n_scope / n_pool if n_pool else None)),
        # deduplicated (retrieval-frame proxy)
        m("CovRecallDedup", fr2(ded["recall"])),
        m("CovRecallDedupPct", pct(ded["recall"])),
        m("CovRecallDedupCI", ci(ded["wilson95"])),
        m("CovRecallDedupMatched", ded["n_matched"]),
        # screened
        m("CovRecallScreened", fr2(scr["recall"])),
        m("CovRecallScreenedPct", pct(scr["recall"])),
        m("CovRecallScreenedCI", ci(scr["wilson95"])),
        # full texts (the reviewer's 259)
        m("CovRecallTexts", fr2(txt["recall"])),
        m("CovRecallTextsPct", pct(txt["recall"])),
        m("CovRecallTextsCI", ci(txt["wilson95"])),
        m("CovRecallTextsMatched", txt["n_matched"]),
        # map
        m("CovRecallMap", fr2(mpb["recall"])),
        m("CovRecallMapPct", pct(mpb["recall"])),
        m("CovRecallMapCI", ci(mpb["wilson95"])),
        # unfiltered headline (all resolved refs, no scope screen)
        m("CovRecallDedupUnfiltered", fr2(ded_un["recall"])),
        m("CovRecallDedupUnfilteredPct", pct(ded_un["recall"])),
        m("CovRecallTextsUnfiltered", fr2(txt_un["recall"])),
        m("CovRecallTextsUnfilteredPct", pct(txt_un["recall"])),
        # misses
        m("CovNMissed", n_out),
        m("CovMissedBeforeSnapshot", miss_snapshot.get("before_snapshot", 0)),
        m("CovMissedSnapshotYear", miss_snapshot.get("snapshot_year_ambiguous", 0)),
        m("CovMissedAfterSnapshot", miss_snapshot.get("after_snapshot", 0)),
        m("CovMissedUnknownYear", miss_snapshot.get("unknown_year", 0)),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
