"""Market dashboard (decision D-036): reads pipeline tables only, and new months appear after a rebuild."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("flask")

from job_market.pipeline import run_pipeline  # noqa: E402
from job_market_web import create_app  # noqa: E402
from job_market_web.build import checked_manifest  # noqa: E402
from job_market_web.dashboard import (  # noqa: E402
    DashboardData, clean_json, context, headline_tiles, load_dashboard, signal_rows,
)
from job_market_web.service import RecommenderService  # noqa: E402

TITLES = ["WordPress website developer", "Logo design for startup", "Python data analyst", "Video editor for YouTube",
          "Shopify store setup", "SEO blog writer", "Virtual assistant for email", "Spanish translation",
          "Facebook ads manager", "Bookkeeping in QuickBooks", "Flutter mobile app", "Machine learning engineer"]
COUNTRIES = ["United States", "United Kingdom", "India", "Canada", "Australia", "Germany"]


def synthetic_raw(start: str, end: str, per_day: int = 24, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for day in pd.date_range(start, end):
        for i in range(per_day):
            hourly = bool(rng.random() < 0.6)
            low = float(rng.choice([10, 15, 20, 25]))
            rows.append({
                "title": f"{TITLES[(i + day.day) % len(TITLES)]} {i % 5}",
                "link": f"https://example.org/{day:%Y%m%d}/{i}",
                "published_date": (day + pd.Timedelta(minutes=60 * i + int(rng.integers(0, 50)))).strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "is_hourly": hourly, "hourly_low": low if hourly else np.nan,
                "hourly_high": low + 20 if hourly else np.nan,
                "budget": np.nan if hourly else float(rng.choice([100, 250, 500])),
                "country": COUNTRIES[int(rng.integers(0, len(COUNTRIES)))],
            })
    return pd.DataFrame(rows)


def tiny_service() -> RecommenderService:
    jobs = pd.DataFrame({"row_id": [1, 2], "title_clean": ["logo design", "python script"], "title_key": ["logo design", "python script"],
                         "link": ["a", "b"], "posted_at": pd.to_datetime(["2024-03-01", "2024-03-02"], utc=True),
                         "posted_date": pd.to_datetime(["2024-03-01", "2024-03-02"]), "contract_type": "fixed",
                         "hourly_low": np.nan, "hourly_high": np.nan, "budget": 100.0, "country": "US", "pay_signature": "",
                         "primary_category": "other_unclear", "newest_in_chain": True})
    rules = {"recommender_version": "1.0", "results": 10, "word_min_df": 1, "char_ngram_min": 3, "char_ngram_max": 5,
             "char_min_df": 1, "hybrid_word_weight": 0.5}
    return RecommenderService.from_tables(jobs, rules, "tfidf_hybrid", "test", None, None)


def build_and_render(settings, raw: pd.DataFrame):
    raw.to_csv(settings.path("raw_csv"), index=False)
    run_pipeline(settings, log=lambda _m: None)
    data = load_dashboard(settings, checked_manifest(settings))
    page = create_app(service=tiny_service(), dashboard=data).test_client().get("/dashboard")
    return data, page


def test_new_month_appears_after_rebuild_without_code_changes(mini_project):
    data, page = build_and_render(mini_project, synthetic_raw("2024-02-16", "2024-03-31"))
    months = data.get("monthly_market_summary.csv")
    assert months["month"].tolist() == ["2024-02", "2024-03"]
    assert page.status_code == 200 and b"Mar 2024" in page.data and b"Apr 2024" not in page.data

    data, page = build_and_render(mini_project, synthetic_raw("2024-02-16", "2024-04-14"))
    months = data.get("monthly_market_summary.csv")
    assert months["month"].tolist() == ["2024-02", "2024-03", "2024-04"]
    assert months["label"].tolist()[-1] == "Apr 2024 (14 days)"
    assert page.status_code == 200 and b"Apr 2024 (14 days)" in page.data
    assert b"2024-04-14" in page.data                                          # data-through date updates
    assert b"Upwork market 2024" in page.data and b"Data: Upwork job posts, 2024-02-16 to 2024-04-14." in page.data
    # A new extract has no scored blind labels, so no accuracy is carried over.
    assert data.blind_labels != "scored" and b"No blind-label accuracy is available for this extract." in page.data
    assert b"sampled titles" not in page.data


def test_dashboard_figures_are_valid_json_and_need_no_internet(mini_project):
    data, page = build_and_render(mini_project, synthetic_raw("2024-02-16", "2024-03-31"))
    html = page.data.decode("utf-8")
    assert "cdn." not in html and "https://cdn" not in html                    # plotly.js and the map are served locally
    payload = html.split('<script id="figures" type="application/json">')[1].split("</script>")[0]
    figures = json.loads(payload)                                               # strict JSON: no NaN
    assert {"weekly_volume", "monthly_categories", "weekly_category"} <= set(figures)
    client = create_app(service=tiny_service(), dashboard=data).test_client()
    assert client.get("/static/world_countries.geojson").status_code == 200
    assert client.get("/static/world_110m.json").status_code == 200


def test_missing_optional_tables_show_not_available():
    months = pd.DataFrame({"month": ["2024-03"], "label": ["Mar 2024 (23 days)"], "first_day": ["2024-03-01"],
                           "last_day": ["2024-03-23"], "days_observed": [23], "partial": [True], "jobs": [100],
                           "jobs_per_day": [4.3], "jobs_per_day_weekday_std": [4.2], "hourly_share_pct": [55.0],
                           "median_hourly_rate": [22.5], "effective_countries": [5.1]})
    data = DashboardData(build_id="x", tables={"monthly_market_summary.csv": months})
    page = create_app(service=tiny_service(), dashboard=data).test_client().get("/dashboard")
    assert page.status_code == 200 and b"Not available in this build" in page.data
    tiles = headline_tiles(data)
    assert len(tiles) == 4 and all(t["change"] is None for t in tiles)          # one month: no change shown
    assert context(data)["figures"] == {}


def test_headline_change_uses_weekday_standardized_volume():
    months = pd.DataFrame({"month": ["2024-02", "2024-03"], "label": ["Feb 2024 (14 days)", "Mar 2024 (23 days)"],
                           "first_day": ["2024-02-16", "2024-03-01"], "last_day": ["2024-02-29", "2024-03-23"],
                           "days_observed": [14, 23], "partial": [True, True], "jobs": [1, 1],
                           "jobs_per_day": [100.0, 90.0], "jobs_per_day_weekday_std": [100.0, 95.0],
                           "hourly_share_pct": [58.0, 57.0], "median_hourly_rate": [22.5, 22.5],
                           "effective_countries": [5.25, 5.19]})
    tiles = headline_tiles(DashboardData(build_id="x", tables={"monthly_market_summary.csv": months}))
    assert tiles[0]["change"] == "-5.0%"                                        # standardized, not the raw -10%
    assert tiles[1]["change"] == "-1.0 pp" and tiles[2]["change"] == "+$0"


def test_clean_json_replaces_nan():
    assert clean_json({"a": [1.0, float("nan")], "b": np.float64(2.5)}) == {"a": [1.0, None], "b": 2.5}


def test_dashboard_not_loaded_returns_503():
    assert create_app(service=tiny_service(), dashboard=None).test_client().get("/dashboard").status_code == 503


def blind_page(blind_labels, rows):
    months = pd.DataFrame({"month": ["2024-03"], "label": ["Mar 2024 (23 days)"], "first_day": ["2024-03-01"],
                           "last_day": ["2024-03-23"], "days_observed": [23], "partial": [True], "jobs": [100],
                           "jobs_per_day": [4.3], "jobs_per_day_weekday_std": [4.2], "hourly_share_pct": [55.0],
                           "median_hourly_rate": [22.5], "effective_countries": [5.1]})
    summary = pd.DataFrame(rows, columns=["label_set", "subset", "system", "titles", "correct", "accuracy"])
    data = DashboardData(build_id="x", tables={"monthly_market_summary.csv": months,
                                               "label_evaluation_summary.csv": summary}, blind_labels=blind_labels)
    return create_app(service=tiny_service(), dashboard=data).test_client().get("/dashboard").data.decode("utf-8")


ROWS = [["blind", "all", "full", 350, 241, 0.6886], ["blind", "all", "rules_only", 350, 240, 0.6857],
        ["dev", "all", "full", 150, 120, 0.8]]
UNAVAILABLE = "No blind-label accuracy is available for this extract."


def test_blind_agreement_comes_from_the_exact_saved_row_when_scored():
    page = blind_page("scored", ROWS)
    assert "Primary categories match blind human labels on 68.9% of 350 sampled titles from this extract." in page
    assert UNAVAILABLE not in page
    assert "Data: Upwork job posts, 2024-03-01 to 2024-03-23." in page


def test_blind_agreement_is_hidden_when_not_scored_or_the_row_is_missing():
    for status, rows in (("labels belong to another extract: x", ROWS), (None, ROWS), ("scored", ROWS[1:])):
        page = blind_page(status, rows)
        assert UNAVAILABLE in page and "sampled titles" not in page and "68.9" not in page


def test_effective_countries_direction_is_the_reverse_of_the_hhi_direction():
    # The row shows 1 / HHI, so the HHI's rising and falling swap; the other labels stay.
    cases = [("hhi", "rising", "Falling"), ("hhi", "falling", "Rising"), ("hhi", "stable", "Stable"),
             ("hhi", "no reliable direction", "No reliable direction"), ("hourly_share", "rising", "Rising")]
    for series, direction, shown in cases:
        table = pd.DataFrame({"series": [series], "recent_value": [0.2], "forecast_1_14": [0.25],
                              "direction": [direction]})
        rows = signal_rows(DashboardData(build_id="x", tables={"forecast_signals_outlook.csv": table}))
        assert rows[0]["direction"] == shown


def test_every_dashboard_table_scrolls_inside_its_card():
    import re

    months = pd.DataFrame({"month": ["2024-03"], "label": ["Mar 2024 (23 days)"], "first_day": ["2024-03-01"],
                           "last_day": ["2024-03-23"], "days_observed": [23], "partial": [True], "jobs": [100],
                           "jobs_per_day": [4.3], "jobs_per_day_weekday_std": [4.2], "hourly_share_pct": [55.0],
                           "median_hourly_rate": [22.5], "effective_countries": [5.1]})
    countries = pd.DataFrame({"month": ["2024-03"], "country": ["India"], "rank": [1], "share_pct": [6.5]})
    outlook = pd.DataFrame({"series": ["web_development"], "rank_1_7": [1], "recent_jobs_per_day": [899.0],
                            "forecast_jobs_per_day_1_7": [897.0], "low_1_7": [846.0], "high_1_7": [951.0],
                            "direction": ["rising"]})
    signals = pd.DataFrame({"series": ["hhi"], "recent_value": [0.19], "forecast_1_14": [0.19], "direction": ["stable"]})
    data = DashboardData(build_id="x", tables={"monthly_market_summary.csv": months, "monthly_country_share.csv": countries,
                                               "forecast_demand_outlook.csv": outlook,
                                               "forecast_signals_outlook.csv": signals})
    html = create_app(service=tiny_service(), dashboard=data).test_client().get("/dashboard").data.decode("utf-8")
    assert "846 to 951" in html
    tables = re.findall(r"<table\b", html)
    wrapped = re.findall(r'<div class="table-scroll">\s*<table\b', html)
    assert len(tables) == 3 and len(wrapped) == 3
    assert ".table-scroll { overflow-x: auto; }" in html
    assert ".row2 > section.card { margin-bottom: 0; min-width: 0; }" in html     # grid columns may shrink
    empty = create_app(service=tiny_service(), dashboard=DashboardData(build_id="x", tables={
        "monthly_market_summary.csv": months})).test_client().get("/dashboard").data.decode("utf-8")
    assert "table-scroll\">" not in empty                              # no empty wrappers without data
