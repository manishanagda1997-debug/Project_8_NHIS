"""Pay analysis (decision D-031): keyword associations, country rates, helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from job_market.pay import (
    ISO3, MISSING_COUNTRY, OTHER_COUNTRY, adjusted_country_index, benjamini_hochberg, bootstrap_median,
    country_effects, country_groups, keyword_associations, keyword_matrix, percent, select_keywords,
    title_terms, weighted_median, within_association,
)


def test_percent_uses_exp_not_the_approximation():
    assert percent(np.log(2.0)) == pytest.approx(100.0)
    assert percent(0.5) == pytest.approx(64.872, abs=1e-3)      # not 50


def test_title_terms_are_binary_and_keep_cpp():
    terms = title_terms("c++ developer c++ developer for game")
    assert terms == {"c++", "developer", "game", "c++ developer", "developer c++"}
    assert "developer for" not in terms                          # never across a stop word
    assert title_terms(None) == set()


def test_select_keywords_needs_jobs_and_distinct_titles():
    keys = pd.Series(["logo design"] * 10 + [f"logo idea {i}" for i in range(5)])
    table = select_keywords(keys, min_jobs=5, min_title_keys=3, overlap=0.8).set_index("keyword")
    assert "logo" in table.index                                  # 15 jobs, 6 distinct titles
    assert "design" not in table.index                            # 10 jobs but only 1 distinct title


def test_select_keywords_drops_a_word_inside_a_phrase():
    keys = pd.Series([f"social media post {i}" for i in range(9)] + ["social club"])
    table = select_keywords(keys, min_jobs=5, min_title_keys=5, overlap=0.8)
    assert "social media" in set(table["keyword"])
    assert "social" not in set(table["keyword"])                  # 9 of its 10 jobs are "social media"


def test_keyword_matrix_is_binary():
    matrix = keyword_matrix(["seo seo expert", "logo"], ["seo", "logo", "seo expert"]).toarray()
    assert matrix.tolist() == [[1, 0, 1], [0, 1, 0]]


def test_within_association_matches_a_dummy_regression():
    rng = np.random.default_rng(0)
    n = 400
    cells = rng.integers(0, 5, n)
    x = (rng.random(n) < 0.3).astype(float)
    y = 0.4 * x + 0.2 * cells + rng.normal(0, 0.3, n)
    beta, se = within_association(y, x, cells, np.arange(n))
    design = np.column_stack([x, np.eye(5)[cells]])
    expected = np.linalg.lstsq(design, y, rcond=None)[0][0]
    assert beta == pytest.approx(expected, abs=1e-10)
    assert 0 < se < 0.1


def test_cluster_standard_error_grows_when_titles_repeat():
    rng = np.random.default_rng(1)
    base_x = (rng.random(100) < 0.5).astype(float)
    base_y = 0.3 * base_x + rng.normal(0, 0.5, 100)
    # The same 100 titles posted 5 times each: no new information.
    x, y = np.repeat(base_x, 5), np.repeat(base_y, 5)
    cells = np.zeros(500, dtype=int)
    _, naive = within_association(y, x, cells, np.arange(500))
    _, clustered = within_association(y, x, cells, np.repeat(np.arange(100), 5))
    assert clustered > 2 * naive


def test_benjamini_hochberg_known_values():
    adjusted = benjamini_hochberg(np.array([0.01, 0.04, 0.03, 0.20]))
    assert adjusted.tolist() == pytest.approx([0.04, 0.0533333, 0.0533333, 0.20], abs=1e-6)
    assert np.isnan(benjamini_hochberg(np.array([np.nan, 0.5])))[0]


def test_country_groups_keep_missing_apart():
    groups = country_groups(pd.Series(["India", "Chad", None]), {"India"})
    assert groups.tolist() == ["India", OTHER_COUNTRY, MISSING_COUNTRY]


def test_weighted_and_bootstrap_median():
    assert weighted_median(np.array([1.0, 2.0, 3.0]), np.array([1.0, 0.0, 5.0])) == 3.0
    rng = np.random.default_rng(2)
    values = rng.normal(20, 2, 300)
    low, high = bootstrap_median(values, np.arange(300), 300, rng)
    assert low < np.median(values) < high


def test_country_effects_recover_known_differences():
    rng = np.random.default_rng(3)
    n = 3000
    country = rng.integers(0, 3, n)
    category = rng.integers(0, 4, n)
    y = np.array([0.0, 0.5, -0.3])[country] + np.array([0.0, 1.0, 2.0, 0.2])[category] + rng.normal(0, 0.05, n)
    effects = country_effects(y, country, category)
    assert effects[1] - effects[0] == pytest.approx(0.5, abs=0.02)
    assert effects[2] - effects[0] == pytest.approx(-0.3, abs=0.02)


def test_adjusted_index_is_relative_to_the_average_job():
    rng = np.random.default_rng(4)
    n = 2000
    country = rng.integers(0, 2, n)
    category = rng.integers(0, 3, n)
    y = np.array([0.0, np.log(1.5)])[country] + np.array([0.0, 0.7, 1.4])[category]
    table = adjusted_country_index(y, country, category, np.arange(n), reps=20, rng=rng)
    share = np.bincount(country) / n
    logs = np.log1p(table["adjusted_index_pct"].to_numpy() / 100)
    assert float(logs @ share) == pytest.approx(0.0, abs=1e-9)
    assert np.exp(logs[1] - logs[0]) == pytest.approx(1.5, abs=1e-6)


def test_keyword_associations_layers_differ_when_country_confounds():
    # Country A pays double and uses "developer" more: the raw premium is
    # partly a country effect, the country layer removes it.
    rng = np.random.default_rng(5)
    rows = []
    for i in range(2000):
        country = "A" if i % 2 else "B"
        dev = rng.random() < (0.7 if country == "A" else 0.2)
        pay = (40 if country == "A" else 20) * (1.1 if dev else 1.0) * np.exp(rng.normal(0, 0.1))
        rows.append({"title_key": f"{'developer' if dev else 'writer'} job {i}", "pay": pay, "country": country})
    frame = pd.DataFrame(rows)
    table = keyword_associations(frame, "pay", ["developer"], frame["country"], pd.Series(["x"] * len(frame)))
    row = table.iloc[0]
    assert row["raw_pct"] > 40
    assert row["country_pct"] == pytest.approx(10, abs=2)
    assert row["country_p_fdr"] < 0.05


def test_iso3_codes_cover_the_large_markets():
    assert {ISO3[c] for c in ["United States", "United Kingdom", "India", "Philippines"]} == {"USA", "GBR", "IND", "PHL"}


def test_bootstrap_mean_interval_contains_the_mean():
    from job_market.pay import bootstrap_mean
    rng = np.random.default_rng(6)
    values = rng.normal(30, 3, 400)
    low, high = bootstrap_mean(values, np.arange(400) // 2, 300, rng)
    assert low < values.mean() < high


def test_country_mean_uses_the_hourly_midpoint_and_keeps_median_results():
    from job_market.steps.pay import country_table
    rules = {"min_country_jobs": 3, "median_bootstrap_reps": 50, "index_bootstrap_reps": 5}
    population = pd.DataFrame({
        "country": ["A"] * 4 + ["B"] * 3,
        "title_key": [f"t{i}" for i in range(7)],
        "primary_category": ["x", "y", "x", "y", "x", "y", "x"],
        # hourly_low and hourly_high deliberately do not average to hourly_mid in
        # the fourth row, so any other rate definition gives a different mean.
        "hourly_low": [5.0, 10.0, 15.0, 10.0, 10.0, 20.0, 30.0],
        "hourly_high": [15.0, 30.0, 25.0, 30.0, 30.0, 40.0, 50.0],
        "hourly_mid": [10.0, 20.0, 20.0, 100.0, 20.0, 30.0, 40.0],
    })
    table = country_table(population, rules, seed=1).set_index("country")
    assert table.loc["A", "mean_rate"] == pytest.approx(37.5)       # (10 + 20 + 20 + 100) / 4, from hourly_mid
    # Lower bound (10.0), upper bound (25.0) or a rebuilt midpoint (17.5) would all differ.
    assert table.loc["A", "median_rate"] == 20.0
    assert table.loc["B", "mean_rate"] == pytest.approx(30.0)
    assert table.loc["A", "mean_ci_low"] <= 37.5 <= table.loc["A", "mean_ci_high"]
    # Adding the mean leaves the median interval and the index unchanged.
    rerun = country_table(population, rules, seed=1).set_index("country")
    assert table.equals(rerun)
