"""SQLite database and SQL cross-checks (decision D-037)."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from job_market.database import (
    DATABASE_FILE, build_info, compare, jobs_table, matches_build, query_files, run_query, sql_dir, sql_sha256,
    write_database,
)
from job_market.pipeline import run_pipeline
from job_market.qa.findings import ERROR, Report
from job_market.qa.project_checks import check_database

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCHEMA = (REPO_ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
QUERIES = {path.name[:2]: path.read_text(encoding="utf-8") for path in query_files(REPO_ROOT)}


def make_db(tmp_path, jobs=None, categories=None, labels=None, relevance=None, results=None):
    tables = {"jobs": jobs if jobs is not None else pd.DataFrame(),
              "job_categories": categories if categories is not None else pd.DataFrame(),
              "category_labels": labels if labels is not None else pd.DataFrame(),
              "relevance_labels": relevance if relevance is not None else pd.DataFrame(),
              "recommendation_results": results if results is not None else pd.DataFrame()}
    return write_database(tmp_path / DATABASE_FILE, SCHEMA, tables, {"source_sha256": "s1", "schema_version": "1"})


def jobs_frame(rates: dict[str, list[float]]) -> pd.DataFrame:
    rows = []
    for country, values in rates.items():
        for value in values:
            rows.append({"row_id": len(rows) + 1, "title_key": "x", "posted_date": "2024-03-01", "iso_week": "2024-W09",
                         "contract_type": "hourly", "hourly_low": value, "hourly_high": value, "hourly_mid": value,
                         "budget": None, "country": country, "eligible_for_timeseries": 1,
                         "eligible_for_hourly_rate_analysis": 1})
    return pd.DataFrame(rows)


def test_eight_queries_and_a_schema_exist():
    assert sorted(QUERIES) == [f"{i:02d}" for i in range(1, 9)]
    assert (sql_dir(REPO_ROOT) / "schema.sql").is_file()
    assert sql_sha256(REPO_ROOT) and sql_sha256(REPO_ROOT / "nowhere") is None


def test_median_matches_numpy_for_odd_and_even_groups(tmp_path):
    rates = {"Odd": [5.0, 1.0, 9.0, 3.0, 7.0], "Even": [10.0, 40.0, 20.0, 30.0, 50.0, 60.0], "Small": [1.0]}
    path = make_db(tmp_path, jobs_frame(rates))
    result = run_query(path, QUERIES["06"], {"min_country_jobs": 2}).set_index("country")
    assert set(result.index) == {"Odd", "Even"}                        # below the minimum: left out
    assert result.loc["Odd", "median_rate"] == np.median(rates["Odd"]) == 5.0
    assert result.loc["Even", "median_rate"] == np.median(rates["Even"]) == 35.0
    assert result.loc["Even", "jobs"] == 6


def test_keys_and_checks_reject_bad_rows(tmp_path):
    path = make_db(tmp_path, jobs_frame({"A": [1.0]}))
    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError):                   # duplicate primary key
            connection.execute("INSERT INTO jobs (row_id, posted_date, iso_week, contract_type, "
                               "eligible_for_timeseries, eligible_for_hourly_rate_analysis) "
                               "VALUES (1, '2024-03-01', '2024-W09', 'hourly', 1, 1)")
        with pytest.raises(sqlite3.IntegrityError):                   # relevance must be 0, 1 or 2
            connection.execute("INSERT INTO relevance_labels VALUES ('P01', 'x', 5)")
    finally:
        connection.close()


def test_rebuild_replaces_the_file_without_stale_rows(tmp_path):
    make_db(tmp_path, jobs_frame({"A": [1.0, 2.0, 3.0]}))
    path = make_db(tmp_path, jobs_frame({"B": [4.0]}))
    assert run_query(path, "SELECT country, COUNT(*) AS n FROM jobs GROUP BY country").to_dict("records") == [
        {"country": "B", "n": 1}]
    assert build_info(path) == {"source_sha256": "s1", "schema_version": "1"}


def test_ndcg_query_uses_the_pooled_ideal(tmp_path):
    # Profile P01: pooled judgements 2, 2, 1, 0; method a returns [2, 0], method b returns [2, 2, 1].
    relevance = pd.DataFrame({"profile_id": "P01", "title_key": ["t1", "t2", "t3", "t4"], "relevance": [2, 2, 1, 0]})
    results = pd.DataFrame({"profile_id": "P01", "method": ["a", "a", "b", "b", "b"], "rank": [1, 2, 1, 2, 3],
                            "row_id": [1, 1, 1, 1, 1], "title_key": ["t1", "t4", "t1", "t2", "t3"]})
    path = make_db(tmp_path, jobs_frame({"A": [1.0]}), relevance=relevance, results=results)
    scores = run_query(path, QUERIES["08"]).set_index("method")
    discounts = 1 / np.log2(np.arange(2, 7))
    ideal = 3 * discounts[0] + 3 * discounts[1] + 1 * discounts[2]
    assert scores.loc["a", "ndcg_at_5"] == pytest.approx(3 * discounts[0] / ideal, abs=1e-12)
    assert scores.loc["b", "ndcg_at_5"] == pytest.approx(1.0, abs=1e-12)          # perfect against the pool
    assert scores.loc["a", "strict_precision_at_5"] == pytest.approx(0.2)
    assert scores.loc["b", "strict_precision_at_5"] == pytest.approx(0.4)


def test_compare_rules():
    sql = pd.DataFrame({"k": ["x", "y"], "n": [3, 4], "v": [0.12345649, 1.0]})
    stored = pd.DataFrame({"k": ["x", "y"], "n": [3, 5], "v": [0.123456, 1.0]})
    table = compare(sql, stored, ["k"], ["n"], ["v"])
    assert table.set_index(["key", "value"])["passed"].to_dict() == {
        ("x", "n"): True, ("x", "v"): True, ("y", "n"): False, ("y", "v"): True}
    strict = compare(sql, stored, ["k"], [], ["v"], stored_decimals=None)
    assert not strict.set_index("key").loc["x", "passed"]                 # 5e-7 off without the rounding allowance
    missing = compare(sql, stored.iloc[:1], ["k"], ["n"], [])
    assert not missing["passed"].all()


def test_jobs_table_never_invents_a_country():
    clean = pd.DataFrame({"row_id": [1, 2], "title_key": ["a", None], "posted_date": pd.to_datetime(["2024-03-01"] * 2),
                          "iso_week": ["2024-W09"] * 2, "contract_type": ["hourly", "fixed"], "hourly_low": [1.0, np.nan],
                          "hourly_high": [2.0, np.nan], "hourly_mid": [1.5, np.nan], "budget": [np.nan, 10.0],
                          "country": ["India", np.nan], "eligible_for_timeseries": [True, False],
                          "eligible_for_hourly_rate_analysis": [True, False]})
    table = jobs_table(clean)
    assert table["country"].tolist() == ["India", None]
    assert table["posted_date"].tolist() == ["2024-03-01", "2024-03-01"]
    assert table["eligible_for_timeseries"].tolist() == [1, 0]


def test_pipeline_database_matches_the_build_and_queries_run(mini_project):
    manifest = run_pipeline(mini_project, log=lambda _m: None)
    path = mini_project.path("processed_dir") / DATABASE_FILE
    info = build_info(path)
    assert matches_build(info, manifest) and info["schema_version"] == "1"
    assert "build_id" not in info and "created_at" not in info          # no time-dependent values
    for number, sql in QUERIES.items():
        run_query(path, sql, {"min_country_jobs": 30} if number == "06" else None)    # every query executes
    report = Report("t")
    check_database(mini_project, manifest, report)
    assert not [f for f in report.findings if f.level == ERROR]
    stale = dict(manifest, fingerprints={**manifest["fingerprints"], "code_sha256": "older-code"})
    report = Report("t")
    check_database(mini_project, stale, report)
    assert [f for f in report.findings if f.level == ERROR]

