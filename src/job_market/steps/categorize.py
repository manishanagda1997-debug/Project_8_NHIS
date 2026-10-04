"""Step 3 - categorize: one job-function category for every job (decision D-028).

How a title gets its category:

1. **Rules** (``job_market.categorize``): weighted keyword patterns and the
   tie-break rules of ``docs/labelling_guide.md``. Most titles are settled
   here, and every decision can be explained by the words that matched.
2. **Fallback classifier** for titles no rule matches: TF-IDF features and a
   logistic regression, trained only on *weak labels* - titles the rules
   categorize with high confidence. No human label is ever used for training,
   so the development and blind label sets stay clean for evaluation.
   The words that made the rule fire are hidden from the training text. The
   classifier only ever sees titles where no rule word appears, so it has to
   learn from the *other* words ("store", "sourcing", "Turkey"); trained on
   the full text it would lean on the rule words and be unsure on every
   title it is actually used for.
3. If the classifier's probability is below the threshold, the job goes to
   Other / Unclear ("below_threshold"). Guessing would put wrong jobs into
   demand counts; an honest "unclear" does not.
4. The classifier may only assign the fixed list of fallback categories that
   proved reliable on the masked proxy test; any other confident guess also
   goes to Other / Unclear ("fallback_blocked").

``jobs_clean.parquet`` is never changed. The result is a separate table,
``job_categories.parquet``, joined on ``row_id``.

The threshold is chosen on the development labels and then frozen together
with the rules and the model settings (decision D-027). The blind labels are
scored once, after the freeze.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import FeatureUnion, Pipeline

from ..categorize import categorize_title, category_text, industry_tags
from ..config import Settings
from ..io import write_csv, write_json, write_parquet
from ..manifest import StepRecord, describe_output
from ..taxonomy import CATEGORY_IDS, OTHER, TAXONOMY_VERSION
from .clean import title_key

NAME = "categorize"
DESCRIPTION = "Give every job one job-function category: keyword rules first, a TF-IDF classifier for the rest."

METHODS = ("rule", "two_tasks", "tfidf_classifier", "below_threshold", "fallback_blocked", "no_text")
OUTPUT_COLUMNS = (
    "row_id", "primary_category", "category_method", "rule_score", "classifier_category",
    "classifier_probability", "matched_terms", "secondary_categories", "industry_tags",
    "taxonomy_version", "categorizer_version",
)
SEPARATOR = "; "


# ------------------------------------------------------------------ rules per title


def rule_table(titles: pd.Series, min_score: int) -> pd.DataFrame:
    """Rule results for each distinct ``title_clean`` (one row per title)."""
    rows = []
    for title in pd.unique(titles.dropna()):
        result = categorize_title(title, min_score=min_score)
        text = category_text(title)
        rows.append(
            {
                "title_clean": title,
                "category_text": text,
                "rule_category": result.category,
                "rule_method": result.method,
                "rule_score": result.score,
                # Number of categories still competing after the tie-breaks.
                "rule_competitors": len(result.scores),
                "matched_terms": SEPARATOR.join(result.matched_terms),
                "secondary_categories": SEPARATOR.join(result.secondary),
                "industry_tags": SEPARATOR.join(industry_tags(text)),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ weak labels


def hide_terms(text: str, terms: str) -> str:
    """Remove the matched rule phrases (longest first) from a category text."""
    padded = f" {text} "
    for term in sorted(filter(None, terms.split(SEPARATOR)), key=len, reverse=True):
        padded = padded.replace(f" {term} ", " ")
    return " ".join(padded.split())


def weak_labels(rules: pd.DataFrame, min_score: int, max_per_category: int, seed: int) -> pd.DataFrame:
    """High-confidence rule results used as training labels for the classifier.

    A weak label needs a rule score of at least ``min_score`` and no other
    category left after the tie-breaks. Titles are distinct already, so a job
    posted many times counts once. Very large categories are sampled down to
    ``max_per_category`` titles to keep training fast; ``class_weight`` handles
    the remaining imbalance.
    """
    strong = rules[
        (rules["rule_method"] == "rule")
        & (rules["rule_category"] != OTHER)          # "Other" is not a function to learn
        & (rules["rule_score"] >= min_score)
        & (rules["rule_competitors"] == 1)
        & (rules["category_text"].str.len() > 0)
    ]
    parts = []
    for category, group in strong.groupby("rule_category", sort=True):
        if len(group) > max_per_category:
            group = group.sample(n=max_per_category, random_state=seed)
        parts.append(group)
    labels = pd.concat(parts, ignore_index=True) if parts else strong.iloc[0:0].copy()
    labels["training_text"] = [hide_terms(t, m) for t, m in zip(labels["category_text"], labels["matched_terms"])]
    labels = labels.loc[np.array([len(text) > 0 for text in labels["training_text"]], dtype=bool)]   # nothing left once the rule words are hidden
    return labels.sort_values("title_clean", kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------ classifier


def build_classifier(settings: dict[str, Any], seed: int) -> Pipeline:
    """Word and character TF-IDF features into a logistic regression.

    Word pairs catch phrases ("lead list"); character pieces catch spelling
    variants and joined words ("photograher", "shopifydeveloper").
    """
    features = FeatureUnion(
        [
            ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True,
                                      max_features=int(settings["max_char_features"]))),
        ]
    )
    model = LogisticRegression(
        C=float(settings["classifier_c"]),
        class_weight="balanced",
        max_iter=int(settings["max_iter"]),
        random_state=seed,
    )
    return Pipeline([("features", features), ("model", model)])


PROXY_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)


def proxy_split(labels: pd.DataFrame, share: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split weak labels so that no title key appears on both sides.

    Titles that differ only in case or punctuation share a title key; keeping
    each key on one side stops the proxy test from grading titles the model
    has effectively seen in training.
    """
    keys = labels["title_clean"].map(title_key)
    splitter = GroupShuffleSplit(n_splits=1, test_size=share, random_state=seed)
    train_index, test_index = next(splitter.split(labels, groups=keys))
    return labels.iloc[train_index], labels.iloc[test_index]


