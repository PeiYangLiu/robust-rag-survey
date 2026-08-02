#!/usr/bin/env python3
"""Recompute the v3 analyses from the deidentified public categorical labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
DEFAULT_PUBLIC_ROOT = (
    REPO / "manuscript" / "supplement" / "v3_human_reanalysis_20260725"
)
DEFAULT_FROZEN = (
    REPO
    / "manuscript"
    / "human_coding"
    / "heldout_claim_validation_v3_20260715"
    / "frozen_test_claims.csv"
)
DEFAULT_ANALYSIS = DEFAULT_FROZEN.parent / "analyze_collected_results.py"
BOOTSTRAP_SEED = 2026071504
BOOTSTRAP_REPLICATES = 100_000
FLOAT_TOLERANCE = 1.0e-12
PUBLIC_INPUTS = (
    "public_arm_ratings.csv",
    "public_gold_ratings.csv",
    "public_adjudications.csv",
)
RECOMPUTABLE_TABLES = {
    "analysis_claim_level.csv": ("CLAIM_LEVEL_HEADER", "claim_level"),
    "analysis_pairwise.csv": ("PAIRWISE_HEADER", "pairwise"),
    "analysis_gold_resolution.csv": ("GOLD_RESOLUTION_HEADER", "gold_resolution"),
    "analysis_agreement.csv": ("AGREEMENT_HEADER", "agreement"),
    "analysis_confusion.csv": ("CONFUSION_HEADER", "confusion"),
    "analysis_missingness_patterns.csv": (
        "MISSINGNESS_PATTERN_HEADER",
        "missingness_patterns",
    ),
    "analysis_individual_raters.csv": (
        "INDIVIDUAL_RATER_HEADER",
        "individual_raters",
    ),
    "analysis_rater_sensitivity.csv": (
        "RATER_SENSITIVITY_HEADER",
        "rater_sensitivity",
    ),
}
PRIVATE_RECOMPUTABLE_TABLES = {
    "analysis_individual_raters.csv",
    "analysis_rater_sensitivity.csv",
}
VERIFIED_TABLES = tuple(
    filename
    for filename in RECOMPUTABLE_TABLES
    if filename not in PRIVATE_RECOMPUTABLE_TABLES
    and (DEFAULT_PUBLIC_ROOT / filename).is_file()
)
RECOMPUTABLE_RESULT_KEYS = (
    "status",
    "analysis_dependencies",
    "separate_outputs",
    "input_authentication_limitation",
    "primary",
    "missingness",
    "arm_accuracy",
    "no_consensus",
    "adjudicator_sensitivity",
    "post_hoc_exploratory_rater_sensitivity",
    "multiplicity",
)
RELEASE_ID_RE = re.compile(r"^release_[0-9a-f]{24}$")


def public_field_allowed(field: str) -> bool:
    normalized = field.lower()
    return (
        normalized != "participant_id"
        and "rationale" not in normalized
        and normalized != "reason"
        and not normalized.endswith("_reason")
        and not re.search(
            r"(?:^|_)(?:start|started|completion|completed)(?:$|_)",
            normalized,
        )
    )


def sanitize_public_object(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: sanitize_public_object(nested)
            for key, nested in value.items()
            if public_field_allowed(str(key))
        }
    if isinstance(value, list):
        return [sanitize_public_object(nested) for nested in value]
    return value


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_analysis(path: Path) -> ModuleType:
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("v3_public_analysis_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load analysis module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = {
        "analyze",
        "write_csv",
        "ARMS",
        "BOOTSTRAP_SEED",
        "BOOTSTRAP_REPLICATES",
    }
    missing = sorted(name for name in required if not hasattr(module, name))
    if missing:
        raise ValueError(f"analysis module is missing: {', '.join(missing)}")
    if module.BOOTSTRAP_SEED != BOOTSTRAP_SEED:
        raise ValueError("analysis module bootstrap seed does not match the release")
    if module.BOOTSTRAP_REPLICATES != BOOTSTRAP_REPLICATES:
        raise ValueError("analysis module bootstrap replicate count does not match")
    return module


def verify_public_manifest(public_root: Path) -> None:
    manifest_path = public_root / "public_release_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "heldout-claim-validation-public-v1":
        raise ValueError("unsupported public release manifest schema")
    listed = set()
    for record in manifest.get("files", []):
        basename = str(record.get("basename", ""))
        path = public_root / basename
        if not basename or Path(basename).name != basename or not path.is_file():
            raise ValueError(f"invalid public manifest entry: {basename!r}")
        if basename in listed:
            raise ValueError(f"duplicate public manifest entry: {basename}")
        listed.add(basename)
        if sha256(path) != record.get("sha256"):
            raise ValueError(f"public manifest hash mismatch: {basename}")
        expected_rows = int(record.get("row_count", -1))
        actual_rows = 1
        if path.suffix == ".csv":
            _header, rows = read_csv(path)
            actual_rows = len(rows)
        if expected_rows != actual_rows:
            raise ValueError(f"public manifest row-count mismatch: {basename}")
    missing = sorted(set(PUBLIC_INPUTS) - listed)
    if missing:
        raise ValueError(f"public manifest omits required input(s): {missing}")


def validate_release_ids(
    rows: Sequence[Mapping[str, str]],
    role: str,
    arm: str = "",
    allow_empty: bool = False,
    expected_participants: int | None = None,
) -> None:
    ids = set()
    for index, row in enumerate(rows, start=2):
        release_id = (row.get("release_participant_id") or "").strip()
        if not RELEASE_ID_RE.fullmatch(release_id):
            raise ValueError(f"invalid release participant ID at {role} row {index}")
        if (row.get("role") or "").strip() != role:
            raise ValueError(f"role mismatch at {role} row {index}")
        if (row.get("arm") or "").strip() != arm:
            raise ValueError(f"arm mismatch at {role} row {index}")
        ids.add(release_id)
    if not ids and not allow_empty:
        raise ValueError(f"no public rows for {role} {arm}".strip())
    if (
        ids
        and expected_participants is not None
        and len(ids) != expected_participants
    ):
        raise ValueError(
            f"{role} {arm} has {len(ids)} release IDs; "
            f"expected {expected_participants}"
        )


def reconstruct_inputs(
    public_root: Path, frozen_claims: Path, module: ModuleType
) -> tuple[
    list[dict[str, str]],
    dict[str, list[dict[str, str]]],
    dict[str, tuple[str, ...]],
    list[dict[str, str]],
    tuple[str, ...],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    verify_public_manifest(public_root)
    frozen_header, frozen = read_csv(frozen_claims)
    required_frozen = {
        "claim_id",
        "source_key",
        "coordinator_only_primary_stratum",
    }
    if not required_frozen <= set(frozen_header):
        raise ValueError("frozen claims lack fields required by the analysis")
    frozen_by_id = {row["claim_id"]: row for row in frozen}
    if len(frozen) != len(frozen_by_id):
        raise ValueError("duplicate frozen claim IDs")

    arm_header, public_arms = read_csv(public_root / "public_arm_ratings.csv")
    gold_header_public, gold = read_csv(public_root / "public_gold_ratings.csv")
    adjudication_header, adjudications = read_csv(
        public_root / "public_adjudications.csv"
    )
    expected_arm_header = {
        "claim_id",
        "source_key",
        "release_participant_id",
        "arm",
        "role",
        "response_status",
        "missing_reason_code",
        "evidence_support_label",
        "comparability_label",
    }
    expected_adjudication_header = {
        "claim_id",
        "source_key",
        "release_participant_id",
        "arm",
        "role",
        "response_status",
        "missing_reason_code",
        "adjudicated_evidence_support_label",
        "adjudicated_comparability_label",
        "disputed_outputs",
    }
    if set(arm_header) != expected_arm_header:
        raise ValueError("unexpected public arm schema")
    if set(gold_header_public) != expected_arm_header:
        raise ValueError("unexpected public gold schema")
    if set(adjudication_header) != expected_adjudication_header:
        raise ValueError("unexpected public adjudication schema")

    def validate_claim(row: Mapping[str, str], label: str) -> None:
        claim_id = (row.get("claim_id") or "").strip()
        if claim_id not in frozen_by_id:
            raise ValueError(f"{label} contains unknown claim {claim_id!r}")
        expected_source = (frozen_by_id[claim_id].get("source_key") or "").strip()
        if (row.get("source_key") or "").strip() != expected_source:
            raise ValueError(f"{label} source mismatch for {claim_id}")

    arm_rows: dict[str, list[dict[str, str]]] = {
        arm: [] for arm in module.ARMS
    }
    for row in public_arms:
        arm = (row.get("arm") or "").strip()
        if arm not in arm_rows:
            raise ValueError(f"invalid public arm: {arm!r}")
        validate_claim(row, "public arm ratings")
        rebuilt = dict(row)
        rebuilt["participant_id"] = rebuilt["release_participant_id"]
        arm_rows[arm].append(rebuilt)
    for arm in module.ARMS:
        validate_release_ids(
            arm_rows[arm], "auditor", arm, expected_participants=6
        )

    for row in gold:
        validate_claim(row, "public gold ratings")
        row["participant_id"] = row["release_participant_id"]
    validate_release_ids(gold, "gold", expected_participants=3)

    adjudicator_rows: list[list[dict[str, str]]] = []
    for role in ("adjudicator_1", "adjudicator_2"):
        rows = [dict(row) for row in adjudications if row.get("role") == role]
        for row in rows:
            validate_claim(row, "public adjudications")
            row["participant_id"] = row["release_participant_id"]
        validate_release_ids(
            rows, role, allow_empty=True, expected_participants=1
        )
        adjudicator_rows.append(rows)
    if sum(len(rows) for rows in adjudicator_rows) != len(adjudications):
        raise ValueError("public adjudications contain an unknown role")

    # These synthetic headers make the inherited analysis skip private extraction
    # columns. Field and timing tables are discarded below, not reconstructed.
    arm_headers = {
        arm: ("extraction_completed_utc", "composition_started_utc")
        for arm in module.ARMS
    }
    gold_header = ("review_started_utc", "composition_started_utc")
    return (
        frozen,
        arm_rows,
        arm_headers,
        gold,
        gold_header,
        adjudicator_rows[0],
        adjudicator_rows[1],
    )


def recomputable_results(results: Mapping[str, object]) -> dict[str, object]:
    return sanitize_public_object(
        {key: results[key] for key in RECOMPUTABLE_RESULT_KEYS}
    )


def compare_json(
    actual: object,
    expected: object,
    path: str,
    differences: list[str],
) -> None:
    if isinstance(actual, bool) or isinstance(expected, bool):
        if actual is not expected:
            differences.append(f"{path}: {actual!r} != {expected!r}")
        return
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if not math.isclose(
            float(actual), float(expected), rel_tol=FLOAT_TOLERANCE,
            abs_tol=FLOAT_TOLERANCE
        ):
            differences.append(f"{path}: {actual!r} != {expected!r}")
        return
    if isinstance(actual, Mapping) and isinstance(expected, Mapping):
        if set(actual) != set(expected):
            differences.append(
                f"{path}: keys {sorted(actual)} != {sorted(expected)}"
            )
            return
        for key in actual:
            compare_json(actual[key], expected[key], f"{path}.{key}", differences)
        return
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            differences.append(f"{path}: lengths {len(actual)} != {len(expected)}")
            return
        for index, (left, right) in enumerate(zip(actual, expected)):
            compare_json(left, right, f"{path}[{index}]", differences)
        return
    if actual != expected:
        differences.append(f"{path}: {actual!r} != {expected!r}")


def compare_csv_rows(
    actual: Sequence[Mapping[str, object]],
    expected: Sequence[Mapping[str, str]],
    filename: str,
    differences: list[str],
) -> None:
    if len(actual) != len(expected):
        differences.append(
            f"{filename}: row counts {len(actual)} != {len(expected)}"
        )
        return
    for row_number, (left, right) in enumerate(zip(actual, expected), start=2):
        if set(left) != set(right):
            differences.append(f"{filename}:{row_number}: field mismatch")
            continue
        for field, value in left.items():
            published = right[field]
            if isinstance(value, bool):
                same = str(value).lower() == published.lower()
            elif isinstance(value, (int, float)):
                try:
                    same = math.isclose(
                        float(value),
                        float(published),
                        rel_tol=FLOAT_TOLERANCE,
                        abs_tol=FLOAT_TOLERANCE,
                    )
                except ValueError:
                    same = False
            else:
                same = str(value) == published
            if not same:
                differences.append(
                    f"{filename}:{row_number}:{field}: "
                    f"{value!r} != {published!r}"
                )
            if len(differences) >= 50:
                return


def verify_published(
    public_root: Path,
    results: Mapping[str, object],
    tables: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    differences: list[str] = []
    published = json.loads(
        (public_root / "analysis_results.json").read_text(encoding="utf-8")
    )
    expected_results = {
        key: published[key] for key in RECOMPUTABLE_RESULT_KEYS
    }
    compare_json(
        recomputable_results(results),
        expected_results,
        "analysis_results.json",
        differences,
    )
    for filename in VERIFIED_TABLES:
        header, expected_rows = read_csv(public_root / filename)
        table_name = RECOMPUTABLE_TABLES[filename][1]
        actual_rows = []
        for row in tables[table_name]:
            if not set(header) <= set(row):
                differences.append(f"{filename}: published fields are not recomputable")
                break
            actual_rows.append({field: row[field] for field in header})
        compare_csv_rows(actual_rows, expected_rows, filename, differences)
    if differences:
        raise ValueError(
            "published verification failed with "
            f"{len(differences)} difference(s):\n" + "\n".join(differences[:50])
        )
    return {
        "status": "exact_within_numeric_tolerance",
        "numeric_tolerance": FLOAT_TOLERANCE,
        "differences": 0,
        "files": ["analysis_results.json", *VERIFIED_TABLES],
    }


def write_outputs(
    output: Path,
    public_root: Path,
    frozen_claims: Path,
    analysis_module: Path,
    module: ModuleType,
    results: Mapping[str, object],
    tables: Mapping[str, Sequence[Mapping[str, object]]],
    verification: Mapping[str, object] | None,
) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "public-v3-reanalysis-v1",
        "status": "PUBLIC_REANALYSIS_COMPLETE",
        "inputs": {
            "public_root": str(public_root),
            "frozen_claims": str(frozen_claims),
            "analysis_module": str(analysis_module),
        },
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
        },
        "release_participant_id_semantics": (
            "Every release_participant_id in derived CSVs is an opaque "
            "HMAC-derived identifier, never an original identifier."
        ),
        "recomputed": recomputable_results(results),
        "not_recomputable_from_public_release": [
            "free-text rationales",
            "row or packet timing",
            "extraction-stage fields and their completeness diagnostics",
            "original participant identities or the HMAC deidentification key",
        ],
        "published_verification": verification or {
            "status": "not_requested",
            "differences": None,
        },
    }
    (output / "public_reanalysis_results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for filename, (header_name, table_name) in RECOMPUTABLE_TABLES.items():
        source_header = getattr(module, header_name)
        header = tuple(
            "release_participant_id" if field == "participant_id" else field
            for field in source_header
            if public_field_allowed(field) or field == "participant_id"
        )
        rows = []
        for row in tables[table_name]:
            public_row = {
                (
                    "release_participant_id"
                    if field == "participant_id"
                    else field
                ): value
                for field, value in row.items()
                if public_field_allowed(field) or field == "participant_id"
            }
            rows.append(public_row)
        module.write_csv(
            output / filename,
            header,
            rows,
        )


def run(
    public_root: Path,
    frozen_claims: Path,
    analysis_module: Path,
    output: Path,
    verify: bool,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, object]:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output directory must be absent or empty: {output}")
    module = load_analysis(analysis_module)
    inputs = reconstruct_inputs(public_root, frozen_claims, module)
    results, tables = module.analyze(*inputs, bootstrap_replicates)
    verification = (
        verify_published(public_root, results, tables) if verify else None
    )
    write_outputs(
        output,
        public_root,
        frozen_claims,
        analysis_module,
        module,
        results,
        tables,
        verification,
    )
    return {
        "output": str(output),
        "claims": results["primary"]["claims"],
        "estimate": results["primary"]["estimate"],
        "verification": (
            verification["status"] if verification else "not_requested"
        ),
    }


def write_synthetic_public(root: Path) -> Path:
    public_root = root / "public"
    public_root.mkdir()
    frozen_path = root / "frozen_test_claims.csv"
    frozen_header = (
        "claim_id",
        "source_key",
        "coordinator_only_primary_stratum",
    )
    claims = [
        {
            "claim_id": f"SYN-{index + 1:02d}",
            "source_key": f"source-{index // 2 + 1}",
            "coordinator_only_primary_stratum": (
                "c2_decisive" if index % 2 == 0 else "c5_decisive"
            ),
        }
        for index in range(4)
    ]

    def write(
        path: Path,
        header: Sequence[str],
        rows: Sequence[Mapping[str, str]],
    ) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    write(frozen_path, frozen_header, claims)
    arm_header = (
        "claim_id",
        "source_key",
        "release_participant_id",
        "arm",
        "role",
        "response_status",
        "missing_reason_code",
        "evidence_support_label",
        "comparability_label",
    )
    arms: list[dict[str, str]] = []
    for arm_index, arm in enumerate(("A", "B", "C", "D")):
        for claim_index, claim in enumerate(claims):
            for vote in range(3):
                participant = (claim_index * 3 + vote) % 6
                arms.append(
                    {
                        "claim_id": claim["claim_id"],
                        "source_key": claim["source_key"],
                        "release_participant_id": (
                            f"release_{arm_index:02x}{participant:02x}" + "0" * 20
                        ),
                        "arm": arm,
                        "role": "auditor",
                        "response_status": "completed",
                        "missing_reason_code": "",
                        "evidence_support_label": "supported_as_written",
                        "comparability_label": "same_estimand",
                    }
                )
    gold: list[dict[str, str]] = []
    for claim in claims:
        for participant in range(3):
            gold.append(
                {
                    "claim_id": claim["claim_id"],
                    "source_key": claim["source_key"],
                    "release_participant_id": (
                        f"release_ff{participant:02x}" + "0" * 20
                    ),
                    "arm": "",
                    "role": "gold",
                    "response_status": "completed",
                    "missing_reason_code": "",
                    "evidence_support_label": "supported_as_written",
                    "comparability_label": "same_estimand",
                }
            )
    adjudication_header = (
        "claim_id",
        "source_key",
        "release_participant_id",
        "arm",
        "role",
        "response_status",
        "missing_reason_code",
        "adjudicated_evidence_support_label",
        "adjudicated_comparability_label",
        "disputed_outputs",
    )
    adjudications: list[dict[str, str]] = []
    write(public_root / "public_arm_ratings.csv", arm_header, arms)
    write(public_root / "public_gold_ratings.csv", arm_header, gold)
    write(public_root / "public_adjudications.csv", adjudication_header, adjudications)
    files = []
    for basename in PUBLIC_INPUTS:
        path = public_root / basename
        _header, rows = read_csv(path)
        files.append(
            {
                "basename": basename,
                "row_count": len(rows),
                "sha256": sha256(path),
            }
        )
    (public_root / "public_release_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "heldout-claim-validation-public-v1",
                "files": files,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return frozen_path


def self_test(analysis_module: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix=".public-v3-self-test-", dir=REPO
    ) as directory:
        root = Path(directory)
        frozen = write_synthetic_public(root)
        summary = run(
            root / "public",
            frozen,
            analysis_module,
            root / "output",
            verify=False,
            bootstrap_replicates=200,
        )
        payload = json.loads(
            (root / "output" / "public_reanalysis_results.json").read_text()
        )
        assert summary["claims"] == 4
        assert payload["bootstrap"]["seed"] == BOOTSTRAP_SEED
        assert "row or packet timing" in payload[
            "not_recomputable_from_public_release"
        ]
        assert not (root / "output" / "analysis_response_diagnostics.csv").exists()
        assert not (root / "output" / "analysis_field_diagnostics.csv").exists()
    print("public v3 reanalysis self-test passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-root", type=Path, default=DEFAULT_PUBLIC_ROOT)
    parser.add_argument("--frozen-claims", type=Path, default=DEFAULT_FROZEN)
    parser.add_argument("--analysis-module", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-published", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test(args.analysis_module.resolve())
        return 0
    if args.output is None:
        raise SystemExit("--output is required unless --self-test is used")
    summary = run(
        args.public_root.resolve(),
        args.frozen_claims.resolve(),
        args.analysis_module.resolve(),
        args.output.resolve(),
        args.verify_published,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
