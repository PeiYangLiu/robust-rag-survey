#!/usr/bin/env python3
"""Match current corpus to venue accepted lists and download high-value venue PDFs."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
META = ROOT / "metadata"
MAN = ROOT / "manuscript"

VENUE_ACCEPTS = META / "venue_accepts_rag_related.csv"
OUTPUT_MATCHES = META / "venue_accepts_existing_matches.csv"
OUTPUT_NEW = META / "venue_accepts_new_candidates.csv"
OUTPUT_DOWNLOADS = META / "venue_accepts_downloads.csv"
OUTPUT_SUMMARY = META / "venue_accepts_match_summary.json"

TOP_NEW_DOWNLOADS = 120
MIN_NEW_SCORE = 45


def norm_title(title: str) -> str:
    title = (title or "").lower()
    title = re.sub(r"\$.*?\$", " ", title)
    title = re.sub(r"[^a-z0-9]+", " ", title)
    title = re.sub(r"\b(a|an|the)\b", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def slug(value: str, max_len: int = 100) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.lower()).strip("_")
    return value[:max_len].strip("_") or "paper"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def current_records() -> list[dict[str, str]]:
    sources = [
        ("evidence_map", MAN / "supplement" / "evidence_map_adjudicated.csv", "cite_key"),
        ("survey_set", MAN / "supplement" / "survey_set_venue_audited.csv", "cite_key"),
        ("downloaded", META / "downloaded_papers.csv", "key"),
    ]
    out = []
    for source_name, path, key_field in sources:
        if not path.exists():
            continue
        for row in read_csv(path):
            title = row.get("title", "")
            if not title:
                continue
            out.append(
                {
                    "current_source": source_name,
                    "current_key": row.get(key_field, ""),
                    "current_title": title,
                    "current_norm": norm_title(title),
                    "current_url": row.get("url", ""),
                    "current_venue": row.get("source_or_venue") or row.get("source", ""),
                    "current_year": row.get("year", ""),
                }
            )
    return out


def best_match(venue_row: dict[str, str], by_norm: dict[str, list[dict[str, str]]], current: list[dict[str, str]]) -> tuple[dict[str, str] | None, float, str]:
    vt = norm_title(venue_row.get("title", ""))
    if vt in by_norm:
        return by_norm[vt][0], 1.0, "exact_norm_title"
    # Only fuzzy match plausible long titles.
    if len(vt) < 30:
        return None, 0.0, ""
    best = None
    best_score = 0.0
    for rec in current:
        ct = rec["current_norm"]
        if not ct:
            continue
        # cheap blocking: require one meaningful shared token for long titles
        vtoks = set(vt.split())
        ctoks = set(ct.split())
        if len(vtoks & ctoks) < 3:
            continue
        score = SequenceMatcher(None, vt, ct).ratio()
        if score > best_score:
            best = rec
            best_score = score
    if best and best_score >= 0.92:
        return best, best_score, "fuzzy_title"
    return None, best_score, ""


def request_pdf(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "robust-rag-survey-venue-download/0.1"})
    with urllib.request.urlopen(req, timeout=80) as response:
        return response.read()


def download_pdf(row: dict[str, str]) -> dict[str, str]:
    url = row.get("pdf_url", "")
    out = {**row, "download_status": "", "local_pdf": "", "bytes": ""}
    if not url:
        out["download_status"] = "no_pdf_url"
        return out
    filename = f"venue_accept_{row['venue']}_{row['year']}_{slug(row['title'])}.pdf"
    path = PDF_DIR / filename
    out["local_pdf"] = str(path.relative_to(ROOT))
    if path.exists() and path.stat().st_size > 10_000:
        out["download_status"] = "exists"
        out["bytes"] = str(path.stat().st_size)
        return out
    try:
        time.sleep(0.2)
        data = request_pdf(url)
        if b"%PDF" not in data[:2048]:
            raise ValueError("not_pdf")
        path.write_bytes(data)
        out["download_status"] = "downloaded"
        out["bytes"] = str(len(data))
    except Exception as exc:
        out["download_status"] = f"failed:{exc!r}"
    return out


def main() -> None:
    accepted = read_csv(VENUE_ACCEPTS)
    current = current_records()
    by_norm: dict[str, list[dict[str, str]]] = {}
    for rec in current:
        by_norm.setdefault(rec["current_norm"], []).append(rec)

    matches = []
    new_candidates = []
    seen_venue_titles = set()
    for row in accepted:
        vt = norm_title(row.get("title", ""))
        if not vt or vt in seen_venue_titles:
            continue
        seen_venue_titles.add(vt)
        rec, score, match_type = best_match(row, by_norm, current)
        if rec:
            matches.append(
                {
                    "match_type": match_type,
                    "match_score": f"{score:.4f}",
                    "venue": row.get("venue", ""),
                    "year": row.get("year", ""),
                    "venue_title": row.get("title", ""),
                    "venue_pdf_url": row.get("pdf_url", ""),
                    "venue_landing_url": row.get("landing_url", ""),
                    "related_score": row.get("related_score", ""),
                    "matched_terms": row.get("matched_terms", ""),
                    **rec,
                }
            )
        else:
            new_candidates.append(
                {
                    "venue": row.get("venue", ""),
                    "year": row.get("year", ""),
                    "title": row.get("title", ""),
                    "authors": row.get("authors", ""),
                    "abstract": row.get("abstract", ""),
                    "pdf_url": row.get("pdf_url", ""),
                    "landing_url": row.get("landing_url", ""),
                    "related_score": row.get("related_score", "0"),
                    "matched_terms": row.get("matched_terms", ""),
                    "best_fuzzy_score": f"{score:.4f}",
                }
            )

    new_candidates.sort(key=lambda r: (-int(r.get("related_score", "0") or 0), r["venue"], r["year"], r["title"]))
    to_download = [r for r in new_candidates if int(r.get("related_score", "0") or 0) >= MIN_NEW_SCORE][:TOP_NEW_DOWNLOADS]
    downloads = [download_pdf(r) for r in to_download]

    match_fields = [
        "match_type",
        "match_score",
        "venue",
        "year",
        "venue_title",
        "venue_pdf_url",
        "venue_landing_url",
        "related_score",
        "matched_terms",
        "current_source",
        "current_key",
        "current_title",
        "current_url",
        "current_venue",
        "current_year",
        "current_norm",
    ]
    new_fields = ["venue", "year", "title", "authors", "abstract", "pdf_url", "landing_url", "related_score", "matched_terms", "best_fuzzy_score"]
    download_fields = new_fields + ["download_status", "local_pdf", "bytes"]
    write_csv(OUTPUT_MATCHES, matches, match_fields)
    write_csv(OUTPUT_NEW, new_candidates, new_fields)
    write_csv(OUTPUT_DOWNLOADS, downloads, download_fields)

    summary = {
        "accepted_related_rows": len(accepted),
        "current_records": len(current),
        "matches": len(matches),
        "new_candidates": len(new_candidates),
        "download_attempts": len(downloads),
        "downloaded_or_exists": sum(1 for d in downloads if d["download_status"] in {"downloaded", "exists"}),
        "download_status_counts": dict(Counter(d["download_status"].split(":")[0] for d in downloads)),
        "outputs": [str(OUTPUT_MATCHES), str(OUTPUT_NEW), str(OUTPUT_DOWNLOADS)],
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    from collections import Counter

    main()
