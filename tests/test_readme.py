"""The README's results match the committed output tables.

Two structured blocks are checked: the Main results table (one row per
assignment task) and the evaluation list. Each number is recomputed from the
committed CSV tables, the run manifest or the executed Notebook 08, rounded
the way the README states it, and must appear in its row. Counts are compared
exactly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:            # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
PROCESSED = REPO_ROOT / "data" / "processed"
TASKS = ["1. Title words and pay", "2. Emerging categories", "3. High-demand roles", "4. Hourly rates by country",
         "5. Job recommendations", "6. Monthly dashboard", "7. Online hiring", "8. Future trends"]


def block(name: str) -> str:
    found = re.search(rf"<!-- {name}:start -->(.*?)<!-- {name}:end -->", README, re.S)
    assert found, f"{name} markers missing from README.md"
    return found.group(1)


def key_rows() -> dict[str, str]:
    rows = [line for line in block("key-results").strip().splitlines() if line.startswith("|")][2:]   # skip header + rule
    table = {}
    for line in rows:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == 3, line
        table[cells[0]] = cells[1] + " | " + cells[2]
    return table


def evaluation_items() -> dict[str, str]:
    items = {}
    for line in block("evaluation").strip().splitlines():
        found = re.match(r"- \*\*(.+?):\*\* (.+)", line.strip())
        assert found, line
        items[found.group(1)] = found.group(2)
    return items


ROWS = key_rows()
ITEMS = evaluation_items()


def csv(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / name)


def counts() -> dict:
    return json.loads((PROCESSED / "run_manifest.json").read_text(encoding="utf-8"))["counts"]


def signed(value: float, decimals: int = 0) -> str:
    return f"{value:+.{decimals}f}"


def expect(row: str, *parts: str) -> None:
    missing = [part for part in parts if part not in row]
    assert not missing, f"{missing} not in: {row}"


def test_one_row_per_task_with_existing_evidence():
    assert list(ROWS) == TASKS
    for task, row in ROWS.items():
        links = re.findall(r"\]\(([^)]+)\)", row)
        assert links, f"no evidence link for {task}"
        for link in links:
            assert (REPO_ROOT / link).is_file(), link


def test_task_1_pay_words():
    kw = csv("pay_keywords_hourly.csv").set_index("keyword")["country_category_pct"]
    expect(ROWS[TASKS[0]], f"\"consultant\" offer about {signed(kw['consultant'])}%",
           f"\"virtual assistant\" about {signed(kw['virtual assistant'])}%")


def test_task_2_emerging_categories():
    t = csv("trend_categories.csv").set_index("primary_category")
    significant = int((t["p_fdr"] < 0.05).sum())
    w, m = t.loc["writing_content"], t.loc["digital_marketing"]
    expect(ROWS[TASKS[1]], f"{significant} of {len(t)} job functions", f"over {counts()['window_days']} days",
           f"{signed(m['change_pp'], 1)} percentage points ({signed(m['relative_change_pct'])}%)",
           f"from {w['start_share_pct']:.1f}% to {w['end_share_pct']:.1f}%", f"({signed(w['relative_change_pct'])}%)")


def test_task_3_high_demand_roles():
    outlook = csv("forecast_demand_outlook.csv")
    top = outlook[(outlook["series"] != "total") & (outlook["series"] != "other_unclear")].sort_values("rank_1_7").iloc[0]
    assert top["series"] == "web_development"
    choice = csv("forecast_model_choice.csv")
    winner = choice[(choice["family"] == "demand") & choice["chosen"]]["model"].item()
    assert winner == "weekday_mean"
    final = csv("forecast_final_evaluation.csv")
    cats = final[(final["family"] == "demand") & (final["series"] != "total") & (final["model"] == winner)]
    total = final[(final["family"] == "demand") & (final["series"] == "total")].set_index("model")["relative_mae"]
    assert total.idxmin() == "seasonal_naive"                      # "The baseline performs better for total jobs"
    expect(ROWS[TASKS[2]], "Web Development has the highest expected demand",
           f"about {int(round(top['forecast_jobs_per_day_1_7'], -2)):,} jobs a day",
           f"{int((cats['relative_mae'] < 1).sum())} of {len(cats)} category series",
           f"mean relative MAE {cats['relative_mae'].mean():.2f}", "The baseline performs better for total jobs")


def test_task_4_countries():
    countries = csv("pay_countries.csv").set_index("country")
    minimum = int(tomllib.loads((REPO_ROOT / "config" / "pipeline.toml").read_text(encoding="utf-8"))["pay"]["min_country_jobs"])
    assert countries["jobs"].min() >= minimum
    us = countries.loc["United States"]
    expect(ROWS[TASKS[3]], f"{len(countries)} client countries", f"at least {minimum} rated hourly jobs",
           f"median offer is USD {us['median_rate']:g} per hour", f"(mean USD {us['mean_rate']:.1f})")


def test_task_5_recommender():
    s = csv("recommend_relevance_summary.csv").set_index("method")
    assert bool(s.loc["tfidf_hybrid", "winner"])
    items = csv("recommend_relevance_items.csv")
    relevant = items[items["relevance"] == 2].groupby("method").size()
    slots = len(items) // items["method"].nunique()
    gap = int(relevant["tfidf_hybrid"] - relevant["tfidf_word"])
    assert gap == 1
    expect(ROWS[TASKS[4]], f"nDCG@5 {s.loc['tfidf_hybrid', 'mean_ndcg']:.3f}",
           f"Precision@5 {s.loc['tfidf_hybrid', 'mean_precision']:.3f}",
           f"{int(s.loc['tfidf_hybrid', 'profiles'])} blind-labelled profiles",
           f"one more relevant result than word TF-IDF in {slots} evaluated slots")


def test_task_6_dashboard():
    monthly = csv("monthly_market_summary.csv")
    assert monthly["partial"].all()
    days = monthly.set_index("month")["days_observed"]
    expect(ROWS[TASKS[5]], f"{len(monthly)} partial months",
           f"{days['2024-02']} days of February and {days['2024-03']} days of March 2024")


def test_task_7_online_hiring():
    series = csv("remote_series_trends.csv").set_index("series")
    hourly, north_america = series.loc["hourly_share"], series.loc["north_america_share"]
    signals = csv("remote_signals_weekly.csv")
    remote = signals[signals["signal"] == "remote / home wording"]
    mentions, jobs = int(remote["title_mentions"].sum()), int(remote["jobs"].sum())
    assert jobs == counts()["window_jobs"]
    expect(ROWS[TASKS[6]], f"from {hourly['start']:.1f}% to {hourly['end']:.1f}%",
           f"about {north_america['mean']:.0f}% of jobs with a known country",
           f"{mentions:,} of {jobs:,} postings ({100 * mentions / jobs:.2f}%) have remote or home wording in the title")


def test_task_8_future_trends():
    outlook = csv("forecast_demand_outlook.csv")
    cats = outlook[outlook["series"] != "total"]
    rising = cats[cats["direction"] == "rising"]
    assert (rising["trend_model"] == "damped_trend").all()
    coverage = csv("forecast_final_coverage.csv")
    pooled = coverage[(coverage["series"] == "pooled") & (coverage["family"] == "demand")].iloc[0]
    expect(ROWS[TASKS[7]], f"{len(rising)} categories meet the rule for a small rise under the damped-trend model",
           f"{int((cats['direction'] == 'no reliable direction').sum())} have no reliable direction",
           f"contain {100 * pooled['coverage']:.1f}% of final-week demand values")


def test_evaluation_data():
    c = counts()
    start = pd.Timestamp(c["timeseries_window_start"])
    end = pd.Timestamp(c["timeseries_window_end"])
    expect(ITEMS["Data"], f"{c['clean_rows']:,} postings", f"{c['window_jobs']:,} jobs", f"{c['window_days']}-day",
           f"{start.day} {start:%b} to {end.day} {end:%b %Y}")


def test_evaluation_categories():
    s = csv("label_evaluation_summary.csv").set_index(["label_set", "subset", "system"]).loc[("blind", "all", "full")]
    expect(ITEMS["Job categories"], f"{100 * s['accuracy']:.1f}%", f"{int(s['correct'])} of {int(s['titles'])} titles",
           f"{100 * s['wilson_low']:.1f}% to {100 * s['wilson_high']:.1f}%")


def test_evaluation_sql_matches_executed_notebook():
    notebook = json.loads((REPO_ROOT / "notebooks" / "08_sql_cross_checks.ipynb").read_text(encoding="utf-8"))
    claims = notebook["cells"][-1]
    text = "".join("".join(o.get("data", {}).get("text/plain", "")) for o in claims.get("outputs", []))
    assert re.search(r"all compared values pass\s+True", text), "Notebook 08 claims output not found"
    assert re.search(r"eight query files\s+True", text)
    assert re.search(r"1,358 compared values in total\s+True", text)
    expect(ITEMS["SQL cross-checks"], "8 SQL queries and 2 extra SQL checks match all 1,358 compared pipeline values")


@pytest.mark.parametrize("image", sorted(set(re.findall(r"!\[[^\]]+\]\(((?!https?://)[^)]+)\)", README))))
def test_readme_images_exist(image):
    assert (REPO_ROOT / image).is_file(), f"README image missing: {image}"
