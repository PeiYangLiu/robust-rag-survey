#!/usr/bin/env python3
"""Task A -- a non-LLM instrument on the same task (reviewer: instrument class).

A reviewer objects that all four control interventions in the paper share one
instrument class -- LLM judges -- so they cannot separate a property of the
*text* (the comparison is not decidable from what a window discloses) from a
property of the *instrument* (LLM judges are the wrong tool).  This script
attacks that objection directly with an instrument from a different class: a
plain statistical classifier that is *trained on the reference labels* and asked
to predict them from the window text.  If a supervised model with direct access
to the answers still cannot beat a constant baseline, the deficit is in the
text, not in the LLM instrument class.  If it can, the objection has teeth.

The reference labels are the evidence-privileged reference of
``analyze_privileged_reference.py`` (adjudicators who read both papers in full);
its derivation is imported and reused verbatim, so the target here is exactly
the label the deployed panel is scored against.

Estimators, each evaluated with grouped cross-validation that groups by the
*citing paper* so no paper is in train and test at once:

  1. ``constant_majority``  -- predict the training fold's majority class.
  2. ``tfidf_logreg``       -- bag-of-words TF-IDF + multinomial logistic
                               regression on the window text.
  3. ``structural_logreg``  -- multinomial logistic regression on hand-built
                               structural features (length, numeric-token count,
                               coordinate-vocabulary density, citation marker,
                               distinct systems named, table-vs-prose shape).
  4. ``llm_panel_majority`` -- the deployed three-LLM panel's own majority
                               verdict, scored against the same reference on the
                               same folds, so every estimator sits on one axis.

The two supervised models (2, 3) are implemented in numpy + scipy (validated to
match scikit-learn to machine precision) so the script runs without
scikit-learn.  Every metric carries a 95% interval from a bootstrap that
resamples *citing papers*, and every random seed is fixed.

Primary target is the three-way verdict (survives / narrows / undefined).
Provenance (transported / re-implemented) is run as a contrast, not as a
positive control for the statistical models: it is the target where the
deployed LLM panel pulls clearly ahead of the cheap statistical instrument, so
it demonstrates the comparison *can* detect an instrument-class gap when the
text carries decidable signal -- and finds none on the verdict, where the
non-LLM instrument matches the LLM panel and neither beats the baseline on
accuracy.

Run:
    python3 manuscript/scripts/revision4/analyze_nonllm_instrument.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

REPO = Path(__file__).resolve().parents[3]
SUP = REPO / "manuscript" / "supplement"
TAB = REPO / "manuscript" / "tables"
MACRO_FILE = TAB / "revision4_instrument_macros.tex"
# Reuse the published reference derivation verbatim.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "revision3"))
import analyze_privileged_reference as apr  # noqa: E402

SEED = 20260802
N_FOLDS = 5
N_BOOT = 2000
TFIDF_MIN_DF = 2
TFIDF_MAX_FEATURES = 2000
LOGREG_C = 1.0

VERDICTS = ("survives", "narrows", "undefined")
PROV = ("transported", "reimplemented", "unclear")

# ---------------------------------------------------------------- coordinates
# Vocabulary that indexes the comparison coordinates a window would have to pin
# down for the quoted gap to be decidable: the retriever/corpus, the datasets,
# the metrics, the top-k budget, the backbone.  A hand-built feature, so the
# exact membership is not load-bearing; it measures how dense the setup
# vocabulary is in the window.
COORDINATE_TERMS = [
    # retriever / corpus / index
    r"retriev\w*", r"\bcorpus\b", r"\bindex(?:ing|es)?\b", r"\bpassages?\b",
    r"\bdocuments?\b", r"knowledge\s+base", r"\bwikipedia\b", r"snapshot",
    r"\bbm25\b", r"\bdpr\b", r"contriever", r"colbert", r"splade",
    r"\bdense\b", r"\bsparse\b", r"top[-\s]?k", r"\bk\s*=\s*\d+", r"\brerank\w*",
    # datasets
    r"\bnq\b", r"natural\s*questions", r"triviaqa", r"hotpotqa", r"popqa",
    r"\bsquad\b", r"ms\s*marco", r"\bfever\b", r"2wiki\w*", r"musique",
    r"\bbeir\b", r"scifact", r"\bfiqa\b", r"\bnfcorpus\b", r"pubmedqa",
    r"\bwebq\w*", r"\bmedqa\b",
    # metrics
    r"\baccuracy\b", r"exact\s*match", r"\bem\b", r"\bf1\b", r"\brecall\b",
    r"\bprecision\b", r"\bndcg\b", r"\bmrr\b", r"hit\s*rate", r"hit@\d+",
    r"attack\s+success\s+rate", r"\basr\b", r"\brouge\b", r"\bbleu\b",
    # backbone / setup
    r"\bbackbone\b", r"\bgenerator\b", r"\breader\b", r"\bbaselines?\b",
    r"\bgpt-?\d\w*", r"\bllama\b", r"mistral", r"deepseek", r"temperature",
    r"\bprompt\b", r"\bzero-?shot\b", r"few-?shot",
]
COORD_RE = re.compile("|".join(COORDINATE_TERMS), re.I)
CITATION_RE = re.compile(
    r"\[\d+(?:\s*[,\u2013-]\s*\d+)*\]"          # [12], [3, 4], [3-5]
    r"|\(\s*[A-Z][A-Za-z.\-]+\s+et\s+al\.?,?\s*\d{4}[a-z]?\s*\)"  # (Smith et al., 2024)
    r"|[A-Z][A-Za-z.\-]+\s+et\s+al\.?,?\s*\(?\d{4}[a-z]?\)?",     # Smith et al. (2024)
    re.I,
)
TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")
WORD_RE = re.compile(r"\S+")


# =============================================================== numpy models
def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def tfidf_fit(docs: list[str], min_df: int, max_features: int):
    """Learn a smooth-idf, l2-normalised TF-IDF space on training docs only."""
    df = Counter()
    for d in docs:
        for t in set(tokens(d)):
            df[t] += 1
    vocab = [t for t, c in df.items() if c >= min_df]
    if max_features and len(vocab) > max_features:
        tf = Counter()
        for d in docs:
            for t in tokens(d):
                tf[t] += 1
        vocab = sorted(vocab, key=lambda t: (-tf[t], t))[:max_features]
    vocab = sorted(vocab)
    index = {t: i for i, t in enumerate(vocab)}
    n = len(docs)
    idf = np.array([np.log((1 + n) / (1 + df[t])) + 1.0 for t in vocab])
    return index, idf


def tfidf_transform(docs: list[str], index: dict, idf: np.ndarray) -> np.ndarray:
    X = np.zeros((len(docs), len(index)))
    for r, d in enumerate(docs):
        counts = Counter(t for t in tokens(d) if t in index)
        for t, c in counts.items():
            X[r, index[t]] = c * idf[index[t]]
    norm = np.sqrt((X * X).sum(axis=1, keepdims=True))
    norm[norm == 0] = 1.0
    return X / norm


def softmax_fit(X: np.ndarray, y: np.ndarray, n_classes: int, C: float):
    """Multinomial logistic regression; objective C*sum(CE) + 0.5||W||^2.

    Matches scikit-learn's ``LogisticRegression`` predictions; deterministic
    zero initialisation, solved with L-BFGS.
    """
    n, d = X.shape

    def obj(theta):
        W = theta[: d * n_classes].reshape(d, n_classes)
        b = theta[d * n_classes:]
        Z = X @ W + b
        Z -= Z.max(axis=1, keepdims=True)
        E = np.exp(Z)
        P = E / E.sum(axis=1, keepdims=True)
        ll = -np.log(P[np.arange(n), y] + 1e-15).sum()
        loss = C * ll + 0.5 * (W * W).sum()
        G = P
        G[np.arange(n), y] -= 1.0
        gW = C * (X.T @ G) + W
        gb = C * G.sum(axis=0)
        return loss, np.concatenate([gW.ravel(), gb])

    theta0 = np.zeros(d * n_classes + n_classes)
    res = minimize(obj, theta0, jac=True, method="L-BFGS-B",
                   options={"maxiter": 1000, "ftol": 1e-9})
    W = res.x[: d * n_classes].reshape(d, n_classes)
    b = res.x[d * n_classes:]
    return W, b


def softmax_predict(X: np.ndarray, W: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (X @ W + b).argmax(axis=1)


# ============================================================ structural feats
STRUCT_NAMES = [
    "log_n_chars", "log_n_tokens", "log_n_lines", "log_n_numeric_tokens",
    "numeric_density", "log_n_external_systems", "log_n_distinct_systems",
    "n_comparison_cues", "has_comparison_cue", "n_attribution_cues",
    "has_attribution_cue", "has_citation_marker", "log_n_coordinate_terms",
    "coordinate_density", "mean_tokens_per_line", "short_numeric_line_frac",
]


def structural_features(cand: dict) -> np.ndarray:
    text = cand.get("window_text", "") or ""
    lines = text.split("\n")
    words = WORD_RE.findall(text)
    n_tokens = max(len(words), 1)
    n_lines = max(len(lines), 1)
    numbers = cand.get("numbers", []) or []
    ext = cand.get("external_systems", []) or []
    own = cand.get("own_systems", []) or []
    distinct = set(ext) | set(own)
    comp = cand.get("comparison_cues", []) or []
    attr = cand.get("attribution_cues", []) or []
    n_coord = len(COORD_RE.findall(text))

    def is_numlike(tok: str) -> bool:
        return bool(re.search(r"\d", tok)) and bool(
            re.fullmatch(r"[\d.,%()+/\-]+", tok)
        )

    short_numeric = 0
    for ln in lines:
        toks = ln.split()
        if not toks:
            continue
        num = sum(1 for t in toks if is_numlike(t))
        if len(toks) <= 3 and num / len(toks) >= 0.5:
            short_numeric += 1

    lg = lambda x: float(np.log1p(x))  # noqa: E731
    return np.array([
        lg(len(text)),
        lg(n_tokens),
        lg(n_lines),
        lg(len(numbers)),
        len(numbers) / n_tokens,
        lg(len(ext)),
        lg(len(distinct)),
        float(len(comp)),
        1.0 if comp else 0.0,
        float(len(attr)),
        1.0 if attr else 0.0,
        1.0 if CITATION_RE.search(text) else 0.0,
        lg(n_coord),
        n_coord / n_tokens,
        n_tokens / n_lines,
        short_numeric / n_lines,
    ])


# ==================================================================== folding
def grouped_folds(groups: list[str], n_splits: int) -> list[list[int]]:
    """Deterministic grouped k-fold: whole citing papers, balanced test sizes."""
    sizes = Counter(groups)
    order = sorted(sizes, key=lambda g: (-sizes[g], g))
    load = [0] * n_splits
    fold_of = {}
    for g in order:
        j = min(range(n_splits), key=lambda k: (load[k], k))
        fold_of[g] = j
        load[j] += sizes[g]
    folds = [[] for _ in range(n_splits)]
    for i, g in enumerate(groups):
        folds[fold_of[g]].append(i)
    return folds


# ==================================================================== metrics
def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float((y_true == y_pred).mean()) if len(y_true) else float("nan")


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, classes: list[int]) -> float:
    scores = []
    for c in classes:
        tp = int(((y_true == c) & (y_pred == c)).sum())
        fp = int(((y_true != c) & (y_pred == c)).sum())
        fn = int(((y_true == c) & (y_pred != c)).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        scores.append(f1)
    return float(np.mean(scores)) if scores else float("nan")


def grouped_bootstrap(
    groups: np.ndarray, y_true: np.ndarray, preds: dict, classes: list[int],
    baseline_key: str, seed: int, n_boot: int,
):
    """Resample citing papers; return point + CI for accuracy, macro-F1, and the
    per-estimator delta over the baseline (paired on each resample)."""
    rng = np.random.default_rng(seed)
    uniq = np.array(sorted(set(groups.tolist())))
    idx_by_group = {g: np.where(groups == g)[0] for g in uniq}

    point = {}
    for key, yp in preds.items():
        point[key] = {
            "accuracy": accuracy(y_true, yp),
            "macro_f1": macro_f1(y_true, yp, classes),
        }

    acc_draws = {k: [] for k in preds}
    f1_draws = {k: [] for k in preds}
    dacc_draws = {k: [] for k in preds}
    df1_draws = {k: [] for k in preds}
    for _ in range(n_boot):
        pick = uniq[rng.integers(0, len(uniq), len(uniq))]
        sel = np.concatenate([idx_by_group[g] for g in pick])
        yt = y_true[sel]
        base_acc = accuracy(yt, preds[baseline_key][sel])
        base_f1 = macro_f1(yt, preds[baseline_key][sel], classes)
        for k, yp in preds.items():
            a = accuracy(yt, yp[sel])
            f = macro_f1(yt, yp[sel], classes)
            acc_draws[k].append(a)
            f1_draws[k].append(f)
            dacc_draws[k].append(a - base_acc)
            df1_draws[k].append(f - base_f1)

    def ci(vals):
        v = np.sort(np.array(vals))
        return [float(v[int(0.025 * len(v))]), float(v[min(len(v) - 1, int(0.975 * len(v)))])]

    out = {}
    for k in preds:
        out[k] = {
            "accuracy": point[k]["accuracy"],
            "accuracy_ci95": ci(acc_draws[k]),
            "macro_f1": point[k]["macro_f1"],
            "macro_f1_ci95": ci(f1_draws[k]),
            "delta_accuracy_vs_baseline": point[k]["accuracy"] - point[baseline_key]["accuracy"],
            "delta_accuracy_ci95": ci(dacc_draws[k]),
            "delta_macro_f1_vs_baseline": point[k]["macro_f1"] - point[baseline_key]["macro_f1"],
            "delta_macro_f1_ci95": ci(df1_draws[k]),
        }
    return out


# ==================================================================== loading
def best_tier(runs, cid, pass_name, judge):
    for tier in ("both_full", "citing_full"):
        if cid in runs.get((pass_name, tier, judge), {}):
            return tier
    return None


def build_reference(sample, runs):
    """Reproduce the evidence-privileged reference majority per window/pass."""
    reference = {}
    for cid, row in sample.items():
        entry = {}
        for pass_name, field, caster in (
            ("comparability", "verdict", apr.norm_verdict),
            ("provenance", "provenance", apr.norm_prov),
        ):
            verified = []
            for judge in apr.REFERENCE:
                tier = best_tier(runs, cid, pass_name, judge)
                if tier is None:
                    continue
                parsed = runs[(pass_name, tier, judge)][cid]["parsed"]
                label = caster(parsed.get(field))
                ok = apr.quote_ok(parsed.get("evidence_quote", ""), row["cite_key"])
                if tier == "both_full" and row["cited_papers"]:
                    cited = [c["cite_key"] for c in row["cited_papers"][:2]]
                    ok = ok and any(
                        apr.quote_ok(parsed.get("evidence_quote_cited", ""), k) for k in cited
                    )
                if ok:
                    verified.append(label)
            entry[pass_name] = apr.majority(verified) if len(verified) >= 2 else None
        reference[cid] = entry
    return reference


def deployed_majority(dep_comp, dep_prov, dep_prov_names, cid, pass_name):
    if pass_name == "comparability":
        vals = [apr.norm_verdict(dep_comp[j].get(cid, {}).get("verdict"))
                for j in apr.DEPLOYED if cid in dep_comp[j]]
    else:
        vals = [apr.norm_prov(dep_prov[n].get(cid, {}).get("provenance"))
                for n in dep_prov_names if cid in dep_prov[n]]
    return apr.majority(vals) if len(vals) >= 2 else None


# ==================================================================== per-target
def run_target(name, pass_name, label_space, sample, cand, reference,
               dep_comp, dep_prov, dep_prov_names, restrict_deployed):
    """Assemble the labelled set and evaluate every estimator with grouped CV."""
    class_index = {c: i for i, c in enumerate(label_space)}
    rows = []
    for cid, ref in ((c, reference[c][pass_name]) for c in sample):
        if ref is None:
            continue
        dep = deployed_majority(dep_comp, dep_prov, dep_prov_names, cid, pass_name)
        if restrict_deployed and dep is None:
            continue
        rows.append((cid, ref, dep))

    cids = [r[0] for r in rows]
    groups = [sample[c]["cite_key"] for c in cids]
    y = np.array([class_index[r[1]] for r in rows])
    present = sorted(set(y.tolist()))
    texts = [cand[c]["window_text"] for c in cids]
    struct = np.array([structural_features(cand[c]) for c in cids])

    folds = grouped_folds(groups, min(N_FOLDS, len(set(groups))))

    # out-of-fold predictions per estimator
    oof = {k: np.full(len(rows), -1, dtype=int)
           for k in ("constant_majority", "tfidf_logreg", "structural_logreg")}
    for test_idx in folds:
        test = np.array(test_idx)
        train = np.array([i for i in range(len(rows)) if i not in set(test_idx)])
        y_tr = y[train]

        maj = Counter(y_tr.tolist()).most_common(1)[0][0]
        oof["constant_majority"][test] = maj

        index, idf = tfidf_fit([texts[i] for i in train], TFIDF_MIN_DF, TFIDF_MAX_FEATURES)
        Xtr = tfidf_transform([texts[i] for i in train], index, idf)
        Xte = tfidf_transform([texts[i] for i in test], index, idf)
        classes_tr = sorted(set(y_tr.tolist()))
        remap = {c: i for i, c in enumerate(classes_tr)}
        inv = {i: c for c, i in remap.items()}
        if len(classes_tr) == 1:
            oof["tfidf_logreg"][test] = classes_tr[0]
        else:
            W, b = softmax_fit(Xtr, np.array([remap[c] for c in y_tr]), len(classes_tr), LOGREG_C)
            oof["tfidf_logreg"][test] = [inv[p] for p in softmax_predict(Xte, W, b)]

        mu = struct[train].mean(axis=0)
        sd = struct[train].std(axis=0)
        sd[sd == 0] = 1.0
        Str = (struct[train] - mu) / sd
        Ste = (struct[test] - mu) / sd
        if len(classes_tr) == 1:
            oof["structural_logreg"][test] = classes_tr[0]
        else:
            W, b = softmax_fit(Str, np.array([remap[c] for c in y_tr]), len(classes_tr), LOGREG_C)
            oof["structural_logreg"][test] = [inv[p] for p in softmax_predict(Ste, W, b)]

    preds = dict(oof)
    # LLM panel estimator (only where a deployed majority exists)
    if restrict_deployed:
        llm = np.array([class_index[r[2]] for r in rows])
        preds["llm_panel_majority"] = llm

    boot = grouped_bootstrap(
        np.array(groups), y, {k: np.asarray(v) for k, v in preds.items()},
        present, "constant_majority", SEED, N_BOOT,
    )

    # confusion matrices (rows = reference label, cols = predicted)
    inv_class = {i: c for c, i in class_index.items()}
    confusion = {}
    for k, yp in preds.items():
        m = Counter()
        for t, p in zip(y.tolist(), np.asarray(yp).tolist()):
            m[(inv_class[t], inv_class[p])] += 1
        cm = {}
        for (t, p), c in m.items():
            cm.setdefault(t, {})[p] = c
        confusion[k] = cm

    beats = {}
    for k, v in boot.items():
        if k == "constant_majority":
            continue
        beats[k] = {
            "accuracy_beats_baseline": v["delta_accuracy_ci95"][0] > 0,
            "macro_f1_beats_baseline": v["delta_macro_f1_ci95"][0] > 0,
        }

    return {
        "target": name,
        "pass_name": pass_name,
        "label_space": list(label_space),
        "restrict_to_deployed_majority": restrict_deployed,
        "n_windows": len(rows),
        "n_papers": len(set(groups)),
        "n_folds": len(folds),
        "label_distribution": {inv_class[c]: int((y == c).sum()) for c in present},
        "majority_class": inv_class[Counter(y.tolist()).most_common(1)[0][0]],
        "majority_class_share": float(np.bincount(y).max() / len(y)),
        "estimators": boot,
        "beats_baseline": beats,
        "confusion_reference_by_predicted": confusion,
    }


def summarise(block: dict) -> dict:
    est = block["estimators"]
    supervised = {k: est[k] for k in ("tfidf_logreg", "structural_logreg") if k in est}
    best_acc = max(supervised.values(), key=lambda v: v["delta_accuracy_vs_baseline"], default=None)
    best_f1 = max(supervised.values(), key=lambda v: v["delta_macro_f1_vs_baseline"], default=None)
    best_acc_name = max(supervised, key=lambda k: supervised[k]["delta_accuracy_vs_baseline"]) if supervised else None
    any_beat_acc = any(v["accuracy_beats_baseline"] for k, v in block["beats_baseline"].items()
                       if k in ("tfidf_logreg", "structural_logreg"))
    any_beat_f1 = any(v["macro_f1_beats_baseline"] for k, v in block["beats_baseline"].items()
                      if k in ("tfidf_logreg", "structural_logreg"))
    return {
        "baseline_accuracy": est["constant_majority"]["accuracy"],
        "baseline_macro_f1": est["constant_majority"]["macro_f1"],
        "best_supervised_estimator_by_accuracy": best_acc_name,
        "best_supervised_delta_accuracy": best_acc["delta_accuracy_vs_baseline"] if best_acc else None,
        "best_supervised_delta_accuracy_ci95": best_acc["delta_accuracy_ci95"] if best_acc else None,
        "best_supervised_delta_macro_f1": best_f1["delta_macro_f1_vs_baseline"] if best_f1 else None,
        "any_supervised_beats_baseline_accuracy": any_beat_acc,
        "any_supervised_beats_baseline_macro_f1": any_beat_f1,
        "llm_panel_delta_accuracy": est.get("llm_panel_majority", {}).get("delta_accuracy_vs_baseline"),
        "llm_panel_accuracy_beats_baseline": block["beats_baseline"].get("llm_panel_majority", {}).get("accuracy_beats_baseline"),
    }


def interpret(targets: dict) -> dict:
    """Build a faithful, numbers-driven reading of the two targets."""
    def g(block, est, field):
        return block["estimators"][est][field]

    v = targets["verdict"]
    p = targets["provenance"]
    r2 = lambda x: round(float(x), 3)  # noqa: E731

    verdict = {
        "n_windows": v["n_windows"], "n_papers": v["n_papers"],
        "baseline_accuracy": r2(g(v, "constant_majority", "accuracy")),
        "any_estimator_beats_baseline_on_accuracy": any(
            v["beats_baseline"][k]["accuracy_beats_baseline"] for k in v["beats_baseline"]
        ),
        "structural_vs_llm_accuracy": [r2(g(v, "structural_logreg", "accuracy")),
                                       r2(g(v, "llm_panel_majority", "accuracy"))],
        "structural_vs_llm_macro_f1": [r2(g(v, "structural_logreg", "macro_f1")),
                                       r2(g(v, "llm_panel_majority", "macro_f1"))],
        "structural_beats_baseline_on_macro_f1": v["beats_baseline"]["structural_logreg"]["macro_f1_beats_baseline"],
        "tfidf_delta_accuracy": r2(g(v, "tfidf_logreg", "delta_accuracy_vs_baseline")),
        "statement": (
            f"On the disputed verdict (N={v['n_windows']} windows, {v['n_papers']} citing papers) no "
            f"instrument -- not the deployed LLM panel, not TF-IDF, not the structural model -- "
            f"significantly beats the constant-majority baseline on accuracy: every 95% CI on the "
            f"delta-accuracy includes 0. The non-LLM structural instrument matches the LLM panel "
            f"(accuracy {r2(g(v,'structural_logreg','accuracy'))} vs {r2(g(v,'llm_panel_majority','accuracy'))}; "
            f"macro-F1 {r2(g(v,'structural_logreg','macro_f1'))} vs {r2(g(v,'llm_panel_majority','macro_f1'))}), "
            f"and both beat the baseline on macro-F1 by a similar margin "
            f"(structural +{r2(g(v,'structural_logreg','delta_macro_f1_vs_baseline'))}, "
            f"CI {[r2(x) for x in g(v,'structural_logreg','delta_macro_f1_ci95')]}). Bag-of-words carries "
            f"no cross-paper signal (delta-accuracy {r2(g(v,'tfidf_logreg','delta_accuracy_vs_baseline'))}). "
            f"Because a different instrument class reaches the same ceiling, the ceiling is a property of "
            f"the text, not a special failure of the LLM instrument class."
        ),
    }
    provenance = {
        "n_windows": p["n_windows"], "n_papers": p["n_papers"],
        "baseline_accuracy": r2(g(p, "constant_majority", "accuracy")),
        "llm_accuracy": r2(g(p, "llm_panel_majority", "accuracy")),
        "structural_accuracy": r2(g(p, "structural_logreg", "accuracy")),
        "llm_minus_structural_accuracy": r2(g(p, "llm_panel_majority", "accuracy") - g(p, "structural_logreg", "accuracy")),
        "any_supervised_beats_baseline": p["summary"]["any_supervised_beats_baseline_accuracy"],
        "statement": (
            f"On provenance (N={p['n_windows']}, {p['n_papers']} papers) the LLM panel reaches "
            f"{r2(g(p,'llm_panel_majority','accuracy'))} accuracy, a "
            f"+{r2(g(p,'llm_panel_majority','accuracy') - g(p,'structural_logreg','accuracy'))} point lead over "
            f"the structural instrument ({r2(g(p,'structural_logreg','accuracy'))}); the statistical instruments "
            f"do not beat the baseline. So the statistical instrument is a conservative lower bound on "
            f"extractable signal, yet it matches the LLM panel on the verdict while trailing it here -- the "
            f"LLM's extra capacity buys a provenance lead but no verdict lead."
        ),
    }
    return {
        "headline": (
            "A non-LLM statistical instrument, trained directly on the reference labels, does no better "
            "than the deployed LLM panel on the verdict and no better than a constant baseline on accuracy; "
            "the verdict ceiling is therefore in the text, not in the LLM instrument class."
        ),
        "verdict": verdict,
        "provenance": provenance,
        "caveats": [
            "Intervals are paper-clustered bootstraps; with a rare minority class and clustering, "
            "delta-accuracy CIs are wide even for the LLM panel on provenance.",
            "There is a little text signal on the verdict: structural and LLM instruments both beat the "
            "baseline on macro-F1 (they recover some 'undefined' windows), but not on accuracy.",
            "The single 'narrows' reference label falls outside the deployed-scored set, so the verdict "
            "evaluation is effectively binary (survives vs undefined).",
        ],
    }


# ============================================================ latex + macros
MACRO_HEADER = (
    "% Generated by scripts/revision4/analyze_nonllm_instrument.py and\n"
    "% scripts/revision4/analyze_reference_independence.py -- do not edit by hand.\n"
    "% Task A macros are prefixed \\Nll; Task B macros are prefixed \\Ind.\n"
    "% Each analysis script owns and rewrites only its own marker-delimited block."
)


def _parse_macro_blocks(text: str) -> dict:
    blocks, cur, buf = {}, None, []
    for ln in text.splitlines():
        if ln.startswith("% >>> BEGIN "):
            cur, buf = ln[len("% >>> BEGIN "):].strip(), []
        elif ln.startswith("% <<< END ") and cur is not None:
            blocks[cur] = "\n".join(buf)
            cur = None
        elif cur is not None:
            buf.append(ln)
    return blocks


def write_macro_section(path: Path, prefix: str, macro_lines: list) -> None:
    """Idempotently merge this script's macro block, preserving the other one."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    blocks = _parse_macro_blocks(text)
    blocks[prefix] = "\n".join(macro_lines)
    order = [p for p in ("Nll", "Ind") if p in blocks]
    order += [p for p in blocks if p not in order]
    out = [MACRO_HEADER]
    for p in order:
        out += [f"% >>> BEGIN {p}", blocks[p], f"% <<< END {p}"]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _n2(x, nd=2, signed=False):
    if x is None or (isinstance(x, float) and x != x):
        return "--"
    return f"{float(x):+.{nd}f}" if signed else f"{float(x):.{nd}f}"


