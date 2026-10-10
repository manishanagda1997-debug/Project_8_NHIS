"""Step 5 - pay: keyword-pay associations (Task 1) and client-country rates (Task 4).

Decision D-031. Hourly pay is the midpoint of a complete hourly range
(``eligible_for_hourly_rate_analysis``); fixed-price budgets are analysed
separately and never mixed with hourly rates. ``country`` is the country of
the **client** who posts the job.

Outputs (all reused later by the SQL layer, the API and the dashboard):

* ``pay_keywords_hourly.csv`` / ``pay_keywords_budget.csv``: every supported
  keyword with raw, country-adjusted and country+category-adjusted
  associations (percent, 95% interval, p-value, FDR-adjusted p-value);
* ``pay_keyword_sensitivity.csv``: the hourly keyword associations under the
  agreed sensitivity variants;
* ``pay_countries.csv``: client countries with at least the minimum number of
  rated jobs: median, interquartile range, cluster-bootstrap interval and a
  category-adjusted index;
* ``pay_country_sensitivity.csv``: country medians under the same variants;
* ``pay_prediction.csv``: how much of the pay differences title words can
  predict on titles never seen in training, against simpler baselines.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import OneHotEncoder

from ..config import Settings
from ..io import write_csv
from ..manifest import StepRecord, describe_output
from ..pay import (
    ISO3, adjusted_country_index, bootstrap_mean, bootstrap_median, country_groups, keyword_associations, select_keywords,
)

NAME = "pay"
DESCRIPTION = "Keyword-pay associations (Task 1) and client-country hourly rates (Task 4)."

# Sensitivity variants: (name, row filter column that must be False or None, pay column).
VARIANTS = (
    ("primary", None, "hourly_mid"),
    ("without_extreme_pay", "extreme_hourly_rate_flag", "hourly_mid"),
    ("without_possible_reposts", "possible_repost_3d", "hourly_mid"),
    ("low_end_of_range", None, "hourly_low"),
    ("high_end_of_range", None, "hourly_high"),
)
SENSITIVITY_LAYERS = ("raw", "country_category")
COUNTRY_COLUMNS = ["country", "iso3", "jobs", "title_keys", "median_rate", "median_low", "median_high", "p25_rate",
                   "p75_rate", "mean_rate", "mean_ci_low", "mean_ci_high",
                   "adjusted_index_pct", "adjusted_low_pct", "adjusted_high_pct"]
PREDICTION_COLUMNS = ["model", "test_jobs", "test_title_keys", "mae_usd", "median_abs_error_usd", "r2_log",
                      "title_keys_shared_with_training"]
MIN_PREDICTION_JOBS = 200   # below this (only in tiny test projects) the check is skipped


def hourly_population(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["eligible_for_hourly_rate_analysis"]].reset_index(drop=True)


def budget_population(frame: pd.DataFrame) -> pd.DataFrame:
    rows = frame[frame["eligible_for_budget_analysis"] & (frame["budget"] > 0)]
    return rows.reset_index(drop=True)


def keyword_table(population: pd.DataFrame, value: str, rules: dict[str, Any], keywords: list[str] | None = None
                  ) -> tuple[pd.DataFrame, list[str]]:
    if keywords is None:
        support = select_keywords(population["title_key"], int(rules["min_keyword_jobs"]),
                                  int(rules["min_keyword_title_keys"]), float(rules["keyword_overlap"]))
        keywords = support["keyword"].tolist()
    counts = population["country"].value_counts()
    keep = set(counts[counts >= int(rules["min_country_jobs"])].index)
    groups = country_groups(population["country"], keep)
    table = keyword_associations(population, value, keywords, groups, population["primary_category"])
    return table, keywords


def country_table(population: pd.DataFrame, rules: dict[str, Any], seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # The brief asks for average rates, so the mean is reported next to the
    # median (the primary measure: the rates have a long high tail). Its own
    # generator keeps the median and index draws exactly as before.
    mean_rng = np.random.default_rng([seed, 1])
    counts = population["country"].value_counts()
    keep = sorted(counts[counts >= int(rules["min_country_jobs"])].index)
    rows = []
    for country in keep:
        part = population[population["country"] == country]
        values = part["hourly_mid"].to_numpy(dtype=float)
        low, high = bootstrap_median(values, part["title_key"].to_numpy(), int(rules["median_bootstrap_reps"]), rng)
        mean_low, mean_high = bootstrap_mean(values, part["title_key"].to_numpy(), int(rules["median_bootstrap_reps"]),
                                             mean_rng)
        rows.append({
            "country": country, "iso3": ISO3.get(country, ""), "jobs": len(part),
            "title_keys": int(part["title_key"].nunique()),
            "median_rate": float(np.median(values)), "median_low": low, "median_high": high,
            "p25_rate": float(np.percentile(values, 25)), "p75_rate": float(np.percentile(values, 75)),
            "mean_rate": float(np.mean(values)), "mean_ci_low": mean_low, "mean_ci_high": mean_high,
        })
    table = pd.DataFrame(rows, columns=COUNTRY_COLUMNS[:-3])
    if table.empty:
        return pd.DataFrame(columns=COUNTRY_COLUMNS)

    # Category-adjusted index over every rated job; small countries share one
    # "(other)" group and missing countries their own group, so they inform the
    # category effects without getting an index of their own.
    groups = country_groups(population["country"], set(keep))
    country_codes, names = pd.factorize(groups, sort=True)
    category_codes = pd.factorize(population["primary_category"].astype(str), sort=True)[0]
    index = adjusted_country_index(
        np.log(population["hourly_mid"].to_numpy(dtype=float)), country_codes, category_codes,
        population["title_key"].to_numpy(), int(rules["index_bootstrap_reps"]), rng,
    )
    index.insert(0, "country", list(names))
    return table.merge(index, on="country", how="left").sort_values("jobs", ascending=False).reset_index(drop=True)


def prediction_table(population: pd.DataFrame, rules: dict[str, Any], seed: int) -> pd.DataFrame:
    """Held-out pay prediction: median baseline, then controls, then controls + title words.

    The split is grouped by ``title_key``: no title appears in both training
    and test. The point is to measure how much title words explain, not to
    build the best possible pay model.
    """
    if len(population) < MIN_PREDICTION_JOBS:
        return pd.DataFrame(columns=PREDICTION_COLUMNS)
    splitter = GroupShuffleSplit(n_splits=1, test_size=float(rules["test_share"]), random_state=seed)
    train_idx, test_idx = next(splitter.split(population, groups=population["title_key"]))
    train, test = population.iloc[train_idx], population.iloc[test_idx]
    y_train = np.log(train["hourly_mid"].to_numpy(dtype=float))
    actual = test["hourly_mid"].to_numpy(dtype=float)
    log_actual = np.log(actual)

    controls = OneHotEncoder(handle_unknown="ignore", min_frequency=int(rules["min_country_jobs"]))
    def control_frame(part):
        return pd.DataFrame({"country": part["country"].astype("object").fillna("(missing)").astype(str),
                             "category": part["primary_category"].astype(str)})
    c_train = controls.fit_transform(control_frame(train))
    c_test = controls.transform(control_frame(test))
    words = TfidfVectorizer(ngram_range=(1, 2), min_df=5, sublinear_tf=True, token_pattern=r"[^ ]+")
    w_train = words.fit_transform(train["title_key"].fillna(""))
    w_test = words.transform(test["title_key"].fillna(""))

    alpha = float(rules["ridge_alpha"])
    predictions = {
        "median baseline": np.full(len(test), np.log(np.median(train["hourly_mid"]))),
        "country + category": Ridge(alpha=alpha).fit(c_train, y_train).predict(c_test),
        "country + category + title words": Ridge(alpha=alpha).fit(
            sparse.hstack([c_train, w_train]).tocsr(), y_train).predict(sparse.hstack([c_test, w_test]).tocsr()),
        "title words only": Ridge(alpha=alpha).fit(w_train, y_train).predict(w_test),
    }
    total = float(((log_actual - log_actual.mean()) ** 2).sum())
    rows = []
    for model, predicted in predictions.items():
        rows.append({
            "model": model, "test_jobs": len(test), "test_title_keys": int(test["title_key"].nunique()),
            "mae_usd": float(np.mean(np.abs(np.exp(predicted) - actual))),
            "median_abs_error_usd": float(np.median(np.abs(np.exp(predicted) - actual))),
            "r2_log": 1.0 - float(((log_actual - predicted) ** 2).sum()) / total,
        })
    shared = len(set(train["title_key"]) & set(test["title_key"]))
    table = pd.DataFrame(rows)
    table["title_keys_shared_with_training"] = shared
    return table[PREDICTION_COLUMNS]


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    rules = settings.section("pay")
    seed = settings.random_seed
    columns = ["row_id", "title_key", "country", "hourly_mid", "hourly_low", "hourly_high", "budget",
               "extreme_hourly_rate_flag", "extreme_budget_flag", "possible_repost_3d",
               "eligible_for_hourly_rate_analysis", "eligible_for_budget_analysis"]
    frame = context["clean"][columns].merge(
        context["categories"][["row_id", "primary_category"]], on="row_id", how="left", validate="one_to_one")
    frame["primary_category"] = frame["primary_category"].astype(str)
    hourly = hourly_population(frame)
    budget = budget_population(frame)

    hourly_keywords, keywords = keyword_table(hourly, "hourly_mid", rules)
    budget_keywords, _ = keyword_table(budget, "budget", rules)

    sensitivity, country_variants = [], []
    for name, exclude, value in VARIANTS:
        part = hourly if exclude is None else hourly[~hourly[exclude].astype(bool)].reset_index(drop=True)
        part = part[part[value] > 0].reset_index(drop=True)
        table, _ = keyword_table(part, value, rules, keywords)
        for layer in SENSITIVITY_LAYERS:
            sensitivity.append(table[["keyword", "jobs"]].assign(variant=name, layer=layer, pct=table[f"{layer}_pct"]))
        medians = part.groupby("country", observed=True)[value].agg(["median", "mean", "size"]).reset_index()
        country_variants.append(medians.rename(columns={"median": "median_rate", "mean": "mean_rate", "size": "jobs"})
                                .assign(variant=name))

    countries = country_table(hourly, rules, seed)
    country_variants = pd.concat(country_variants, ignore_index=True)
    country_variants = country_variants[country_variants["country"].isin(countries["country"])]
    prediction = prediction_table(hourly, rules, seed)

    processed = settings.path("processed_dir")
    for name, table in (
        ("pay_keywords_hourly.csv", hourly_keywords),
        ("pay_keywords_budget.csv", budget_keywords),
        ("pay_keyword_sensitivity.csv", pd.concat(sensitivity, ignore_index=True)),
        ("pay_countries.csv", countries),
        ("pay_country_sensitivity.csv", country_variants.sort_values(["variant", "country"]).reset_index(drop=True)),
        ("pay_prediction.csv", prediction),
    ):
        path = write_csv(table.round(6), processed / name)
        record.outputs.append(describe_output(path, settings.root, rows=len(table)))

    record.metrics = {
        "hourly_rated_jobs": int(len(hourly)),
        "budget_jobs": int(len(budget)),
        "hourly_keywords": int(len(hourly_keywords)),
        "budget_keywords": int(len(budget_keywords)),
        "countries_with_enough_jobs": int(len(countries)),
    }
    return record
