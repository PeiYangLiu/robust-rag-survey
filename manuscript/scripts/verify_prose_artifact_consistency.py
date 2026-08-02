#!/usr/bin/env python3
"""Check that numbers asserted in ``main.tex`` prose match the artifacts.

The released verifier checks the *ledger* against the sources.  A reviewer
observed that the manuscript claimed more than that established -- "every value
machine-checked at its source line" -- while the prose itself was never
compared to anything.  Two scripts now close that gap from different sides:

*   ``verify_manuscript_quotations.py`` checks every quoted string in the
    manuscript and its included tables against a registered source line range;
*   this script checks every *number* the manuscript asserts about its own
    artifacts against the artifact that produced it.

Each check names the macro or literal in the manuscript, the artifact field it
must equal, and the tolerance.  A literal that drifts from its artifact is a
failure, which is the failure mode that produced the reviewer's W3 and W5.

Exits nonzero on any mismatch.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANUSCRIPT = REPO / "manuscript"
SUP = MANUSCRIPT / "supplement"
TAB = MANUSCRIPT / "tables"
MAIN = MANUSCRIPT / "main.tex"
MAIN_SURVEY = MANUSCRIPT / "main_survey.tex"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def macros() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in (
        "revision_macros.tex",
        "revision2_macros.tex",
        "revision3_macros.tex",
        "revision4_macros.tex",
        "revision4_human_macros.tex",
        "revision4_c3_macros.tex",
        "revision4_diag_macros.tex",
        "revision4_instrument_macros.tex",
        "coverage_macros.tex",
        "controlled_model_judges_v2_macros.tex",
    ):
        path = TAB / name
        if path.exists():
            out.update(
                dict(
                    re.findall(
                        r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}",
                        path.read_text(encoding="utf-8"),
                    )
                )
            )
    return out


def close(a, b, tol=0.006) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def main() -> int:
    body = MAIN.read_text(encoding="utf-8") + MAIN_SURVEY.read_text(encoding="utf-8")
    mac = macros()
    census = load(SUP / "cross_paper_census.json")
    dec = census.get("agreement_decomposition", {})
    ledger = load(SUP / "cross_paper_comparability_cases.json")
    lsum = ledger.get("summary", {})
    multi = load(SUP / "sigma_r_multi_anchor.json").get("anchors", {})
    human = load(SUP / "sigma_anchors" / "sigma_r_human_anchors.json").get("anchors", {})
    tier = load(SUP / "cross_paper_tier_control.json")
    rec = load(SUP / "ledger_recoding_agreement.json")
    abl = load(SUP / "codebook_ablation.json")
    ins = load(SUP / "comparability_instrument_results.json")

    failures: list[str] = []
    checks = 0

    def eq(label: str, got, want, tol=0.006):
        nonlocal checks
        checks += 1
        if not close(got, want, tol):
            failures.append(f"  FAIL {label}: manuscript {got!r} vs artifact {want!r}")

    def same(label: str, got, want):
        nonlocal checks
        checks += 1
        if str(got).strip() != str(want).strip():
            failures.append(f"  FAIL {label}: manuscript {got!r} vs artifact {want!r}")

    # ---- census macros against the census JSON -------------------------
    for name, field, key in (
        ("DecProv", "provenance", "point"),
        ("DecProvK", "provenance", "fleiss_kappa"),
        ("DecVerdict", "verdict", "point"),
        ("DecVerdictK", "verdict", "fleiss_kappa"),
        ("DecElig", "eligibility", "point"),
        ("DecEligM", "eligibility_matched", "point"),
        ("DecEligMK", "eligibility_matched", "fleiss_kappa"),
        ("DecGap", "provenance_minus_verdict", "point"),
        ("DecGapK", "provenance_minus_verdict_kappa", "point"),
        ("DecGapEl", "eligibility_matched_minus_verdict", "point"),
        ("DecGapElK", "eligibility_matched_minus_verdict_kappa", "point"),
    ):
        eq(f"\\{name}", mac.get(name), (dec.get(field) or {}).get(key))

    # Each reported difference must be the subtraction of two reported numbers.
    eq(
        "gap identity: provenance - verdict",
        float(mac["DecGap"]),
        float(mac["DecProv"]) - float(mac["DecVerdict"]),
        0.011,
    )
    eq(
        "gap identity: eligibility(matched) - verdict",
        float(mac["DecGapEl"]),
        float(mac["DecEligM"]) - float(mac["DecVerdict"]),
        0.011,
    )
    eq(
        "kappa gap identity: provenance - verdict",
        float(mac["DecGapK"]),
        float(mac["DecProvK"]) - float(mac["DecVerdictK"]),
        0.011,
    )
    eq(
        "kappa gap identity: eligibility(matched) - verdict",
        float(mac["DecGapElK"]),
        float(mac["DecEligMK"]) - float(mac["DecVerdictK"]),
        0.011,
    )

    # ---- ledger counts --------------------------------------------------
    st = lsum.get("counts_by_conclusion_change_stated_only", {})
    inv = lsum.get("counts_by_conclusion_change_survey_invited_only", {})
    same("\\LedgerStated", mac.get("LedgerStated"), lsum.get("n_stated"))
    same("\\LedgerStatedUndef", mac.get("LedgerStatedUndef"), st.get("undefined", 0))
    same("\\LedgerStatedNarrow", mac.get("LedgerStatedNarrow"), st.get("narrows", 0))
    same("\\LedgerStatedSurv", mac.get("LedgerStatedSurv"), st.get("survives", 0))
    same("\\LedgerInvited", mac.get("LedgerInvited"), lsum.get("n_survey_invited"))
    same("\\LedgerInvitedUndef", mac.get("LedgerInvitedUndef"), inv.get("undefined", 0))
    checks += 1
    if int(mac["LedgerStatedUndef"]) + int(mac["LedgerStatedNarrow"]) + int(
        mac["LedgerStatedSurv"]
    ) != int(mac["LedgerStated"]):
        failures.append("  FAIL stated verdicts do not sum to the stated count")

    # ---- sigma anchors ---------------------------------------------------
    values = [v["sigma_r"] for v in human.values()]
    values += [v["sigma_r"] for v in multi.values()]
    eq("\\SigmaMin", mac.get("SigmaMin"), min(values))
    eq("\\SigmaMax", mac.get("SigmaMax"), max(values))
    for name, key in (
        ("SigmaCensus", "census_verdict_panel"),
        ("SigmaInstrument", "instrument_benchmark"),
        ("SigmaPanel", "model_panel_checkpoints"),
    ):
        if key in multi:
            eq(f"\\{name}", mac.get(name), multi[key]["sigma_r"])
    # No claim in this paper may rest on annotation collected from people.
    checks += 1
    if any(v.get("reviewer_kind") == "human" for v in multi.values()):
        failures.append(
            "  FAIL a sigma_r anchor of ours is a human annotation collected "
            "for this paper; the paper claims none exists"
        )
    for name, entry in list(human.items()) + list(multi.items()):
        ci = entry.get("boot_reviewers_ci95")
        checks += 1
        if not ci or not (ci[0] - 1e-9 <= entry["sigma_r"] <= ci[1] + 1e-9):
            failures.append(
                f"  FAIL {name}: sigma_r {entry['sigma_r']:.3f} outside its "
                f"reported reviewer-bootstrap interval {ci}"
            )

    # ---- tier control ----------------------------------------------------
    if tier:
        for name, panel, field in (
            ("TierSubmittedVerdictK", "submitted", "verdict_kappa"),
            ("TierSmallVerdictK", "small", "verdict_kappa"),
            ("TierFrontierVerdictK", "frontier", "verdict_kappa"),
            ("TierSameDevVerdictK", "same_dev_tier", "verdict_kappa"),
            ("TierFrontierVerdictKAll", "frontier", "verdict_kappa_allitems"),
            ("TierSubmittedVerdictKAll", "submitted", "verdict_kappa_allitems"),
        ):
            got = mac.get(name)
            want = ((tier.get(panel) or {}).get(field) or {}).get("point")
            if want is not None:
                eq(f"\\{name}", got, want)
        ft = tier.get("factor_tests", {})
        # Every reported p-value must come from a randomisation over JUDGES.
        # A p-value computed over judge *pairs* is the wrong-unit error this
        # paper is about, and it passed an earlier version of this check.
        for label, key in (
            ("TierDevP", "developer_partition_exact"),
            ("TierTierP", "tier_label_exact"),
            ("TierPairP", "frontier_pairing_exact"),
        ):
            if ft.get(key):
                eq(f"\\{label}", mac.get(label), ft[key]["p_exact_two_sided"], 0.011)
                checks += 1
                if ft[key].get("randomisation_unit") != "judge":
                    failures.append(
                        f"  FAIL {key} is not randomised over judges"
                    )
        for label, key in (
            ("TierDevDiff", "developer_partition_exact"),
            ("TierPairDiff", "frontier_pairing_exact"),
        ):
            if ft.get(key):
                eq(f"\\{label}", mac.get(label), ft[key]["difference"], 0.011)
        # Every panel in the tier table is scored on one common population.
        checks += 1
        pool_n = (tier.get("pool") or {}).get("n_pool_eligible")
        bad = [
            name
            for name in ("submitted", "small", "frontier", "frontier_cross_dev")
            if tier.get(name) and tier[name].get("n_pool_eligible") != pool_n
        ]
        if bad:
            failures.append(f"  FAIL panels not scored on a common item set: {bad}")

    # ---- independent re-coding of the ledger -----------------------------
    if rec:
        cp = rec.get("cross_paper", {})
        eq("\\RecThreeWay", mac.get("RecThreeWay"), cp.get("majority_exact"))
        eq("\\RecBinary", mac.get("RecBinary"), cp.get("binary_majority_exact"))
        eq("\\RecPanelK", mac.get("RecPanelK"), cp.get("panel_fleiss_kappa"))
        same("\\RecCases", mac.get("RecCases"), cp.get("n_cases"))
        # The paper may not quote a rate from a ledger its own re-coding does
        # not reproduce.  This is the check that would have caught the
        # withdrawn headline.
        checks += 1
        if float(cp.get("majority_exact", 0)) < 0.9 and re.search(
            r"\\LedgerStatedUndef\{\}[^.]{0,80}(of|are)\b", body
        ):
            failures.append(
                "  FAIL the manuscript quotes a ledger verdict rate while the "
                "independent re-coding reproduces the three-way label on only "
                f"{cp['majority_exact']:.0%} of cases"
            )

    # ---- codebook ablation ------------------------------------------------
    if abl:
        arms = abl.get("arms", {})
        for label, arm in (("AblFiveK", "five"), ("AblCFourK", "c1c4"), ("AblDirectK", "direct")):
            if arms.get(arm):
                eq(f"\\{label}", mac.get(label), arms[arm]["verdict_kappa"])
        same("\\AblItems", (mac.get("AblItems") or "").replace(",", ""), abl.get("n_items"))

    # ---- constructed instrument benchmark ---------------------------------
    if ins:
        est = ins.get("estimators", {})
        eq("\\InsBaseline", mac.get("InsBaseline"), ins.get("majority_class_baseline"))
        eq(
            "\\InsRule",
            mac.get("InsRule"),
            (est.get("Five coordinates (rule)") or {}).get("mean_exact"),
        )
        eq(
            "\\InsAblated",
            mac.get("InsAblated"),
            (est.get("Rule with C2/C5 ablated") or {}).get("mean_exact"),
        )
        # Direction check.  The manuscript must not assert that the coordinates
        # lose to, or fail to beat, a majority-class baseline unless the
        # artifact says so.  An earlier version asserted exactly that while its
        # own artifact reported the opposite, and no check caught it.
        checks += 1
        rule = (est.get("Five coordinates (rule)") or {}).get("mean_exact")
        base = ins.get("majority_class_baseline")
        loses = re.search(
            r"(lose to|fail(?:s|ing)? to beat|below the)[^.]{0,60}"
            r"(majority-class|majority class|constant) baseline",
            body,
        )
        if rule is not None and base is not None and rule > base and loses:
            failures.append(
                "  FAIL the manuscript says the coordinates lose to a "
                f"majority-class baseline, but the artifact reports {rule:.3f} "
                f"against {base:.3f}"
            )
        if rule is not None and base is not None and rule <= base and not loses:
            failures.append(
                "  FAIL the artifact reports the coordinates at or below the "
                "majority-class baseline, but the manuscript does not say so"
            )

    # ---- literals that must not drift ------------------------------------
    # A literal in prose that duplicates a macro is how [0.00,0.53] survived a
    # recomputation to [0.00,0.35]; assert the retired values are gone.
    for retired, why in (
        (r"\[0\.00,\s*0\.53\]", "superseded three-coder interval"),
        (r"ten of twelve source-verified", "superseded ledger headline"),
    ):
        checks += 1
        if re.search(retired, body):
            failures.append(f"  FAIL manuscript still contains a {why}: {retired}")

    # The retracted attribution must not reappear anywhere.
    checks += 1
    if re.search(r"``from 97\\%''", body):
        failures.append(
            "  FAIL the retracted attribution 'from 97%' is back in the prose"
        )

    # The human anchor is now reported, so it must match the released artifact
    # rather than be absent.  Claims we never collected are still banned.
    checks += 1
    banned = re.search(r"(480-claim|four-contributor|crowdwork)", body)
    if banned:
        failures.append(
            f"  FAIL the manuscript refers to human annotation we do not "
            f"release: {banned.group(0)!r}"
        )

    anchor_path = SUP / "human_anchor_results.json"
    if anchor_path.exists():
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        eq("\\HumN", mac.get("HumN"), anchor["n_items"])
        eq("\\HumSources", mac.get("HumSources"), anchor["n_sources"])
        eq(
            "\\HumVerdictK",
            mac.get("HumVerdictK"),
            anchor["panels"]["human"]["verdict"]["fleiss_kappa"],
        )
        eq(
            "\\HumVerdictKmax",
            mac.get("HumVerdictKmax"),
            anchor["panels"]["human"]["verdict"]["kappa_max"],
        )
        if "model_deployed" in anchor["panels"]:
            eq(
                "\\HumModVerdictK",
                mac.get("HumModVerdictK"),
                anchor["panels"]["model_deployed"]["verdict"]["fleiss_kappa"],
            )
        checks += 1
        if "human coders" not in body and "trained people" not in body:
            failures.append(
                "  FAIL the human anchor is released but the manuscript never "
                "reports it"
            )
    else:
        checks += 1
        failures.append(
            "  FAIL the manuscript reports a human anchor but "
            "supplement/human_anchor_results.json is missing"
        )

    # every macro used must exist
    used = set(re.findall(r"\\([A-Z][A-Za-z]+)\{\}", body))
    known = set(mac) | {
        "LaTeX", "TeX", "S", "P",
    }
    unknown = sorted(u for u in used if u not in known)
    checks += 1
    if unknown:
        failures.append(f"  FAIL undefined macros used in main.tex: {unknown}")

    print(f"prose/artifact consistency checks: {checks}, failures: {len(failures)}")
    for msg in failures:
        print(msg)
    if failures:
        print("PROSE/ARTIFACT CONSISTENCY FAILED")
        return 1
    print("ALL PROSE/ARTIFACT CONSISTENCY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
