#!/usr/bin/env python3
"""Drop unusable rows from a judge's coding file so the run can resume.

``code_cross_paper_frame.py`` appends one row per candidate whether or not the
call succeeded, and resumes by skipping candidates already present.  A row that
carries an ``api_error`` (rate limit) or that failed to parse is therefore
sticky: the resume logic treats it as done.  This removes those rows so the
next invocation retries exactly them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CODING = REPO / "manuscript" / "supplement" / "cross_paper_coding"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("judges", nargs="+")
    args = ap.parse_args()
    for name in args.judges:
        path = CODING / f"{name}.jsonl"
        if not path.exists():
            print(f"{name}: no file")
            continue
        keep, dropped, seen = [], 0, set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cid = row.get("candidate_id")
            if not row.get("parsed") or cid in seen:
                dropped += 1
                continue
            seen.add(cid)
            keep.append(line)
        path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        print(f"{name}: kept {len(keep)}, dropped {dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