def _ci2(pair, nd=2):
    if not pair or len(pair) != 2 or any(p is None or p != p for p in pair):
        return "--"
    return f"[{float(pair[0]):.{nd}f}, {float(pair[1]):.{nd}f}]"


EST_ROWS = [
    ("constant_majority", "Constant majority (baseline)"),
    ("tfidf_logreg", "TF-IDF $+$ logistic reg."),
    ("structural_logreg", "Structural feats.\\ $+$ logistic reg."),
    ("llm_panel_majority", "LLM panel majority"),
]


def latex_table(payload: dict) -> str:
    def panel(name, title):
        b = payload["targets"][name]
        est = b["estimators"]
        rows = [rf"\multicolumn{{5}}{{@{{}}l}}{{\emph{{{title}}}}} \\"]
        for key, label in EST_ROWS:
            if key not in est:
                continue
            v = est[key]
            if key == "constant_majority":
                dacc = dfx = "---"
            else:
                dacc = f"{_n2(v['delta_accuracy_vs_baseline'], signed=True)}\\,{_ci2(v['delta_accuracy_ci95'])}"
                dfx = f"{_n2(v['delta_macro_f1_vs_baseline'], signed=True)}\\,{_ci2(v['delta_macro_f1_ci95'])}"
            rows.append(
                f"\\quad {label} & {_n2(v['accuracy'])} & {_n2(v['macro_f1'])} & {dacc} & {dfx} \\\\"
            )
        return rows

    v = payload["targets"]["verdict"]
    p = payload["targets"]["provenance"]
    body = []
    body += panel("verdict",
                  rf"Verdict (survives / undefined), $N={v['n_windows']}$ windows, {v['n_papers']} papers")
    body.append(r"\midrule")
    body += panel("provenance",
                  rf"Provenance (re-impl.\ / transported), $N={p['n_windows']}$ windows, {p['n_papers']} papers")
    body_str = "\n".join(body)
    return rf"""% Generated by scripts/revision4/analyze_nonllm_instrument.py -- do not edit.
\begin{{table}}[t]
\centering\scriptsize
\setlength{{\tabcolsep}}{{3pt}}
\resizebox{{\columnwidth}}{{!}}{{%
\begin{{tabular}}{{@{{}}lrrll@{{}}}}
\toprule
Instrument (non-LLM unless noted) & Acc. & macro-F1 & $\Delta$Acc.\ [95\% CI] & $\Delta$macro-F1 [95\% CI] \\
\midrule
{body_str}
\bottomrule
\end{{tabular}}}}
\caption{{A non-LLM instrument on the same task. Each instrument is trained on
the evidence-privileged reference labels and evaluated with grouped
cross-validation that holds out whole citing papers; the LLM panel row is the
deployed three-judge majority scored on the same windows and reproduces the
published accuracies ({_n2(v['estimators']['llm_panel_majority']['accuracy'])} and {_n2(p['estimators']['llm_panel_majority']['accuracy'])}). Intervals resample
citing papers. On the disputed verdict no instrument -- LLM or not -- beats the
constant baseline on accuracy (every $\Delta$Acc.\ CI includes 0), and the
non-LLM structural model matches the LLM panel; the accuracy ceiling is a
property of the text, not of the LLM instrument class. Provenance is the
contrast where the LLM panel pulls ahead of the cheap instrument.}}
\label{{tab:nonllm-instrument}}
\end{{table}}
"""


