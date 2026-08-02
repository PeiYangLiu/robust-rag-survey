#!/usr/bin/env python3
"""Build the v1/v2 claim-level development-source exclusion list."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


FIXED_V2_KEYS = frozenset(
    {
        "securityRAGSurvey2026",
        "alushi2026comparison",
        "joren2025sufficient",
        "ragComprehensive2025",
        "trustRAGCompass2024",
        "wen2025abstention",
        "liu2025donotabstain",
        "trustworthyRAGSurvey2025",
        "zhu2026trustabstain",
    }
)
PAIR_COLUMNS = (
    ("paper_a_id", "paper_a_title"),
    ("paper_b_id", "paper_b_title"),
)
DEVELOPMENT_SOURCES_HEADER = (
    "source_key",
    "normalized_title",
    "source_title",
    "provenance_scope",
)
V1_SCOPE = "v1_validation_pair_provenance"
V2_SCOPE = "v2_fixed_nine"


def default_provenance_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "supplement"
        / "validation_pair_provenance.csv"
    )


def default_v2_title_source_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "observed_claim_human_validation_20260714"
        / "annotated_20260714"
        / "analysis_results"
        / "final"
        / "human_final_consensus.csv"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_title(title: str) -> str:
    """Normalize title identity without relying on citation keys."""

    decomposed = unicodedata.normalize("NFKD", title).casefold()
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    tokenized = "".join(
        character if character.isalnum() else " " for character in without_marks
    )
    return " ".join(tokenized.split())


def collapse_title_variants(
    titles_by_key: Mapping[str, set[str]], source_name: str
) -> dict[str, str]:
    collapsed: dict[str, str] = {}
    for source_key, titles in titles_by_key.items():
        normalized = {normalize_title(title) for title in titles}
        if "" in normalized:
            raise ValueError(f"{source_name} has an empty title for {source_key}")
        if len(normalized) != 1:
            raise ValueError(
                f"{source_name} maps {source_key} to conflicting titles: "
                f"{sorted(titles)}"
            )
        collapsed[source_key] = sorted(titles)[0]
    return collapsed


def read_pair_sources(path: Path) -> tuple[dict[str, str], int]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {column for pair in PAIR_COLUMNS for column in pair}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"{path} must contain columns {', '.join(sorted(required))}"
            )
        rows = list(reader)
    titles_by_key: dict[str, set[str]] = defaultdict(set)
    for row_number, row in enumerate(rows, start=2):
        for id_column, title_column in PAIR_COLUMNS:
            source_key = (row.get(id_column) or "").strip()
            source_title = (row.get(title_column) or "").strip()
            if not source_key or not source_title:
                raise ValueError(
                    f"{path}:{row_number} has an empty {id_column}/{title_column}"
                )
            if any(character in source_key for character in "\r\n"):
                raise ValueError(f"{path}:{row_number} has a multiline {id_column}")
            titles_by_key[source_key].add(source_title)
    return collapse_title_variants(titles_by_key, str(path)), len(rows)


def read_pair_source_keys(path: Path) -> tuple[set[str], int]:
    sources, rows = read_pair_sources(path)
    return set(sources), rows


def read_v2_sources(path: Path) -> tuple[dict[str, str], int]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"source_key", "source_title"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain source_key and source_title")
        rows = list(reader)
    titles_by_key: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        source_key = (row.get("source_key") or "").strip()
        if source_key not in FIXED_V2_KEYS:
            continue
        source_title = (row.get("source_title") or "").strip()
        if not source_title:
            raise ValueError(f"{path} has an empty source_title for {source_key}")
        titles_by_key[source_key].add(source_title)
    missing = sorted(FIXED_V2_KEYS - set(titles_by_key))
    if missing:
        raise ValueError(f"{path} lacks fixed v2 source titles: {missing}")
    return collapse_title_variants(titles_by_key, str(path)), len(rows)


def build_key_set(path: Path) -> tuple[set[str], dict[str, object]]:
    pair_keys, pair_rows = read_pair_source_keys(path)
    combined = pair_keys.union(FIXED_V2_KEYS)
    metadata: dict[str, object] = {
        "provenance_path": str(path),
        "provenance_sha256": sha256_file(path),
        "pair_rows": pair_rows,
        "unique_v1_pair_source_keys": len(pair_keys),
        "fixed_v2_source_keys": len(FIXED_V2_KEYS),
        "overlap_between_inputs": len(pair_keys.intersection(FIXED_V2_KEYS)),
        "combined_development_source_keys": len(combined),
    }
    return combined, metadata


def build_source_rows(
    provenance_path: Path, v2_title_source_path: Path
) -> tuple[list[dict[str, str]], dict[str, object]]:
    v1_sources, pair_rows = read_pair_sources(provenance_path)
    v2_sources, v2_rows = read_v2_sources(v2_title_source_path)
    rows: list[dict[str, str]] = []
    for source_key in sorted(set(v1_sources).union(v2_sources)):
        titles = {
            title
            for title in (v1_sources.get(source_key), v2_sources.get(source_key))
            if title is not None
        }
        normalized_titles = {normalize_title(title) for title in titles}
        if len(normalized_titles) != 1:
            raise ValueError(
                f"v1/v2 title conflict for {source_key}: {sorted(titles)}"
            )
        source_title = (
            v2_sources[source_key]
            if source_key in v2_sources
            else v1_sources[source_key]
        )
        scopes = []
        if source_key in v1_sources:
            scopes.append(V1_SCOPE)
        if source_key in v2_sources:
            scopes.append(V2_SCOPE)
        rows.append(
            {
                "source_key": source_key,
                "normalized_title": normalize_title(source_title),
                "source_title": source_title,
                "provenance_scope": "|".join(scopes),
            }
        )
    title_to_keys: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        title_to_keys[row["normalized_title"]].add(row["source_key"])
    metadata: dict[str, object] = {
        "pair_rows": pair_rows,
        "v2_title_source_rows": v2_rows,
        "v2_title_source_path": str(v2_title_source_path),
        "v2_title_source_sha256": sha256_file(v2_title_source_path),
        "development_source_rows": len(rows),
        "unique_development_titles": len(title_to_keys),
        "development_title_alias_groups": sum(
            len(keys) > 1 for keys in title_to_keys.values()
        ),
    }
    return rows, metadata


def serialize_keys(keys: Iterable[str]) -> str:
    return "".join(f"{key}\n" for key in sorted(set(keys)))


def serialize_sources(rows: Sequence[Mapping[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=DEVELOPMENT_SOURCES_HEADER, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(content, encoding="utf-8")
    staging.replace(path)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provenance",
        type=Path,
        default=default_provenance_path(),
        help="v1 validation-pair provenance CSV",
    )
    parser.add_argument(
        "--v2-title-source",
        type=Path,
        default=default_v2_title_source_path(),
        help="80-claim final CSV supplying the nine fixed v2 source titles",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "DEVELOPMENT_SOURCE_KEYS.txt",
    )
    parser.add_argument(
        "--sources-output",
        type=Path,
        default=root / "DEVELOPMENT_SOURCES.csv",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the output is current without writing it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    provenance_path = args.provenance.resolve()
    v2_title_source_path = args.v2_title_source.resolve()
    keys, key_metadata = build_key_set(provenance_path)
    source_rows, source_metadata = build_source_rows(
        provenance_path, v2_title_source_path
    )
    expected_keys = serialize_keys(keys)
    expected_sources = serialize_sources(source_rows)
    metadata = {**key_metadata, **source_metadata}
    if args.check:
        observed_keys = (
            args.output.read_text(encoding="utf-8")
            if args.output.exists()
            else ""
        )
        observed_sources = (
            args.sources_output.read_text(encoding="utf-8")
            if args.sources_output.exists()
            else ""
        )
        if observed_keys != expected_keys or observed_sources != expected_sources:
            print(
                json.dumps(
                    {
                        **metadata,
                        "output": str(args.output),
                        "sources_output": str(args.sources_output),
                        "status": "FAIL_OUT_OF_DATE",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        status = "PASS_CURRENT"
    else:
        write_atomic(args.output, expected_keys)
        write_atomic(args.sources_output, expected_sources)
        status = "WROTE"
    print(
        json.dumps(
            {
                **metadata,
                "output": str(args.output),
                "sources_output": str(args.sources_output),
                "status": status,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
