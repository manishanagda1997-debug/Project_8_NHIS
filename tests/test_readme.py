"""The README's Key results table matches the committed output tables.

Only the structured table between the key-results markers is checked: each
row's numbers are recomputed from the committed CSV tables, the run manifest
or the executed Notebook 08, rounded the way the README states them, and must
appear in that row. Counts are compared exactly.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
PROCESSED = REPO_ROOT / "data" / "processed"


def key_rows() -> dict[str, str]:
    block = re.search(r"<!-- key-results:start -->(.*?)<!-- key-results:end -->", README, re.S)
    assert block, "Key results markers missing from README.md"
    rows = [line for line in block.group(1).strip().splitlines() if line.startswith("|")][2:]   # skip header + rule
    table = {}
    for line in rows:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == 3, line
        table[cells[0]] = cells[1] + " | " + cells[2]
    return table


ROWS = key_rows()


def csv(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / name)


def counts() -> dict:
    return json.loads((PROCESSED / "run_manifest.json").read_text(encoding="utf-8"))["counts"]


def signed(value: float, decimals: int = 0) -> str:
    return f"{value:+.{decimals}f}"


def expect(area: str, *parts: str) -> None:
    row = ROWS[area]
    missing = [part for part in parts if part not in row]
    assert not missing, f"README Key results '{area}': {missing} not in: {row}"


def test_table_has_eight_rows_with_existing_evidence():
    assert len(ROWS) == 8
    for area, row in ROWS.items():
        links = re.findall(r"\]\(([^)]+)\)", row)
        assert links, f"no evidence link for {area}"
        for link in links:
            assert (REPO_ROOT / link).is_file(), link


def test_data():
    c = counts()
    start = pd.Timestamp(c["timeseries_window_start"])
    end = pd.Timestamp(c["timeseries_window_end"])
    expect("Data", f"{c['clean_rows']:,} postings", f"{c['window_jobs']:,} jobs", f"{c['window_days']}-day",
           f"{start.day} {start:%b} - {end.day} {end:%b %Y}")


def test_pay_words():
    kw = csv("pay_keywords_hourly.csv").set_index("keyword")["country_category_pct"]
    expect("Task 1: pay words", f"\"consultant\" offer about {signed(kw['consultant'])}%",
           f"\"virtual assistant\" about {signed(kw['virtual assistant'])}%")


def test_emerging_categories():
    t = csv("trend_categories.csv").set_index("primary_category")
    significant = int((t["p_fdr"] < 0.05).sum())
    w, m = t.loc["writing_content"], t.loc["digital_marketing"]
    expect("Task 2: emerging categories", f"{significant} job functions",
           f"from {w['start_share_pct']:.1f}% to {w['end_share_pct']:.1f}%", f"({signed(w['relative_change_pct'])}%)",
           f"{signed(m['change_pp'], 1)} percentage points ({signed(m['relative_change_pct'])}%)")


def test_forecasts():
    choice = csv("forecast_model_choice.csv")
    winner = choice[(choice["family"] == "demand") & choice["chosen"]]["model"].item()
    assert winner == "weekday_mean"
    final = csv("forecast_final_evaluation.csv")
    cats = final[(final["family"] == "demand") & (final["series"] != "total") & (final["model"] == winner)]
    total = final[(final["family"] == "demand") & (final["series"] == "total")].set_index("model")["relative_mae"]
    assert total.idxmin() == "seasonal_naive"                      # "for total volume the baseline is better"
    expect("Tasks 3 and 8: forecasts", f"{int((cats['relative_mae'] < 1).sum())} of {len(cats)} category series",
           f"mean relative MAE {cats['relative_mae'].mean():.2f}")


def test_countries():
    countries = csv("pay_countries.csv").set_index("country")
    minimum = int(tomllib.loads((REPO_ROOT / "config" / "pipeline.toml").read_text(encoding="utf-8"))["pay"]["min_country_jobs"])
    assert countries["jobs"].min() >= minimum
    expect("Task 4: countries", f"{len(countries)} client countries", f"at least {minimum} rated hourly jobs",
           f"${countries.loc['United States', 'median_rate']:g}/h")


def test_categories():
    s = csv("label_evaluation_summary.csv").set_index(["label_set", "subset", "system"]).loc[("blind", "all", "full")]
    expect("Job categories", f"{100 * s['accuracy']:.1f}%", f"{int(s['correct'])} of {int(s['titles'])} titles",
           f"{100 * s['wilson_low']:.1f}%-{100 * s['wilson_high']:.1f}%")


def test_recommender():
    s = csv("recommend_relevance_summary.csv").set_index("method")
    assert bool(s.loc["tfidf_hybrid", "winner"])
    expect("Task 5: recommender", f"nDCG@5 {s.loc['tfidf_hybrid', 'mean_ndcg']:.3f}",
           f"Precision@5 {s.loc['tfidf_hybrid', 'mean_precision']:.3f}", f"{int(s.loc['tfidf_hybrid', 'profiles'])} blind",
           f"keyword baseline nDCG@5 {s.loc['keyword', 'mean_ndcg']:.3f}")


def test_sql_claims_in_executed_notebook():
    notebook = json.loads((REPO_ROOT / "notebooks" / "08_sql_cross_checks.ipynb").read_text(encoding="utf-8"))
    claims = notebook["cells"][-1]
    text = "".join("".join(o.get("data", {}).get("text/plain", "")) for o in claims.get("outputs", []))
    assert re.search(r"all compared values pass\s+True", text), "Notebook 08 claims output not found"
    assert re.search(r"eight query files\s+True", text)
    expect("SQL cross-checks", "8 SQL queries reproduce every compared pipeline value")


@pytest.mark.parametrize("image", sorted(set(re.findall(r"!\[[^\]]+\]\(((?!https?://)[^)]+)\)", README))))
def test_readme_images_exist(image):
    assert (REPO_ROOT / image).is_file(), f"README image missing: {image}"
