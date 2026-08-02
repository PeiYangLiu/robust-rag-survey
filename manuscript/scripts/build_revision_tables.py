#!/usr/bin/env python3
"""Generate the LaTeX tables and figures added in the EACL revision."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
SUPPLEMENT = REPO / "manuscript" / "supplement"
TABLES = REPO / "manuscript" / "tables"
FIGURES = REPO / "manuscript" / "figures"


def clip(text: str, limit: int) -> str:
    """Trim to whole clauses, then whole words, so no number is cut in half."""
    text = str(text).strip()
    if len(text) <= limit:
        return text
    clauses = [part.strip() for part in text.split(";") if part.strip()]
    kept: list[str] = []
    for clause in clauses:
        candidate = "; ".join(kept + [clause])
        if kept and len(candidate) > limit:
            break
        kept.append(clause)
    joined = "; ".join(kept)
    if joined and len(joined) <= limit:
        return joined if joined == text else joined + "\u2026"
    words = text.split()
    out: list[str] = []
    for word in words:
        if len(" ".join(out + [word])) > limit - 1:
            break
        out.append(word)
    return " ".join(out) + "\u2026"


def escape(text: str) -> str:
    out = str(text)
    for source, target in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
        ("->", r"$\rightarrow$"),
    ):
        out = out.replace(source, target)
    return out


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


# ---------------------------------------------------------------------------
# Cross-paper comparability cases
# ---------------------------------------------------------------------------


def build_cross_paper_tables() -> None:
    summary = json.loads(
        (SUPPLEMENT / "cross_paper_comparability_cases_summary.json").read_text(
            encoding="utf-8"
        )
    )
    cases = summary["cases"]
    cross = [case for case in cases if case["case_class"] == "cross_paper"]
    controls = [case for case in cases if case["case_class"] != "cross_paper"]
    counts = Counter(case["conclusion_change"] for case in cross)

    lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{2pt}",
        r"\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.048\textwidth}"
        r">{\raggedright\arraybackslash}p{0.040\textwidth}"
        r">{\raggedright\arraybackslash}p{0.140\textwidth}"
        r">{\raggedright\arraybackslash}p{0.098\textwidth}"
        r">{\raggedright\arraybackslash}p{0.062\textwidth}"
        r">{\raggedright\arraybackslash}p{0.062\textwidth}"
        r">{\raggedright\arraybackslash}p{0.400\textwidth}@{}}",
        r"\toprule",
        r"ID & Src & Compared results & Quoted gap & Mismatch & Verdict & Consequence of matching the coordinate \\",
        r"\midrule",
    ]
    for case in cross:
        lines.append(
            " & ".join(
                (
                    escape(case["case_id"]),
                    escape(case.get("comparison_type_label", "")),
                    escape(case["side_A"]) + r" vs.~" + escape(case["side_B"]),
                    escape(case["naive_gap_short"]),
                    escape(case["mismatched_coordinates"]).replace("; ", ", "),
                    escape(case["conclusion_change"]),
                    escape(case["numeric_consequence_short"]),
                )
            )
            + r" \\"
        )
    lines.append(r"\midrule")
    lines.append(
        r"\multicolumn{7}{@{}l}{\emph{Within-harness controls (one paper, one harness)}} \\"
    )
    for case in controls:
        lines.append(
            " & ".join(
                (
                    escape(case["case_id"]),
                    escape(case.get("comparison_type_label", "")),
                    escape(case["side_A"]) + r" vs.~" + escape(case["side_B"]),
                    escape(case["naive_gap_short"]),
                    escape(case["mismatched_coordinates"]).replace("; ", ", "),
                    escape(case["conclusion_change"]),
                    escape(case["numeric_consequence_short"]),
                )
            )
            + r" \\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Worked cross-paper comparisons. "
        rf"Of {len(cross)} comparisons published papers state (Src=stated) or "
        r"invite by grouping (Src=invited), "
        rf"{counts.get('undefined', 0)} have no common scope, "
        rf"{counts.get('narrows', 0)} survive only on a strict subset and "
        rf"{counts.get('survives', 0)} survive as stated; "
        rf"{len(controls)} within-harness contrasts are negative controls. "
        r"Every number is copied verbatim from a locally extracted full text and "
        r"re-checked at its line by \texttt{verify\_cross\_paper\_cases.py}. "
        r"C1 evidence state, C2 origin/capability, C3 intervention, C4 outcome, "
        r"C5 policy/utility. Appendix Table~\ref{tab:cross-paper-cases-full} "
        r"gives source lines and coordinate-matched values.}",
        r"\label{tab:cross-paper-cases}",
        r"\end{table*}",
        "",
    ]
    write(TABLES / "main_cross_paper_cases.tex", "\n".join(lines))

    rows = list(csv.DictReader((SUPPLEMENT / "cross_paper_comparability_cases.csv").open(encoding="utf-8")))
    detail = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{@{}p{0.055\textwidth}p{0.30\textwidth}p{0.30\textwidth}p{0.29\textwidth}@{}}",
        r"\toprule",
        r"ID & Side A (reported value) & Side B (reported value) & Coordinate-matched reading \\",
        r"\midrule",
    ]
    for row in rows:
        matched = row.get("matched_number", "") or "not recoverable from text"
        detail.append(
            " & ".join(
                (
                    escape(row["case_id"]),
                    escape(clip(row["side_A_number"], 165)),
                    escape(clip(row["side_B_number"], 165)),
                    escape(clip(matched, 190)),
                )
            )
            + r" \\"
        )
        detail.append(r"\addlinespace[1pt]")
    detail += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Reported values and coordinate-matched readings for every "
        r"comparability case. The released ledger records the file and line "
        r"range supporting each value; the verifier re-opens each range and "
        r"fails on any mismatch.}",
        r"\label{tab:cross-paper-cases-full}",
        r"\end{table*}",
        "",
    ]
    write(TABLES / "cross_paper_cases_full.tex", "\n".join(detail))


# ---------------------------------------------------------------------------
# Retrospective remedies
# ---------------------------------------------------------------------------


def _remedy_rows(payload: Mapping[str, object], **filters) -> list[Mapping[str, object]]:
    out = []
    for row in payload["rows"]:
        if all(row[key] == value for key, value in filters.items()):
            out.append(row)
    return out


def build_remedy_tables() -> None:
    payload = json.loads(
        (SUPPLEMENT / "retrospective_remedy_simulation.json").read_text(encoding="utf-8")
    )
    anchor = json.loads(
        (SUPPLEMENT / "reviewer_heterogeneity_anchor.json").read_text(encoding="utf-8")
    )
    point = float(anchor["direct_estimate"]["sigma_r_point"])
    full_grid = payload["sigma_r_grid"]
    nearest = min(full_grid, key=lambda value: abs(value - point))
    # Show the anchored range compactly: zero, our own estimate, the median and
    # the maximum of the crossed designs of Table 3.
    wanted = [0.0, nearest, 0.78]
    grid = [min(full_grid, key=lambda v: abs(v - w)) for w in wanted]
    grid = sorted(dict.fromkeys(grid))

    def cell(row: Mapping[str, object], key: str) -> str:
        return f"{100.0 * float(row[key]):.1f}"

    lines = [
        r"\begin{table}[t]",
        r"\centering\footnotesize",
        r"\setlength{\tabcolsep}{2.6pt}",
        r"\begin{tabular}{@{}lrrrr@{}}",
        r"\toprule",
        r"Setting & Panel/src & Votes/src & Rev.\ $t$ & Rev.\ RI \\",
        r"\midrule",
        r"\multicolumn{5}{@{}l}{\emph{Size: no prompt effect, $\alpha=.05$}} \\",
    ]
    for sigma in grid:
        rows = _remedy_rows(
            payload,
            reviewer_abilities="resampled",
            sigma_r=sigma,
            sources=80,
            true_prompt_effect_logit=0.0,
        )
        if not rows:
            continue
        row = rows[0]
        marker = r"$\;\ast$" if sigma == nearest else ""
        lines.append(
            f"$\\sigma_r={sigma:.2f}$, $G=80${marker} & "
            + " & ".join(
                cell(row, key)
                for key in (
                    "panel_majority_source_se",
                    "votes_source_se",
                    "reviewer_mean_t",
                    "reviewer_permutation",
                )
            )
            + r" \\"
        )
    for sources in (160,):
        rows = _remedy_rows(
            payload,
            reviewer_abilities="resampled",
            sigma_r=nearest,
            sources=sources,
            true_prompt_effect_logit=0.0,
        )
        if not rows:
            continue
        row = rows[0]
        lines.append(
            f"$\\sigma_r={nearest:.2f}$, $G={sources}$ & "
            + " & ".join(
                cell(row, key)
                for key in (
                    "panel_majority_source_se",
                    "votes_source_se",
                    "reviewer_mean_t",
                    "reviewer_permutation",
                )
            )
            + r" \\"
        )
    lines.append(r"\midrule")
    lines.append(r"\multicolumn{5}{@{}l}{\emph{Power: true prompt effect $0.4$ logits}} \\")
    for sigma, sources in ((nearest, 80), (0.78, 80)):
        sigma = min(full_grid, key=lambda v: abs(v - sigma))
        rows = _remedy_rows(
            payload,
            reviewer_abilities="resampled",
            sigma_r=sigma,
            sources=sources,
            true_prompt_effect_logit=0.4,
        )
        if not rows:
            continue
        row = rows[0]
        lines.append(
            f"$\\sigma_r={sigma:.2f}$, $G={sources}$ & "
            + " & ".join(
                cell(row, key)
                for key in (
                    "panel_majority_source_se",
                    "votes_source_se",
                    "reviewer_mean_t",
                    "reviewer_permutation",
                )
            )
            + r" \\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        rf"\caption{{Rejection percentages over {payload['replicates']:,} replicates with "
        r"twelve reviewers, six per prompt, six claims per source $G$, and "
        r"balanced three-of-six panels. Reviewer abilities are redrawn every "
        r"replicate, so the target is a reviewer-population effect rather than a "
        r"realized-panel contrast. $\sigma_r$ is the between-reviewer ability "
        r"standard deviation on the logit scale; the starred row is the value "
        rf"estimated from the crossed three-coder diagnostic ($\hat\sigma_r={point:.2f}$, "
        r"Appendix Table~\ref{tab:reviewer-heterogeneity-anchor}). "
        r"\emph{Panel/src} is the status-quo paired source $t$ test on "
        r"panel-majority correctness; \emph{Votes/src} keeps the source-level "
        r"standard error but uses individual votes; \emph{Rev.\ $t$} is a "
        r"two-sample $t$ test on the twelve individual reviewer accuracies; "
        r"\emph{Rev.\ RI} refers the same contrast to all 924 arm assignments. "
        r"The last two are executable retrospectively from released "
        r"pre-aggregation votes with reviewer identifiers, and retain power.}",
        r"\label{tab:retrospective-remedies}",
        r"\end{table}",
        "",
    ]
    write(TABLES / "main_retrospective_remedies.tex", "\n".join(lines))

    # The complete grid is ~190 rows.  As a single ``table*`` it was taller
    # than a page and was silently clipped in the PDF; ``longtable`` is not
    # usable because this document is two-column.  It is therefore emitted as
    # consecutive full-width floats that each fit on a page.
    header = [
        r"\toprule",
        r"Abilities & Quantity & $\sigma_r$ & $G$ & Claims & Panel/src & Votes/src & Rev.\ $t$ & Rev.\ RI \\",
        r"\midrule",
    ]
    body = []
    for row in payload["rows"]:
        body.append(
            " & ".join(
                (
                    escape(row["reviewer_abilities"]),
                    escape(row["quantity"]),
                    f"{float(row['sigma_r']):.2f}",
                    str(row["sources"]),
                    str(row["claims"]),
                    f"{100.0 * float(row['panel_majority_source_se']):.1f}",
                    f"{100.0 * float(row['votes_source_se']):.1f}",
                    f"{100.0 * float(row['reviewer_mean_t']):.1f}",
                    f"{100.0 * float(row['reviewer_permutation']):.1f}",
                )
            )
            + r" \\"
        )
    chunk = 48
    parts = [body[i : i + chunk] for i in range(0, len(body), chunk)]
    full = []
    for index, rows in enumerate(parts, start=1):
        of = f" ({index} of {len(parts)})" if len(parts) > 1 else ""
        full += [
            r"\begin{table*}[p]",
            r"\centering\scriptsize",
            r"\setlength{\tabcolsep}{4pt}",
            r"\begin{tabular}{@{}llrrrrrrr@{}}",
            *header,
            *rows,
            r"\bottomrule",
            r"\end{tabular}",
            r"\caption{Complete grid for the retrospective-remedy simulation"
            + of
            + r". \emph{fixed\_quantiles} holds reviewer abilities at twelve "
            r"population quantiles as in the original simulation; "
            r"\emph{resampled} redraws them each replicate. Entries are "
            r"rejection percentages. The grid is split across floats because a "
            r"single one exceeded a page and was previously clipped; the "
            r"machine-readable grid is "
            r"\texttt{supplement/retrospective\_remedy\_simulation.json}.}",
            (
                r"\label{tab:retrospective-remedies-full}"
                if index == 1
                else rf"\label{{tab:retrospective-remedies-full-{index}}}"
            ),
            r"\end{table*}",
            "",
        ]
    write(TABLES / "retrospective_remedies_full.tex", "\n".join(full))


# ---------------------------------------------------------------------------
# Reviewer-heterogeneity anchor
# ---------------------------------------------------------------------------


def build_anchor_table() -> None:
    """Report the three-coder anchor under the estimator actually used.

    The submitted version of this table reported an interval bootstrapped over
    source clusters, which is neither of the resampling schemes the paper now
    uses and which a reviewer found contradicting the main sigma table.  All
    three schemes are read from ``sigma_r_multi_anchor.json`` so that this table
    and Table~\ref{tab:sigma-r-anchors} cannot drift apart again.
    """
    anchor = json.loads(
        (SUPPLEMENT / "reviewer_heterogeneity_anchor.json").read_text(encoding="utf-8")
    )
    multi = json.loads(
        (SUPPLEMENT / "sigma_r_multi_anchor.json").read_text(encoding="utf-8")
    )["anchors"]["diagnostic_3coder"]
    accuracies = ", ".join(f"{v:.3f}" for v in sorted(multi["reviewer_accuracies"], reverse=True))

    def ci(key):
        lo, hi = multi[key]
        return f"[{lo:.3f}, {hi:.3f}]"

    lines = [
        r"\begin{table}[t]",
        r"\centering\footnotesize",
        r"\begin{tabular}{@{}lr@{}}",
        r"\toprule",
        r"Quantity & Value \\",
        r"\midrule",
        rf"Crossed design & {multi['n_reviewers']} coders $\times$ {multi['n_items']} claims \\",
        rf"Coder accuracy vs.\ adjudicated & {accuracies} \\",
        rf"$\hat\sigma_r$ (moment estimate) & {float(multi['sigma_r']):.3f} \\",
        rf"Reviewer bootstrap 95\% & {ci('boot_reviewers_ci95')} \\",
        rf"Item bootstrap 95\% & {ci('boot_items_ci95')} \\",
        rf"Parametric bootstrap 95\% & {ci('boot_parametric_ci95')} \\",
        rf"Parametric bias of $\hat\sigma_r$ & ${float(multi['boot_parametric_bias']):+.3f}$ \\",
        r"\midrule",
        r"\multicolumn{2}{@{}l}{\emph{Identification from published reporting}} \\",
        rf"Widest admissible $\sigma_r$ set & {100.0 * float(anchor['widest_admissible_sigma_r_fraction_of_grid']):.0f}\% of the grid \\",
        r"Point identified by reporting? & no \\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Reviewer heterogeneity is estimable only from a crossed "
        r"reviewer-by-item design, and three coders do not estimate it. All "
        r"three resampling schemes are shown because they disagree about the "
        r"width and not about the conclusion: every interval contains zero, so "
        r"this design alone cannot distinguish a badly miscalibrated panel from "
        r"a homogeneous one. The reviewer bootstrap is the scheme reported for "
        r"all seven designs in Table~\ref{tab:sigma-r-anchors}, because the "
        r"reviewer is the unit the parameter is about; the item bootstrap "
        r"resamples the wrong unit and is shown only for comparison. A "
        r"parametric bootstrap puts the estimator's bias at "
        rf"${float(multi['boot_parametric_bias']):+.3f}$ here, against at most "
        r"$0.012$ in every large design, which is what two degrees of freedom "
        r"costs. The published agreement rates located in the audited papers "
        r"place no usable restriction on $\sigma_r$: at the label prevalence "
        r"those papers imply, every value on a $0$--$1.2$ grid reproduces the "
        r"reported agreement for some item dispersion. Separating the two "
        r"components requires the item-by-annotator assignment, which none of "
        r"the nine audited papers reports.}",
        r"\label{tab:reviewer-heterogeneity-anchor}",
        r"\end{table}",
        "",
    ]
    write(TABLES / "reviewer_heterogeneity_anchor.tex", "\n".join(lines))


# ---------------------------------------------------------------------------
# Rule baselines
# ---------------------------------------------------------------------------


def build_rule_baseline_table() -> None:
    payload = json.loads(
        (SUPPLEMENT / "claim_rule_baselines.json").read_text(encoding="utf-8")
    )
    display = {
        "Three-field taxonomy": "Three-field taxonomy",
        "Evidence+controls (C2/C5 ablated)": "Ablation (no C2/C5)",
        "Five coordinates": "Five coordinates",
        "Five coordinates + controls": "Five coord.\\ + controls",
        "Random draw from adjudicated marginal": "Random (marginal)",
    }
    lines = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{2.5pt}",
        r"\begin{tabular}{@{}lrrl@{}}",
        r"\toprule",
        r"Estimator & Exact & $\kappa$ / $p$ & 95\% CI \\",
        r"\midrule",
    ]
    for entry in payload["estimators"]:
        interval = entry["ci95"]
        ci = "--" if interval is None else f"[{interval[0]:.3f}, {interval[1]:.3f}]"
        marker = "" if entry["kind"] == "rule" else r"$^{\dagger}$"
        lines.append(
            f"{escape(display.get(entry['label'], entry['label']))}{marker} & "
            f"{float(entry['exact_accuracy']):.3f} & "
            f"{float(entry['cohen_kappa']):.3f} & {ci} \\\\"
        )
    lines.append(r"\midrule")
    lines.append(r"\multicolumn{4}{@{}l}{\emph{Paired contrasts (source-clustered bootstrap)}} \\")
    short = {
        "Five coordinates + controls": "Full",
        "Five coordinates": "5-coord",
        "Evidence+controls (C2/C5 ablated)": "Ablation",
    }
    for contrast in payload["contrasts"]:
        interval = contrast["ci95"]
        right = contrast["right"]
        right_label = short.get(right, "Majority")
        lines.append(
            f"{short.get(contrast['left'], contrast['left'])} $-$ {right_label} & "
            f"{float(contrast['difference']):+.3f} & "
            f"{float(contrast['mcnemar_exact_p']):.2f} & "
            f"[{interval[0]:+.3f}, {interval[1]:+.3f}] \\\\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        rf"\caption{{Development diagnostic on {payload['items']} comparison claims, "
        r"with the trivial baselines ($\dagger$) the schema must beat. Intervals "
        r"are percentile bootstrap intervals clustered on the source paper. "
        r"No rule variant separates from the strongest trivial baseline "
        rf"({escape(payload['strongest_trivial_baseline']['label'])}, "
        rf"{float(payload['strongest_trivial_baseline']['exact_accuracy']):.3f}), "
        r"and adding the C2 and C5 coordinates to the ablation moves exact "
        r"agreement by an amount whose interval spans zero. The diagnostic "
        r"therefore supplies no evidence that the coordinates work as a "
        r"classifier, which is why the paper's substantive evidence rests on the "
        r"source-linked comparability cases instead.}",
        r"\label{tab:rule-baselines}",
        r"\end{table}",
        "",
    ]
    write(TABLES / "main_rule_baselines.tex", "\n".join(lines))


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def build_two_layer_figure() -> None:
    text = r"""\begin{figure}[t]