def train_classifier(
    labels: pd.DataFrame, settings: dict[str, Any], seed: int
) -> tuple[Pipeline, dict[str, Any], dict[str, pd.DataFrame]]:
    """Fit on weak labels and run the masked proxy test.

    Proxy test: a held-out part of the weak labels (no shared title key with
    training), with the rule words hidden, so it resembles the titles the
    classifier really meets. It measures agreement with the high-confidence
    rule labels, not accuracy - only human labels can measure that.
    """
    train, test = proxy_split(labels, float(settings["holdout_share"]), seed)
    probe = build_classifier(settings, seed).fit(train["training_text"], train["rule_category"])
    predicted, probability = classify(probe, test["training_text"])
    agrees = predicted == test["rule_category"].to_numpy()

    by_threshold = pd.DataFrame(
        [
            {
                "threshold": t,
                "predictions": int((probability >= t).sum()),
                "coverage": round(float((probability >= t).mean()), 4),
                "agreement": round(float(agrees[probability >= t].mean()), 4) if (probability >= t).any() else None,
            }
            for t in PROXY_THRESHOLDS
        ]
    )
    threshold = float(settings["classifier_threshold"])
    kept = probability >= threshold
    by_category = (
        pd.DataFrame({"predicted_category": predicted[kept], "agrees": agrees[kept]})
        .groupby("predicted_category")["agrees"].agg(predictions="size", agreement="mean").reset_index()
    )
    by_category["agreement"] = by_category["agreement"].round(4)
    by_category["enough_support"] = by_category["predictions"] >= int(settings.get("fallback_min_proxy_predictions", 30))
    by_category["passes_guard_rule"] = by_category["enough_support"] & (
        by_category["agreement"] >= float(settings.get("fallback_min_proxy_agreement", 0.7)))
    by_category = by_category.sort_values("predicted_category").reset_index(drop=True)

    train_texts = set(train["training_text"])
    novel = ~test["training_text"].isin(train_texts).to_numpy()      # no identical masked text in training
    allowed = settings.get("fallback_categories")
    guarded = kept & (np.isin(predicted, list(allowed)) if allowed is not None else True)
    final = build_classifier(settings, seed).fit(labels["training_text"], labels["rule_category"])
    report = {
        "weak_labels": int(len(labels)),
        "weak_label_categories": int(labels["rule_category"].nunique()),
        "proxy_test_titles": int(len(test)),
        "proxy_title_keys_shared_with_training": int(
            len(set(train["title_clean"].map(title_key)) & set(test["title_clean"].map(title_key)))),
        "proxy_masked_texts_also_in_training": int(test["training_text"].isin(train_texts).sum()),
        "proxy_agreement_all": round(float(agrees.mean()), 4),
        "proxy_predictions_at_threshold": int(kept.sum()),
        "proxy_agreement_at_threshold": round(float(agrees[kept].mean()), 4) if kept.any() else None,
        "proxy_agreement_at_threshold_no_twin": round(float(agrees[kept & novel].mean()), 4) if (kept & novel).any() else None,
        "proxy_predictions_with_guard": int(guarded.sum()),
        "proxy_agreement_with_guard": round(float(agrees[guarded].mean()), 4) if guarded.any() else None,
        "proxy_agreement_with_guard_no_twin": round(float(agrees[guarded & novel].mean()), 4) if (guarded & novel).any() else None,
    }
    if allowed is not None:
        # The list is frozen in the configuration; this records whether this
        # build's proxy test still selects the same categories.
        passing = set(by_category.loc[by_category["passes_guard_rule"], "predicted_category"])
        report["fallback_list_matches_proxy_rule"] = passing == set(allowed)
    return final, report, {"by_threshold": by_threshold, "by_category": by_category}


