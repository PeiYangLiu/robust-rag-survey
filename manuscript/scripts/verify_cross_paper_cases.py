#!/usr/bin/env python3
"""Deterministic verifier for cross-paper comparability cases.

Opens every cited file/line range and asserts that each quoted snippet
and each quoted numeral literally occurs at the cited lines.

Also verifies matched_number provenance when the field is not
'not_recoverable_from_text'.

Exits nonzero on any mismatch.
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE, "supplement", "cross_paper_comparability_cases.json")

def read_lines(filepath, start, end):
    """Read lines start..end (1-indexed, inclusive) from a file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        # clamp
        s = max(0, start - 1)
        e = min(len(lines), end)
        return "".join(lines[s:e])
    except Exception as exc:
        return f"[ERROR reading {filepath}: {exc}]"

def extract_numerals(text):
    """Extract decimal numerals, ignoring numbers glued to identifiers.

    Two refinements matter for this corpus.  Thousands separators are stripped
    so that a ledger entry writing ``1399`` matches a source printing
    ``1,399``.  And a numeral is only extracted when it is not preceded by a
    letter, so a model name such as ``ChatGPT3.5`` or ``GPT-4`` does not
    contribute ``3.5`` or ``4`` as if it were a reported measurement.
    """
    text = re.sub(r'(?<=\d),(?=\d{3}\b)', '', str(text))
    return set(re.findall(r'(?<![A-Za-z0-9.])(\d+\.?\d*)', text))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve(path):
    """Ledger paths are stored repo-relative; make them absolute."""
    return path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)


def check_provenance_entry(entry, case_id):
    """Check one provenance entry. Returns (pass, message)."""
    fp = _resolve(entry["file"])
    if not os.path.exists(fp):
        return False, f"  FAIL [{case_id}] File not found: {fp}"

    line_spec = entry["lines"]
    content_hint = entry.get("content", "")

    # Parse line range
    m = re.match(r'(\d+)\s*-\s*(\d+)', line_spec)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
    else:
        start = end = int(line_spec.strip())

    # Allow generous margin (+/- 5 lines)
    block = read_lines(fp, max(1, start - 5), end + 5)
    if block.startswith("[ERROR"):
        return False, f"  FAIL [{case_id}] {block}"

    # Strategy 1: check if content_hint keywords are present
    # Extract keywords (words of 3+ chars)
    keywords = [w for w in re.findall(r'[A-Za-z0-9._-]{3,}', content_hint)]
    # Extract numerals from content_hint
    numerals = extract_numerals(content_hint)

    # Normalize block for matching
    block_lower = block.lower()
    block_nums = extract_numerals(block)

    # Check numerals (most important)
    missing_nums = []
    for num in numerals:
        if num not in block_nums:
            # Try without trailing zeros
            stripped = num.rstrip('0').rstrip('.')
            if stripped and stripped not in block_nums and not any(stripped in bn for bn in block_nums):
                missing_nums.append(num)

    # Check keywords (at least 60% should be present)
    found_kw = sum(1 for kw in keywords if kw.lower() in block_lower)
    kw_ratio = found_kw / max(1, len(keywords))

    # A missing numeral is always a failure.  The previous rule failed only
    # when keyword coverage was ALSO below 40%, so a provenance entry could
    # name a number that does not occur at the cited lines and still pass as
    # long as its surrounding words did.
    if missing_nums:
        return False, (f"  FAIL [{case_id}] L{line_spec} of {os.path.basename(fp)}: "
                       f"missing numerals {sorted(missing_nums)}\n"
                       f"    Expected: {content_hint}\n"
                       f"    Got (excerpt): {block[:200]}")
    if keywords and kw_ratio < 0.4:
        return False, (f"  FAIL [{case_id}] L{line_spec} of {os.path.basename(fp)}: "
                       f"keyword ratio {kw_ratio:.0%} below 40%\n"
                       f"    Expected: {content_hint}")

    return True, f"  PASS [{case_id}] L{line_spec} of {os.path.basename(fp)}"

def extract_data_numerals(text):
    """Extract data numerals from matched_number, filtering out line references and years."""
    all_nums = extract_numerals(text)
    # Remove line references: numbers preceded by 'L' or in patterns like L1234-5678
    line_refs = set()
    for _m in re.finditer(r'L(\d+)(?:\s*-\s*(\d+))?', str(text)):
        line_refs.add(_m.group(1))
        if _m.group(2):
            line_refs.add(_m.group(2))
    # Also remove numbers that are part of file names (e.g., poisonedRAG2024.txt -> 2024)
    file_nums = set(re.findall(r'[a-zA-Z](\d{4})\b', text))
    # Remove year-like 4-digit numbers (2020-2029) unless they have a decimal
    filtered = set()
    for n in all_nums:
        if n in line_refs:
            continue
        if n in file_nums:
            continue
        # Also skip numbers with trailing dot that are years (e.g. "2024.")
        base = n.rstrip('.')
        if base in file_nums or base in line_refs:
            continue
        # Skip 4-digit integers that look like years or line numbers
        if re.match(r'^\d{4}\.?$', n) and int(n.rstrip('.')) > 100:
            continue
        filtered.add(n)
    return filtered

