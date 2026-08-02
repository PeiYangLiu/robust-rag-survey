#!/usr/bin/env python3
"""Prepare the protocol-consistent, model-free held-out candidate pool."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from build_development_source_keys import normalize_title


PACKAGE = Path(__file__).resolve().parent
MANUSCRIPT = Path(__file__).resolve().parents[2]
REPOSITORY = MANUSCRIPT.parent
MAP_PATH = MANUSCRIPT / "supplement" / "evidence_map_venue_expanded_adjudicated.csv"
TEXT_ROOT = MANUSCRIPT / "citation_audit" / "expanded_texts"
DEVELOPMENT_SOURCES_PATH = PACKAGE / "DEVELOPMENT_SOURCES.csv"
SOURCE_SEED = 2026071501
MIN_TEXT_BYTES = 5_000
MIN_DETERMINISTIC_CANDIDATES = 12
MAX_CANDIDATES_PER_SELECTED_SOURCE = 20
TARGET_SELECTED_SOURCES = 80
DEFAULT_FRAME_FROZEN_UTC = "2026-07-15T08:07:45Z"
MODEL_FREE_STATUS = "MODEL_FREE_DETERMINISTIC_NOMINATION_NOT_HUMAN_LABEL"
MODEL_ONLY_STATUS = "SYNTHETIC_OR_MODEL_ONLY_PRESCREEN_NOT_HUMAN_LABEL"

SOURCE_HEADER = (
    "source_key",
    "title",
    "year",
    "venue_family",
    "publication_status",
    "stable_url_or_doi",
    "corpus_snapshot_id",
    "full_text_sha256",
    "license_or_access_note",
    "sampling_stratum",
    "eligible_candidate_count",
    "eligibility_status",
    "exclusion_reason_code",
    "exclusion_reason_detail",
    "development_source_flag",
    "deterministic_source_rank",
    "frame_frozen_utc",
)
CANDIDATE_HEADER = (
    "candidate_claim_id",
    "source_key",
    "source_title",
    "source_url_or_doi",
    "source_selection_rank",
    "source_candidate_rank",
    "source_section",
    "pdf_page",
    "exact_quote",
    "context_before",
    "context_after",
    "cue_score",
    "section_priority",
    "source_text_sha256",
    "corpus_snapshot_id",
    "candidate_record_sha256",
    "extraction_method",
    "model_free_status",
)
MODEL_PRESCREEN_HEADER = (
    "candidate_claim_id",
    "source_key",
    "claim_text",
    "context_before",
    "context_after",
    "source_section",
    "source_locator",
    "source_url_or_doi",
    "source_evidence_excerpt",
    "source_file_sha256",
    "candidate_extraction_method",
    "prescreen_system",
    "prescreen_system_version",
    "prescreen_prompt_sha256",
    "prescreen_seed",
    "prescreen_c2_decisive_probability",
    "prescreen_c5_decisive_probability",
    "prescreen_rationale",
    "model_only_status",
    "human_sampling_reviewer_1_id",
    "human_sampling_reviewer_2_id",
    "human_sampling_tiebreak_reviewer_id",
    "human_sampling_eligibility",
    "human_sampling_stratum",
    "selection_status",
    "exclusion_reason_code",
    "exclusion_reason_detail",
    "deterministic_claim_rank",
)

STRONG_CUES = re.compile(
    r"\b(?:outperform(?:s|ed|ing)?|better than|worse than|higher than|"
    r"lower than|compared (?:to|with)|superior|inferior|versus|vs\.|"
    r"relative to|in contrast to|whereas)\b",
    re.I,
)
EFFECT_CUES = re.compile(
    r"\b(?:improv(?:e|es|ed|ing|ement)|decreas(?:e|es|ed|ing)|"
    r"increas(?:e|es|ed|ing)|gain(?:s|ed)?|drop(?:s|ped)?|"
    r"reduc(?:e|es|ed|ing|tion)|best|state[- ]of[- ]the[- ]art|"
    r"significant(?:ly)?)\b",
    re.I,
)
BASELINE_CUES = re.compile(
    r"\b(?:baseline|ablation|variant|method|model|system|setting|condition)\b",
    re.I,
)
NUMBER = re.compile(r"(?<!\w)(?:\d+(?:\.\d+)?%?|0\.\d+)(?!\w)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
RESULT_SECTIONS = re.compile(
    r"\b(?:result|experiment|evaluation|analysis|ablation|discussion|"
    r"case stud|finding|conclusion)\b",
    re.I,
)
LOW_PRIORITY_SECTIONS = re.compile(
    r"\b(?:introduction|related work|background|preliminar)\b",
    re.I,
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        return list(reader)


def serialize_csv(
    header: Sequence[str], rows: Sequence[Mapping[str, object]]
) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".new")
    staging.write_text(content, encoding="utf-8")
    staging.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def stable_digest(seed: int, namespace: str, value: str) -> str:
    return hashlib.sha256(f"{seed}|{namespace}|{value}".encode("utf-8")).hexdigest()


def cue_score(sentence: str) -> int:
    score = 3 * len(STRONG_CUES.findall(sentence))
    score += len(EFFECT_CUES.findall(sentence))
    if BASELINE_CUES.search(sentence):
        score += 1
    if len(NUMBER.findall(sentence)) >= 2:
        score += 1
    return score


def section_priority(section: str) -> int:
    if RESULT_SECTIONS.search(section):
        return 2
    if LOW_PRIORITY_SECTIONS.search(section):
        return -1
    if "abstract" in section.lower():
        return 1
    return 0


def is_heading(line: str) -> bool:
    stripped = re.sub(r"\s+", " ", line.strip())
    if not stripped or len(stripped) > 110 or stripped.endswith((".", ";", ",")):
        return False
    if stripped.lower() in {"references", "bibliography", "appendix"}:
        return True
    if re.match(r"^\d+(?:\.\d+)*\.?\s+\S", stripped):
        return True
    words = stripped.split()
    if len(words) > 10:
        return False
    if stripped.isupper() and any(character.isalpha() for character in stripped):
        return True
    return bool(
        re.match(
            r"^(?:abstract|introduction|related work|background|methods?|"
            r"experimental setup|experiments?|results?|evaluation|analysis|"
            r"ablations?|discussion|limitations?|conclusion|appendix)"
            r"(?:\s|$)",
            stripped,
            re.I,
        )
    )


def page_paragraphs(page: str) -> list[tuple[str, str]]:
    section = "unlabeled"
    paragraphs: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        text = re.sub(r"\s+", " ", " ".join(buffer)).strip()
        if text:
            paragraphs.append((section, text))
        buffer.clear()

    for raw_line in page.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if is_heading(line):
            flush()
            section = re.sub(r"\s+", " ", line)
            if section.lower() in {"references", "bibliography"}:
                break
            continue
        buffer.append(line)
    flush()
    return paragraphs


def split_pages(text: str) -> list[tuple[int, str]]:
    marker = re.compile(r"(?m)^=+\s*PAGE\s+(\d+)\s*=+\s*$")
    matches = list(marker.finditer(text))
    if matches:
        pages: list[tuple[int, str]] = []
        prefix = text[: matches[0].start()]
        if prefix.strip():
            pages.append((1, prefix))
        for index, match in enumerate(matches):
            start = match.end()
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(text)
            )
            pages.append((int(match.group(1)), text[start:end]))
        return pages
    return list(enumerate(text.split("\f"), 1))


def extract_candidates(text: str) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    sequence = 0
    for page_number, page in split_pages(text):
        for section, paragraph in page_paragraphs(page):
            sentences = [
                value.strip()
                for value in SENTENCE_SPLIT.split(paragraph)
                if value.strip()
            ]
            for sentence_index, sentence in enumerate(sentences):
                score = cue_score(sentence)
                if not 50 <= len(sentence) <= 800 or score < 2:
                    continue
                normalized = re.sub(r"\W+", " ", sentence.lower()).strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                sequence += 1
                candidates.append(
                    {
                        "sequence": sequence,
                        "pdf_page": page_number,
                        "source_section": section,
                        "section_priority": section_priority(section),
                        "cue_score": score,
                        "exact_quote": sentence,
                        "context_before": (
                            sentences[sentence_index - 1]
                            if sentence_index > 0
                            else ""
                        ),
                        "context_after": (
                            sentences[sentence_index + 1]
                            if sentence_index + 1 < len(sentences)
                            else ""
                        ),
                    }
                )
    return candidates


def load_development_exclusions() -> tuple[set[str], set[str]]:
    rows = read_csv(DEVELOPMENT_SOURCES_PATH)
    keys = {(row.get("source_key") or "").strip() for row in rows}
    titles = {(row.get("normalized_title") or "").strip() for row in rows}
    if "" in keys or "" in titles:
        raise ValueError("development source registry contains an empty key/title")
    for row in rows:
        if normalize_title((row.get("source_title") or "").strip()) != (
            row.get("normalized_title") or ""
        ).strip():
            raise ValueError("development source title normalization mismatch")
    return keys, titles


def publication_status(map_row: Mapping[str, str]) -> str:
    source_stratum = (map_row.get("source_stratum") or "").strip()
    venue = (map_row.get("source_or_venue") or "").strip().casefold()
    if source_stratum == "arxiv_or_preprint" or venue == "arxiv":
        return "preprint"
    return "venue-linked"


def expanded_text_snapshot(
    map_sha256: str, text_hashes: Mapping[str, str]
) -> tuple[str, str]:
    digest = hashlib.sha256()
    digest.update(f"map_sha256={map_sha256}\n".encode("utf-8"))
    for source_key in sorted(text_hashes):
        digest.update(
            f"{source_key}.txt={text_hashes[source_key]}\n".encode("utf-8")
        )
    snapshot_sha256 = digest.hexdigest()
    return f"mapb342-expandedtexts-{snapshot_sha256[:16]}", snapshot_sha256


def read_replacement_exclusions(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    rows = read_csv(path)
    exclusions: dict[str, str] = {}
    for index, row in enumerate(rows, start=2):
        source_key = (row.get("source_key") or "").strip()
        reason = (row.get("exclusion_reason_detail") or "").strip()
        if not source_key or not reason:
            raise ValueError(
                f"{path}:{index} requires source_key and exclusion_reason_detail"
            )
        if source_key in exclusions:
            raise ValueError(f"duplicate replacement exclusion: {source_key}")
        exclusions[source_key] = reason
    return exclusions


def rank_and_select_sources(
    frame: list[dict[str, object]], target: int, seed: int
) -> tuple[list[str], dict[str, int]]:
    eligible_by_stratum: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in frame:
        if row["eligibility_status"] == "eligible_unranked":
            eligible_by_stratum[str(row["sampling_stratum"])].append(row)
    ranked_by_stratum: dict[str, list[dict[str, object]]] = {}
    for stratum, rows in eligible_by_stratum.items():
        ranked = sorted(
            rows,
            key=lambda row: stable_digest(seed, "source", str(row["source_key"])),
        )
        ranked_by_stratum[stratum] = ranked
        for rank, row in enumerate(ranked, start=1):
            row["deterministic_source_rank"] = rank

    round_robin: list[str] = []
    pass_index = 0
    ordered_strata = sorted(ranked_by_stratum)
    while len(round_robin) < target:
        added = False
        for stratum in ordered_strata:
            ranked = ranked_by_stratum[stratum]
            if pass_index < len(ranked):
                round_robin.append(str(ranked[pass_index]["source_key"]))
                added = True
                if len(round_robin) == target:
                    break
        if not added:
            break
        pass_index += 1
    if len(round_robin) != target:
        raise ValueError(
            f"only {len(round_robin)} protocol-eligible sources; need {target}"
        )
    selected = set(round_robin)
    selection_rank = {
        source_key: rank for rank, source_key in enumerate(round_robin, start=1)
    }
    for row in frame:
        if row["eligibility_status"] != "eligible_unranked":
            continue
        row["eligibility_status"] = (
            "eligible_selected"
            if str(row["source_key"]) in selected
            else "eligible_reserve"
        )
    return round_robin, selection_rank


def canonical_candidate_hash(row: Mapping[str, object]) -> str:
    fields = (
        "candidate_claim_id",
        "source_key",
        "source_title",
        "source_url_or_doi",
        "source_selection_rank",
        "source_candidate_rank",
        "source_section",
        "pdf_page",
        "exact_quote",
        "context_before",
        "context_after",
        "cue_score",
        "section_priority",
        "source_text_sha256",
        "corpus_snapshot_id",
        "extraction_method",
        "model_free_status",
    )
    payload = {field: str(row.get(field, "")) for field in fields}
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def prepare_outputs(
    frame_frozen_utc: str,
    replacement_exclusions: Mapping[str, str],
) -> tuple[str, str, str, dict[str, object]]:
    map_rows = read_csv(MAP_PATH)
    if len(map_rows) != 342:
        raise ValueError(f"expected frozen 342-row Map B, found {len(map_rows)}")
    map_keys = [(row.get("cite_key") or "").strip() for row in map_rows]
    if len(map_keys) != len(set(map_keys)):
        raise ValueError("Map B contains duplicate source keys")
    development_keys, development_titles = load_development_exclusions()
    map_sha256 = sha256_file(MAP_PATH)

    text_hashes: dict[str, str] = {}
    for source_key in map_keys:
        text_path = TEXT_ROOT / f"{source_key}.txt"
        if text_path.is_file():
            text_hashes[source_key] = sha256_file(text_path)
    corpus_snapshot_id, text_snapshot_sha256 = expanded_text_snapshot(
        map_sha256, text_hashes
    )

    frame: list[dict[str, object]] = []
    candidate_cache: dict[str, list[dict[str, object]]] = {}
    map_by_key = {row["cite_key"].strip(): row for row in map_rows}
    for map_row in map_rows:
        source_key = (map_row.get("cite_key") or "").strip()
        title = (map_row.get("title") or "").strip()
        normalized = normalize_title(title)
        venue_family = (map_row.get("source_or_venue") or "").strip()
        status = publication_status(map_row)
        sampling_stratum = f"{venue_family}::{status}" if venue_family else ""
        text_path = TEXT_ROOT / f"{source_key}.txt"
        development_match = (
            source_key in development_keys or normalized in development_titles
        )
        exclusion_code = ""
        exclusion_detail = ""
        candidate_count = 0

        if not source_key or not title:
            exclusion_code = "OTHER_PREDECLARED_ELIGIBILITY_FAILURE"
            exclusion_detail = "missing_key_or_title"
        elif development_match:
            exclusion_code = "DEV_SOURCE_OR_COMPANION"
            exclusion_detail = (
                "claim_level_development_key"
                if source_key in development_keys
                else "claim_level_development_title_alias"
            )
        elif not venue_family:
            exclusion_code = "OTHER_PREDECLARED_ELIGIBILITY_FAILURE"
            exclusion_detail = "missing_venue_family"
        elif (map_row.get("map_b_adjudicated_include") or "").strip().lower() != "true":
            exclusion_code = "OUTSIDE_FROZEN_CORPUS"
            exclusion_detail = "not_in_adjudicated_map"
        elif not text_path.is_file():
            exclusion_code = "NO_STABLE_FULL_TEXT"
            exclusion_detail = "local_expanded_text_unavailable"
        elif text_path.stat().st_size < MIN_TEXT_BYTES:
            exclusion_code = "NO_STABLE_FULL_TEXT"
            exclusion_detail = "local_expanded_text_too_short"
        else:
            extracted = extract_candidates(
                text_path.read_text(encoding="utf-8", errors="replace")
            )
            candidate_cache[source_key] = extracted
            candidate_count = len(extracted)
            if candidate_count < MIN_DETERMINISTIC_CANDIDATES:
                exclusion_code = "OTHER_PREDECLARED_ELIGIBILITY_FAILURE"
                exclusion_detail = (
                    "fewer_than_12_deterministic_comparison_candidates"
                )
        if source_key in replacement_exclusions and not exclusion_code:
            exclusion_code = "OTHER_PREDECLARED_ELIGIBILITY_FAILURE"
            exclusion_detail = (
                "human_screen_fewer_than_six_decisive:"
                + replacement_exclusions[source_key]
            )
        eligibility_status = "excluded" if exclusion_code else "eligible_unranked"
        frame.append(
            {
                "source_key": source_key,
                "title": title,
                "year": (map_row.get("year") or "").strip(),
                "venue_family": venue_family,
                "publication_status": status,
                "stable_url_or_doi": (map_row.get("url") or "").strip(),
                "corpus_snapshot_id": corpus_snapshot_id,
                "full_text_sha256": text_hashes.get(source_key, ""),
                "license_or_access_note": (
                    "not_assessed; local expanded-text snapshot used for nomination"
                    if source_key in text_hashes
                    else "not_assessed; local expanded text unavailable"
                ),
                "sampling_stratum": sampling_stratum,
                "eligible_candidate_count": candidate_count,
                "eligibility_status": eligibility_status,
                "exclusion_reason_code": exclusion_code,
                "exclusion_reason_detail": exclusion_detail,
                "development_source_flag": str(development_match).lower(),
                "deterministic_source_rank": "",
                "frame_frozen_utc": frame_frozen_utc,
            }
        )

    selected_keys, selection_rank = rank_and_select_sources(
        frame, TARGET_SELECTED_SOURCES, SOURCE_SEED
    )
    eligible_rows = [
        row
        for row in frame
        if row["eligibility_status"] in {"eligible_selected", "eligible_reserve"}
    ]
    title_keys: dict[str, set[str]] = defaultdict(set)
    for row in eligible_rows:
        title_keys[normalize_title(str(row["title"]))].add(str(row["source_key"]))
    duplicates = {title: keys for title, keys in title_keys.items() if len(keys) > 1}
    if duplicates:
        raise ValueError(f"eligible sources contain duplicate titles: {duplicates}")

    candidates: list[dict[str, object]] = []
    for source_key in selected_keys:
        map_row = map_by_key[source_key]
        frame_row = next(row for row in frame if row["source_key"] == source_key)
        extracted = list(candidate_cache[source_key])
        extracted.sort(
            key=lambda row: (
                -int(row["section_priority"]),
                -int(row["cue_score"]),
                int(row["pdf_page"]),
                int(row["sequence"]),
            )
        )
        for source_candidate_rank, candidate in enumerate(
            extracted[:MAX_CANDIDATES_PER_SELECTED_SOURCE], start=1
        ):
            row: dict[str, object] = {
                "candidate_claim_id": (
                    f"H3-{selection_rank[source_key]:03d}-"
                    f"{source_candidate_rank:02d}"
                ),
                "source_key": source_key,
                "source_title": frame_row["title"],
                "source_url_or_doi": (map_row.get("url") or "").strip(),
                "source_selection_rank": selection_rank[source_key],
                "source_candidate_rank": source_candidate_rank,
                "source_section": candidate["source_section"],
                "pdf_page": candidate["pdf_page"],
                "exact_quote": candidate["exact_quote"],
                "context_before": candidate["context_before"],
                "context_after": candidate["context_after"],
                "cue_score": candidate["cue_score"],
                "section_priority": candidate["section_priority"],
                "source_text_sha256": frame_row["full_text_sha256"],
                "corpus_snapshot_id": corpus_snapshot_id,
                "candidate_record_sha256": "",
                "extraction_method": (
                    "deterministic_comparative_cue_v1_model_free"
                ),
                "model_free_status": MODEL_FREE_STATUS,
            }
            row["candidate_record_sha256"] = canonical_candidate_hash(row)
            candidates.append(row)

    frame_text = serialize_csv(SOURCE_HEADER, frame)
    candidate_text = serialize_csv(CANDIDATE_HEADER, candidates)
    selected_rows = [
        next(row for row in frame if row["source_key"] == source_key)
        for source_key in selected_keys
    ]
    candidate_counts = Counter(
        str(row["source_key"]) for row in candidates
    )
    summary: dict[str, object] = {
        "status": "MODEL_FREE_POOL_AWAITING_HUMAN_SAMPLING_SCREEN",
        "protocol_source_selection": "sha256_rank_within_stratum_then_lexical_round_robin",
        "custom_source_quotas_used": False,
        "sampling_source_seed": SOURCE_SEED,
        "map_rows": len(map_rows),
        "map_sha256": map_sha256,
        "expanded_text_files": len(text_hashes),
        "expanded_text_snapshot_sha256": text_snapshot_sha256,
        "corpus_snapshot_id": corpus_snapshot_id,
        "source_frame_rows": len(frame),
        "eligible_sources": len(eligible_rows),
        "selected_sources": len(selected_rows),
        "reserve_sources": sum(
            row["eligibility_status"] == "eligible_reserve" for row in frame
        ),
        "excluded_sources": sum(
            row["eligibility_status"] == "excluded" for row in frame
        ),
        "selected_publication_status": dict(
            sorted(
                Counter(
                    str(row["publication_status"]) for row in selected_rows
                ).items()
            )
        ),
        "selected_map_source_stratum": dict(
            sorted(
                Counter(
                    (map_by_key[str(row["source_key"])].get("source_stratum") or "")
                    .strip()
                    for row in selected_rows
                ).items()
            )
        ),
        "selected_failure_or_risk_type": dict(
            sorted(
                Counter(
                    (
                        map_by_key[str(row["source_key"])].get(
                            "failure_or_risk_type"
                        )
                        or ""
                    ).strip()
                    for row in selected_rows
                ).items()
            )
        ),
        "selected_venue_families": dict(
            sorted(
                Counter(str(row["venue_family"]) for row in selected_rows).items()
            )
        ),
        "deterministic_candidates": len(candidates),
        "candidates_per_selected_source_min": min(candidate_counts.values()),
        "candidates_per_selected_source_max": max(candidate_counts.values()),
        "max_candidates_per_selected_source": MAX_CANDIDATES_PER_SELECTED_SOURCE,
        "replacement_exclusions_applied": dict(sorted(replacement_exclusions.items())),
        "model_prescreen_status": "NOT_RUN_BY_THIS_COMMAND",
        "source_sampling_frame_sha256": sha256_text(frame_text),
        "candidate_claims_deterministic_sha256": sha256_text(candidate_text),
        "prohibited_use": (
            "deterministic and model nominations are not human or gold labels"
        ),
    }
    summary_text = json.dumps(
        summary, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    return frame_text, candidate_text, summary_text, summary


def resolve_input_column(
    fieldnames: Sequence[str],
    requested: str | None,
    alternatives: Sequence[str],
    description: str,
) -> str:
    if requested:
        if requested not in fieldnames:
            raise ValueError(f"missing requested {description} column: {requested}")
        return requested
    for alternative in alternatives:
        if alternative in fieldnames:
            return alternative
    raise ValueError(
        f"cannot infer {description} column; tried {', '.join(alternatives)}"
    )


def parse_score(value: str, field: str, candidate_id: str) -> str:
    try:
        score = float(value)
    except ValueError as exc:
        raise ValueError(
            f"{candidate_id} has a nonnumeric {field}: {value!r}"
        ) from exc
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{candidate_id} has {field} outside [0,1]: {score}")
    return format(score, ".12g")


def import_model_prescreen(args: argparse.Namespace) -> dict[str, object]:
    deterministic_rows = read_csv(args.candidate_output)
    deterministic_by_id = {
        row["candidate_claim_id"].strip(): row for row in deterministic_rows
    }
    if len(deterministic_by_id) != len(deterministic_rows):
        raise ValueError("deterministic candidate IDs are not unique")
    with args.import_model_prescreen.open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        reader = csv.DictReader(handle)
        input_fields = tuple(reader.fieldnames or ())
        input_rows = list(reader)
    id_column = resolve_input_column(
        input_fields,
        args.id_column,
        ("candidate_claim_id", "candidate_id"),
        "candidate ID",
    )
    c2_column = resolve_input_column(
        input_fields,
        args.c2_score_column,
        (
            "c2_score",
            "prescreen_c2_decisive_score",
            "prescreen_c2_decisive_probability",
        ),
        "C2 ranking score",
    )
    c5_column = resolve_input_column(
        input_fields,
        args.c5_score_column,
        (
            "c5_score",
            "prescreen_c5_decisive_score",
            "prescreen_c5_decisive_probability",
        ),
        "C5 ranking score",
    )
    rationale_column = resolve_input_column(
        input_fields,
        args.rationale_column,
        ("rationale", "prescreen_rationale", "reason"),
        "rationale",
    )
    if not args.prescreen_system or not args.prescreen_system_version:
        raise ValueError(
            "--prescreen-system and --prescreen-system-version are required"
        )
    if not SHA256_RE.fullmatch(args.prescreen_prompt_sha256 or ""):
        raise ValueError("--prescreen-prompt-sha256 must be 64 lowercase hex digits")
    if args.prescreen_seed is None:
        raise ValueError("--prescreen-seed is required")

    input_by_id: dict[str, dict[str, str]] = {}
    for row in input_rows:
        candidate_id = (row.get(id_column) or "").strip()
        if not candidate_id or candidate_id in input_by_id:
            raise ValueError(f"empty or duplicate model candidate ID: {candidate_id}")
        input_by_id[candidate_id] = row
    if set(input_by_id) != set(deterministic_by_id):
        missing = sorted(set(deterministic_by_id) - set(input_by_id))
        extra = sorted(set(input_by_id) - set(deterministic_by_id))
        raise ValueError(
            f"model input must exactly cover deterministic candidates; "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )

    output_rows: list[dict[str, str]] = []
    for candidate_id in sorted(
        deterministic_by_id,
        key=lambda value: (
            int(deterministic_by_id[value]["source_selection_rank"]),
            int(deterministic_by_id[value]["source_candidate_rank"]),
        ),
    ):
        deterministic = deterministic_by_id[candidate_id]
        model = input_by_id[candidate_id]
        output_rows.append(
            {
                "candidate_claim_id": candidate_id,
                "source_key": deterministic["source_key"],
                "claim_text": deterministic["exact_quote"],
                "context_before": deterministic["context_before"],
                "context_after": deterministic["context_after"],
                "source_section": deterministic["source_section"],
                "source_locator": f"PDF page {deterministic['pdf_page']}",
                "source_url_or_doi": deterministic["source_url_or_doi"],
                "source_evidence_excerpt": deterministic["exact_quote"],
                "source_file_sha256": deterministic["source_text_sha256"],
                "candidate_extraction_method": deterministic["extraction_method"],
                "prescreen_system": args.prescreen_system,
                "prescreen_system_version": args.prescreen_system_version,
                "prescreen_prompt_sha256": args.prescreen_prompt_sha256,
                "prescreen_seed": str(args.prescreen_seed),
                "prescreen_c2_decisive_probability": parse_score(
                    (model.get(c2_column) or "").strip(),
                    c2_column,
                    candidate_id,
                ),
                "prescreen_c5_decisive_probability": parse_score(
                    (model.get(c5_column) or "").strip(),
                    c5_column,
                    candidate_id,
                ),
                "prescreen_rationale": (model.get(rationale_column) or "").strip(),
                "model_only_status": MODEL_ONLY_STATUS,
                "human_sampling_reviewer_1_id": "",
                "human_sampling_reviewer_2_id": "",
                "human_sampling_tiebreak_reviewer_id": "",
                "human_sampling_eligibility": "",
                "human_sampling_stratum": "",
                "selection_status": "awaiting_human_sampling_screen",
                "exclusion_reason_code": "",
                "exclusion_reason_detail": "",
                "deterministic_claim_rank": "",
            }
        )
    output_text = serialize_csv(MODEL_PRESCREEN_HEADER, output_rows)
    write_atomic(args.model_output, output_text)
    return {
        "status": "IMPORTED_MODEL_ONLY_NOMINATION_SCORES",
        "rows": len(output_rows),
        "output": str(args.model_output),
        "output_sha256": sha256_text(output_text),
        "score_semantics": (
            "self-reported ranking scores in [0,1], not calibrated probabilities"
        ),
        "human_sampling_fields_populated": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=MAP_PATH)
    parser.add_argument("--text-root", type=Path, default=TEXT_ROOT)
    parser.add_argument(
        "--frame-output", type=Path, default=PACKAGE / "source_sampling_frame.csv"
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=PACKAGE / "candidate_claims_deterministic.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PACKAGE / "candidate_pool_summary.json",
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=PACKAGE / "candidate_claims_model_prescreen.csv",
    )
    parser.add_argument(
        "--frame-frozen-utc", default=DEFAULT_FRAME_FROZEN_UTC
    )
    parser.add_argument("--replacement-exclusions", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--import-model-prescreen", type=Path)
    parser.add_argument("--id-column")
    parser.add_argument("--c2-score-column")
    parser.add_argument("--c5-score-column")
    parser.add_argument("--rationale-column")
    parser.add_argument("--prescreen-system")
    parser.add_argument("--prescreen-system-version")
    parser.add_argument("--prescreen-prompt-sha256")
    parser.add_argument("--prescreen-seed", type=int)
    return parser.parse_args()


def self_test() -> None:
    sample = (
        "4 Results\n"
        "Our method outperforms the baseline by 12.5% compared with 8.0% "
        "for Model B.\n\n"
        "Accuracy is higher than the no-retrieval setting, whereas latency "
        "increases."
    )
    candidates = extract_candidates(sample)
    if len(candidates) != 2:
        raise AssertionError("candidate extraction self-test failed")
    if normalize_title("A–B: Test!") != "a b test":
        raise AssertionError("title normalization self-test failed")
    print("self-test passed; no files written")


def main() -> int:
    global MAP_PATH, TEXT_ROOT
    args = parse_args()
    MAP_PATH = args.map.resolve()
    TEXT_ROOT = args.text_root.resolve()
    if args.self_test:
        self_test()
        return 0
    if args.import_model_prescreen is not None:
        summary = import_model_prescreen(args)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.replacement_exclusions is not None:
        raise ValueError(
            "--replacement-exclusions is disabled because global regeneration "
            "renumbers already-screened claims; use apply_source_replacements.py"
        )

    frame_text, candidate_text, summary_text, summary = prepare_outputs(
        args.frame_frozen_utc, {}
    )
    if args.check:
        replacement_summary_path = PACKAGE / "source_replacement_summary.json"
        if replacement_summary_path.exists():
            replacement_summary = json.loads(
                replacement_summary_path.read_text(encoding="utf-8")
            )
            batches = replacement_summary.get("batches")
            if not isinstance(batches, list) or not batches:
                raise ValueError("source replacement summary lacks a batch")
            parent = batches[0].get("parent")
            if not isinstance(parent, dict):
                raise ValueError("source replacement summary lacks parent hashes")
            baseline_checks = {
                "source_sampling_frame_sha256": sha256_text(frame_text),
                "candidate_claims_deterministic_sha256": sha256_text(
                    candidate_text
                ),
            }
            stale_parent = [
                field
                for field, expected in baseline_checks.items()
                if parent.get(field) != expected
            ]
            if stale_parent:
                print(
                    json.dumps(
                        {
                            "status": "FAIL_REPLACEMENT_PARENT_MISMATCH",
                            "mismatches": stale_parent,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 1
            replacement_records = [
                row
                for batch in batches
                if isinstance(batch, dict)
                for row in batch.get("replacements", [])
                if isinstance(row, dict)
            ]
            deficient_keys = {
                str(row.get("deficient_source_key", "")).strip()
                for row in replacement_records
            }
            active_slots = batches[-1].get("active_source_slots", [])
            active_keys = {
                str(row.get("source_key", "")).strip()
                for row in active_slots
                if isinstance(row, dict)
            }
            baseline_frame_rows = list(
                csv.DictReader(io.StringIO(frame_text))
            )
            baseline_candidate_rows = list(
                csv.DictReader(io.StringIO(candidate_text))
            )
            baseline_selected = {
                row["source_key"]
                for row in baseline_frame_rows
                if row["eligibility_status"] == "eligible_selected"
            }
            retained_keys = (
                baseline_selected & active_keys
            ) - deficient_keys
            current_frame_rows = read_csv(args.frame_output)
            current_candidate_rows = read_csv(args.candidate_output)
            correction_path = (
                args.candidate_output.parent / "frozen_text_corrections.csv"
            )
            frozen_path = args.candidate_output.parent / "frozen_test_claims.csv"
            human_path = (
                args.candidate_output.parent
                / "candidate_claims_model_prescreen.csv"
            )
            if (
                correction_path.exists()
                and frozen_path.exists()
                and human_path.exists()
            ):
                from frozen_text_corrections import (
                    validate_and_reverse_corrections,
                )

                correction_rows = read_csv(correction_path)
                frozen_rows = read_csv(frozen_path)
                if correction_rows and frozen_rows:
                    correction_state = validate_and_reverse_corrections(
                        correction_rows,
                        current_candidate_rows,
                        read_csv(human_path),
                        frozen_rows,
                    )
                    current_candidate_rows = (
                        correction_state.deterministic_rows
                    )
            retained_comparisons = {
                "retained_source_frame_rows": (
                    [
                        row
                        for row in baseline_frame_rows
                        if row["source_key"] in retained_keys
                    ],
                    [
                        row
                        for row in current_frame_rows
                        if row["source_key"] in retained_keys
                    ],
                ),
                "retained_deterministic_candidate_rows": (
                    [
                        row
                        for row in baseline_candidate_rows
                        if row["source_key"] in retained_keys
                    ],
                    [
                        row
                        for row in current_candidate_rows
                        if row["source_key"] in retained_keys
                    ],
                ),
            }
            changed_retained = [
                name
                for name, (before, after) in retained_comparisons.items()
                if before != after
            ]
            if changed_retained:
                print(
                    json.dumps(
                        {
                            "status": "FAIL_RETAINED_ROWS_CHANGED",
                            "mismatches": changed_retained,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 1
            if (
                not args.summary_output.exists()
                or args.summary_output.read_text(encoding="utf-8")
                != summary_text
            ):
                print(
                    json.dumps(
                        {
                            "status": "FAIL_REPLACEMENT_PARENT_MISMATCH",
                            "mismatches": [str(args.summary_output)],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 1
            from apply_source_replacements import command_apply

            check_result = command_apply(
                argparse.Namespace(
                    source_frame=args.frame_output,
                    deterministic_candidates=args.candidate_output,
                    human_screened_candidates=(
                        PACKAGE / "candidate_claims_model_prescreen.csv"
                    ),
                    ledger=(
                        PACKAGE / "sampling_exclusion_replacement_ledger.csv"
                    ),
                    screen_summary=PACKAGE / "sampling_screen_summary.json",
                    replacement_summary=replacement_summary_path,
                    text_root=TEXT_ROOT,
                    expected_sources=80,
                    check=True,
                    recorded_utc=None,
                )
            )
            print(json.dumps(check_result, indent=2, sort_keys=True))
            return 0
        expected = {
            args.frame_output: frame_text,
            args.candidate_output: candidate_text,
            args.summary_output: summary_text,
        }
        mismatches = [
            str(path)
            for path, content in expected.items()
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if mismatches:
            print(
                json.dumps(
                    {"status": "FAIL_OUT_OF_DATE", "mismatches": mismatches},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
    else:
        write_atomic(args.frame_output, frame_text)
        write_atomic(args.candidate_output, candidate_text)
        write_atomic(args.summary_output, summary_text)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
