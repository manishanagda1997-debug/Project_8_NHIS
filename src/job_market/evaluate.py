"""Scoring categories against human labels (decisions D-027 and D-029).

Small, pure functions: they take tables and return tables, so the pipeline
step, the notebook and the tests all use the same arithmetic.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .taxonomy import OTHER

RULE_METHODS = ("rule", "two_tasks", "no_text")


def wilson_interval(correct: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Better than "p +/- 1.96 * standard error" for small samples and for
    proportions near 0 or 1: it never leaves the range 0-1.
    """
    if total <= 0:
        return (float("nan"), float("nan"))
    p = correct / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def rules_only(predictions: pd.DataFrame) -> pd.Series:
    """The prediction without the fallback classifier: anything the rules did
    not decide becomes Other / Unclear."""
    decided = predictions["category_method"].astype(str).isin(RULE_METHODS)
    return predictions["primary_category"].astype(str).where(decided, OTHER)


def score_items(labels: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    """One row per labelled job: human label, prediction, method, correctness."""
    items = labels.merge(predictions, on="row_id", how="left", validate="one_to_one")
    if items["primary_category"].isna().any():
        missing = items.loc[items["primary_category"].isna(), "sample_id"].tolist()
        raise ValueError(f"labelled jobs without a prediction: {missing[:5]}")
    items["human"] = items["category"].astype(str)
    items["predicted"] = items["primary_category"].astype(str)
    items["rules_only"] = rules_only(items)
    items["correct"] = items["human"] == items["predicted"]
    items["correct_rules_only"] = items["human"] == items["rules_only"]
    items["unsure"] = items["unsure"].fillna(False).astype(bool)
    return items


def summary_rows(items: pd.DataFrame, label_set: str) -> pd.DataFrame:
    """Accuracy with a Wilson interval for the whole set and its main subsets."""
    subsets = {
        "all": np.ones(len(items), dtype=bool),
        "labelled_sure": ~items["unsure"].to_numpy(),
        "labelled_unsure": items["unsure"].to_numpy(),
        "decided_by_rule": items["category_method"].astype(str).eq("rule").to_numpy(),
        "predicted_not_other": items["predicted"].ne(OTHER).to_numpy(),
    }
    rows = []
    for name, mask in subsets.items():
        part = items[mask]
        for system, column in (("full", "correct"), ("rules_only", "correct_rules_only")):
            if system == "rules_only" and name != "all":
                continue
            n, k = len(part), int(part[column].sum())
            low, high = wilson_interval(k, n)
            rows.append(
                {
                    "label_set": label_set, "subset": name, "system": system, "titles": n, "correct": k,
                    "accuracy": round(k / n, 4) if n else None,
                    "wilson_low": round(low, 4) if n else None, "wilson_high": round(high, 4) if n else None,
                }
            )
    return pd.DataFrame(rows)


def per_category(items: pd.DataFrame, label_set: str) -> pd.DataFrame:
    """Precision, recall and F1 for every category that appears in the labels or predictions."""
    categories = sorted(set(items["human"]) | set(items["predicted"]))
    rows = []
    for category in categories:
        human = items["human"].eq(category)
        predicted = items["predicted"].eq(category)
        hit = int((human & predicted).sum())
        precision = hit / predicted.sum() if predicted.any() else 0.0
        recall = hit / human.sum() if human.any() else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append(
            {
                "label_set": label_set, "category": category, "human_titles": int(human.sum()),
                "predicted_titles": int(predicted.sum()), "correct": hit, "precision": round(precision, 4),
                "recall": round(recall, 4), "f1": round(f1, 4),
            }
        )
    return pd.DataFrame(rows)


def confusion(items: pd.DataFrame, label_set: str) -> pd.DataFrame:
    """Counts of (human label, predicted label) pairs, including correct pairs."""
    table = items.groupby(["human", "predicted"]).size().rename("titles").reset_index()
    table.insert(0, "label_set", label_set)
    return table.sort_values(["titles", "human", "predicted"], ascending=[False, True, True]).reset_index(drop=True)
