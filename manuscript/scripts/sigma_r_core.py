"""Shared estimator and bootstrap machinery for sigma_r estimation.

This module provides ONE code-path for all seven crossed designs so that the
reported uncertainty is computed identically everywhere.

Estimand: sigma_r = SD of reviewer ability on the logit scale.

Three bootstrap procedures are implemented:
  1. **Reviewer bootstrap** (primary headline interval): resample reviewers
     with replacement, recompute the moment estimator.  This is the correct
     resampling unit because sigma_r IS a between-reviewer parameter.
  2. **Parametric bootstrap**: simulate reviewer abilities from the fitted
     N(mu_hat, sigma_hat^2) on the logit scale, draw Binomial outcomes with
     observed per-reviewer item counts, re-estimate.  Quantifies finite-sample
     bias of the moment estimator.
  3. **Item bootstrap** (supplementary only): resample items with replacement.
     This inflates within-reviewer variance (by duplicating items), biasing
     sigma_hat upward; retained for continuity but not reported as the headline.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


# ─────────────────────── moment estimator ───────────────────────


def moment_sigma_from_sufficient(
    correct_sum: np.ndarray, counts: np.ndarray
) -> tuple[float, float]:
    """Compute the moment estimator from per-reviewer sufficient statistics.

    Returns (sigma_r, mu_logit) where mu_logit is the mean logit accuracy.
    """
    keep = counts > 0
    if keep.sum() < 2:
        return 0.0, 0.0
    n = counts[keep].astype(float)
    a = correct_sum[keep].astype(float) / n
    a = np.clip(a, 0.5 / n, 1.0 - 0.5 / n)
    logits = np.log(a / (1.0 - a))
    observed = float(np.var(logits, ddof=1))
    sampling = float(np.mean(1.0 / (n * a * (1.0 - a))))
    sigma = math.sqrt(max(0.0, observed - sampling))
    mu = float(logits.mean())
    return sigma, mu


def moment_sigma_from_lists(
    correct: Sequence[Sequence[int]],
) -> tuple[float, float, list[float], list[int]]:
    """Compute from list-of-lists (dense designs).

    Returns (sigma_r, mu_logit, accuracies, counts).
    """
    accuracies, cnts = [], []
    for row in correct:
        n = len(row)
        if n == 0:
            continue
        a = sum(row) / n
        accuracies.append(min(max(a, 0.5 / n), 1.0 - 0.5 / n))
        cnts.append(n)
    k = len(accuracies)
    if k < 2:
        return 0.0, 0.0, accuracies, cnts
    logits = [math.log(a / (1.0 - a)) for a in accuracies]
    observed = float(np.var(logits, ddof=1))
    sampling = float(
        np.mean([1.0 / (n * a * (1.0 - a)) for a, n in zip(accuracies, cnts)])
    )
    sigma = math.sqrt(max(0.0, observed - sampling))
    mu = float(np.mean(logits))
    return sigma, mu, accuracies, cnts


# ─────────────────────── reviewer bootstrap ───────────────────────


def reviewer_bootstrap_vectorised(
    correct_sum: np.ndarray,
    counts: np.ndarray,
    draws: int,
    seed: int,
) -> np.ndarray:
    """Reviewer bootstrap using per-reviewer sufficient statistics (vectorised).

    Resamples reviewer indices with replacement, keeping each reviewer's
    (correct_sum, counts) pair intact.  Very fast even for large corpora.
    """
    keep = counts > 0
    cs = correct_sum[keep]
    ct = counts[keep]
    k = cs.size
    if k < 2:
        return np.zeros(draws)
    rng = np.random.default_rng(seed)
    boot = np.empty(draws)
    for d in range(draws):
        idx = rng.integers(0, k, size=k)
        boot[d] = moment_sigma_from_sufficient(cs[idx], ct[idx])[0]
    return boot


def reviewer_bootstrap_dense(
    correct: list[list[int]],
    draws: int,
    seed: int,
) -> np.ndarray:
    """Reviewer bootstrap for dense (list-of-lists) designs."""
    k = len(correct)
    if k < 2:
        return np.zeros(draws)
    rng = np.random.default_rng(seed)
    boot = np.empty(draws)
    for d in range(draws):
        idx = rng.integers(0, k, size=k)
        picked = [correct[i] for i in idx]
        boot[d] = moment_sigma_from_lists(picked)[0]
    return boot


# ─────────────────────── parametric bootstrap ───────────────────────


def parametric_bootstrap(
    sigma_r: float,
    mu_logit: float,
    counts: np.ndarray,
    draws: int,
    seed: int,
    sigma_item: float = 0.0,
    n_items_per_reviewer: np.ndarray | None = None,
) -> np.ndarray:
    """Parametric bootstrap: simulate from fitted two-way logit model.

    For each replicate:
      - Draw reviewer abilities u_j ~ N(0, sigma_r)
      - Each reviewer j gets Binomial(n_j, logistic(mu + u_j)) correct
      - Re-estimate sigma_r with the moment estimator

    If sigma_item > 0 and n_items_per_reviewer is given, adds item random
    effects: for each reviewer, draws n_j item effects, computes per-item
    probabilities, and sums Bernoulli outcomes.
    """
    keep = counts > 0
    n = counts[keep].astype(np.int64)
    k = n.size
    if k < 2:
        return np.zeros(draws)
    rng = np.random.default_rng(seed)
    boot = np.empty(draws)

    if sigma_item > 0.0 and n_items_per_reviewer is not None:
        ni = n_items_per_reviewer[keep].astype(np.int64)
        for d in range(draws):
            u = rng.normal(0.0, sigma_r, size=k)
            cs = np.empty(k)
            for j in range(k):
                v = rng.normal(0.0, sigma_item, size=int(ni[j]))
                p = 1.0 / (1.0 + np.exp(-(mu_logit + u[j] + v)))
                cs[j] = float(rng.binomial(1, p).sum())
            boot[d] = moment_sigma_from_sufficient(cs, ni.astype(float))[0]
    else:
        for d in range(draws):
            u = rng.normal(0.0, max(sigma_r, 1e-8), size=k)
            p = 1.0 / (1.0 + np.exp(-(mu_logit + u)))
            cs = rng.binomial(n, p).astype(float)
            boot[d] = moment_sigma_from_sufficient(cs, n.astype(float))[0]
    return boot


# ─────────────────────── item bootstrap (vectorised) ───────────────────────


def item_bootstrap_vectorised(
    r: np.ndarray,
    i: np.ndarray,
    c: np.ndarray,
    n_reviewers_kept: int,
    n_items: int,
    draws: int,
    seed: int,
) -> np.ndarray:
    """Item bootstrap: resample item indices, recompute per-reviewer sums.

    This is the EXISTING approach, retained for supplementary reporting.
    NOTE: inflates within-reviewer variance → upward bias on sigma_r.
    """
    order = np.argsort(i, kind="stable")
    r_s, i_s, c_s = r[order], i[order], c[order]
    boundaries = np.searchsorted(i_s, np.arange(n_items + 1))
    present_items = np.unique(i_s)
    rng = np.random.default_rng(seed)
    boot = np.empty(draws)
    k = n_reviewers_kept
    for d in range(draws):
        picked = rng.choice(present_items, size=present_items.size, replace=True)
        segs_r, segs_c = [], []
        for item in picked:
            lo, hi = boundaries[item], boundaries[item + 1]
            if hi > lo:
                segs_r.append(r_s[lo:hi])
                segs_c.append(c_s[lo:hi])
        rr = np.concatenate(segs_r)
        cc = np.concatenate(segs_c)
        boot[d] = moment_sigma_from_sufficient(
            np.bincount(rr, weights=cc, minlength=k),
            np.bincount(rr, minlength=k),
        )[0]
    return boot


# ─────────────────────── interval helpers ───────────────────────


def percentile_interval(values: np.ndarray, alpha: float = 0.05) -> list[float]:
    """Percentile bootstrap CI: [q_{alpha/2}, q_{1-alpha/2}]."""
    lo = float(np.quantile(values, alpha / 2))
    hi = float(np.quantile(values, 1.0 - alpha / 2))
    return [lo, hi]


def summarise_bootstrap(
    boot: np.ndarray, point: float, label: str
) -> dict[str, object]:
    """Standard summary dict for any bootstrap distribution."""
    ci = percentile_interval(boot)
    return {
        f"boot_{label}_ci95": ci,
        f"boot_{label}_mean": float(boot.mean()),
        f"boot_{label}_bias": float(boot.mean() - point),
        f"boot_{label}_draws": int(boot.size),
    }
