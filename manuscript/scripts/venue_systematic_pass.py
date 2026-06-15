#!/usr/bin/env python3
"""Create a lightweight venue-oriented metadata search artifact.

The goal is not to replace manual proceedings review. It records transparent
queries, hit counts, and venue-linked candidate counts so the manuscript can
distinguish a reproducible metadata pass from a venue-complete systematic
review.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUPP = ROOT / "supplement"

YEARS = "2020-2026"
VENUE_PATTERNS = {
    "ACL": [r"\bACL\b", r"Association for Computational Linguistics"],
    "EMNLP": [r"\bEMNLP\b", r"Empirical Methods in Natural Language Processing"],
    "NAACL": [r"\bNAACL\b", r"North American Chapter"],
    "COLING": [r"\bCOLING\b", r"Computational Linguistics"],
    "SIGIR": [r"\bSIGIR\b", r"Information Retrieval"],
    "WWW": [r"\bWWW\b", r"Web Conference"],
    "WSDM": [r"\bWSDM\b", r"Web Search and Data Mining"],
    "KDD": [r"\bKDD\b", r"Knowledge Discovery"],
    "USENIX Security": [r"USENIX Security"],
    "CCS": [r"\bCCS\b", r"Computer and Communications Security"],
    "NDSS": [r"\bNDSS\b", r"Network and Distributed System Security"],
    "ICLR": [r"\bICLR\b", r"Learning Representations"],
    "NeurIPS": [r"\bNeurIPS\b", r"Neural Information Processing Systems"],
}

ACL_VENUES = ["ACL", "EMNLP", "NAACL", "COLING"]

QUERIES = [
    "retrieval augmented generation",
    "retrieval-augmented generation",
    "retrieval augmented language model",
    "retrieval augmented question answering",
    "retrieval augmentation noisy context",
    "irrelevant context retrieval augmented",
    "retrieval augmented knowledge conflict",
    "retrieval augmented uncertainty",
    "retrieval augmented calibration",
    "retrieval augmented abstention",
    "retrieval augmented poisoning",
    "retrieval augmented prompt injection",
    "retrieval corpus poisoning",
    "adversarial retrieval question answering",
    "faithfulness retrieval augmented generation",
]

ROBUST_TERMS = [
    "robust",
    "noise",
    "noisy",
    "irrelevant",
    "distract",
    "conflict",
    "poison",
    "attack",
    "injection",
    "uncertain",
    "calibr",
    "abstain",
    "unanswer",
    "faithful",
    "hallucination",
    "evaluation",
    "benchmark",
]


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def robust_relevant(title: str) -> bool:
    low = title.lower()
    if "retrieval" not in low and "rag" not in low:
        return False
    return any(term in low for term in ROBUST_TERMS)


def rag_candidate(title: str, abstract: str = "") -> bool:
    low = f"{title} {abstract}".lower()
    if "retrieval augmented" in low or "retrieval-augmented" in low:
        return True
    if re.search(r"\brag\b", low) and ("retrieval" in low or "generation" in low):
        return True
    return False


def robust_rag_candidate(title: str, abstract: str = "") -> bool:
    low = f"{title} {abstract}".lower()
    return rag_candidate(title, abstract) and any(term in low for term in ROBUST_TERMS)


def venue_matches(text: str) -> list[str]:
    matches: list[str] = []
    for venue, patterns in VENUE_PATTERNS.items():
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            matches.append(venue)
    return matches


def request_json(url: str, sleep_s: float = 0.7) -> dict[str, Any]:
    time.sleep(sleep_s)
    req = urllib.request.Request(url, headers={"User-Agent": "robust-rag-survey-metadata-pass/0.1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def dblp_query(query: str, h: int = 200) -> tuple[int, list[dict[str, Any]], str]:
    url = "https://dblp.org/search/publ/api?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "h": str(h)}
    )
    data = request_json(url, sleep_s=1.2)
    hits = data.get("result", {}).get("hits", {})
    total = int(hits.get("@total", 0) or 0)
    raw = hits.get("hit", [])
    if isinstance(raw, dict):
        raw = [raw]
    rows = []
    for hit in raw:
        info = hit.get("info", {})
        title = norm_text(info.get("title", ""))
        venue = norm_text(info.get("venue", ""))
        year = str(info.get("year", ""))
        url_out = info.get("ee") or info.get("url") or ""
        text = " ".join([title, venue, year])
        matched = venue_matches(text)
        if matched and robust_rag_candidate(title):
            rows.append(
                {
                    "source_api": "DBLP",
                    "query": query,
                    "title": title,
                    "year": year,
                    "venue_text": venue,
                    "matched_venues": ";".join(matched),
                    "url": url_out,
                }
            )
    return total, rows, url


def openalex_query(query: str, per_page: int = 200) -> tuple[int, list[dict[str, Any]], str]:
    filt = "from_publication_date:2020-01-01,to_publication_date:2026-12-31"
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": query, "filter": filt, "per-page": str(per_page)}
    )
    data = request_json(url, sleep_s=0.7)
    total = int(data.get("meta", {}).get("count", 0) or 0)
    rows = []
    for work in data.get("results", []):
        title = norm_text(work.get("display_name", ""))
        year = str(work.get("publication_year", ""))
        source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        abstract_index = work.get("abstract_inverted_index") or {}
        abstract = " ".join(sorted(abstract_index, key=lambda token: min(abstract_index[token] or [10**9])))
        text = " ".join([title, source, year])
        matched = venue_matches(text)
        if matched and robust_rag_candidate(title, abstract):
            rows.append(
                {
                    "source_api": "OpenAlex",
                    "query": query,
                    "title": title,
                    "year": year,
                    "venue_text": norm_text(source),
                    "matched_venues": ";".join(matched),
                    "url": work.get("id", ""),
                }
            )
    return total, rows, url


def split_bib_entries(text: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"(?m)^@\w+\{", text)]
    entries = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        entries.append(text[start:end])
    return entries


def field(entry: str, name: str) -> str:
    match = re.search(rf"(?is)\b{name}\s*=\s*\{{(.*?)\}}\s*,\s*(?:\n\s*\w+\s*=|\n\}})", entry)
    if not match:
        match = re.search(rf"(?is)\b{name}\s*=\s*\"(.*?)\"\s*,\s*(?:\n\s*\w+\s*=|\n\}})", entry)
    return norm_text(match.group(1).replace("\n", " ")) if match else ""


def acl_anthology_pass() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = "https://aclanthology.org/anthology+abstracts.bib.gz"
    req = urllib.request.Request(url, headers={"User-Agent": "robust-rag-survey-metadata-pass/0.1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read()
    text = gzip.decompress(raw).decode("utf-8", errors="replace")
    entries = split_bib_entries(text)
    venue_counts = Counter()
    rag_counts = Counter()
    robust_counts = Counter()
    rows = []

    for entry in entries:
        year_s = field(entry, "year")
        try:
            year = int(year_s)
        except ValueError:
            continue
        if year < 2020 or year > 2026:
            continue
        title = field(entry, "title")
        abstract = field(entry, "abstract")
        booktitle = field(entry, "booktitle")
        venue = ""
        for v in ACL_VENUES:
            if re.search(rf"\b{v}\b", booktitle, flags=re.IGNORECASE):
                venue = v
                break
        if not venue:
            continue
        venue_counts[venue] += 1
        if rag_candidate(title, abstract):
            rag_counts[venue] += 1
        if robust_rag_candidate(title, abstract):
            robust_counts[venue] += 1
            rows.append(
                {
                    "source_api": "ACL Anthology bib",
                    "query": "local scan: title/abstract contains RAG terms and robustness terms",
                    "title": title,
                    "year": str(year),
                    "venue_text": booktitle,
                    "matched_venues": venue,
                    "url": field(entry, "url"),
                }
            )

    summary = {
        "url": url,
        "entries_scanned_2020_2026_for_target_venues": dict(sorted(venue_counts.items())),
        "rag_candidates_by_venue": dict(sorted(rag_counts.items())),
        "robust_rag_candidates_by_venue": dict(sorted(robust_counts.items())),
        "robust_rag_candidate_count": len(rows),
    }
    return rows, summary


def main() -> None:
    SUPP.mkdir(parents=True, exist_ok=True)
    query_rows = []
    candidates: dict[str, dict[str, Any]] = {}
    errors = []
    acl_summary: dict[str, Any] = {}

    try:
        acl_rows, acl_summary = acl_anthology_pass()
        for row in acl_rows:
            candidates[title_key(row["title"])] = row
        query_rows.append(
            {
                "api": "ACL Anthology bib",
                "query": "local scan: title/abstract contains RAG terms and robustness terms",
                "years": YEARS,
                "reported_hit_count": sum(acl_summary.get("entries_scanned_2020_2026_for_target_venues", {}).values()),
                "retrieved_top_n": "all matching ACL Anthology bib entries",
                "venue_matched_relevant_candidates": acl_summary.get("robust_rag_candidate_count", 0),
                "query_url": acl_summary.get("url", ""),
                "error": "",
            }
        )
    except Exception as exc:
        errors.append({"api": "ACL Anthology bib", "query": "local scan", "error": repr(exc)})

    for query in QUERIES:
        for api_name, func in [("DBLP", dblp_query), ("OpenAlex", openalex_query)]:
            try:
                total, rows, url = func(query)
            except Exception as exc:  # recorded, not swallowed
                errors.append({"api": api_name, "query": query, "error": repr(exc)})
                query_rows.append(
                    {
                        "api": api_name,
                        "query": query,
                        "years": YEARS,
                        "reported_hit_count": "",
                        "retrieved_top_n": "",
                        "venue_matched_relevant_candidates": "",
                        "query_url": "",
                        "error": repr(exc),
                    }
                )
                continue

            for row in rows:
                key = title_key(row["title"])
                if key not in candidates:
                    candidates[key] = row
                else:
                    old = candidates[key]
                    old["source_api"] = ";".join(sorted(set(old["source_api"].split(";") + [row["source_api"]])))
                    old["query"] = "; ".join(sorted(set(old["query"].split("; ") + [row["query"]])))
                    old["matched_venues"] = ";".join(
                        sorted(set(old["matched_venues"].split(";") + row["matched_venues"].split(";")))
                    )
            query_rows.append(
                {
                    "api": api_name,
                    "query": query,
                    "years": YEARS,
                    "reported_hit_count": total,
                    "retrieved_top_n": 200,
                    "venue_matched_relevant_candidates": len(rows),
                    "query_url": url,
                    "error": "",
                }
            )

    candidate_rows = sorted(candidates.values(), key=lambda r: (r["year"], r["matched_venues"], r["title"]))
    venue_counter = Counter()
    api_counter = Counter()
    for row in candidate_rows:
        for venue in row["matched_venues"].split(";"):
            if venue:
                venue_counter[venue] += 1
        for api in row["source_api"].split(";"):
            if api:
                api_counter[api] += 1

    with (SUPP / "venue_systematic_queries.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "api",
                "query",
                "years",
                "reported_hit_count",
                "retrieved_top_n",
                "venue_matched_relevant_candidates",
                "query_url",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(query_rows)

    with (SUPP / "venue_systematic_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["source_api", "query", "title", "year", "venue_text", "matched_venues", "url"],
        )
        writer.writeheader()
        writer.writerows(candidate_rows)

    summary = {
        "snapshot_date": "2026-06-03",
        "description": "Reproducible metadata search over DBLP and OpenAlex for venue-linked robust-RAG candidates. This is a venue-oriented metadata pass, not a manual full-proceedings review.",
        "venues_targeted": list(VENUE_PATTERNS),
        "years": YEARS,
        "queries": QUERIES,
        "query_rows": len(query_rows),
        "unique_candidate_titles": len(candidate_rows),
        "candidate_titles_by_venue": dict(sorted(venue_counter.items())),
        "candidate_titles_by_api": dict(sorted(api_counter.items())),
        "acl_anthology_scan": acl_summary,
        "errors": errors,
        "limitations": [
            "Search is based on DBLP/OpenAlex metadata and top returned records for each query.",
            "Venue names are matched from metadata strings; some proceedings may be missing or inconsistently named.",
            "The pass is reproducible and venue-oriented but does not claim exhaustive manual review of every paper in every proceedings volume.",
        ],
    }
    with (SUPP / "venue_systematic_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