def classify(model: Pipeline, texts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Most likely category and its probability for each text."""
    if len(texts) == 0:
        return np.array([], dtype=object), np.array([], dtype=float)
    probabilities = model.predict_proba(texts)
    best = probabilities.argmax(axis=1)
    return model.classes_[best], probabilities[np.arange(len(best)), best]


# ------------------------------------------------------------------ final decision


def decide(rules: pd.DataFrame, threshold: float, allowed: list[str] | None = None) -> pd.DataFrame:
    """Primary category and method per distinct title (needs classifier columns).

    ``allowed`` is the fixed list of categories the fallback classifier may
    assign; ``None`` allows all of them.
    """
    out = rules.copy()
    has_text = out["category_text"].str.len() > 0
    by_rule = out["rule_method"].isin(["rule", "two_tasks"])
    confident = out["classifier_probability"] >= threshold
    permitted = out["classifier_category"].isin(allowed) if allowed is not None else pd.Series(True, index=out.index)

    out["category_method"] = np.select(
        [by_rule & (out["rule_method"] == "rule"), by_rule, ~has_text, confident & permitted, confident],
        ["rule", "two_tasks", "no_text", "tfidf_classifier", "fallback_blocked"],
        default="below_threshold",
    )
    out["primary_category"] = np.select(
        [out["category_method"] == "rule", out["category_method"] == "tfidf_classifier"],
        [out["rule_category"], out["classifier_category"]],
        default=OTHER,
    )
    return out


def categorize_jobs(
    frame: pd.DataFrame, settings: dict[str, Any], seed: int
) -> tuple[pd.DataFrame, Pipeline | None, dict[str, Any], dict[str, pd.DataFrame]]:
    """The whole step on a master table; returns (job table, model, report, proxy tables)."""
    rules = rule_table(frame["title_clean"], int(settings["min_rule_score"]))
    labels = weak_labels(
        rules, int(settings["weak_label_min_score"]), int(settings["weak_label_max_per_category"]), seed
    )
    counts = labels["rule_category"].value_counts()
    usable = counts[counts >= int(settings["min_weak_labels_per_category"])].index
    labels = labels[labels["rule_category"].isin(usable)]
    if labels["rule_category"].nunique() >= 2:
        model, report, proxy = train_classifier(labels, settings, seed)
        predicted, probability = classify(model, rules["category_text"])
    else:
        # Too little data to train (only in tiny test projects): every title
        # without a rule match goes to Other / Unclear.
        model, report = None, {"weak_labels": int(len(labels)), "classifier_trained": False}
        proxy = {"by_threshold": pd.DataFrame(), "by_category": pd.DataFrame()}
        predicted, probability = np.full(len(rules), None, dtype=object), np.zeros(len(rules))
    report.setdefault("classifier_trained", True)
    rules["classifier_category"] = predicted
    rules["classifier_probability"] = probability.round(6)
    allowed = list(settings["fallback_categories"]) if "fallback_categories" in settings else None
    titles = decide(rules, float(settings["classifier_threshold"]), allowed)

    jobs = frame[["row_id", "title_clean"]].merge(titles, on="title_clean", how="left", validate="many_to_one")
    missing = jobs["primary_category"].isna()          # rows without any title text
    jobs.loc[missing, ["primary_category", "category_method"]] = [OTHER, "no_text"]
    jobs["rule_score"] = jobs["rule_score"].fillna(0).astype("int16")
    jobs["taxonomy_version"] = TAXONOMY_VERSION
    jobs["categorizer_version"] = str(settings["categorizer_version"])
    for column in ("matched_terms", "secondary_categories", "industry_tags"):
        jobs[column] = jobs[column].fillna("")
    jobs = jobs[list(OUTPUT_COLUMNS)].copy()
    jobs["primary_category"] = pd.Categorical(jobs["primary_category"], categories=list(CATEGORY_IDS))
    jobs["category_method"] = pd.Categorical(jobs["category_method"], categories=list(METHODS))
    jobs["classifier_category"] = pd.Categorical(jobs["classifier_category"], categories=list(CATEGORY_IDS))
    jobs["taxonomy_version"] = jobs["taxonomy_version"].astype("category")
    jobs["categorizer_version"] = jobs["categorizer_version"].astype("category")

    report["categorizer_version"] = str(settings["categorizer_version"])
    report["distinct_titles"] = int(len(rules))
    report["classifier_threshold"] = float(settings["classifier_threshold"])
    return jobs, model, report, proxy


def category_summary(jobs: pd.DataFrame) -> pd.DataFrame:
    """Jobs per category and method, with the share of all jobs."""
    table = (
        jobs.groupby(["primary_category", "category_method"], observed=True).size().rename("jobs").reset_index()
    )
    table["share_of_all_jobs"] = (table["jobs"] / len(jobs)).round(6)
    table["primary_category"] = table["primary_category"].astype(str)
    table["category_method"] = table["category_method"].astype(str)
    return table.sort_values(["primary_category", "category_method"], kind="stable").reset_index(drop=True)


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    config = settings.section("categorize")
    if settings.taxonomy_version != TAXONOMY_VERSION:
        raise ValueError(
            f"config taxonomy version {settings.taxonomy_version} differs from code version {TAXONOMY_VERSION}"
        )
    jobs, model, report, proxy = categorize_jobs(context["clean"], config, settings.random_seed)

    processed = settings.path("processed_dir")
    path = write_parquet(jobs, processed / "job_categories.parquet")
    record.outputs.append(describe_output(path, settings.root, rows=len(jobs)))
    summary = category_summary(jobs)
    path = write_csv(summary, processed / "category_summary.csv")
    record.outputs.append(describe_output(path, settings.root, rows=len(summary)))
    path = write_json(report, processed / "classifier_report.json")
    record.outputs.append(describe_output(path, settings.root))
    for name, table in (("classifier_proxy_by_threshold.csv", proxy["by_threshold"]),
                        ("classifier_proxy_by_category.csv", proxy["by_category"])):
        path = write_csv(table, processed / name)
        record.outputs.append(describe_output(path, settings.root, rows=len(table)))

    shares = jobs["category_method"].value_counts(normalize=True)
    record.metrics = {
        **report,
        **{f"share_{method}": round(float(shares.get(method, 0.0)), 4) for method in METHODS},
    }
    context["categories"] = jobs
    context["category_model"] = model
    return record
