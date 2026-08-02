#!/usr/bin/env python3
"""Rerun the recoverable API portion of the scoping-search protocol."""

from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


USER_AGENT = "robust-rag-search-rerun/1.0"
ATOM = {
    "atom": "http://www.w3.org/2005/Atom",
    "open": "http://a9.com/-/spec/opensearch/1.1/",
}


def fetch(url: str, timeout: int = 90) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def arxiv_url(query: str, max_results: int) -> str:
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    return f"https://export.arxiv.org/api/query?{params}"


def run_arxiv(row: dict[str, object]) -> dict[str, object]:
    url = arxiv_url(str(row["query"]), int(row["max_results"]))
    root = ET.fromstring(fetch(url))
    total = root.findtext("open:totalResults", default="", namespaces=ATOM)
    entries = root.findall("atom:entry", ATOM)
    return {
        "source": "arXiv API",
        "query": row["query"],
        "url": url,
        "reported_hit_count": total,
        "retrieved_count": len(entries),
        "status": "ok",
        "error": "",
    }


def run_venue(row: dict[str, str]) -> dict[str, object]:
    url = row["query_url"]
    if not url or row["api"] == "ACL Anthology bib":
        return {
            "source": row["api"],
            "query": row["query"],
            "url": url,
            "reported_hit_count": row["reported_hit_count"],
            "retrieved_count": row["retrieved_top_n"],
            "status": "plan_only",
            "error": "ACL scan is reproduced by scripts/venue_systematic_pass.py"
            if row["api"] == "ACL Anthology bib"
            else row["error"],
        }
    data = json.loads(fetch(url))
    if row["api"] == "DBLP":
        hits = data.get("result", {}).get("hits", {})
        total = hits.get("@total", "")
        retrieved = len(hits.get("hit", []))
    else:
        total = data.get("meta", {}).get("count", "")
        retrieved = len(data.get("results", []))
    return {
        "source": row["api"],
        "query": row["query"],
        "url": url,
        "reported_hit_count": total,
        "retrieved_count": retrieved,
        "status": "ok",
        "error": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute API calls. Without this flag, only validate and print the plan.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write a timestamped rerun manifest outside the frozen canonical denominator.",
    )
    args = parser.parse_args()

    manuscript = Path(__file__).resolve().parents[1]
    supplement = manuscript / "supplement"
    protocol = json.loads((supplement / "search_protocol.json").read_text())
    with (supplement / "venue_systematic_queries.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        venue_rows = list(csv.DictReader(handle))

    plan = {
        "canonical_search_cutoff": protocol["snapshot_date"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "historical_reproduction_warning": (
            "Live APIs can reproduce query logic but not historical ordering or counts. "
            "Outputs do not alter the frozen corpus."
        ),
        "arxiv_query_count": len(protocol["arxiv_queries"]),
        "venue_query_row_count": len(venue_rows),
        "known_unrecoverable_sources": [
            "initial OpenReview execution",
            "initial USENIX landing-page execution",
            "initial AAAI/ACM landing-page execution",
            "initial curated-list merge counts",
        ],
        "results": [],
    }
    if args.live:
        for row in protocol["arxiv_queries"]:
            try:
                plan["results"].append(run_arxiv(row))
            except Exception as error:
                plan["results"].append(
                    {
                        "source": "arXiv API",
                        "query": row["query"],
                        "url": arxiv_url(row["query"], row["max_results"]),
                        "reported_hit_count": "",
                        "retrieved_count": "",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
        for row in venue_rows:
            try:
                plan["results"].append(run_venue(row))
            except Exception as error:
                plan["results"].append(
                    {
                        "source": row["api"],
                        "query": row["query"],
                        "url": row["query_url"],
                        "reported_hit_count": "",
                        "retrieved_count": "",
                        "status": "error",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
