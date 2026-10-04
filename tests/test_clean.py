"""Cleaning step: every rule from decisions D-012 to D-019, tested on small
hand-made data where the right answer is known in advance."""

import numpy as np
import pandas as pd
import pytest

from job_market.steps.clean import (
    build_master,
    clean_title,
    day_quality,
    earlier_match_within,
    pay_signature,
    repair_mojibake,
    title_key,
    title_script,
)
from job_market.steps.ingest import parse_timestamps

RULES = {
    "reference_day_share": 0.5,
    "reference_quantile": 0.9,
    "min_day_ratio": 0.9,
    "weak_hour_share": 0.3,
    "extreme_quantile": 0.999,
    "repeat_windows_days": [1, 3, 7],
    "primary_repeat_window_days": 3,
}


def job(title="Data analyst", hours=0, hourly=True, low=20.0, high=40.0, budget=np.nan, country="India", link=None):
    """One raw row; ``hours`` is the posting time in hours after 2024-03-01 00:00 UTC."""
    ts = pd.Timestamp("2024-03-01", tz="UTC") + pd.Timedelta(hours=hours)
    return {
        "title": title,
        "link": link or f"https://www.upwork.com/jobs/{abs(hash((title, hours, country, low, budget)))}",
        "published_date": ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
        "is_hourly": hourly,
        "hourly_low": low if hourly else np.nan,
        "hourly_high": high if hourly else np.nan,
        "budget": np.nan if hourly else budget,
        "country": country,
    }


def master(rows):
    raw = pd.DataFrame(rows)
    for column in ("hourly_low", "hourly_high", "budget"):
        raw[column] = raw[column].astype("float64")
    raw["is_hourly"] = raw["is_hourly"].astype(bool)
    frame, extra = build_master(raw, parse_timestamps(raw["published_date"]), RULES)
    return frame, extra


# ------------------------------------------------------------------ titles


def test_html_entities_decode_including_double_encoding():
    assert clean_title("SEO &amp; content")[0] == "SEO & content"
    assert clean_title("Q&amp;amp;A writer")[0] == "Q&A writer"
    assert clean_title("Tool &quot;Ninja&quot;")[1] is True


def test_mojibake_from_cp1252_is_repaired():
    text, repaired = repair_mojibake("Werbetexter f\u00c3\u00bcr eine Homepage")
    assert (text, repaired) == ("Werbetexter f\u00fcr eine Homepage", True)


def test_emoji_mojibake_from_cp1254_is_repaired():
    text, repaired = repair_mojibake("Framer Expert Needed \u011f\u0178\u201d\u00a5")
    assert repaired and text == "Framer Expert Needed \U0001F525"


@pytest.mark.parametrize("text", ["Werbetexter f\u00fcr Homepage", "Dise\u00f1o web", "\u0420\u0430\u0431\u043e\u0442\u0430", "Plain ASCII"])
def test_correct_text_is_never_changed(text):
    assert repair_mojibake(text) == (text, False)


def test_whitespace_and_nfkc_normalisation():
    assert clean_title("  React   developer\u3000needed ")[0] == "React developer needed"
    assert clean_title("\uff2c\uff4f\uff47\uff4f design")[0] == "Logo design"  # full-width letters


def test_missing_title_stays_missing():
    assert clean_title(None) == (None, False, False)
    assert clean_title(np.nan) == (None, False, False)


def test_title_key_ignores_case_punctuation_and_emoji_but_keeps_letters():
    assert title_key("Logo Design!! \U0001F680") == "logo design"
    assert title_key("UI/UX designer") == "ui ux designer"
    assert title_key("\u0420\u0430\u0431\u043e\u0442\u0430 SEO") == "\u0440\u0430\u0431\u043e\u0442\u0430 seo"
    assert title_key(None) == ""


@pytest.mark.parametrize(
    ("title", "key"),
    [
        ("C++ Developer", "c++ developer"),
        ("C# Developer", "c# developer"),
        ("C Developer", "c developer"),
        ("A+ Content", "a+ content"),
        ("Audio + Video", "audio video"),
        ("Branding + Logo", "branding logo"),
        ("Node.js Developer", "node js developer"),
        ("C#/.NET", "c# net"),
        ("#hiring now", "hiring now"),
        ("aws_data engineer", "aws data engineer"),
    ],
)
def test_title_key_keeps_plus_and_hash_only_when_attached(title, key):
    assert title_key(title) == key