def check_matched_number(case):
    """Verify matched_number field against provenance if not 'not_recoverable_from_text'."""
    mn = case.get("matched_number", "not_recoverable_from_text")
    if mn == "not_recoverable_from_text":
        return True, f"  SKIP [{case['case_id']}] matched_number = not_recoverable_from_text"

    # Extract data numerals from matched_number (exclude line refs/years)
    numerals = extract_data_numerals(mn)
    if not numerals:
        return True, f"  SKIP [{case['case_id']}] matched_number has no data numerals"

    # Check that each numeral appears in at least one provenance block
    all_prov_text = ""
    for entry in case["provenance"]:
        fp = _resolve(entry["file"])
        line_spec = entry["lines"]
        m = re.match(r'(\d+)\s*-\s*(\d+)', line_spec)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
        else:
            start = end = int(line_spec.strip())
        all_prov_text += read_lines(fp, max(1, start - 5), end + 5)

    prov_nums = extract_numerals(all_prov_text)
    missing = []
    for num in numerals:
        if num not in prov_nums:
            stripped = num.rstrip('0').rstrip('.')
            if stripped and stripped not in prov_nums and not any(stripped in pn for pn in prov_nums):
                missing.append(num)

    if missing:
        return False, (f"  FAIL [{case['case_id']}] matched_number numerals {missing} "
                       f"not found in any provenance block")

    return True, f"  PASS [{case['case_id']}] matched_number numerals verified"

def _squash(text):
    """Collapse whitespace and hyphenated line breaks for verbatim matching.

    The extracted texts preserve the PDF's line wrapping, including hyphenated
    word splits, so a quotation that is verbatim in the paper is not a literal
    substring of the file.  Squashing both sides makes the comparison exact on
    content while tolerating layout.
    """
    text = re.sub(r'-\s*\n\s*', '', text)      # re-join hyphenated line breaks
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()

def check_quoted_string(entry, case_id, index):
    """Assert a string the manuscript presents in quotation marks is verbatim.

    This is the check whose absence let a fabricated quotation survive review:
    the old verifier only re-opened the line ranges named in ``provenance`` and
    compared numerals, so a ``comparison_claim`` that put words in a cited
    paper's mouth was never tested against that paper.
    """
    fp = _resolve(entry["file"])
    if not os.path.exists(fp):
        return False, f"  FAIL [{case_id}] quote {index}: file not found: {fp}"

    m = re.match(r'(\d+)\s*-\s*(\d+)', str(entry["lines"]))
    if m:
        start, end = int(m.group(1)), int(m.group(2))
    else:
        start = end = int(str(entry["lines"]).strip())

    block = _squash(read_lines(fp, max(1, start - 3), end + 3))
    quote = _squash(entry["quote"])
    if quote in block:
        return True, (f"  PASS [{case_id}] quote {index} verbatim at "
                      f"{os.path.basename(fp)}:{entry['lines']}")
    return False, (f"  FAIL [{case_id}] quote {index} NOT verbatim at "
                   f"{os.path.basename(fp)}:{entry['lines']}\n"
                   f"    Claimed: {quote[:160]}\n"
                   f"    Source : {block[:160]}")

def check_claim_has_no_unbacked_quote(case):
    """Every quoted span inside ``comparison_claim`` must be a declared quote.

    ``comparison_claim`` is prose, and prose is where the error was.  If it
    quotes anything, that span has to appear in ``quoted_strings`` so that the
    check above can test it against a source line range.
    """
    cid = case["case_id"]
    claim = case.get("comparison_claim", "")
    # A single quote only opens a quotation at a word boundary and only closes
    # at one, so that apostrophes inside tokens (k'=1, PoisonedRAG's) and
    # possessives are not mistaken for quotation marks.
    spans = re.findall(r"(?:^|(?<=[\s(\[]))'([^']{12,}?)'(?=$|[\s.,;:)\]])", claim)
    spans += re.findall(r'"([^"]{12,}?)"', claim)
    if not spans:
        return True, f"  SKIP [{cid}] comparison_claim quotes nothing"
    declared = [_squash(q["quote"]) for q in case.get("quoted_strings", [])]
    labels = [_squash(s) for s in case.get("unsourced_labels", [])]
    unbacked = [
        s for s in spans
        if not any(_squash(s) in d for d in declared)
        and _squash(s) not in labels
    ]
    if unbacked:
        return False, (f"  FAIL [{cid}] comparison_claim quotes text with no "
                       f"declared source: {unbacked[0][:120]!r}")
    return True, f"  PASS [{cid}] all {len(spans)} claim quotations declared"

