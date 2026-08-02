#!/usr/bin/env python3
"""Generalization re-analysis of the controlled model-judge experiment.

This script answers, from the released per-model contrasts, four questions that
a mean-effect meta-analysis does not answer and that a reviewer of the previous
version raised directly:

1.  **Prediction interval.**  If the reported effect is claimed to refer to a
    *model population*, the relevant summary is the random-effects prediction
    interval for a newly drawn model, not the confidence interval for the mean.
    We report the Higgins--Thompson--Spiegelhalter interval,
    ``mu +/- t_{k-2} * sqrt(tau^2 + se_mu^2)``.

2.  **Developer stratification.**  Checkpoints are nested in developers, and a
    pooled estimate over checkpoints treats sibling checkpoints as independent
    draws.  We report (a) leave-one-developer-out pooled estimates, (b) a
    developer-level meta-analysis that first averages within developer, and
    (c) the pooled estimate with the largest developer family removed.

3.  **Equivalence on the negative control.**  A pooled null is not evidence of
    absence.  We report a two-one-sided-test (TOST) equivalence result on the
    competence probe against a pre-declared margin, and we report how many
    individual models show a probe effect whose interval excludes zero, so that
    a pooled null produced by cancellation is visible rather than hidden.

4.  **Paraphrase stability.**  We summarise the distribution of paraphrase sign
    agreement, which measures whether the direction of the effect is stable
    under rewording.

Inputs are the per-model contrast CSV written by
``analyze_controlled_model_judges_v2.py`` (and, when present, the v3 CSV that
adds API-served and additional open checkpoints).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Sequence

REPO = Path(__file__).resolve().parents[2]
STRATA = ("probe_competence", "c2_capability", "c5_utility")

# Pre-declared equivalence margin for the competence-probe negative control.
# It is the smallest pooled effect the paper would treat as substantively
# interesting on a substantive stratum, expressed on the accuracy scale.
TOST_MARGIN = 0.02

DEVELOPER_OF = {
    "qwen": "Alibaba",
    "allenai": "AI2",
    "ibm-granite": "IBM",
    "microsoft": "Microsoft",
    "tiiuae": "TII",
    "nousresearch": "Meta",
    "meta-llama": "Meta",
    "unsloth/llama": "Meta",
    "unsloth/gemma": "Google",
    "google": "Google",
    "unsloth/mistral": "Mistral",
    "mistralai": "Mistral",
    "01-ai": "01.AI",
    "thudm": "Zhipu",
    "zai-org": "Zhipu",
    "internlm": "ShanghaiAILab",
    "huggingfaceh4": "HuggingFace",
    "huggingfacetb": "HuggingFace",
    "upstage": "Upstage",
    "nvidia": "NVIDIA",
    "coherelabs": "Cohere",
    "cohereforai": "Cohere",
    "stabilityai": "Stability",
    "deepseek-ai": "DeepSeek",
    "mosaicml": "Databricks",
    "gpt-": "OpenAI",
    "claude": "Anthropic",
    "gemini": "Google",
}


def developer(model: str) -> str:
    lowered = model.lower()
    for key, value in DEVELOPER_OF.items():
        if lowered.startswith(key) or ("/" in key and key in lowered):
            return value
    return lowered.split("/")[0]


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def student_t_quantile(p: float, df: float) -> float:
    """Two-sided-friendly inverse Student-t by bisection on the CDF."""
    if df <= 0:
        raise ValueError("df must be positive")
    lo, hi = -60.0, 60.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if student_t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def student_t_cdf(t: float, df: float) -> float:
    x = df / (df + t * t)
    ib = _incomplete_beta(0.5 * df, 0.5, x)
    return 1.0 - 0.5 * ib if t > 0 else 0.5 * ib


def _incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1.0 - x) * b - lbeta) / a
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 300):
        m = i // 2
        if i == 0:
            numerator = 1.0
        elif i % 2 == 0:
            numerator = (m * (b - m) * x) / ((a + 2.0 * m - 1.0) * (a + 2.0 * m))
        else:
            numerator = -((a + m) * (a + b + m) * x) / ((a + 2.0 * m) * (a + 2.0 * m + 1.0))
        d = 1.0 + numerator * d
        d = 1e-30 if abs(d) < 1e-30 else d
        d = 1.0 / d
        c = 1.0 + numerator / c
        c = 1e-30 if abs(c) < 1e-30 else c
        f *= c * d
        if abs(1.0 - c * d) < 1e-12:
            break
    result = front * (f - 1.0)
    if x < (a + 1.0) / (a + b + 2.0):
        return result
    return 1.0 - _incomplete_beta(b, a, 1.0 - x)


def dersimonian_laird(
    estimates: Sequence[float], ses: Sequence[float]
) -> dict[str, float]:
    """DerSimonian--Laird random-effects pooling with a prediction interval."""
    k = len(estimates)
    if k == 0:
        return {}
    weights = [1.0 / (se**2) if se > 0 else 0.0 for se in ses]
    if sum(weights) == 0:
        return {}
    fixed_mean = sum(w * e for w, e in zip(weights, estimates)) / sum(weights)
    q = sum(w * (e - fixed_mean) ** 2 for w, e in zip(weights, estimates))
    if k > 1:
        c = sum(weights) - sum(w * w for w in weights) / sum(weights)
        tau2 = max(0.0, (q - (k - 1)) / c) if c > 0 else 0.0
    else:
        tau2 = 0.0
    re_weights = [1.0 / (se**2 + tau2) if (se**2 + tau2) > 0 else 0.0 for se in ses]
    mu = sum(w * e for w, e in zip(re_weights, estimates)) / sum(re_weights)
    se_mu = math.sqrt(1.0 / sum(re_weights))
    z = mu / se_mu if se_mu > 0 else 0.0
    p = 2.0 * (1.0 - normal_cdf(abs(z)))
    i2 = max(0.0, (q - (k - 1)) / q) if q > 0 else 0.0
    out = {
        "k": k,
        "pooled_estimate": mu,
        "pooled_se": se_mu,
        "ci_low": mu - 1.959963985 * se_mu,
        "ci_high": mu + 1.959963985 * se_mu,
        "z": z,
        "p": p,
        "q": q,
        "tau2": tau2,
        "tau": math.sqrt(tau2),
        "i2": i2,
    }
    # Higgins-Thompson-Spiegelhalter prediction interval, t on k-2 df.
    if k >= 3:
        crit = student_t_quantile(0.975, k - 2)
        half = crit * math.sqrt(tau2 + se_mu**2)
        out["pi_low"] = mu - half
        out["pi_high"] = mu + half
        out["pi_df"] = k - 2
        out["pi_t"] = crit
        out["pi_excludes_zero"] = bool(out["pi_low"] > 0 or out["pi_high"] < 0)
    return out


def tost(mu: float, se: float, margin: float) -> dict[str, float]:
    """Two one-sided tests for equivalence to zero within +/- margin."""
    if se <= 0:
        return {"p_tost": float("nan")}
    z_lower = (mu + margin) / se
    z_upper = (margin - mu) / se
    p_lower = 1.0 - normal_cdf(z_lower)
    p_upper = 1.0 - normal_cdf(z_upper)
    p = max(p_lower, p_upper)
    return {
        "margin": margin,
        "p_tost": p,
        "equivalent_at_05": bool(p < 0.05),
        "ci90_low": mu - 1.6448536 * se,
        "ci90_high": mu + 1.6448536 * se,
    }


def load_rows(paths: Sequence[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        for row in csv.DictReader(path.open()):
            key = (row["model"], row["stratum"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def analyse(rows: list[dict[str, str]], contrast: str) -> dict[str, object]:
    est_key = f"{contrast}_estimate"
    se_key = f"{contrast}_bootstrap_se"
    sign_key = f"{contrast}_paraphrase_sign_agreement"

    by_stratum: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["stratum"] not in STRATA:
            continue
        if str(row["passes_validity_gate"]).lower() != "true":
            continue
        if not row.get(est_key) or not row.get(se_key):
            continue
        se = float(row[se_key])
        if se <= 0:
            # A degenerate bootstrap SE carries no information about a model
            # population; keep the record but floor the SE at the smallest
            # positive value observed so the model is not given infinite weight.
            se = 0.0
        by_stratum[row["stratum"]].append(
            {
                "model": row["model"],
                "developer": developer(row["model"]),
                "serving": row.get("serving", "local_checkpoint") or "local_checkpoint",
                "estimate": float(row[est_key]),
                "se": se,
                "ci_low": float(row.get(f"{contrast}_ci_low") or "nan"),
                "ci_high": float(row.get(f"{contrast}_ci_high") or "nan"),
                "paraphrase_sign_agreement": float(row.get(sign_key) or "nan"),
            }
        )

    result: dict[str, object] = {"contrast": contrast, "strata": {}}
    for stratum, records in sorted(by_stratum.items()):
        positive_ses = [r["se"] for r in records if r["se"] > 0]
        floor = min(positive_ses) if positive_ses else 1e-4
        for r in records:
            if r["se"] <= 0:
                r["se"] = floor
                r["se_floored"] = True

        estimates = [r["estimate"] for r in records]
        ses = [r["se"] for r in records]
        pooled = dersimonian_laird(estimates, ses)

        # (a) leave-one-developer-out
        developers = sorted({str(r["developer"]) for r in records})
        loo = {}
        for dev in developers:
            kept = [r for r in records if r["developer"] != dev]
            if len(kept) >= 2:
                loo[dev] = dersimonian_laird(
                    [r["estimate"] for r in kept], [r["se"] for r in kept]
                )

        # (b) developer-level meta-analysis: average within developer first
        dev_records = []
        for dev in developers:
            group = [r for r in records if r["developer"] == dev]
            n = len(group)
            mean = sum(r["estimate"] for r in group) / n
            # SE of a simple mean of correlated-at-most siblings: combine the
            # within-model sampling variance with the between-sibling spread.
            within = sum(r["se"] ** 2 for r in group) / (n**2)
            if n > 1:
                spread = sum((r["estimate"] - mean) ** 2 for r in group) / (n * (n - 1))
            else:
                spread = 0.0
            dev_records.append(
                {
                    "developer": dev,
                    "n_checkpoints": n,
                    "estimate": mean,
                    "se": math.sqrt(within + spread),
                }
            )
        dev_pooled = dersimonian_laird(
            [r["estimate"] for r in dev_records],
            [max(r["se"], 1e-6) for r in dev_records],
        )

        # (c) individual models whose interval excludes zero, by sign
        pos = [
            r["model"] for r in records if r["ci_low"] == r["ci_low"] and r["ci_low"] > 0
        ]
        neg = [
            r["model"]
            for r in records
            if r["ci_high"] == r["ci_high"] and r["ci_high"] < 0
        ]

        entry: dict[str, object] = {
            "n_models": len(records),
            "n_developers": len(developers),
            "developers": developers,
            "pooled": pooled,
            "leave_one_developer_out": loo,
            "developer_level_pooled": dev_pooled,
            "developer_records": dev_records,
            "models_ci_excludes_zero_positive": sorted(pos),
            "models_ci_excludes_zero_negative": sorted(neg),
            "per_model": sorted(records, key=lambda r: -float(r["estimate"])),
        }
        sign_values = [
            r["paraphrase_sign_agreement"]
            for r in records
            if r["paraphrase_sign_agreement"] == r["paraphrase_sign_agreement"]
        ]
        if sign_values:
            ordered = sorted(sign_values)
            entry["paraphrase_sign_agreement"] = {
                "min": ordered[0],
                "median": ordered[len(ordered) // 2],
                "max": ordered[-1],
                "share_at_or_below_half": sum(v <= 0.5 for v in ordered) / len(ordered),
                "share_at_one": sum(v >= 1.0 for v in ordered) / len(ordered),
            }
        if stratum == "probe_competence" and pooled:
            entry["equivalence_tost"] = tost(
                float(pooled["pooled_estimate"]), float(pooled["pooled_se"]), TOST_MARGIN
            )
        result["strata"][stratum] = entry
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        nargs="+",
        default=[
            REPO / "manuscript" / "supplement" / "controlled_model_judge_results_v3.csv",
            REPO / "manuscript" / "supplement" / "controlled_model_judge_results_v2.csv",
        ],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO
        / "manuscript"
        / "supplement"
        / "controlled_model_judge_generalization.json",
    )
    args = parser.parse_args()

    rows = load_rows(args.results)
    if not rows:
        raise SystemExit("no per-model contrast rows found")

    payload = {
        "schema_version": "controlled-model-judge-generalization-v1",
        "sources": [str(p) for p in args.results if p.exists()],
        "tost_margin": TOST_MARGIN,
        "prediction_interval": "Higgins-Thompson-Spiegelhalter, t_{k-2}",
        "contrasts": {
            name: analyse(rows, name)
            for name in ("full_minus_placebo", "full_minus_ablated")
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    primary = payload["contrasts"]["full_minus_placebo"]["strata"]
    for stratum in STRATA:
        if stratum not in primary:
            continue
        entry = primary[stratum]
        pooled = entry["pooled"]
        print(f"== {stratum} (k={pooled.get('k')}, developers={entry['n_developers']})")
        print(
            f"   pooled {pooled['pooled_estimate']*100:+.2f} pp  "
            f"CI [{pooled['ci_low']*100:+.2f}, {pooled['ci_high']*100:+.2f}]  "
            f"I2={pooled['i2']*100:.1f}%  tau={pooled['tau']*100:.2f} pp"
        )
        if "pi_low" in pooled:
            print(
                f"   prediction interval [{pooled['pi_low']*100:+.2f}, "
                f"{pooled['pi_high']*100:+.2f}] pp  "
                f"excludes zero: {pooled['pi_excludes_zero']}"
            )
        dev = entry["developer_level_pooled"]
        if dev:
            print(
                f"   developer-level pooled {dev['pooled_estimate']*100:+.2f} pp "
                f"CI [{dev['ci_low']*100:+.2f}, {dev['ci_high']*100:+.2f}] (k={dev['k']})"
            )
        for name, value in sorted(entry["leave_one_developer_out"].items()):
            print(
                f"   leave-out {name:<14} pooled {value['pooled_estimate']*100:+.2f} pp "
                f"CI [{value['ci_low']*100:+.2f}, {value['ci_high']*100:+.2f}]"
            )
        print(
            f"   models CI>0: {len(entry['models_ci_excludes_zero_positive'])}, "
            f"CI<0: {len(entry['models_ci_excludes_zero_negative'])}"
        )
        if "equivalence_tost" in entry:
            t = entry["equivalence_tost"]
            print(
                f"   TOST margin +/-{t['margin']*100:.1f} pp: p={t['p_tost']:.4f}, "
                f"equivalent={t['equivalent_at_05']}"
            )
        print()
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
