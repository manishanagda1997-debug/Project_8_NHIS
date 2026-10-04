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
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

from ..categorize import categorize_title, category_text, industry_tags
from ..config import Settings
from ..io import write_csv, write_json, write_parquet
from ..manifest import StepRecord, describe_output
from ..taxonomy import CATEGORY_IDS, OTHER, TAXONOMY_VERSION

NAME = "categorize"
DESCRIPTION = "Give every job one job-function category: keyword rules first, a TF-IDF classifier for the rest."

METHODS = ("rule", "two_tasks", "tfidf_classifier", "below_threshold", "no_text")
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
    labels = labels[labels["training_text"].str.len() > 0]      # nothing left once the rule words are hidden
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


def train_classifier(labels: pd.DataFrame, settings: dict[str, Any], seed: int) -> tuple[Pipeline, dict[str, Any]]:
    """Fit on weak labels; report agreement with the rules on a held-out part.

    The held-out score says how often the classifier finds the rule's category
    with the rule words hidden. It is not the accuracy of the categories -
    only human labels can measure that.
    """
    train, test = train_test_split(
        labels, test_size=float(settings["holdout_share"]), random_state=seed, stratify=labels["rule_category"]
    )
    probe = build_classifier(settings, seed).fit(train["training_text"], train["rule_category"])
    agreement = float((probe.predict(test["training_text"]) == test["rule_category"]).mean())
    final = build_classifier(settings, seed).fit(labels["training_text"], labels["rule_category"])
    report = {
        "weak_labels": int(len(labels)),
        "weak_label_categories": int(labels["rule_category"].nunique()),
        "holdout_titles": int(len(test)),
        "holdout_agreement_rule_words_hidden": round(agreement, 4),
    }
    return final, report


def classify(model: Pipeline, texts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Most likely category and its probability for each text."""
    if len(texts) == 0:
        return np.array([], dtype=object), np.array([], dtype=float)
    probabilities = model.predict_proba(texts)
    best = probabilities.argmax(axis=1)
    return model.classes_[best], probabilities[np.arange(len(best)), best]


# ------------------------------------------------------------------ final decision


def decide(rules: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Primary category and method per distinct title (needs classifier columns)."""
    out = rules.copy()
    has_text = out["category_text"].str.len() > 0
    by_rule = out["rule_method"].isin(["rule", "two_tasks"])
    confident = out["classifier_probability"] >= threshold

    out["category_method"] = np.select(
        [by_rule & (out["rule_method"] == "rule"), by_rule, ~has_text, confident],
        ["rule", "two_tasks", "no_text", "tfidf_classifier"],
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
) -> tuple[pd.DataFrame, Pipeline | None, dict[str, Any]]:
    """The whole step on a master table; returns (job table, model, report)."""
    rules = rule_table(frame["title_clean"], int(settings["min_rule_score"]))
    labels = weak_labels(
        rules, int(settings["weak_label_min_score"]), int(settings["weak_label_max_per_category"]), seed
    )
    counts = labels["rule_category"].value_counts()
    usable = counts[counts >= int(settings["min_weak_labels_per_category"])].index
    labels = labels[labels["rule_category"].isin(usable)]
    if labels["rule_category"].nunique() >= 2:
        model, report = train_classifier(labels, settings, seed)
        predicted, probability = classify(model, rules["category_text"])
    else:
        # Too little data to train (only in tiny test projects): every title
        # without a rule match goes to Other / Unclear.
        model, report = None, {"weak_labels": int(len(labels)), "classifier_trained": False}
        predicted, probability = np.full(len(rules), None, dtype=object), np.zeros(len(rules))
    report.setdefault("classifier_trained", True)
    rules["classifier_category"] = predicted
    rules["classifier_probability"] = probability.round(6)
    titles = decide(rules, float(settings["classifier_threshold"]))

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
    return jobs, model, report


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
    jobs, model, report = categorize_jobs(context["clean"], config, settings.random_seed)

    processed = settings.path("processed_dir")
    path = write_parquet(jobs, processed / "job_categories.parquet")
    record.outputs.append(describe_output(path, settings.root, rows=len(jobs)))
    summary = category_summary(jobs)
    path = write_csv(summary, processed / "category_summary.csv")
    record.outputs.append(describe_output(path, settings.root, rows=len(summary)))
    path = write_json(report, processed / "classifier_report.json")
    record.outputs.append(describe_output(path, settings.root))

    shares = jobs["category_method"].value_counts(normalize=True)
    record.metrics = {
        **report,
        **{f"share_{method}": round(float(shares.get(method, 0.0)), 4) for method in METHODS},
    }
    context["categories"] = jobs
    context["category_model"] = model
    return record