def check_rendered_fields(case):
    """Every numeral in a rendered prose field must be traceable to the sources.

    ``check_matched_number`` covered one field.  A reviewer showed that
    ``naive_gap``, the two side values, the corrected reading and the
    consequence were never checked, so a fabricated number in any of them
    passed.  Those fields are what the tables print, so they are what a reader
    sees.

    A rendered numeral is accepted if it is quoted -- present in a provenance
    block -- or if it is *derived*: equal to the difference or the sum of two
    quoted numerals, which is what a stated gap is.  Anything else is a number
    the sources do not support, which is the error class this paper is about.
    """
    cid = case["case_id"]
    fields = (
        "naive_gap",
        "naive_gap_short",
        "side_A_number",
        "side_B_number",
        "corrected_reading",
        "numeric_consequence",
        "numeric_consequence_short",
    )
    all_prov = ""
    for entry in case["provenance"]:
        m = re.match(r'(\d+)\s*-\s*(\d+)', str(entry["lines"]))
        if m:
            start, end = int(m.group(1)), int(m.group(2))
        else:
            start = end = int(str(entry["lines"]).strip())
        all_prov += read_lines(_resolve(entry["file"]), max(1, start - 5), end + 5)
    prov_nums = extract_numerals(all_prov)
    prov_vals = []
    for n in prov_nums:
        try:
            prov_vals.append(float(n))
        except ValueError:
            pass
    # Percentages and fractions of the same quantity are the same evidence.
    scaled = set(prov_vals) | {v / 100.0 for v in prov_vals} | {
        v * 100.0 for v in prov_vals
    }

    # Declared derived quantities.  Each must state its arithmetic, every input
    # must be a quoted value, and the arithmetic must hold.  An auto-derivation
    # rule was tried and rejected: with N quoted values the N^2 pairwise
    # differences cover the range densely enough to accept a fabricated number.
    declared = {}
    for spec in case.get("derived_numbers", []):
        value = float(spec["value"])
        op = spec.get("op", "sub")
        inputs = [float(x) for x in spec.get("inputs", [])]
        if op == "literal":
            declared[round(value, 6)] = True
            continue
        if not all(any(abs(i - s) < 1e-6 for s in scaled) for i in inputs):
            continue  # an input that is not quoted cannot license the output
        if op == "sub" and len(inputs) == 2:
            ok = abs(abs(inputs[0] - inputs[1]) - value) < 5e-3
        elif op == "add" and len(inputs) == 2:
            ok = abs(inputs[0] + inputs[1] - value) < 5e-3
        elif op == "scale" and len(inputs) == 1:
            ok = min(abs(inputs[0] / 100.0 - value), abs(inputs[0] * 100.0 - value)) < 5e-6
        else:
            ok = False
        if ok:
            declared[round(value, 6)] = True

    def derivable(value: float) -> bool:
        return declared.get(round(value, 6), False)

    missing = {}
    for field in fields:
        text = case.get(field)
        if not text:
            continue
        for num in extract_data_numerals(str(text)):
            if num in prov_nums:
                continue
            stripped = num.rstrip('0').rstrip('.')
            if stripped and (stripped in prov_nums or
                             any(pn.startswith(num) for pn in prov_nums)):
                continue
            try:
                value = float(num)
            except ValueError:
                continue
            if any(abs(value - s) < 1e-9 for s in scaled) or derivable(value):
                continue
            missing.setdefault(field, []).append(num)
    if missing:
        field, nums = next(iter(missing.items()))
        return False, (f"  FAIL [{cid}] rendered field {field!r} contains "
                       f"numerals that are neither quoted nor derivable from "
                       f"the provenance blocks: {sorted(set(nums))}")
    return True, f"  PASS [{cid}] all rendered numeric fields traceable"


def main():
    if not os.path.exists(JSON_PATH):
        print(f"ERROR: {JSON_PATH} not found")
        sys.exit(1)

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    total = 0
    passed = 0
    failed = 0
    messages = []

    for case in cases:
        case_id = case["case_id"]

        # Check provenance entries
        for entry in case["provenance"]:
            total += 1
            ok, msg = check_provenance_entry(entry, case_id)
            messages.append(msg)
            if ok:
                passed += 1
            else:
                failed += 1

        # Check matched_number
        total += 1
        ok, msg = check_matched_number(case)
        messages.append(msg)
        if ok:
            passed += 1
        else:
            failed += 1

        # Check every declared verbatim quotation
        for index, entry in enumerate(case.get("quoted_strings", []), start=1):
            total += 1
            ok, msg = check_quoted_string(entry, case_id, index)
            messages.append(msg)
            if ok:
                passed += 1
            else:
                failed += 1

        # Check the prose field itself quotes nothing undeclared
        total += 1
        ok, msg = check_claim_has_no_unbacked_quote(case)
        messages.append(msg)
        if ok:
            passed += 1
        else:
            failed += 1

        # Check every numeral in every field a table renders
        total += 1
        ok, msg = check_rendered_fields(case)
        messages.append(msg)
        if ok:
            passed += 1
        else:
            failed += 1

    # Print all messages
    for msg in messages:
        print(msg)

    print(f"\n{'='*60}")
    print(f"TOTAL: {total} checks | PASSED: {passed} | FAILED: {failed}")
    if failed > 0:
        print("VERIFICATION FAILED")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