def test_c_family_titles_are_not_one_repeat_key():
    assert len({title_key("C++ Developer"), title_key("C# Developer"), title_key("C Developer")}) == 3


@pytest.mark.parametrize(
    "text, script",
    [
        ("Senior React Developer", "latin"),
        ("\u0420\u0430\u0431\u043e\u0442\u0430 \u0434\u043b\u044f SEO", "cyrillic"),
        ("\u5bfb\u627etik tok\u7ea2\u4eba", "mixed"),
        ("\u8d44\u6df1\u4e2d\u56fd\u5546\u4e1a\u6218\u7565\u54a8\u8be2\u5e08", "cjk"),
        ("\U0001F680\U0001F680", "none"),
        (None, "none"),
    ],
)
def test_title_script(text, script):
    assert title_script(text) == script


# --------------------------------------------------------------------- pay


def test_pay_info_midpoint_and_no_imputation():
    frame, _ = master(
        [
            job(low=20, high=40),
            job(hours=1, low=15, high=np.nan),
            job(hours=2, low=np.nan, high=np.nan),
            job(hours=3, hourly=False, budget=500),
        ]
    )
    assert list(frame["pay_info"]) == ["hourly_range", "hourly_low_only", "hourly_no_rate", "fixed_budget"]
    assert frame["hourly_mid"].iloc[0] == 30.0
    assert frame["hourly_mid"].iloc[1:].isna().all()  # never estimated from one rate
    assert frame["hourly_low"].iloc[2] != frame["hourly_low"].iloc[2]  # raw NaN stays NaN


def test_missing_pay_never_counts_as_same_pay():
    frame = pd.DataFrame(
        {
            "pay_info": ["hourly_no_rate", "hourly_no_rate", "hourly_low_only"],
            "hourly_low": [np.nan, np.nan, 15.0],
            "hourly_high": [np.nan, np.nan, np.nan],
            "budget": [np.nan, np.nan, np.nan],
        }
    )
    assert list(pay_signature(frame)) == ["", "", ""]


def test_pay_signature_is_exact_and_includes_contract_type():
    frame = pd.DataFrame(
        {
            "pay_info": ["hourly_range", "hourly_range", "fixed_budget"],
            "hourly_low": [24.99, 25.0, np.nan],
            "hourly_high": [30.0, 30.0, np.nan],
            "budget": [np.nan, np.nan, 25.0],
        }
    )
    signatures = list(pay_signature(frame))
    assert signatures[0] != signatures[1]  # $24.99 and $25.00 are different pay
    assert signatures[2].startswith("fixed|")


def test_extreme_values_are_flagged_and_kept():
    rows = [job(hours=i, low=10, high=20) for i in range(50)] + [job(hours=60, low=500, high=999)]
    frame, extra = master(rows)
    assert frame["extreme_hourly_rate_flag"].iloc[-1]
    assert frame["hourly_high"].iloc[-1] == 999.0  # never clipped
    assert len(frame) == 51  # never removed
    assert extra["thresholds"]["extreme_hourly_rate_threshold"] > 20


# ----------------------------------------------------------------- repeats


def repeat_frame(rows):
    frame, _ = master(rows)
    return frame


def test_first_posting_of_a_chain_is_not_flagged():
    frame = repeat_frame([job(hours=0), job(hours=10), job(hours=20)])
    assert list(frame["possible_repost_3d"]) == [False, True, True]
    assert list(frame["repeated_title_3d"]) == [False, True, True]


def test_window_boundary():
    frame = repeat_frame([job(hours=0), job(hours=72), job(hours=72 + 73)])
    # exactly 3 days apart counts; 73 hours later does not
    assert list(frame["possible_repost_3d"]) == [False, True, False]
    assert list(frame["possible_repost_7d"]) == [False, True, True]
    assert list(frame["possible_repost_1d"]) == [False, False, False]


