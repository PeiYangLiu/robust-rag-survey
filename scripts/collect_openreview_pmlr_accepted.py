#!/usr/bin/env python3
"""Collect accepted-paper metadata from OpenReview and PMLR.

Outputs:
  metadata/venue_accepts_raw.csv
  metadata/venue_accepts_rag_related.csv
  metadata/venue_accepts_summary.json

ICLR / NeurIPS are collected from OpenReview accepted venue ids where possible.
ICML is collected from PMLR proceedings volumes, because ICML proceedings are
archived by PMLR even when OpenReview metadata exists.
"""

from __future__ import annotations

import csv
import html
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "metadata"
META.mkdir(exist_ok=True)

RAW_CSV = META / "venue_accepts_raw.csv"
FILTERED_CSV = META / "venue_accepts_rag_related.csv"
SUMMARY_JSON = META / "venue_accepts_summary.json"

USER_AGENT = "robust-rag-survey-venue-collector/0.1"

# PMLR volume numbers for ICML. Add future volumes here when released.
ICML_PMLR_VOLUMES = {
    2019: "97",
    2020: "119",
    2021: "139",
    2022: "162",
    2023: "202",
    2024: "235",
    2025: "267",
}

# OpenReview accepted venue IDs vary across years. The collector tries common
# IDs and records which one succeeds.
OPENREVIEW_VENUE_CANDIDATES = {
    "ICLR": {
        2020: ["ICLR.cc/2020/Conference"],
        2021: ["ICLR.cc/2021/Conference"],
        2022: ["ICLR.cc/2022/Conference"],
        2023: ["ICLR.cc/2023/Conference", "ICLR.cc/2023/Conference/Track"],
        2024: ["ICLR.cc/2024/Conference"],
        2025: ["ICLR.cc/2025/Conference"],
    },
    "NeurIPS": {
        2020: ["NeurIPS.cc/2020/Conference"],
        2021: ["NeurIPS.cc/2021/Conference"],
        2022: ["NeurIPS.cc/2022/Conference"],
        2023: ["NeurIPS.cc/2023/Conference"],
        2024: ["NeurIPS.cc/2024/Conference"],
        2025: ["NeurIPS.cc/2025/Conference"],
    },
}

RAG_TERMS = {
    "retrieval augmented": 10,
    "retrieval-augmented": 10,
    "rag": 7,
    "retrieval augmented generation": 14,
    "retrieval-augmented generation": 14,
    "retrieval augmented language": 12,
    "open-domain question answering": 8,
    "open domain question answering": 8,
    "dense passage retrieval": 9,
    "retrieval": 2,
    "retriever": 3,
    "evidence": 2,
    "faithfulness": 6,
    "citation": 6,
    "attribution": 5,
    "hallucination": 5,
    "calibration": 6,
    "selective prediction": 7,
    "uncertainty": 4,
    "abstention": 7,
    "unanswerable": 6,
    "answerability": 6,
    "poisoning": 8,
    "prompt injection": 8,
    "adversarial retrieval": 8,
    "knowledge conflict": 8,
    "counterfactual": 4,
    "long context": 4,
}


def request(url: str, *, raw: bool = False) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()
    if raw:
        return data.decode("utf-8", errors="replace")
    return json.loads(data.decode("utf-8"))


def get_content(note: dict[str, Any], key: str) -> Any:
    value = note.get("content", {}).get(key, "")
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def normalize_list(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(x) for x in value)
    return str(value or "")


def pdf_url_from_openreview(note: dict[str, Any]) -> str:
    forum = note.get("forum") or note.get("id") or ""
    if not forum:
        return ""
    return f"https://openreview.net/pdf?id={forum}"


def openreview_url(note: dict[str, Any]) -> str:
    forum = note.get("forum") or note.get("id") or ""
    if not forum:
        return ""
    return f"https://openreview.net/forum?id={forum}"