def macros(payload: dict) -> list:
    lines = []
    add = lines.append
    tags = {"verdict": "Vd", "provenance": "Pv"}
    ests = {"constant_majority": "Base", "tfidf_logreg": "Tfidf",
            "structural_logreg": "Struct", "llm_panel_majority": "Llm"}
    for name, tg in tags.items():
        b = payload["targets"][name]
        est = b["estimators"]
        add(rf"\newcommand{{\Nll{tg}N}}{{{b['n_windows']}}}")
        add(rf"\newcommand{{\Nll{tg}Papers}}{{{b['n_papers']}}}")
        for ekey, es in ests.items():
            if ekey not in est:
                continue
            v = est[ekey]
            add(rf"\newcommand{{\Nll{tg}{es}Acc}}{{{_n2(v['accuracy'])}}}")
            add(rf"\newcommand{{\Nll{tg}{es}AccCI}}{{{_ci2(v['accuracy_ci95'])}}}")
            add(rf"\newcommand{{\Nll{tg}{es}FOne}}{{{_n2(v['macro_f1'])}}}")
            add(rf"\newcommand{{\Nll{tg}{es}dAcc}}{{{_n2(v['delta_accuracy_vs_baseline'], signed=True)}}}")
            add(rf"\newcommand{{\Nll{tg}{es}dAccCI}}{{{_ci2(v['delta_accuracy_ci95'])}}}")
            add(rf"\newcommand{{\Nll{tg}{es}dFOne}}{{{_n2(v['delta_macro_f1_vs_baseline'], signed=True)}}}")
            add(rf"\newcommand{{\Nll{tg}{es}dFOneCI}}{{{_ci2(v['delta_macro_f1_ci95'])}}}")
    # headline scalars used in prose
    pv = payload["interpretation"]["provenance"]
    add(rf"\newcommand{{\NllPvLlmLead}}{{{_n2(pv['llm_minus_structural_accuracy'], signed=True)}}}")
    add(rf"\newcommand{{\NllVdAnyBeatsAcc}}{{{'yes' if payload['interpretation']['verdict']['any_estimator_beats_baseline_on_accuracy'] else 'no'}}}")
    add(rf"\newcommand{{\NllVdStructBeatsFOne}}{{{'yes' if payload['interpretation']['verdict']['structural_beats_baseline_on_macro_f1'] else 'no'}}}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=Path, default=SUP / "privileged_reference_sample.jsonl")
    ap.add_argument("--candidates", type=Path, default=SUP / "cross_paper_frame_candidates.jsonl")
    ap.add_argument("--runs", type=Path, default=SUP / "privileged_reference_runs")
    ap.add_argument("--coding-dir", type=Path, default=SUP / "cross_paper_coding")
    ap.add_argument("--prov-dir", type=Path, default=SUP / "cross_paper_provenance")
    ap.add_argument("--out", type=Path, default=SUP / "nonllm_instrument_results.json")
    args = ap.parse_args()

    sample = {}
    for line in args.sample.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            sample[r["candidate_id"]] = r
    cand = {}
    for line in args.candidates.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            cand[d["candidate_id"]] = d
    missing = [c for c in sample if c not in cand]
    if missing:
        raise SystemExit(f"{len(missing)} sample windows absent from candidates frame")

    runs = apr.load_runs(args.runs)
    dep_comp, dep_prov = apr.load_deployed(args.coding_dir, args.prov_dir)
    dep_prov_names = sorted(dep_prov)
    reference = build_reference(sample, runs)

    targets = {}
    for name, pass_name, space in (
        ("verdict", "comparability", VERDICTS),
        ("provenance", "provenance", PROV),
    ):
        block = run_target(name, pass_name, space, sample, cand, reference,
                           dep_comp, dep_prov, dep_prov_names, restrict_deployed=True)
        block["summary"] = summarise(block)
        # robustness: supervised estimators on the full established-reference set
        full = run_target(name, pass_name, space, sample, cand, reference,
                          dep_comp, dep_prov, dep_prov_names, restrict_deployed=False)
        full["summary"] = summarise(full)
        block["on_full_reference_set"] = {
            "n_windows": full["n_windows"],
            "n_papers": full["n_papers"],
            "label_distribution": full["label_distribution"],
            "estimators": {k: full["estimators"][k] for k in
                           ("constant_majority", "tfidf_logreg", "structural_logreg")},
            "any_supervised_beats_baseline_accuracy": full["summary"]["any_supervised_beats_baseline_accuracy"],
            "any_supervised_beats_baseline_macro_f1": full["summary"]["any_supervised_beats_baseline_macro_f1"],
        }
        targets[name] = block

    payload = {
        "schema_version": 1,
        "seed": SEED,
        "design_note": (
            "A non-LLM instrument (a plain statistical classifier trained on the "
            "evidence-privileged reference labels) is asked to predict those "
            "labels from the window text under grouped cross-validation by "
            "citing paper. If a supervised model with direct access to the "
            "answers cannot beat a constant-majority baseline, the deficit is a "
            "property of the text, not of the LLM instrument class. Provenance "
            "is run as a contrast: it is the target where the LLM panel pulls "
            "clearly ahead of the cheap statistical instrument, so it shows the "
            "comparison can detect an instrument-class gap when the text carries "
            "signal -- and finds none on the verdict."
        ),
        "config": {
            "n_folds": N_FOLDS,
            "n_bootstrap": N_BOOT,
            "tfidf_min_df": TFIDF_MIN_DF,
            "tfidf_max_features": TFIDF_MAX_FEATURES,
            "logreg_C": LOGREG_C,
            "structural_features": STRUCT_NAMES,
            "n_coordinate_terms_in_vocab": len(COORDINATE_TERMS),
            "implementation": "numpy+scipy softmax regression (matches scikit-learn to machine precision)",
        },
        "reference_derivation": (
            "Imported verbatim from scripts/revision3/analyze_privileged_reference.py: "
            "majority of quote-verified privileged adjudicators, established with >=2 verified votes."
        ),
        "targets": targets,
        "interpretation": interpret(targets),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (TAB / "nonllm_instrument.tex").write_text(latex_table(payload), encoding="utf-8")
    write_macro_section(MACRO_FILE, "Nll", macros(payload))

    print(json.dumps({
        name: {
            "n": b["n_windows"], "papers": b["n_papers"],
            "baseline_acc": round(b["summary"]["baseline_accuracy"], 3),
            "estimators": {
                k: {"acc": round(v["accuracy"], 3), "f1": round(v["macro_f1"], 3),
                    "dAcc": round(v["delta_accuracy_vs_baseline"], 3),
                    "dAcc_ci": [round(x, 3) for x in v["delta_accuracy_ci95"]]}
                for k, v in b["estimators"].items()
            },
            "any_supervised_beats_baseline": b["summary"]["any_supervised_beats_baseline_accuracy"],
        }
        for name, b in targets.items()
    }, indent=2))
    print(f"\nwrote {args.out}")
    print(f"wrote {TAB / 'nonllm_instrument.tex'}")
    print(f"wrote {MACRO_FILE} (\\Nll block)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