def test_different_pay_is_a_repeated_title_but_not_a_possible_repost():
    frame = repeat_frame([job(hours=0, low=20, high=40), job(hours=5, low=25, high=40)])
    assert list(frame["repeated_title_3d"]) == [False, True]
    assert list(frame["possible_repost_3d"]) == [False, False]


def test_jobs_without_pay_can_repeat_but_never_repost():
    frame = repeat_frame([job(hours=0, low=np.nan, high=np.nan), job(hours=5, low=np.nan, high=np.nan)])
    assert list(frame["repeated_title_3d"]) == [False, True]
    assert not frame["possible_repost_3d"].any()


def test_missing_country_never_matches_missing_country():
    frame = repeat_frame([job(hours=0, country=None), job(hours=5, country=None)])
    assert not frame["repeated_title_3d"].any()
    assert not frame["possible_repost_3d"].any()


def test_hourly_and_fixed_with_the_same_number_are_not_reposts():
    frame = repeat_frame([job(hours=0, hourly=False, budget=25), job(hours=5, low=25, high=25)])
    assert not frame["possible_repost_3d"].any()


def test_earlier_match_ignores_ineligible_rows():
    frame, _ = master([job(hours=0), job(hours=5)])
    none_eligible = pd.Series(False, index=frame.index)
    assert not earlier_match_within(frame, ["title_key"], none_eligible, 3).any()


# -------------------------------------------------------------- day quality


def stamps(day_hours):
    """{date: {hour: count}} -> timestamp Series; unlisted hours get 10 postings."""
    values = []
    for day, overrides in day_hours.items():
        for hour in range(24):
            for minute in range(overrides.get(hour, 10)):
                values.append(pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=hour, minutes=minute))
    return pd.Series(values)


def three_weeks(changes=None, saturday=10):
    """21 days from Monday 4 March 2024, 10 postings per hour (Saturdays:
    ``saturday`` per hour), with per-day hour overrides in ``changes``."""
    days = {}
    for offset in range(21):
        date = pd.Timestamp("2024-03-04") + pd.Timedelta(days=offset)
        base = saturday if date.dayofweek == 5 else 10
        hours = {h: base for h in range(24)}
        hours.update((changes or {}).get(date.strftime("%Y-%m-%d"), {}))
        days[date.strftime("%Y-%m-%d")] = hours
    return stamps(days)


def status_of(table, date):
    return table.set_index(table["date"].dt.strftime("%Y-%m-%d")).loc[date, "status"]


def test_day_quality_statuses_and_window():
    ts = three_weeks(
        {
            "2024-03-05": {h: 0 for h in range(12, 22)},  # ten empty hours: 58% of a Tuesday -> incomplete
            "2024-03-12": {5: 0},  # one empty hour: 96% of a Tuesday -> intraday gap
            "2024-03-20": {1: 0, 2: 1, 3: 0},  # three weak hours: 88% of a Wednesday -> incomplete
        }
    )
    table = day_quality(ts, RULES)
    assert status_of(table, "2024-03-04") == "complete"
    assert status_of(table, "2024-03-05") == "incomplete"
    assert status_of(table, "2024-03-12") == "intraday_gap"
    assert status_of(table, "2024-03-20") == "incomplete"
    window = table.loc[table["in_timeseries_window"], "date"].dt.strftime("%Y-%m-%d")
    assert (window.min(), window.max()) == ("2024-03-06", "2024-03-19")   # longest run without incomplete days


def test_quiet_weekday_is_compared_with_the_same_weekday():
    # Saturdays are half as busy as other days every week: that is normal, not missing data.
    table = day_quality(three_weeks(saturday=5), RULES)
    assert set(table["status"]) == {"complete"}
    assert table["completeness_ratio"].eq(1.0).all()


def test_damaged_day_does_not_judge_itself():
    # 14 of 24 hours collapse to 2 postings. Against its own median hour the day
    # would look fine (its median hour is 2); against normal Thursdays 14 hours are weak.
    ts = three_weeks({"2024-03-14": {h: 2 for h in range(14)}})
    row = day_quality(ts, RULES).set_index("date").loc[pd.Timestamp("2024-03-14")]
    assert row["weak_hours"] == 14
    assert row["status"] == "incomplete"
    assert row["completeness_ratio"] == pytest.approx((14 * 2 + 10 * 10) / 240, abs=1e-4)