def fetch_openreview_venue(venue: str, year: int, venue_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    limit = 1000
    offset = 0
    while True:
        params = {
            "content.venueid": venue_id,
            "limit": str(limit),
            "offset": str(offset),
        }
        url = "https://api2.openreview.net/notes?" + urllib.parse.urlencode(params)
        data = request(url)
        notes = data.get("notes", [])
        if not notes:
            break
        for note in notes:
            title = str(get_content(note, "title") or "").strip()
            abstract = str(get_content(note, "abstract") or "").strip()
            authors = normalize_list(get_content(note, "authors"))
            keywords = normalize_list(get_content(note, "keywords"))
            rows.append(
                {
                    "source": "OpenReview",
                    "venue": venue,
                    "year": str(year),
                    "venue_id": venue_id,
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "keywords": keywords,
                    "decision": "accepted",
                    "pdf_url": pdf_url_from_openreview(note),
                    "landing_url": openreview_url(note),
                    "proceedings_url": "",
                    "forum": str(note.get("forum") or note.get("id") or ""),
                }
            )
        if len(notes) < limit:
            break
        offset += limit
        time.sleep(0.3)
    return rows


def fetch_openreview_venue_v1(venue: str, year: int, venue_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    limit = 1000
    offset = 0
    while True:
        params = {
            "content.venueid": venue_id,
            "limit": str(limit),
            "offset": str(offset),
        }
        url = "https://api.openreview.net/notes?" + urllib.parse.urlencode(params)
        data = request(url)
        notes = data.get("notes", [])
        if not notes:
            break
        for note in notes:
            title = str(get_content(note, "title") or "").strip()
            abstract = str(get_content(note, "abstract") or "").strip()
            authors = normalize_list(get_content(note, "authors"))
            keywords = normalize_list(get_content(note, "keywords"))
            forum = str(note.get("forum") or note.get("id") or "")
            pdf = str(get_content(note, "pdf") or "")
            pdf_url = urllib.parse.urljoin("https://openreview.net", pdf) if pdf.startswith("/") else (pdf or f"https://openreview.net/pdf?id={forum}")
            rows.append(
                {
                    "source": "OpenReview",
                    "venue": venue,
                    "year": str(year),
                    "venue_id": venue_id,
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "keywords": keywords,
                    "decision": "accepted",
                    "pdf_url": pdf_url,
                    "landing_url": f"https://openreview.net/forum?id={forum}" if forum else "",
                    "proceedings_url": "",
                    "forum": forum,
                }
            )
        if len(notes) < limit:
            break
        offset += limit
        time.sleep(0.3)
    return rows


def collect_openreview() -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    rows: list[dict[str, str]] = []
    attempts: list[dict[str, Any]] = []
    for venue, year_map in OPENREVIEW_VENUE_CANDIDATES.items():
        for year, candidates in year_map.items():
            found_for_year = False
            for venue_id in candidates:
                try:
                    got = fetch_openreview_venue(venue, year, venue_id)
                    attempts.append({"venue": venue, "year": year, "venue_id": venue_id, "n": len(got), "status": "ok"})
                    if not got:
                        got_v1 = fetch_openreview_venue_v1(venue, year, venue_id)
                        attempts.append({"venue": venue, "year": year, "venue_id": venue_id, "n": len(got_v1), "status": "ok_v1_fallback"})
                        got = got_v1
                    if got:
                        rows.extend(got)
                        found_for_year = True
                        break
                except Exception as exc:
                    attempts.append({"venue": venue, "year": year, "venue_id": venue_id, "n": 0, "status": repr(exc)})
            if not found_for_year:
                attempts.append({"venue": venue, "year": year, "venue_id": "", "n": 0, "status": "no accepted notes found"})
    return rows, attempts


def parse_pmlr_volume(year: int, volume: str) -> list[dict[str, str]]:
    url = f"https://proceedings.mlr.press/v{volume}/"
    page = request(url, raw=True)
    blocks = re.findall(r'<div class="paper">(.*?)</div>', page, flags=re.S)
    rows = []
    for block in blocks:
        title_match = re.search(r'<p class="title">(.*?)</p>', block, flags=re.S)
        authors_match = re.search(r'<p class="details">(.*?)</p>', block, flags=re.S)
        pdf_match = re.search(r'href="([^"]+\.pdf)"', block, flags=re.S)
        abs_match = re.search(r'href="([^"]+\.html)"', block, flags=re.S)
        if not title_match:
            continue
        title = html.unescape(re.sub(r"<.*?>", "", title_match.group(1))).strip()
        authors = ""
        if authors_match:
            authors = html.unescape(re.sub(r"<.*?>", "", authors_match.group(1))).strip()
        pdf_url = urllib.parse.urljoin(url, pdf_match.group(1)) if pdf_match else ""
        landing = urllib.parse.urljoin(url, abs_match.group(1)) if abs_match else url
        abstract = ""
        # Fetch abstracts only for papers whose title is plausibly relevant.
        # Fetching every PMLR abstract is slow and unnecessary for this audit pass.
        title_score, _ = related_score({"title": title, "abstract": "", "keywords": ""})
        if title_score >= 5 and landing and landing != url:
            try:
                time.sleep(0.05)
                article = request(landing, raw=True)
                m = re.search(r'<div id="abstract"[^>]*>(.*?)</div>', article, flags=re.S)
                if m:
                    abstract = html.unescape(re.sub(r"<.*?>", " ", m.group(1))).strip()
            except Exception:
                pass
        rows.append(
            {
                "source": "PMLR",
                "venue": "ICML",
                "year": str(year),
                "venue_id": f"PMLR v{volume}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "keywords": "",
                "decision": "accepted",
                "pdf_url": pdf_url,
                "landing_url": landing,
                "proceedings_url": url,
                "forum": "",
            }
        )
    return rows


def collect_pmlr_icml() -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    rows: list[dict[str, str]] = []
    attempts: list[dict[str, Any]] = []
    for year, volume in ICML_PMLR_VOLUMES.items():
        try:
            got = parse_pmlr_volume(year, volume)
            rows.extend(got)
            attempts.append({"venue": "ICML", "year": year, "volume": volume, "n": len(got), "status": "ok"})
        except Exception as exc:
            attempts.append({"venue": "ICML", "year": year, "volume": volume, "n": 0, "status": repr(exc)})
    return rows, attempts


def related_score(row: dict[str, str]) -> tuple[int, list[str]]:
    text = " ".join([row.get("title", ""), row.get("abstract", ""), row.get("keywords", "")]).lower()
    score = 0
    hits = []
    for term, weight in RAG_TERMS.items():
        if term in text:
            score += weight
            hits.append(term)
    if "retrieval" in text and ("generation" in text or "question answering" in text or "language model" in text):
        score += 8
        hits.append("retrieval+generation/qa/lm")
    return score, hits


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "source",
        "venue",
        "year",
        "venue_id",
        "title",
        "authors",
        "abstract",
        "keywords",
        "decision",
        "pdf_url",
        "landing_url",
        "proceedings_url",
        "forum",
        "related_score",
        "matched_terms",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(out)


def dedupe(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out = []
    for row in rows:
        key = (row.get("venue", ""), row.get("title", "").lower().strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> None:
    or_rows, or_attempts = collect_openreview()
    pmlr_rows, pmlr_attempts = collect_pmlr_icml()
    rows = dedupe(or_rows + pmlr_rows)
    for row in rows:
        score, hits = related_score(row)
        row["related_score"] = str(score)
        row["matched_terms"] = "; ".join(hits)
    filtered = [row for row in rows if int(row.get("related_score", "0")) >= 10]
    filtered.sort(key=lambda r: (-int(r["related_score"]), r["venue"], r["year"], r["title"]))
    write_csv(RAW_CSV, rows)
    write_csv(FILTERED_CSV, filtered)
    summary = {
        "raw_rows": len(rows),
        "filtered_rows": len(filtered),
        "by_venue_year": dict(Counter(f"{r['venue']} {r['year']}" for r in rows)),
        "filtered_by_venue_year": dict(Counter(f"{r['venue']} {r['year']}" for r in filtered)),
        "openreview_attempts": or_attempts,
        "pmlr_attempts": pmlr_attempts,
        "outputs": [str(RAW_CSV), str(FILTERED_CSV)],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
