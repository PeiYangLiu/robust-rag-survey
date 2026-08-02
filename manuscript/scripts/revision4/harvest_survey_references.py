#!/usr/bin/env python3
"""Harvest the reference lists of the six prior surveys the manuscript compares to.

This is the *network* half of the frame-coverage audit. It downloads the
bibliography of each prior survey from the Semantic Scholar Graph API and caches
the raw JSON under ``manuscript/supplement/coverage_audit/raw/`` so that the
deterministic analysis (``analyze_frame_coverage.py``) can run fully offline and
be reproduced by a third party from the cached bytes.

Semantic Scholar needs no API key but is aggressively rate limited on shared
IPs, so every call retries on HTTP 429 with exponential backoff and the harvest
is idempotent: a survey whose consolidated cache already exists is skipped.

Usage::

    python3 harvest_survey_references.py            # fetch anything not cached
    python3 harvest_survey_references.py --force     # re-fetch everything

Only the Python 3 standard library is used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# manuscript/scripts/revision4 -> manuscript
MANUSCRIPT = os.path.dirname(os.path.dirname(HERE))
RAW_DIR = os.path.join(MANUSCRIPT, "supplement", "coverage_audit", "raw")

S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
REF_FIELDS = "title,externalIds,year"
USER_AGENT = "robust-rag-survey-coverage-audit/1.0 (mailto:anonymous@example.org)"

# Ordered identifier candidates per survey. The first identifier that the API
# accepts (HTTP 200) is used; the rest are fallbacks. The bib key matches the
# manuscript citation key so the analysis can join back to references.bib.
SURVEYS = [
    {
        "key": "ragSurvey2024",
        "title": "Retrieval-Augmented Generation for Large Language Models: A Survey",
        "ids": ["arXiv:2312.10997"],
    },
    {
        "key": "ragEvaluationSurvey2024",
        "title": "Evaluation of Retrieval-Augmented Generation: A Survey",
        "ids": ["arXiv:2405.07437"],
    },
    {
        "key": "trustRAGCompass2024",
        "title": "Trustworthiness in Retrieval-Augmented Generation Systems: A Survey",
        "ids": ["arXiv:2409.10102"],
    },
    {
        "key": "securityRAGSurvey2026",
        "title": "Securing Retrieval-Augmented Generation: A Taxonomy of Attacks, "
                 "Defenses, and Future Directions",
        "ids": ["arXiv:2604.08304", "arXiv:2604.08304v2"],
    },
    {
        "key": "xuKnowledgeConflicts2024",
        "title": "Knowledge Conflicts for LLMs: A Survey",
        "ids": ["arXiv:2403.08319", "ACL:2024.emnlp-main.486",
                "DOI:10.18653/v1/2024.emnlp-main.486"],
    },
    {
        "key": "wenAbstentionSurvey2025",
        "title": "Know Your Limits: A Survey of Abstention in Large Language Models",
        "ids": ["DOI:10.1162/tacl_a_00754", "arXiv:2407.18418",
                "ACL:2025.tacl-1.26"],
    },
]

POLITE_DELAY = 4.0          # seconds between successful calls
# Semantic Scholar's unauthenticated limit resets roughly per second and is
# shared, so many *short* retries land in an open window faster than a few long
# ones. Backoff grows gently and is capped, and we allow a large retry budget.
MAX_RETRIES = 60            # retries on 429 / transient errors
BACKOFF = [4, 4, 5, 5, 6, 6, 8, 8, 10, 10, 12, 12, 15]
PAGE_LIMIT = 1000           # S2 max page size for references


def _sleep(sec: float) -> None:
    sys.stderr.write(f"    sleeping {sec:.0f}s\n")
    sys.stderr.flush()
    time.sleep(sec)


def http_get_json(url: str):
    """GET a URL, returning (status_code, parsed_json_or_None).

    Retries on HTTP 429 and transient network/5xx errors with exponential
    backoff. Returns the last observed status on give-up.
    """
    last_status = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode("utf-8", "replace")
                return resp.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            if exc.code == 429 or 500 <= exc.code < 600:
                wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                sys.stderr.write(f"    HTTP {exc.code} (attempt {attempt + 1}); backing off\n")
                _sleep(wait)
                continue
            # 404 and other 4xx: return immediately so caller can try fallback id
            try:
                body = exc.read().decode("utf-8", "replace")
                return exc.code, json.loads(body)
            except Exception:
                return exc.code, None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_status = f"neterr:{exc}"
            wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
            sys.stderr.write(f"    network error {exc} (attempt {attempt + 1}); backing off\n")
            _sleep(wait)
            continue
    return last_status, None


def fetch_metadata(paper_id: str):
    url = f"{S2_BASE}/{paper_id}?fields=title,year,externalIds,referenceCount"
    return http_get_json(url)


def fetch_references(paper_id: str):
    """Page through the references endpoint, returning (list_of_citedPaper, pages_raw)."""
    refs = []
    pages = []
    offset = 0
    while True:
        url = (f"{S2_BASE}/{paper_id}/references"
               f"?fields={REF_FIELDS}&limit={PAGE_LIMIT}&offset={offset}")
        status, data = http_get_json(url)
        if status != 200 or not isinstance(data, dict):
            return None, pages, status
        pages.append(data)
        for row in data.get("data", []):
            cited = row.get("citedPaper")
            if cited:
                refs.append(cited)
        nxt = data.get("next")
        if nxt is None or not data.get("data"):
            break
        offset = nxt
        _sleep(POLITE_DELAY)
    return refs, pages, 200


def harvest_survey(survey: dict, force: bool) -> dict:
    key = survey["key"]
    out_path = os.path.join(RAW_DIR, f"{key}_references.json")
    if os.path.exists(out_path) and not force:
        with open(out_path) as fh:
            cached = json.load(fh)
        sys.stderr.write(f"[skip] {key}: cached ({len(cached.get('references', []))} refs)\n")
        return {"key": key, "status": "cached",
                "resolved_id": cached.get("resolved_id"),
                "n_references": len(cached.get("references", []))}

    sys.stderr.write(f"[fetch] {key}\n")
    resolved_id = None
    meta = None
    for pid in survey["ids"]:
        sys.stderr.write(f"  resolving via {pid}\n")
        status, data = fetch_metadata(pid)
        if status == 200 and isinstance(data, dict) and data.get("paperId"):
            resolved_id = pid
            meta = data
            break
        sys.stderr.write(f"  -> {pid} returned {status}\n")
        _sleep(POLITE_DELAY)

    if resolved_id is None:
        sys.stderr.write(f"[FAIL] {key}: no identifier resolved\n")
        record = {"key": key, "title": survey["title"], "resolved_id": None,
                  "status": "unresolved", "tried_ids": survey["ids"],
                  "references": []}
        with open(out_path, "w") as fh:
            json.dump(record, fh, indent=2)
        return {"key": key, "status": "unresolved", "resolved_id": None,
                "n_references": 0}

    _sleep(POLITE_DELAY)
    refs, pages, status = fetch_references(resolved_id)
    if refs is None:
        sys.stderr.write(f"[FAIL] {key}: references endpoint returned {status}\n")
        record = {"key": key, "title": survey["title"], "resolved_id": resolved_id,
                  "status": f"refs_error_{status}", "metadata": meta, "references": []}
        with open(out_path, "w") as fh:
            json.dump(record, fh, indent=2)
        return {"key": key, "status": f"refs_error_{status}",
                "resolved_id": resolved_id, "n_references": 0}

    record = {
        "key": key,
        "title": survey["title"],
        "resolved_id": resolved_id,
        "status": "ok",
        "reference_count_reported": (meta or {}).get("referenceCount"),
        "metadata": meta,
        "references": refs,
    }
    with open(out_path, "w") as fh:
        json.dump(record, fh, indent=2)
    # also persist raw pages for byte-level reproducibility
    with open(os.path.join(RAW_DIR, f"{key}_raw_pages.json"), "w") as fh:
        json.dump(pages, fh)
    sys.stderr.write(f"[ok] {key}: {len(refs)} references via {resolved_id}\n")
    return {"key": key, "status": "ok", "resolved_id": resolved_id,
            "n_references": len(refs)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-fetch even if cached")
    args = ap.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    summary = []
    for survey in SURVEYS:
        summary.append(harvest_survey(survey, args.force))
        _sleep(POLITE_DELAY)

    with open(os.path.join(RAW_DIR, "harvest_log.json"), "w") as fh:
        json.dump({"surveys": summary}, fh, indent=2)
    sys.stderr.write("\n=== harvest summary ===\n")
    for row in summary:
        sys.stderr.write(f"  {row['key']}: {row['status']} "
                         f"({row['n_references']} refs) via {row['resolved_id']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