def test_calendar_day_without_postings_breaks_the_window():
    ts = three_weeks()
    ts = ts[ts.dt.strftime("%Y-%m-%d") != "2024-03-13"]
    table = day_quality(ts, RULES)
    assert len(table) == 21  # 13 March is added back as an empty day
    assert status_of(table, "2024-03-13") == "incomplete"


def test_low_volume_day_is_incomplete():
    ts = three_weeks({"2024-03-07": {h: 1 for h in range(24)}})
    assert status_of(day_quality(ts, RULES), "2024-03-07") == "incomplete"


def test_sparse_early_days_are_not_reference_days():
    early = pd.Series([pd.Timestamp("2024-02-01 10:00", tz="UTC"), pd.Timestamp("2024-02-08 10:00", tz="UTC")])
    ts = pd.concat([early, three_weeks()], ignore_index=True)
    table = day_quality(ts, RULES)
    assert not table.loc[table["date"] < pd.Timestamp("2024-03-04"), "reference_day"].any()
    assert status_of(table, "2024-02-01") == "incomplete"
    assert status_of(table, "2024-03-04") == "complete"


# ------------------------------------------------------------ master table


def test_every_raw_row_is_kept_and_raw_columns_are_unchanged():
    rows = [job(hours=i, title="SEO &amp; ads") for i in range(5)]
    rows.append({**job(hours=6), "title": None, "link": None, "country": None})
    raw = pd.DataFrame(rows)
    frame, _ = master(rows)
    assert len(frame) == len(raw)
    for column in raw.columns:
        pd.testing.assert_series_equal(frame[column], raw[column], check_dtype=False)
    assert frame["title_clean"].iloc[0] == "SEO & ads"


def test_empty_record_is_kept_but_excluded_from_every_analysis():
    frame, _ = master([job(), {**job(hours=1), "title": None, "link": None, "country": None}])
    empty = frame.iloc[1]
    assert not empty["valid_job_record"]
    assert not any(empty[c] for c in frame.columns if c.startswith("eligible_for_"))


def test_eligibility_flags_follow_pay_completeness():
    frame, _ = master([job(), job(hours=1, low=15, high=np.nan), job(hours=2, hourly=False, budget=100)])
    assert list(frame["eligible_for_hourly_rate_analysis"]) == [True, False, False]
    assert list(frame["eligible_for_budget_analysis"]) == [False, False, True]
    assert frame["eligible_for_text_analysis"].all()


def test_flag_columns_are_plain_booleans():
    frame, _ = master([job(), job(hours=1)])
    flags = [c for c in frame.columns if c.startswith(("eligible_", "possible_", "repeated_", "title_has", "extreme_"))]
    assert flags and all(frame[c].dtype == bool for c in flags)


def test_time_columns_use_utc():
    frame, _ = master([job(hours=23.5)])
    row = frame.iloc[0]
    assert str(row["posted_at"].tz) == "UTC"
    assert row["hour"] == 23
    assert row["weekday"] == "Friday"  # 1 March 2024
    assert row["iso_week"] == "2024-W09"


# ----------------------------------------------------------------- outputs


def test_build_writes_master_and_audit_tables(mini_project):
    pytest.importorskip("pyarrow")
    from job_market.pipeline import run_pipeline

    manifest = run_pipeline(mini_project, log=lambda _m: None)
    written = {entry["path"].rsplit("/", 1)[-1] for entry in manifest["outputs"]}
    assert {"jobs_clean.parquet", "cleaning_log.csv", "day_quality.csv", "repeat_sensitivity.csv"} <= written
    assert manifest["counts"]["clean_rows"] == manifest["counts"]["raw_rows"]


def test_parquet_round_trip_preserves_types(tmp_path):
    pytest.importorskip("pyarrow")
    from job_market.io import read_parquet, write_parquet

    frame, _ = master([job(), job(hours=30, hourly=False, budget=250)])
    back = read_parquet(write_parquet(frame, tmp_path / "jobs.parquet"))
    pd.testing.assert_frame_equal(back, frame.reset_index(drop=True))