\centering
\resizebox{\columnwidth}{!}{%
\begin{tikzpicture}[
  font=\scriptsize,
  wide/.style={draw, rounded corners=2pt, align=center, inner sep=3pt,
               text width=6.9cm, fill=black!8},
  cell/.style={draw, rounded corners=2pt, align=center, inner sep=2.5pt,
               text width=1.85cm, minimum height=9mm, fill=white},
  arrow/.style={-{Stealth[length=4pt]}, thick}
]
\draw[dashed, rounded corners=3pt, black!45] (-0.15,-1.75) rectangle (7.75,0.95);
\draw[dashed, rounded corners=3pt, black!45] (-0.15,-5.15) rectangle (7.75,-2.45);
\node[anchor=north west, font=\scriptsize\bfseries, black!60]
  at (-0.10,0.90) {Substantive layer};
\node[anchor=north west, font=\scriptsize\bfseries, black!60]
  at (-0.10,-2.50) {Measurement layer};

\node[wide] (claim) at (3.8,0.30)
  {\textbf{Cross-paper claim:} ``$A$ is more robust than $B$.''};
\node[cell] (c1) at (1.15,-1.15) {C1 evidence state\\C2 capability};
\node[cell] (c3) at (3.80,-1.15) {C3 intervention\\C4 outcome unit};
\node[cell] (c5) at (6.45,-1.15) {C5 action set\\and loss};

\node[wide] (judge) at (3.8,-3.10)
  {\textbf{Claim-review study:} ``prompt $D$ improves review.''};
\node[cell] (m1) at (1.15,-4.55) {M1 item\\M2 reviewer};
\node[cell] (m3) at (3.80,-4.55) {M3 assignment\\M4 reference};
\node[cell] (m5) at (6.45,-4.55) {M5 downstream\\loss};

\draw[arrow] (3.8,-1.80) -- (3.8,-2.75);
\node[anchor=west, font=\tiny, text width=3.9cm, align=left]
  at (3.95,-2.28) {an unmatched coordinate makes the claim unanswerable};
\node[anchor=east, font=\tiny, text width=2.9cm, align=right]
  at (3.65,-2.28) {\S\ref{sec:cases}: 4 of 8 stated are undefined};
\end{tikzpicture}}
\caption{The two layers answer different questions about the same sentence.
The substantive layer asks whether two published results concern one decision
problem; Table~\ref{tab:cross-paper-cases} applies it to real comparisons. The
measurement layer asks what a study of claim review estimates;
Table~\ref{tab:retrospective-remedies} shows which analyses of such a study
are valid. Passing one layer cannot repair failure in the other.}
\label{fig:two-layer}
\end{figure}
"""
    write(FIGURES / "two_layer_audit.tex", text)


def build_calibration_figure() -> None:
    payload = json.loads(
        (SUPPLEMENT / "retrospective_remedy_simulation.json").read_text(encoding="utf-8")
    )
    series = {
        "panel_majority_source_se": ("Panel majority, source SE", "black", "solid"),
        "votes_source_se": ("Individual votes, source SE", "black!55", "dashed"),
        "reviewer_mean_t": ("Reviewer-level $t$", "black", "solid"),
        "reviewer_permutation": ("Reviewer randomization", "black!55", "dashed"),
    }
    sources = sorted({int(row["sources"]) for row in payload["rows"]})
    sigma = min(
        payload["sigma_r_grid"],
        key=lambda value: abs(
            value
            - float(
                json.loads(
                    (SUPPLEMENT / "reviewer_heterogeneity_anchor.json").read_text(
                        encoding="utf-8"
                    )
                )["direct_estimate"]["sigma_r_point"]
            )
        ),
    )
    points: dict[str, list[tuple[int, float]]] = {name: [] for name in series}
    for row in payload["rows"]:
        if (
            row["reviewer_abilities"] != "resampled"
            or float(row["sigma_r"]) != sigma
            or float(row["true_prompt_effect_logit"]) != 0.0
        ):
            continue
        for name in series:
            points[name].append((int(row["sources"]), 100.0 * float(row[name])))
    for name in points:
        points[name].sort()

    width, height = 0.86, 3.4
    max_y = 70.0

    def coordinates(values: Sequence[tuple[int, float]]) -> str:
        out = []
        for index, (source_count, value) in enumerate(values):
            x = width * index / max(1, len(values) - 1)
            y = height * min(value, max_y) / max_y
            out.append(f"({x:.3f}\\columnwidth,{y:.3f}cm)")
        return " -- ".join(out)

    body = [
        r"\begin{figure}[t]",
        r"\centering",
        r"\resizebox{\columnwidth}{!}{%",
        r"\begin{tikzpicture}[font=\scriptsize]",
        rf"\draw[->] (0,0) -- ({width + 0.03:.2f}\columnwidth,0) node[right, xshift=-2pt, yshift=-6pt] {{$G$}};",
        rf"\draw[->] (0,0) -- (0,{height + 0.35:.2f}cm);",
        rf"\node[rotate=90, anchor=south] at (-0.06\columnwidth,{height / 2:.2f}cm) {{rejection rate (\%)}};",
    ]
    for value in (0, 20, 40, 60):
        y = height * value / max_y
        body.append(
            rf"\draw[black!15] (0,{y:.3f}cm) -- ({width:.2f}\columnwidth,{y:.3f}cm);"
        )
        body.append(rf"\node[anchor=east] at (-0.005\columnwidth,{y:.3f}cm) {{{value}}};")
    y_alpha = height * 5.0 / max_y
    body.append(
        rf"\draw[black!45, densely dotted, thick] (0,{y_alpha:.3f}cm) -- ({width:.2f}\columnwidth,{y_alpha:.3f}cm);"
    )
    for index, source_count in enumerate(sources):
        x = width * index / max(1, len(sources) - 1)
        body.append(rf"\node[anchor=north] at ({x:.3f}\columnwidth,0) {{{source_count}}};")
    for name, (label, colour, style) in series.items():
        body.append(
            rf"\draw[{colour}, {style}, thick] {coordinates(points[name])};"
        )
        for index, (_source, value) in enumerate(points[name]):
            x = width * index / max(1, len(points[name]) - 1)
            y = height * min(value, max_y) / max_y
            marker = "*" if style == "solid" else "o"
            body.append(rf"\node[{colour}] at ({x:.3f}\columnwidth,{y:.3f}cm) {{$\{'bullet' if marker == '*' else 'circ'}$}};")
    labelled = points["panel_majority_source_se"][-1]
    body.append(
        rf"\node[anchor=east, font=\tiny] at ({width:.2f}\columnwidth,{height * min(labelled[1], max_y) / max_y + 0.28:.2f}cm) {{panel majority, source SE}};"
    )
    votes = points["votes_source_se"][-1]
    body.append(
        rf"\node[anchor=east, font=\tiny, black!55] at ({width:.2f}\columnwidth,{height * min(votes[1], max_y) / max_y + 0.28:.2f}cm) {{individual votes, source SE}};"
    )
    body.append(
        rf"\node[anchor=west, font=\tiny] at (0.02\columnwidth,{y_alpha + 0.26:.2f}cm) {{reviewer-level $t$ / randomization}};"
    )
    body += [
        r"\end{tikzpicture}}",
        rf"\caption{{Null rejection rate against the number of sources $G$ at the "
        rf"estimated reviewer heterogeneity $\sigma_r={sigma:.2f}$, with reviewer "
        r"abilities redrawn each replicate. Adding sources makes the two "
        r"source-level analyses steadily worse, and using individual votes "
        r"instead of majority labels does not help: the defect is the unit of "
        r"uncertainty, not the aggregation. The two reviewer-level analyses stay "
        r"at the nominal level and are executable from released pre-aggregation "
        r"votes. Table~\ref{tab:retrospective-remedies} gives the values and the "
        r"corresponding power.}",
        r"\label{fig:remedy-calibration}",
        r"\end{figure}",
        "",
    ]
    write(FIGURES / "remedy_calibration.tex", "\n".join(body))




SHORT_MODEL_NAMES = {
    "Qwen/Qwen2.5-7B-Instruct": "Qwen2.5-7B",
    "Qwen/Qwen2.5-14B-Instruct": "Qwen2.5-14B",
    "Qwen/Qwen2.5-32B-Instruct": "Qwen2.5-32B",
    "Qwen/Qwen3-8B": "Qwen3-8B",
    "Qwen/Qwen3-14B": "Qwen3-14B",
    "microsoft/Phi-4-mini-instruct": "Phi-4-mini",
    "microsoft/phi-4": "Phi-4",
    "allenai/OLMo-2-1124-7B-Instruct": "OLMo-2-7B",
    "allenai/OLMo-2-1124-13B-Instruct": "OLMo-2-13B",
    "ibm-granite/granite-3.1-8b-instruct": "Granite-3.1-8B",
    "tiiuae/Falcon3-7B-Instruct": "Falcon3-7B",
}


def build_model_judge_table() -> None:
    path = SUPPLEMENT / "controlled_model_judge_results_v2.json"
    if not path.exists():
        print("skipping model-judge table: results not available yet")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = {
        (record["model"], record["stratum"]): record for record in payload["records"]
    }
    models = payload["models"]
    gates = payload["validity_gate"]

    def contrast(model: str, stratum: str) -> str:
        record = records.get((model, stratum))
        if record is None:
            return "--"
        estimate = 100.0 * float(record["full_minus_placebo_estimate"])
        low = 100.0 * float(record["full_minus_placebo_ci_low"])
        high = 100.0 * float(record["full_minus_placebo_ci_high"])
        return f"{estimate:+.1f} [{low:+.1f}, {high:+.1f}]"

    lines = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{1.8pt}",
        r"\begin{tabular}{@{}lrrll@{}}",
        r"\toprule",
        r"Model & Probe & Gate & C2 $\Delta$ [95\% CI] & C5 $\Delta$ [95\% CI] \\",
        r"\midrule",
    ]
    for model in models:
        status = gates[model]
        probe = 100.0 * max(
            float(status["probe_accuracy_ablated"]), float(status["probe_accuracy_full"])
        )
        passes = "yes" if status["passes_validity_gate"] else "no"
        lines.append(
            " & ".join(
                (
                    escape(SHORT_MODEL_NAMES.get(model, model)),
                    f"{probe:.0f}",
                    passes,
                    contrast(model, "c2_capability"),
                    contrast(model, "c5_utility"),
                )
            )
            + r" \\"
        )
    meta = payload["random_effects_meta_analysis"]
    lines.append(r"\midrule")
    row = ["Pooled (gate-passing)", "", ""]
    for stratum in ("c2_capability", "c5_utility"):
        entry = meta.get(stratum)
        if entry is None:
            row.append("--")
            continue
        row.append(
            f"{100.0 * float(entry['pooled_estimate']):+.1f} "
            f"[{100.0 * float(entry['ci_low']):+.1f}, "
            f"{100.0 * float(entry['ci_high']):+.1f}]"
        )
    lines.append(" & ".join(row) + r" \\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Controlled consequence test, version 2. Each model answers "
        r"600 items under three arms crossed with four paraphrases (7{,}200 "
        r"greedy decisions per model). \emph{Probe} is percentage accuracy on "
        r"the displayed-loss competence stratum, and \emph{Gate} records the "
        r"pre-declared validity rule (probe $\ge 50\%$ in one arm and no single "
        r"action on more than 90\% of items). $\Delta$ is the primary contrast, "
        r"\emph{full} minus the length-matched \emph{placebo} arm, in percentage "
        r"points, with a percentile bootstrap interval clustered on the 300 "
        r"counterfactual pairs. The pooled row is a DerSimonian--Laird "
        r"random-effects combination over gate-passing models, so it refers to a "
        r"model population rather than to any checkpoint. Appendix "
        r"Table~\ref{tab:controlled-model-judges-strata-v2} adds the "
        r"\emph{full} minus \emph{ablated} contrast, per-paraphrase spread, "
        r"mean regret, and Holm-adjusted values.}",
        r"\label{tab:controlled-model-judges-v2}",
        r"\end{table}",
        "",
    ]
    write(TABLES / "main_controlled_model_judges_v2.tex", "\n".join(lines))


def build_model_judge_appendix() -> None:
    path = SUPPLEMENT / "controlled_model_judge_results_v2.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{@{}llrrrrrrrr@{}}",
        r"\toprule",
        r"Model & Stratum & Abl. & Plac. & Full & F$-$P & F$-$A & Para.\ SD & McNemar $p$ & Holm $p$ \\",
        r"\midrule",
    ]
    for record in payload["records"]:
        holm = record.get("full_minus_placebo_holm_p", "")
        holm_text = f"{float(holm):.3f}" if holm not in ("", None) else "--"
        lines.append(
            " & ".join(
                (
                    escape(SHORT_MODEL_NAMES.get(record["model"], record["model"])),
                    escape(str(record["stratum"]).replace("_", " ")),
                    f"{100.0 * float(record['ablated_accuracy']):.1f}",
                    f"{100.0 * float(record['placebo_accuracy']):.1f}",
                    f"{100.0 * float(record['full_accuracy']):.1f}",
                    f"{100.0 * float(record['full_minus_placebo_estimate']):+.1f}",
                    f"{100.0 * float(record['full_minus_ablated_estimate']):+.1f}",
                    f"{100.0 * float(record['full_minus_placebo_paraphrase_sd']):.1f}",
                    f"{float(record['full_minus_placebo_mcnemar_exact_p']):.3f}",
                    holm_text,
                )
            )
            + r" \\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Per-model, per-stratum results for the version-2 controlled "
        r"experiment. Accuracies are percentages averaged over four paraphrases; "
        r"F$-$P and F$-$A are the full-minus-placebo and full-minus-ablated "
        r"contrasts in percentage points; \emph{Para.\ SD} is the standard "
        r"deviation of the full-minus-placebo contrast across paraphrases. "
        r"McNemar tests use per-item paraphrase-majority decisions. Holm "
        r"adjustment covers gate-passing models on the two substantive strata.}",
        r"\label{tab:controlled-model-judges-strata-v2}",
        r"\end{table*}",
        "",
    ]
    write(TABLES / "controlled_model_judges_strata_v2.tex", "\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip", nargs="*", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    builders = {
        "cases": build_cross_paper_tables,
        "remedies": build_remedy_tables,
        "anchor": build_anchor_table,
        "baselines": build_rule_baseline_table,
        "figure-two-layer": build_two_layer_figure,
        "figure-calibration": build_calibration_figure,
        "model-judges": build_model_judge_table,
        "model-judges-appendix": build_model_judge_appendix,
    }
    for name, builder in builders.items():
        if name in args.skip:
            continue
        builder()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
