#!/usr/bin/env python3
"""Validate and summarize the published robust-RAG human-evaluation audit."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
MANUSCRIPT = REPO / "manuscript"
DEFAULT_AUDIT = (
    MANUSCRIPT / "supplement" / "published_human_evaluation_audit.json"
)
DEFAULT_SCREEN_MANIFEST = (
    MANUSCRIPT
    / "supplement"
    / "published_human_evaluation_screen_manifest.csv"
)
DEFAULT_SUMMARY = (
    MANUSCRIPT / "supplement" / "published_human_evaluation_audit_summary.json"
)
DEFAULT_MAIN_TABLE = (
    MANUSCRIPT / "tables" / "main_published_human_evaluation_audit.tex"
)
DEFAULT_CASE_TABLE = (
    MANUSCRIPT / "tables" / "published_human_evaluation_case_ledger.tex"
)
HUMAN_PATTERN = re.compile(
    r"human evaluat|manual(?:ly)? (?:evaluat|annotat|check|review)|"
    r"human annotat|annotator|rater|crowdworker|crowdsourc|user study|"
    r"human judge|human-labeled|human labeled|expert evaluat|expert annotat",
    flags=re.IGNORECASE,
)
FIELDS = (
    "total_annotator_count",
    "raters_per_item",
    "item_assignment",
    "aggregation_rule",
    "rater_uncertainty",
    "recruitment_or_qualification",
    "compensation",
    "reference_resolution",
)
FIELD_LABELS = {
    "total_annotator_count": "Distinct annotator count",
    "raters_per_item": "Raters per item",
    "item_assignment": "Item--annotator assignment",
    "aggregation_rule": "Aggregation rule",
    "rater_uncertainty": "Rater agreement/uncertainty",
    "recruitment_or_qualification": "Recruitment or qualifications",
    "compensation": "Compensation",
    "reference_resolution": "Disagreement/reference resolution",
}
ALLOWED_STATUSES = {
    "reported",
    "partly_reported",
    "not_reported",
    "not_applicable",
}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(text, encoding="utf-8")
    staging.replace(path)


def load_map(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locator_sha256(text_path: Path, ranges: Sequence[str]) -> str:
    lines = text_path.read_text(encoding="utf-8", errors="strict").splitlines()
    payload = []
    for value in ranges:
        start, end = map(int, value.split("-"))
        payload.append(value)
        payload.extend(lines[start - 1 : end])
    return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def validate_line_ranges(text_path: Path, ranges: Sequence[str]) -> None:
    lines = text_path.read_text(encoding="utf-8", errors="strict").splitlines()
    for value in ranges:
        match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", value)
        if not match:
            raise ValueError(f"invalid source line range {value!r}")
        start, end = map(int, match.groups())
        if start > end or end > len(lines):
            raise ValueError(f"out-of-range locator {text_path}:{value}")
        if not any(line.strip() for line in lines[start - 1 : end]):
            raise ValueError(f"empty source line range {text_path}:{value}")


def validate_and_summarize(
    audit: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, Mapping[str, str]]]:
    screen = audit["screen"]
    map_path = REPO / str(screen["map_path"])
    text_directory = REPO / str(screen["text_directory"])
    map_rows = load_map(map_path)
    by_key = {row["cite_key"]: row for row in map_rows}
    text_paths = {path.stem: path for path in text_directory.glob("*.txt")}
    venue_text_rows = [
        row
        for row in map_rows
        if row["source_stratum"] == "venue_or_proceedings_linked"
        and row["cite_key"] in text_paths
    ]
    candidates = [
        row["cite_key"]
        for row in venue_text_rows
        if HUMAN_PATTERN.search(
            text_paths[row["cite_key"]].read_text(
                encoding="utf-8", errors="strict"
            )
        )
    ]
    rows = audit["rows"]
    with DEFAULT_SCREEN_MANIFEST.open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        frozen_screen = list(csv.DictReader(handle))
    frozen_by_key = {row["cite_key"]: row for row in frozen_screen}
    venue_keys = {row["cite_key"] for row in venue_text_rows}
    if venue_keys != set(frozen_by_key):
        raise ValueError("venue-linked full-text identity set changed")
    if set(candidates) != {
        row["cite_key"] for row in frozen_screen if row["term_screened"] == "true"
    }:
        raise ValueError("human-term candidate identity set changed")
    for cite_key, frozen in frozen_by_key.items():
        if sha256(text_paths[cite_key]) != frozen["text_sha256"]:
            raise ValueError(f"full-text hash changed for {cite_key}")
    if len(venue_text_rows) != int(screen["expected_venue_linked_texts"]):
        raise ValueError("venue-linked full-text screen count changed")
    if len(candidates) != int(screen["expected_term_screened_candidates"]):
        raise ValueError("human-term candidate count changed")
    if len(rows) != int(screen["expected_included_studies"]):
        raise ValueError("included audit count changed")
    included_keys = [str(row["cite_key"]) for row in rows]
    if len(included_keys) != len(set(included_keys)):
        raise ValueError("duplicate included study")
    if not set(included_keys).issubset(candidates):
        raise ValueError("included study did not pass the fixed term screen")
    if set(included_keys) != {
        row["cite_key"] for row in frozen_screen if row["included"] == "true"
    }:
        raise ValueError("included audit identity set changed")

    counts = {field: Counter() for field in FIELDS}
    for row in rows:
        cite_key = str(row["cite_key"])
        if cite_key not in by_key:
            raise ValueError(f"unknown map key: {cite_key}")
        if by_key[cite_key]["source_stratum"] != "venue_or_proceedings_linked":
            raise ValueError(f"non-published audit row: {cite_key}")
        validate_line_ranges(text_paths[cite_key], row["source_line_ranges"])
        frozen = frozen_by_key[cite_key]
        if (
            locator_sha256(text_paths[cite_key], row["source_line_ranges"])
            != frozen["locator_sha256"]
        ):
            raise ValueError(f"source locator content changed for {cite_key}")
        for field in FIELDS:
            status = str(row[field])
            if status not in ALLOWED_STATUSES:
                raise ValueError(f"invalid {field} status for {cite_key}")
            counts[field][status] += 1
        if row["treatment_assigned_to_annotators"] != "no":
            raise ValueError("audit contains an annotator-level treatment")
        if row["confirmed_assignment_unit_mismatch"] != "no":
            raise ValueError("audit contains a claimed assignment-unit mismatch")

    summary = {
        "schema_version": "published-robust-rag-human-evaluation-audit-summary-v1",
        "venue_linked_full_texts": len(venue_text_rows),
        "term_screened_candidates": len(candidates),
        "included_human_judgment_studies": len(rows),
        "included_cite_keys": included_keys,
        "term_screened_cite_keys": sorted(candidates),
        "screen_manifest": DEFAULT_SCREEN_MANIFEST.name,
        "screen_manifest_sha256": sha256(DEFAULT_SCREEN_MANIFEST),
        "reporting_counts": {
            field: {
                status: counts[field][status]
                for status in (
                    "reported",
                    "partly_reported",
                    "not_reported",
                    "not_applicable",
                )
            }
            for field in FIELDS
        },
        "annotator_treatment_studies": 0,
        "confirmed_assignment_unit_mismatches": 0,
        "interpretation": (
            "Missing fields are reporting gaps, not evidence that an unreported "
            "design choice was absent or incorrect."
        ),
    }
    return summary, by_key


def render_main_table(summary: Mapping[str, object]) -> str:
    counts = summary["reporting_counts"]
    lines = [
        r"\begin{table}[t]",
        r"\centering\footnotesize",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Reporting field & R & P & NR & N/A \\",
        r"\midrule",
    ]
    for field in FIELDS:
        row = counts[field]
        lines.append(
            f"{FIELD_LABELS[field]} & {row['reported']} & "
            f"{row['partly_reported']} & {row['not_reported']} & "
            f"{row['not_applicable']} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            (
                r"\caption{Reporting audit of nine published robust-RAG studies "
                r"that collected original human judgments, identified from 39 "
                r"venue-linked Map B papers with local full text (19 passed the "
                r"term screen). R/P/NR denote reported, partly reported, and not "
                r"reported. None randomized an audit prompt across annotators, "
                r"so we found no verifiable assignment-unit mismatch. Missing "
                r"fields are reporting gaps, not evidence of design errors.}"
            ),
            r"\label{tab:published-human-evaluation-audit}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def render_case_table(
    audit: Mapping[str, object],
    by_key: Mapping[str, Mapping[str, str]],
) -> str:
    status_symbol = {
        "reported": "R",
        "partly_reported": "P",
        "not_reported": "--",
        "not_applicable": "N/A",
    }
    lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabularx}{\linewidth}{l>{\raggedright\arraybackslash}Xrrrrrr}",
        r"\toprule",
        (
            r"Study & Human role & $N_r$ & $r/i$ & Assign. & Agg. & "
            r"Rater unc. & Resolution \\"
        ),
        r"\midrule",
    ]
    for row in audit["rows"]:
        cite_key = str(row["cite_key"])
        role = latex_escape(str(row["human_role"]))
        lines.append(
            rf"\citet{{{cite_key}}} & {role} & "
            f"{status_symbol[str(row['total_annotator_count'])]} & "
            f"{status_symbol[str(row['raters_per_item'])]} & "
            f"{status_symbol[str(row['item_assignment'])]} & "
            f"{status_symbol[str(row['aggregation_rule'])]} & "
            f"{status_symbol[str(row['rater_uncertainty'])]} & "
            f"{status_symbol[str(row['reference_resolution'])]} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabularx}",
            (
                r"\caption{Case ledger for the published human-evaluation "
                r"reporting audit. $N_r$ is the distinct annotator count and "
                r"$r/i$ the number of raters per item; R/P/-- denote reported, "
                r"partly reported, and not reported. The machine-readable audit "
                r"links each judgment to full-text line ranges. No row assigns "
                r"a prompt treatment to annotators, and no row is classified as "
                r"a confirmed assignment-unit error.}"
            ),
            r"\label{tab:published-human-evaluation-cases}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    audit = json.loads(DEFAULT_AUDIT.read_text(encoding="utf-8"))
    summary, by_key = validate_and_summarize(audit)
    write_text(
        DEFAULT_SUMMARY,
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    write_text(DEFAULT_MAIN_TABLE, render_main_table(summary))
    write_text(DEFAULT_CASE_TABLE, render_case_table(audit, by_key))
    print(
        json.dumps(
            {
                "status": "ok",
                "included": summary["included_human_judgment_studies"],
                "candidates": summary["term_screened_candidates"],
                "outputs": [
                    str(DEFAULT_SUMMARY),
                    str(DEFAULT_MAIN_TABLE),
                    str(DEFAULT_CASE_TABLE),
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
