"""Flask API around the recommender (decision D-035)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("flask")

from job_market.recommend import filter_mask, pay_text, pool_mask, recommend  # noqa: E402
from job_market_web import create_app  # noqa: E402
from job_market_web.service import ASSOCIATION_NOTE, TITLE_NOTE, RecommenderService  # noqa: E402

RULES = {
    "recommender_version": "1.0", "results": 10, "word_min_df": 1, "char_ngram_min": 3, "char_ngram_max": 5,
    "char_min_df": 1, "hybrid_word_weight": 0.5, "related_top_jobs": 50, "related_min_jobs": 2, "related_max_terms": 5,
    "related_max_q": 0.05, "related_min_lift": 2.0, "related_prefix_chars": 5,
    "related_generic_words": ["expert", "developer", "need"],
}
TITLES = [
    "Python data analyst", "Power BI dashboard", "Python pandas script", "SQL report in Power BI", "Data analysis in Excel",
    "Logo design", "Brand identity and logo", "Logo for coffee shop", "WordPress website fix", "WordPress Elementor page",
    "Shopify store setup", "Shopify product listing", "Video editing for YouTube", "Reels video editor",
    "Spanish translation", "English to Spanish translation", "Bookkeeping in QuickBooks", "Xero bookkeeping",
    "React native app", "Flutter mobile app",
]


def jobs_table() -> pd.DataFrame:
    titles = TITLES * 2 + ["Logo design", "Logo design"]
    n = len(titles)
    days = list(range(n))[:n]
    days = [d % 20 for d in days]
    posted = pd.Timestamp("2024-03-01", tz="UTC") + pd.to_timedelta(days, unit="D") + pd.to_timedelta(np.arange(n), unit="min")
    frame = pd.DataFrame({
        "row_id": np.arange(1, n + 1), "title_clean": titles, "title_key": [t.lower() for t in titles],
        "link": [f"https://example.org/job/{i}" for i in range(1, n + 1)], "posted_at": posted,
        "posted_date": posted.tz_localize(None).normalize(), "contract_type": ["hourly", "fixed"] * (n // 2),
        "hourly_low": np.nan, "hourly_high": np.nan, "budget": np.nan, "country": "United States", "pay_signature": "",
        "primary_category": "other_unclear",
    })
    hourly = frame["contract_type"].eq("hourly")
    frame.loc[hourly, "hourly_low"] = 15.0
    frame.loc[hourly, "hourly_high"] = np.where(np.arange(hourly.sum()) % 2 == 0, 35.0, 25.0)
    frame.loc[~hourly, "budget"] = np.where(np.arange((~hourly).sum()) % 2 == 0, 800.0, 100.0)
    # A repost chain: the last two "Logo design" rows share pay and are one day apart.
    frame.loc[[n - 2, n - 1], ["contract_type", "budget", "hourly_low", "hourly_high", "pay_signature"]] = [
        ["fixed", 300.0, np.nan, np.nan, "fixed|300.0"], ["fixed", 300.0, np.nan, np.nan, "fixed|300.0"]]
    frame.loc[n - 2, "posted_at"] = frame.loc[n - 1, "posted_at"] - pd.Timedelta(days=1)
    frame.loc[n - 2, "posted_date"] = frame.loc[n - 2, "posted_at"].tz_localize(None).normalize()
    frame["newest_in_chain"] = True
    frame.loc[n - 2, "newest_in_chain"] = False
    return frame


@pytest.fixture(scope="module")
def service():
    pay = pd.DataFrame({"keyword": ["power bi", "excel"], "country_category_pct": [8.0, 5.0],
                        "country_category_p_fdr": [0.01, 0.01]})
    trend = pd.DataFrame(columns=["keyword", "change_pp", "relative_change_pct", "p_fdr"])
    return RecommenderService.from_tables(jobs_table(), RULES, "tfidf_hybrid", "test-build", pay, trend)


@pytest.fixture(scope="module")
def client(service):
    return create_app(service=service).test_client()


def test_health(client):
    data = client.get("/api/health").get_json()
    assert data["status"] == "ok" and data["method"] == "hybrid_word_character_tfidf"
    assert data["build_id"] == "test-build" and data["indexed_jobs"] == len(jobs_table())


def test_page_renders(client):
    page = client.get("/")
    assert page.status_code == 200 and b"Job" in page.data and b"test-build" in page.data


EXISTING_RECOMMEND_FIELDS = {
    "build_id", "recommender_version", "method", "method_status", "approval_note", "approval_ref", "build_approval_ref",
    "query", "filters_applied", "candidate_pool_size", "returned_count", "results", "related_keywords", "notes"}


def test_recommend_returns_results_and_metadata(client, service):
    data = client.get("/api/recommend?skills=python, pandas, power bi&days=all").get_json()
    assert EXISTING_RECOMMEND_FIELDS <= set(data)                         # earlier fields stay; meta only adds
    assert data["method"] == "hybrid_word_character_tfidf" and data["recommender_version"] == "1.0"
    assert data["returned_count"] == len(data["results"]) > 0
    assert data["candidate_pool_size"] >= data["returned_count"]
    assert data["notes"] == service.notes() and data["notes"][0] == TITLE_NOTE and data["notes"][2] == ASSOCIATION_NOTE
    assert data["filters_applied"]
    first = data["results"][0]
    assert {"rank", "row_id", "title", "link", "pay", "country", "posted_date", "score"} <= set(first)
    assert "data/processed" not in str(data) and "\\" not in str(data)    # no file system paths


def test_api_matches_the_python_recommender(client, service):
    data = client.get("/api/recommend?skills=logo, brand identity&days=all&contract=fixed&min_budget=200").get_json()
    jobs = service.index.jobs
    mask = (pool_mask(jobs, 0) & jobs["newest_in_chain"]).to_numpy() & filter_mask(jobs, contract="fixed", min_budget=200).to_numpy()
    direct = recommend(service.index, "logo, brand identity", "tfidf_hybrid", mask, 10)
    assert [r["row_id"] for r in data["results"]] == direct["row_id"].tolist()


def test_results_are_deterministic(client):
    url = "/api/recommend?skills=wordpress, shopify&days=all"
    assert client.get(url).get_json()["results"] == client.get(url).get_json()["results"]


def test_hourly_filter_uses_the_top_of_the_range(client, service):
    data = client.get("/api/recommend?skills=python, logo, shopify, video, spanish&days=all&contract=hourly&min_hourly=30").get_json()
    assert data["results"]
    assert all(r["pay"] == "$15–$35/hr" for r in data["results"])      # $15-$25 jobs never pass $30
    assert any("maximum of the client's stated hourly range" in line for line in data["filters_applied"])


def test_fixed_filter_and_diversity(client):
    data = client.get("/api/recommend?skills=logo design&days=all&contract=fixed&min_budget=200").get_json()
    assert all(r["contract_type"] == "fixed" for r in data["results"])
    assert all(r["pay"] in ("Fixed: $800", "Fixed: $300") for r in data["results"])
    titles = [r["title"].lower() for r in data["results"]]
    distinct = len(set(titles))
    assert len(set(titles[:distinct])) == distinct            # different titles first; repeats only fill the list


def test_reposts_are_not_recommended(client, service):
    data = client.get("/api/recommend?skills=logo design&days=all").get_json()
    n = len(service.index.jobs)
    ids = [r["row_id"] for r in data["results"]]
    assert n - 1 not in ids                                                 # older posting of the chain (row_id n-1)


@pytest.mark.parametrize("query, message", [
    ("", "skills is required"),
    ("skills=" + "a" * 301, "at most 300"),
    ("skills=!!!", "at least one word"),
    ("skills=python&days=10", "days must be"),
    ("skills=python&contract=weekly", "contract must be"),
    ("skills=python&contract=hourly&min_hourly=0", "positive"),
    ("skills=python&contract=hourly&min_hourly=-5", "positive"),
    ("skills=python&contract=hourly&min_hourly=abc", "must be a number"),
    ("skills=python&contract=fixed&min_hourly=30", "only be used with contract=hourly"),
    ("skills=python&min_hourly=30", "only be used with contract=hourly"),
    ("skills=python&contract=hourly&min_budget=500", "only be used with contract=fixed"),
    ("skills=python&method=keyword", "Unknown parameter"),
])
def test_bad_requests_get_clear_errors(client, query, message):
    response = client.get("/api/recommend?" + query)
    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_similar_excludes_the_job_and_its_reposts(client, service):
    n = len(service.index.jobs)
    data = client.get(f"/api/similar/{n - 1}?days=all").get_json()            # the older posting of the chain
    ids = [r["row_id"] for r in data["results"]]
    assert data["selected"]["row_id"] == n - 1
    assert n - 1 not in ids and n not in ids                                 # itself and its repost
    assert 0 < len(ids) <= 5


def test_similar_errors(client):
    assert client.get("/api/similar/999999").status_code == 404
    assert client.get("/api/similar/999999").get_json() == {"error": "Job not found."}
    assert client.get("/api/similar/abc").status_code == 400
    assert client.get("/api/similar/1?days=3").status_code == 400
    assert client.get("/api/nothing").get_json() == {"error": "Not found."}


def test_related_keywords_or_message(client):
    data = client.get("/api/recommend?skills=bookkeeping&days=all").get_json()
    related = data["related_keywords"]
    assert related["items"] or related["message"].startswith("No strongly supported")


def test_pay_text():
    assert pay_text("hourly", 15.0, 35.0, np.nan) == "$15–$35/hr"
    assert pay_text("hourly", 30.0, np.nan, np.nan) == "$30/hr"
    assert pay_text("hourly", 12.5, 12.5, np.nan) == "$12.50/hr"
    assert pay_text("hourly", np.nan, np.nan, np.nan) == "Rate not stated"
    assert pay_text("fixed", np.nan, np.nan, 1500.0) == "Fixed: $1,500"
    assert pay_text("fixed", np.nan, np.nan, np.nan) == "Budget not stated"


def test_dates_days_years_and_profiles_follow_the_data_and_settings():
    # Another extract: 6 observed days across a year boundary, and 3 profiles in the settings.
    jobs = jobs_table()
    jobs["posted_date"] = pd.Timestamp("2023-12-29") + pd.to_timedelta(np.arange(len(jobs)) % 6, unit="D")
    rules = {**RULES, "profiles": [{"id": "P01"}, {"id": "P02"}, {"id": "P03"}]}
    other = RecommenderService.from_tables(jobs, rules, "tfidf_hybrid", "other-build")
    client = create_app(service=other).test_client()
    data = client.get("/api/recommend?skills=logo design&days=all").get_json()
    assert data["first_day"] == "2023-12-29" and data["last_day"] == "2024-01-03" and data["observed_days"] == 6
    assert data["notes"][1] == "Jobs were posted from 2023-12-29 to 2024-01-03; links may point to closed jobs."
    assert data["filters_applied"][0] == "Jobs posted in all available days (6)."
    page = client.get("/").data.decode("utf-8")
    assert "Upwork market 2023 to 2024" in page and "All 6 days" in page
    assert "relevance test with 3 freelancer profiles" in page
    assert "from 2023-12-29 to 2024-01-03, so links may point to closed jobs" in page
    assert "37" not in page and "February" not in page


def test_single_year_is_shown_once(service):
    assert service.meta()["data_years"] == "2024"
