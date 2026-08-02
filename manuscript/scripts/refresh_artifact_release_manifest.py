#!/usr/bin/env python3
"""Build the full release inventory without self-referential manifest hashes."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path


OUTPUT_PATHS = {
    "manuscript/supplement/artifact_release_manifest.csv",
    "manuscript/supplement/artifact_release_manifest.json",
}
EXCLUDED_OUTCOME_PREFIXES = (
    "manuscript/supplement/v3_human_reanalysis_20260725/",
    "manuscript/supplement/v3_",
    "manuscript/tables/v3_",
    "manuscript/tables/main_v3_",
    "manuscript/figures/v3_",
    "manuscript/figures/generated/fig4_v3_",
)
EXCLUDED_RELEASE_EXACT = {
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/README.md",
}
HELDOUT_DESIGN_PREFIX = (
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/"
)


def is_excluded_outcome(
    path: str, reviewer_paths: set[str]
) -> bool:
    return (
        path in EXCLUDED_RELEASE_EXACT
        or path.startswith(EXCLUDED_OUTCOME_PREFIXES)
        or (
            path.startswith(HELDOUT_DESIGN_PREFIX)
            and path not in reviewer_paths
        )
    )
INCLUDE_GLOBS = (
    "README.md",
    "LICENSE",
    "DATA_LICENSE.md",
    "files/v3_invalidated_shared_answer_run_20260719/invalidation_report.json",
    "manuscript/*.tex",
    "manuscript/*.pdf",
    "manuscript/*.zip",
    "manuscript/*.bib",
    "manuscript/*.bst",
    "manuscript/*.sty",
    "manuscript/figures/**/*.tex",
    "manuscript/figures/generated/*.pdf",
    "manuscript/figures/generated/*.png",
    "manuscript/tables/**/*.tex",
    "manuscript/supplement/**/*.csv",
    "manuscript/supplement/**/*.json",
    "manuscript/supplement/**/*.jsonl",
    "manuscript/supplement/**/*.md",
    "manuscript/supplement/**/*.txt",
    "manuscript/human_coding/observed_claim_human_validation_20260714/analysis/*.py",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/**/*.csv",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/**/*.json",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/**/*.md",
    "manuscript/human_coding/observed_claim_human_validation_20260714/annotated_20260714/**/*.txt",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/*.py",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/*.md",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/*.json",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/*.csv",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/*.txt",
    "manuscript/human_coding/heldout_claim_validation_v3_20260715/MANIFEST.sha256",
    "manuscript/scripts/*.py",
    "overleaf_package/**/*",
    "scripts/*.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_count(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return str(max(0, sum(1 for _ in csv.reader(handle)) - 1))
    if suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return str(sum(1 for line in handle if line.strip()))
    return ""


def default_status(relative_path: str) -> tuple[str, str]:
    if "v3_human_reanalysis_20260725" in relative_path:
        return (
            "excluded_unverifiable_human_collection",
            "Historical deidentified export excluded because it cannot be linked to controlled recruitment, one-to-one pseudonym mapping, and separate response receipts in an access-controlled audit trail.",
        )
    if "heldout_claim_validation_v3_20260715" in relative_path:
        return (
            "design_audit_only",
            "Frozen pre-outcome protocol or workflow artifact retained as a design case; no later human outcome is accepted.",
        )
    if (
        "/tables/v3_" in relative_path
        or "/tables/main_v3_" in relative_path
        or "/figures/v3_" in relative_path
        or "/figures/generated/fig4_v3_" in relative_path
        or "/supplement/v3_" in relative_path
    ):
        return (
            "excluded_unverifiable_human_collection",
            "Historical table, figure, or derived output from the excluded human collection; not manuscript evidence.",
        )
    if "expert_validation_60pair_results_R17_20260607" in relative_path:
        return "superseded", "Earlier R17 result; not used for manuscript numbers."
    if "candidate_set_R17" in relative_path:
        return "superseded", "Earlier R17 packet; retained for provenance only."
    if "synthetic_" in relative_path:
        return (
            "exploratory_synthetic_not_human",
            "Model-generated dry run; never human evidence.",
        )
    if "round2_candidate_pairs_20260616" in relative_path:
        return "exploratory", "Heuristic candidate construction; no completed human study."
    if "action_labeled_pilot" in relative_path:
        return (
            "exploratory",
            "Repeated-template schema prototype; model scores are not manuscript evidence.",
        )
    return "supporting", "Supporting release artifact."


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_csv = repo_root / "manuscript" / "supplement" / "artifact_release_manifest.csv"
    output_json = repo_root / "manuscript" / "supplement" / "artifact_release_manifest.json"
    canonical_csv = (
        repo_root / "manuscript" / "supplement" / "canonical_artifact_index.csv"
    )

    canonical_rows: list[dict[str, str]] = []
    with canonical_csv.open(newline="", encoding="utf-8-sig") as handle:
        canonical_rows = list(csv.DictReader(handle))
    canonical_by_path = {row["path"]: row for row in canonical_rows}
    with zipfile.ZipFile(repo_root / "manuscript" / "review_data_package.zip") as archive:
        reviewer_paths = set(archive.namelist())

    release_paths: set[str] = set()
    for pattern in INCLUDE_GLOBS:
        for path in repo_root.glob(pattern):
            if path.is_file():
                release_paths.add(path.relative_to(repo_root).as_posix())
    release_paths -= OUTPUT_PATHS
    release_paths = {
        path
        for path in release_paths
        if not is_excluded_outcome(path, reviewer_paths)
    }

    records_by_path: dict[str, dict[str, str]] = {
        relative_path: {
            "artifact": relative_path.replace("/", "__").rsplit(".", 1)[0],
            "path": relative_path,
        }
        for relative_path in release_paths
    }
    for row in canonical_rows:
        if is_excluded_outcome(row["path"], reviewer_paths):
            continue
        records_by_path[row["path"]] = {
            "artifact": row["artifact"],
            "path": row["path"],
        }
    output_rows: list[dict[str, str]] = []
    for relative_path in sorted(records_by_path):
        path = repo_root / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"Manifest path does not exist: {relative_path}")
        canonical = canonical_by_path.get(relative_path)
        if canonical:
            status = canonical["status"]
            notes = canonical["notes"]
        else:
            status, notes = default_status(relative_path)
        output_rows.append(
            {
                "artifact": records_by_path[relative_path]["artifact"],
                "path": relative_path,
                "status": status,
                "exists": "true",
                "rows": row_count(path),
                "sha256": sha256(path),
                "notes": notes,
            }
        )

    fields = ["artifact", "path", "status", "exists", "rows", "sha256", "notes"]
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    with output_json.open("w", encoding="utf-8") as handle:
        json.dump(output_rows, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(
        f"Wrote {len(output_rows)} non-self-referential records to "
        f"{output_csv} and {output_json}"
    )


if __name__ == "__main__":
    main()
