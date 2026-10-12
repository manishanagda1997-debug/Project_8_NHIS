"""The final report's Key numbers table matches the committed result tables.

Only the structured table between the key-numbers markers is checked: each
row's numbers are recomputed from the committed CSV tables or the run
manifest, rounded the way the report states them, and must appear in that
row. The test also checks that every image the report shows exists and that
every figure the figure script draws is used in the report.
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
REPORT_PATH = REPO_ROOT / "reports" / "final_report.md"
REPORT = REPORT_PATH.read_text(encoding="utf-8")
PROCESSED = REPO_ROOT / "data" / "processed"


def key_rows() -> dict[str, str]:
    block = re.search(r"<!-- key-numbers:start -->(.*?)<!-- key-numbers:end -->", REPORT, re.S)
    assert block, "Key numbers markers missing from reports/final_report.md"
    rows = [line for line in block.group(1).strip().splitlines() if line.startswith("|")][2:]
    table = {}
    for line in rows:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == 3, line
        table[cells[0]] = cells[1]
    return table


ROWS = key_rows()


def csv(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / name)


def counts() -> dict:
    return json.loads((PROCESSED / "run_manifest.json").read_text(encoding="utf-8"))["counts"]


def signed(value: float, decimals: int = 0) -> str:
    return f"{value:+.{decimals}f}"


def nearest(value: float, step: int) -> int:
    return int(round(value / step) * step)


def expect(area: str, *parts: str) -> None:
    row = ROWS[area]
    missing = [part for part in parts if part not in row]
    assert not missing, f"Report Key numbers '{area}': {missing} not in: {row}"


def test_table_has_thirteen_rows():
    assert len(ROWS) == 13


def test_data():
    c = counts()
    start, end = pd.Timestamp(c["timeseries_window_start"]), pd.Timestamp(c["timeseries_window_end"])
    expect("Data", f"{c['raw_rows']:,} postings", f"{c['window_jobs']:,} jobs", f"{c['window_days']}-day",
           f"{start.day} {start:%b} to {end.day} {end:%b %Y}")


def test_pay_words():
    kw = csv("pay_keywords_hourly.csv").set_index("keyword")["country_category_pct"]
    expect("Task 1: pay words", f"\"consultant\" about {signed(kw['consultant'])}%",
           f"\"virtual assistant\" about {signed(kw['virtual assistant'])}%")


def test_emerging_categories():
    t = csv("trend_categories.csv").set_index("primary_category")
    w = t.loc["writing_content"]
    expect("Task 2: emerging categories", f"{int((t['p_fdr'] < 0.05).sum())} job functions",
           f"from {w['start_share_pct']:.1f}% to {w['end_share_pct']:.1f}%", f"({signed(w['relative_change_pct'])}%)")


def test_high_demand():
    o = csv("forecast_demand_outlook.csv")
    functions = o[~o["series"].isin(["total", "other_unclear"])]          # Other / Unclear is not ranked
    top = functions.sort_values("forecast_jobs_per_day_1_7", ascending=False).head(3)
    assert top["series"].tolist() == ["web_development", "design_creative", "digital_marketing"]
    stated = re.search(r"about (\d+), (\d+) and (\d+) jobs a day", ROWS["Task 3: high demand"])
    assert stated, ROWS["Task 3: high demand"]
    for text, value in zip(stated.groups(), top["forecast_jobs_per_day_1_7"]):
        assert abs(int(text) - value) <= 5, (text, value)                 # "about": within 5 jobs a day


def test_forecast_test():
    final = csv("forecast_final_evaluation.csv")
    cats = final[(final["family"] == "demand") & (final["series"] != "total") & (final["model"] == "weekday_mean")]
    assert bool(cats["chosen"].all())
    total = final[(final["family"] == "demand") & (final["series"] == "total")].set_index("model")["relative_mae"]
    assert total.idxmin() == "seasonal_naive"                      # "the baseline performs better for total jobs"
    development = csv("forecast_backtest_by_series.csv")
    dev_total = development[(development["family"] == "demand") & (development["series"] == "total")].set_index("model")["mae"]
    assert dev_total["seasonal_naive"] < dev_total["weekday_mean"]   # ... in development as well
    expect("Tasks 3 and 8: forecast test", f"{int((cats['relative_mae'] < 1).sum())} of {len(cats)} category series",
           f"mean Relative MAE {cats['relative_mae'].mean():.2f}", "the baseline performs better for total jobs")


def test_countries():
    c = csv("pay_countries.csv").set_index("country")
    us = c.loc["United States"]
    settings = tomllib.loads((REPO_ROOT / "config" / "pipeline.toml").read_text(encoding="utf-8"))
    minimum = int(settings["pay"]["min_country_jobs"])
    assert c["jobs"].min() >= minimum
    expect("Task 4: countries", f"{len(c)} client countries", f"at least {minimum} rated hourly jobs",
           f"median USD {us['median_rate']:g} per hour", f"mean USD {us['mean_rate']:.1f}",
           f"adjusted index {signed(us['adjusted_index_pct'])}%")


def test_recommender():
    s = csv("recommend_relevance_summary.csv").set_index("method")
    assert bool(s.loc["tfidf_hybrid", "winner"])
    expect("Task 5: recommender", f"nDCG@5 {s.loc['tfidf_hybrid', 'mean_ndcg']:.3f}",
           f"Precision@5 {s.loc['tfidf_hybrid', 'mean_precision']:.3f}", f"{int(s.loc['tfidf_hybrid', 'profiles'])} blind")
    items = csv("recommend_relevance_items.csv")
    relevant = items[items["relevance"] == 2].groupby("method").size()
    slots = items.groupby("method").size()
    assert (slots == 60).all(), slots                              # 12 profiles x 5 results per method
    assert int(relevant["tfidf_hybrid"] - relevant["tfidf_word"]) == 1
    slots = 60
    expect("Task 5: recommender", f"one more relevant result than word TF-IDF in {slots} evaluated slots")


def test_pool():
    pools = csv("recommend_pool_sizes.csv").set_index("pool_days")
    expect("Task 5: candidate pool", f"{int(pools.loc[14, 'jobs_after_reposts']):,} jobs in the 14-day pool")


def test_dashboard():
    m = csv("monthly_market_summary.csv").set_index("month")
    feb, mar = m.loc["2024-02", "jobs_per_day_weekday_std"], m.loc["2024-03", "jobs_per_day_weekday_std"]
    expect("Task 6: dashboard", f"{feb:,.0f} jobs a day in Feb 2024", f"{mar:,.0f} in Mar 2024",
           f"({100 * (mar / feb - 1):.1f}%)")


def test_online_hiring():
    s = csv("remote_series_trends.csv").set_index("series").loc["hourly_share"]
    assert s["change_high"] < 0                                       # a significant fall
    signals = csv("remote_signals_weekly.csv")
    remote = signals[signals["signal"] == "remote / home wording"]
    assert int(remote["jobs"].sum()) == counts()["window_jobs"] == 229520
    expect("Task 7: online hiring", f"from {s['start']:.1f}% to {s['end']:.1f}%",
           f"remote or home wording in {int(remote['title_mentions'].sum()):,} of {int(remote['jobs'].sum()):,} postings")


def test_outlook():
    o = csv("forecast_demand_outlook.csv").set_index("series").loc["total"]
    expect("Task 8: outlook", f"about {nearest(o['forecast_jobs_per_day_1_7'], 100):,} jobs a day",
           f"{nearest(o['low_1_7'], 10):,} to {nearest(o['high_1_7'], 10):,} for days 1 to 7")
    coverage = csv("forecast_final_coverage.csv")
    pooled = coverage[(coverage["series"] == "pooled") & (coverage["family"] == "demand")].iloc[0]
    expect("Task 8: outlook", f"ranges built the same way contain {100 * pooled['coverage']:.1f}% of final-week demand values")


def test_categories():
    s = csv("label_evaluation_summary.csv").set_index(["label_set", "subset", "system"]).loc[("blind", "all", "full")]
    expect("Job categories", f"{100 * s['accuracy']:.1f}%", f"{int(s['correct'])} of {int(s['titles'])} titles")


def test_sql_claims_in_executed_notebook():
    notebook = json.loads((REPO_ROOT / "notebooks" / "08_sql_cross_checks.ipynb").read_text(encoding="utf-8"))
    text = "".join("".join(o.get("data", {}).get("text/plain", "")) for o in notebook["cells"][-1].get("outputs", []))
    assert re.search(r"all compared values pass\s+True", text)
    assert re.search(r"eight query files\s+True", text)
    assert re.search(r"1,358 compared values in total\s+True", text)
    expect("SQL cross-checks", "8 SQL queries and 2 extra SQL checks match all 1,358 compared pipeline values")


@pytest.mark.parametrize("image", sorted(set(re.findall(r"!\[[^\]]+\]\(((?!https?://)[^)]+)\)", REPORT))))
def test_report_images_exist(image):
    assert (REPORT_PATH.parent / image).is_file(), f"Report image missing: {image}"


def test_every_drawn_figure_is_in_the_report():
    script = (REPO_ROOT / "reports" / "make_figures.py").read_text(encoding="utf-8")
    drawn = set(re.findall(r'save\(fig, "(f\d_[a-z_]+\.png)"\)', script))
    assert len(drawn) == 8
    assert drawn == set(re.findall(r"figures/(f\d_[a-z_]+\.png)", REPORT))
