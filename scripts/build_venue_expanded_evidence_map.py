#!/usr/bin/env python3
"""Build a venue-expanded evidence map from the adjudicated map plus human citation audit B."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD_MAP = ROOT / "manuscript" / "supplement" / "evidence_map_adjudicated.csv"
CORE100 = ROOT / "manuscript" / "supplement" / "core100_full.csv"
HUMAN = ROOT / "manuscript" / "human_coding" / "citation_annotation_batch_B_20260606" / "citation_annotations.csv"
VENUE200 = ROOT / "metadata" / "venue_200_published_manifest.csv"
MULTI100 = ROOT / "metadata" / "multimodal_rag_100_manifest.csv"
ACCEPTED = ROOT / "metadata" / "venue_accepts_rag_related.csv"
OUT = ROOT / "manuscript" / "supplement" / "evidence_map_venue_expanded.csv"
SUMMARY = ROOT / "manuscript" / "supplement" / "evidence_map_venue_expanded_summary.json"


INCLUDE_DECISIONS = {"main_cite", "case_study", "appendix_cite"}
DECISION_RANK = {"main_cite": 4, "case_study": 3, "appendix_cite": 2, "background_only": 1, "exclude": 0}

BASE_FIELDS = [
    "cite_key",
    "title",
    "authors",
    "year",
    "source_or_venue",
    "url",
    "taxonomy_categories",
    "failure_or_risk_type",
    "method_family",
    "intervention_point",
    "benchmark_or_task",
    "metrics_reported_or_relevant",
    "core_reading_set",
    "actual_contribution",
    "limitation_or_note",
]

EXTRA_FIELDS = [
    "evidence_map_version",
    "source_stratum",
    "original_map_member",
    "venue_expanded_added",
    "previous_core100_raw",
    "human_citation_decision",
    "human_primary_perspective",
    "human_scenario_type",
    "human_relevance",
    "human_evidence_strength",
    "human_suggested_location",
    "artifact_availability",
    "human_supports_claims",
    "human_rationale",
    "human_caveat",
    "human_confidence_1_5",
    "human_collection",
    "human_paper_id",
    "local_pdf",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def norm_title(title: str) -> str:
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    title = re.sub(r"\b(a|an|the)\b", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def source_stratum(source: str) -> str:
    s = (source or "").lower()
    if not s:
        return "other_or_unclear"
    if "arxiv" in s:
        return "arxiv_or_preprint"
    if "openreview" in s and not any(v in s for v in ["iclr", "neurips"]):
        return "review_platform"
    if "workshop" in s:
        return "workshop_or_challenge"
    if any(term in s for term in ["acl", "emnlp", "naacl", "eacl", "coling", "tacl", "neurips", "iclr", "icml", "usenix", "ccs", "ndss", "www", "sigir", "kdd", "findings", "proceedings", "transactions"]):
        return "venue_or_proceedings_linked"
    return "other_or_unclear"


def map_perspective_to_taxonomy(p: str, scenario: str) -> tuple[str, str, str, str]:
    if p == "evidence_construction":
        return "noisy_retrieval;distraction", "noisy_retrieval", "method/evaluation", "retriever/context"
    if p == "model_evidence_use":
        return "knowledge_conflict;faithfulness", "knowledge_conflict", "method/evaluation", "generator"
    if p == "security_integrity":
        return "adversarial_corruption", "adversarial_corruption", "attack/defense", "corpus/KB"
    if p == "action_control":
        return "calibration_control;ood_uncertainty", "calibration_control", "method/evaluation", "system control"
    if p == "evaluation":
        return "evaluation_benchmark", "evaluation_benchmark", "benchmark/evaluation", "evaluation"
    if p == "modality_scenario_core":
        return f"modality_scenario;{scenario}", "modality_scenario", "method/evaluation", "mixed"
    if p == "foundation":
        return "background_foundation", "survey_related", "foundation", "not applicable"
    if p == "boundary":
        return f"boundary;{scenario}", "survey_related", "boundary", "mixed"
    return "survey_related", "survey_related", "unclear", "mixed"


def best_human_rows() -> dict[str, dict[str, str]]:
    venue_by_id = {("venue200_published", r["index"]): r for r in read_csv(VENUE200)}
    multi_by_id = {("multimodal_rag_100", r["index"]): r for r in read_csv(MULTI100)}
    accepted_by_title = {norm_title(r.get("title", "")): r for r in read_csv(ACCEPTED)}
    best: dict[str, dict[str, str]] = {}
    for row in read_csv(HUMAN):
        if row.get("citation_decision") not in INCLUDE_DECISIONS:
            continue
        key = (row.get("collection", ""), row.get("paper_id", ""))
        manifest = venue_by_id.get(key) or multi_by_id.get(key) or {}
        nt = norm_title(row.get("title", ""))
        if not nt:
            continue
        merged = {**manifest, **row}
        accepted = accepted_by_title.get(nt, {})
        if accepted.get("authors") and not merged.get("authors"):
            merged["authors"] = accepted["authors"]
        if accepted.get("landing_url") and not merged.get("landing_url"):
            merged["landing_url"] = accepted["landing_url"]
        if nt not in best or DECISION_RANK[row["citation_decision"]] > DECISION_RANK[best[nt]["citation_decision"]]:
            best[nt] = merged
        elif nt in best:
            # Merge collection provenance for duplicate papers across venue200 and multimodal100.
            best[nt]["collection"] = best[nt].get("collection", "") + ";" + row.get("collection", "")
            best[nt]["paper_id"] = best[nt].get("paper_id", "") + ";" + row.get("paper_id", "")
    return best


def enrich_old(row: dict[str, str], human: dict[str, str] | None, core_titles: set[str]) -> dict[str, str]:
    out = {k: row.get(k, "") for k in BASE_FIELDS}
    out["previous_core100_raw"] = row.get("core100", "")
    out["core_reading_set"] = "true" if norm_title(row.get("title", "")) in core_titles else "false"
    out["evidence_map_version"] = "venue_expanded_2026_06_06"
    out["original_map_member"] = "true"
    out["venue_expanded_added"] = "false"
    if human:
        venue = human.get("venue") or row.get("source_or_venue", "")
        if source_stratum(row.get("source_or_venue", "")) != "venue_or_proceedings_linked" and source_stratum(venue) == "venue_or_proceedings_linked":
            out["source_or_venue"] = venue
            out["url"] = human.get("landing_url") or human.get("pdf_url") or human.get("url") or out["url"]
        out["human_citation_decision"] = human.get("citation_decision", "")
        out["human_primary_perspective"] = human.get("primary_perspective", "")
        out["human_scenario_type"] = human.get("scenario_type", "")
        out["human_relevance"] = human.get("relevance", "")
        out["human_evidence_strength"] = human.get("evidence_strength", "")
        out["human_suggested_location"] = human.get("suggested_location", "")
        out["artifact_availability"] = human.get("artifact_availability", "")
        out["human_supports_claims"] = human.get("supports_claims", "")
        out["human_rationale"] = human.get("rationale", "")
        out["human_caveat"] = human.get("caveat", "")
        out["human_confidence_1_5"] = human.get("confidence_1_5", "")
        out["human_collection"] = human.get("collection", "")
        out["human_paper_id"] = human.get("paper_id", "")
        out["local_pdf"] = human.get("curated_pdf") or human.get("pdf_path") or ""
    else:
        for k in EXTRA_FIELDS:
            out.setdefault(k, "")
    out["source_stratum"] = source_stratum(out.get("source_or_venue", ""))
    return out


def new_row(i: int, human: dict[str, str], core_titles: set[str]) -> dict[str, str]:
    p = human.get("primary_perspective", "")
    scenario = human.get("scenario_type", "")
    tax, failure, family, intervention = map_perspective_to_taxonomy(p, scenario)
    venue = human.get("venue", "")
    url = human.get("landing_url") or human.get("pdf_url", "")
    out = {
        "cite_key": f"venueExpanded{i:03d}",
        "title": human.get("title", ""),
        "authors": human.get("authors", ""),
        "year": human.get("year", ""),
        "source_or_venue": venue,
        "url": url,
        "taxonomy_categories": tax,
        "failure_or_risk_type": failure,
        "method_family": family,
        "intervention_point": intervention,
        "benchmark_or_task": human.get("scenario_type", ""),
        "metrics_reported_or_relevant": human.get("relevance", ""),
        "core_reading_set": "true" if norm_title(human.get("title", "")) in core_titles else "false",
        "actual_contribution": human.get("supports_claims", ""),
        "limitation_or_note": human.get("caveat", ""),
        "evidence_map_version": "venue_expanded_2026_06_06",
        "source_stratum": source_stratum(venue),
        "original_map_member": "false",
        "venue_expanded_added": "true",
        "previous_core100_raw": "",
        "human_citation_decision": human.get("citation_decision", ""),
        "human_primary_perspective": p,
        "human_scenario_type": scenario,
        "human_relevance": human.get("relevance", ""),
        "human_evidence_strength": human.get("evidence_strength", ""),
        "human_suggested_location": human.get("suggested_location", ""),
        "artifact_availability": human.get("artifact_availability", ""),
        "human_supports_claims": human.get("supports_claims", ""),
        "human_rationale": human.get("rationale", ""),
        "human_caveat": human.get("caveat", ""),
        "human_confidence_1_5": human.get("confidence_1_5", ""),
        "human_collection": human.get("collection", ""),
        "human_paper_id": human.get("paper_id", ""),
        "local_pdf": human.get("curated_pdf") or human.get("pdf_path") or "",
    }
    return out


def main() -> None:
    old = read_csv(OLD_MAP)
    core_titles = {norm_title(r["title"]) for r in read_csv(CORE100)}
    human_by_title = best_human_rows()
    out = []
    used_human: set[str] = set()
    for row in old:
        nt = norm_title(row.get("title", ""))
        human = human_by_title.get(nt)
        if human:
            used_human.add(nt)
        out.append(enrich_old(row, human, core_titles))
    counter = 1
    for nt, human in sorted(human_by_title.items(), key=lambda kv: (kv[1].get("citation_decision", ""), kv[1].get("title", ""))):
        if nt in used_human:
            continue
        out.append(new_row(counter, human, core_titles))
        counter += 1
    fields = BASE_FIELDS + EXTRA_FIELDS
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out)
    summary = {
        "version": "venue_expanded_2026_06_06",
        "rows": len(out),
        "old_rows": len(old),
        "human_recommended_unique_titles": len(human_by_title),
        "new_rows_added": sum(1 for r in out if r["venue_expanded_added"] == "true"),
        "original_rows_enriched": sum(1 for r in out if r["original_map_member"] == "true" and r.get("human_citation_decision")),
        "source_strata": dict(Counter(r["source_stratum"] for r in out)),
        "citation_decisions": dict(Counter(r.get("human_citation_decision", "no_human_annotation") or "no_human_annotation" for r in out)),
        "perspectives": dict(Counter(r.get("human_primary_perspective", "no_human_annotation") or "no_human_annotation" for r in out)),
        "core_reading_set": dict(Counter(r["core_reading_set"] for r in out)),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
