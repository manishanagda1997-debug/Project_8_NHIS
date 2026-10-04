"""Job recommendations (decision D-034)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from job_market.labels import LabelSheetError, read_relevance_sheet, write_relevance_sheet
from job_market.recommend import (
    build_index, choose_winner, describe_keyword, diverse_top, filter_mask, ndcg_at_k, newest_in_repost_chain,
    pool_mask, recommend, related_keywords, similar_jobs, stated_hourly_max, strict_precision_at_k, word_analyzer,
)
from job_market.steps.recommend import relevance_items, score_relevance

RULES = {"word_min_df": 1, "char_ngram_min": 3, "char_ngram_max": 5, "char_min_df": 1, "hybrid_word_weight": 0.5}


def jobs_table(titles: list[str], days: list[int] | None = None) -> pd.DataFrame:
    n = len(titles)
    days = days or list(range(n))
    posted = pd.Timestamp("2024-03-01", tz="UTC") + pd.to_timedelta(days, unit="D")
    return pd.DataFrame({
        "row_id": np.arange(1, n + 1), "title_clean": titles, "title_key": [t.lower() for t in titles],
        "posted_at": posted, "posted_date": posted.tz_localize(None).normalize(), "contract_type": "hourly",
        "hourly_low": 10.0, "hourly_high": 20.0, "budget": np.nan, "country": "US", "pay_signature": "",
    })


def test_newest_posting_of_a_repost_chain_is_kept():
    frame = jobs_table(["logo design", "logo design", "logo design", "web app"], days=[0, 1, 9, 1])
    frame["pay_signature"] = ["h|10|20"] * 4
    keep = newest_in_repost_chain(frame, days=3)
    assert keep.tolist() == [False, True, True, True]       # day 0 has a repost on day 1; day 9 is too far
    frame.loc[1, "country"] = "UK"
    assert newest_in_repost_chain(frame, days=3).tolist() == [True, True, True, True]


def test_jobs_without_pay_terms_are_never_reposts():
    frame = jobs_table(["logo design", "logo design"], days=[0, 1])
    assert newest_in_repost_chain(frame).all()


def test_pool_uses_the_final_observed_days():
    frame = jobs_table(["a b"] * 5, days=[0, 1, 2, 3, 4])
    assert pool_mask(frame, 2).tolist() == [False, False, False, True, True]
    assert pool_mask(frame, 0).all()


def test_hourly_filter_uses_the_top_of_the_stated_range():
    frame = jobs_table(["a"] * 6)
    frame["hourly_low"] = [15.0, 15.0, np.nan, 30.0, np.nan, np.nan]
    frame["hourly_high"] = [35.0, 25.0, np.nan, np.nan, np.nan, np.nan]
    frame.loc[4:, "contract_type"] = "fixed"
    frame.loc[4:, "budget"] = [800.0, 100.0]
    assert stated_hourly_max(frame).tolist()[:2] == [35.0, 25.0]
    # $15-35 passes, $15-25 fails, no rate fails, one stated rate uses it, fixed-price never compared
    assert filter_mask(frame, min_hourly=30).tolist() == [True, False, False, True, False, False]
    assert filter_mask(frame, min_budget=500).tolist() == [False, False, False, False, True, False]
    assert filter_mask(frame, contract="fixed").sum() == 2


def test_word_analyzer_does_not_invent_phrases():
    terms = word_analyzer("web developer needed for wordpress")
    assert "developer wordpress" not in terms
    assert {"web", "developer", "wordpress", "web developer"} <= set(terms)


def test_keyword_method_counts_whole_words():
    index = build_index(jobs_table(["python data analyst", "python developer", "logo design"]), RULES)
    top = recommend(index, "python, data analysis", "keyword", np.ones(3, bool), 10)
    assert top["row_id"].tolist() == [1, 2]                 # 2 words, then 1 word; no zero scores
    assert top["rank"].tolist() == [1, 2]


@pytest.mark.parametrize("method", ["keyword", "tfidf_word", "tfidf_hybrid"])
def test_diversity_and_newer_first(method):
    titles = ["shopify store setup", "shopify store setup", "shopify store setup", "shopify expert"]
    index = build_index(jobs_table(titles, days=[0, 1, 2, 3]), RULES)
    top = recommend(index, "shopify store setup", method, np.ones(4, bool), 2)
    assert top["title_key"].nunique() == 2                  # one copy of the repeated title
    assert top["row_id"].iloc[0] == 3                       # tie between copies -> newest
    full = recommend(index, "shopify store setup", method, np.ones(4, bool), 4)
    assert len(full) == 4                                    # too few distinct titles: copies fill the list
    assert full["score"].is_monotonic_decreasing


def test_diverse_top_keeps_score_order():
    ranked = pd.DataFrame({"title_key": ["a", "a", "b"], "score": [3.0, 2.0, 1.0]}, index=[10, 11, 12])
    assert diverse_top(ranked, 3).index.tolist() == [10, 11, 12]
    assert diverse_top(ranked, 2).index.tolist() == [10, 12]


def test_similar_jobs_excludes_the_job_itself_and_respects_the_mask():
    index = build_index(jobs_table(["logo design", "logo design brand", "brand logo", "python script"]), RULES)
    mask = np.array([True, True, False, True])
    top = similar_jobs(index, 1, "tfidf_word", mask, 5)
    assert 1 not in top["row_id"].tolist() and 3 not in top["row_id"].tolist()
    assert top["row_id"].iloc[0] == 2
    with pytest.raises(KeyError):
        similar_jobs(index, 99, "tfidf_word", mask, 5)


def test_unknown_method_fails():
    index = build_index(jobs_table(["a b c", "a b"]), RULES)
    with pytest.raises(ValueError):
        recommend(index, "a", "magic", np.ones(2, bool), 2)


def test_ndcg_and_strict_precision():
    pooled = [2, 2, 1, 0, 0, 0]
    assert ndcg_at_k([2, 2, 1, 0, 0], pooled, 5) == pytest.approx(1.0)
    assert ndcg_at_k([0, 0, 1, 2, 2], pooled, 5) < ndcg_at_k([2, 2, 1, 0, 0], pooled, 5)
    assert ndcg_at_k([2, 2], pooled, 5) < 1.0                # missing positions count as 0
    assert ndcg_at_k([0, 0], [0, 0, 0], 5) == 0.0
    assert strict_precision_at_k([2, 1, 1, 2, 0], 5) == pytest.approx(0.4)   # partly relevant does not count
    assert strict_precision_at_k([2, 2], 5) == pytest.approx(0.4)


def test_winner_rule():
    methods = ["keyword", "tfidf_word", "tfidf_hybrid"]
    def summary(ndcg, precision):
        return pd.DataFrame({"method": methods, "mean_ndcg": ndcg, "mean_precision": precision})
    assert choose_winner(summary([0.5, 0.6, 0.7], [0.9, 0.9, 0.1]), methods, 0.02)[0] == "tfidf_hybrid"
    winner, reason = choose_winner(summary([0.5, 0.69, 0.70], [0.9, 0.6, 0.4]), methods, 0.02)
    assert winner == "tfidf_word" and "Precision" in reason
    winner, reason = choose_winner(summary([0.70, 0.70, 0.71], [0.5, 0.5, 0.5]), methods, 0.02)
    assert winner == "keyword" and "simpler" in reason


def test_related_keywords_need_evidence_and_relation():
    titles = pd.Series(["power bi dashboard", "power bi report", "excel power bi", "sql report", "tableau"])
    pay = pd.DataFrame({"keyword": ["power bi", "tableau", "excel", "sql"], "country_category_pct": [12.0, 30.0, -5.0, 8.0],
                        "country_category_p_fdr": [0.01, 0.01, 0.01, 0.01]})
    trend = pd.DataFrame({"keyword": ["dashboard"], "change_pp": [0.2], "relative_change_pct": [15.0], "p_fdr": [0.2]})
    table = related_keywords(titles, "python, sql", pay, trend, min_jobs=2, max_terms=5, max_q=0.05)
    # tableau: too few related jobs; excel: negative; sql: already in the profile; dashboard: not significant
    assert table["keyword"].tolist() == ["power bi"]
    text = describe_keyword(table.iloc[0])
    assert "associated with" in text and "learn" not in text.lower()


def test_relevance_items_are_blind_and_unique():
    results = pd.DataFrame({
        "profile_id": ["P01"] * 4 + ["P02"], "method": ["keyword", "tfidf_word", "keyword", "tfidf_word", "keyword"],
        "rank": [1, 1, 2, 2, 1], "row_id": [1, 2, 3, 4, 5], "title_key": ["a", "a", "b", "c", "a"],
        "title": ["A", "A!", "B", "C", "A"], "posted_at": pd.to_datetime(["2024-03-01", "2024-03-02", "2024-03-01",
                                                                         "2024-03-01", "2024-03-01"])})
    items = relevance_items(results, seed=1)
    assert list(items.columns) == ["item_id", "profile_id", "title", "title_key"]
    assert len(items) == 4                                   # (P01,a) once, shown with the newest title
    assert items.loc[(items["profile_id"] == "P01") & (items["title_key"] == "a"), "title"].item() == "A!"
    labels = items.assign(relevance=[2, 1, 0, 2])
    rules = {"eval_top_k": 5, "methods": ["keyword", "tfidf_word"], "tie_threshold": 0.02,
             "profiles": [{"id": "P01", "name": "x"}, {"id": "P02", "name": "y"}]}
    scored, by_profile, summary, winner, _ = score_relevance(results, labels, rules)
    assert set(by_profile["method"]) == {"keyword", "tfidf_word"} and winner in rules["methods"]
    with pytest.raises(LabelSheetError):
        score_relevance(results, labels.iloc[1:], rules)


def test_relevance_sheet_round_trip(tmp_path):
    pytest.importorskip("openpyxl")
    items = pd.DataFrame({"item_id": ["R001", "R002"], "profile_id": ["P01", "P01"], "title": ["A", "B"],
                          "title_key": ["a", "b"]})
    path = write_relevance_sheet(items, [{"id": "P01", "name": "x", "skills": "a"}], tmp_path / "rel.xlsx")
    with pytest.raises(FileExistsError):
        write_relevance_sheet(items, [], path)
    with pytest.raises(LabelSheetError):
        read_relevance_sheet(path)                           # nothing judged yet
    assert read_relevance_sheet(path, require_complete=False)["relevance"].isna().all()
    from openpyxl import load_workbook
    book = load_workbook(path)
    book["relevance"]["D2"] = 2
    book["relevance"]["D3"] = 5
    book.save(path)
    with pytest.raises(LabelSheetError):
        read_relevance_sheet(path, require_complete=False)
    book["relevance"]["D3"] = 0
    book.save(path)
    assert read_relevance_sheet(path)["relevance"].tolist() == [2, 0]


def test_related_keywords_refinement_rules():
    titles = pd.Series(["react native app", "react developer", "react app expert", "flutter app", "flutter expert"])
    market = pd.Series(["react website"] * 2 + ["logo design"] * 18 + ["app expert"] * 5)
    pay = pd.DataFrame({"keyword": ["react", "expert", "app developer", "flutter developer", "app"],
                        "country_category_pct": [5.0, 12.0, 3.0, 4.0, 2.0], "country_category_p_fdr": [0.01] * 5})
    trend = pd.DataFrame(columns=["keyword", "change_pp", "relative_change_pct", "p_fdr"])
    table = related_keywords(titles, "flutter, ios app development", pay, trend, min_jobs=1, max_terms=5, max_q=0.05,
                             market_titles=market, min_lift=2.0, generic_words={"expert", "developer"}, prefix_chars=5)
    # expert: generic; app developer: "app" in profile, "developer" generic (and ~ "development");
    # flutter developer: nothing new; app: in profile; react: new, lift (3/5)/(2/25) = 7.5
    assert table["keyword"].tolist() == ["react"]
    assert table["lift"].iloc[0] == pytest.approx(7.5)
    strict = related_keywords(titles, "flutter", pay, trend, 1, 5, 0.05, market_titles=market, min_lift=10.0,
                              generic_words={"expert"}, prefix_chars=5)
    assert "react" not in strict["keyword"].tolist()          # not disproportionate enough
    assert related_keywords(titles, "react, flutter, app", pay, trend, 1, 5, 0.05, market_titles=market,
                            min_lift=2.0, generic_words={"expert", "developer"}, prefix_chars=5).empty   # no result is valid
