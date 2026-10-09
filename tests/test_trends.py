"""Short-window trends and online-hiring signals (decision D-032)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pathlib import Path

from job_market.steps.clean import clean_title, title_key
from job_market.trends import (
    ARRANGEMENT_RULES_VERSION, COUNTRY_REGION, SIGNALS, UNMAPPED_REGION, arrangement_flags, complete_weeks,
    concentration, daily_shares, newey_west_cov, region_of, trend_fit, trend_table, week_comparison, wilson,
)

DATES = pd.Series(pd.date_range("2024-02-16", "2024-03-23", freq="D"))


def test_trend_fit_recovers_slope_with_weekday_effects():
    t = np.arange(len(DATES))
    weekday = np.array([0.0, 0.01, 0.02, 0.01, 0.0, -0.02, -0.03])[DATES.dt.dayofweek]
    values = 0.10 + 0.001 * t + weekday
    fit = trend_fit(values, DATES, lag=7)
    assert fit["change"] == pytest.approx(0.001 * (len(DATES) - 1), abs=1e-9)
    assert fit["relative_change_pct"] == pytest.approx(100 * fit["change"] / fit["start_level"])
    assert fit["change_low"] <= fit["change"] <= fit["change_high"]


def test_no_trend_is_not_significant():
    rng = np.random.default_rng(0)
    fit = trend_fit(0.05 + rng.normal(0, 0.002, len(DATES)), DATES, lag=7)
    assert fit["change_low"] < 0 < fit["change_high"]


def test_newey_west_with_lag_zero_is_the_robust_sandwich():
    rng = np.random.default_rng(1)
    design = np.column_stack([np.ones(50), rng.normal(size=50)])
    residuals = rng.normal(size=50)
    bread = np.linalg.inv(design.T @ design)
    expected = bread @ (design.T * residuals**2) @ design @ bread
    assert np.allclose(newey_west_cov(design, residuals, 0), expected)


def test_complete_weeks_in_the_real_window():
    assert complete_weeks(DATES) == ["2024-W08", "2024-W09", "2024-W10", "2024-W11"]


def frame():
    rows = []
    for day in DATES:
        n_a = 30 + (day - DATES.min()).days       # category "a" grows
        rows += [{"posted_date": day, "cat": "a"}] * n_a + [{"posted_date": day, "cat": "b"}] * 60
    out = pd.DataFrame(rows)
    iso = out["posted_date"].dt.isocalendar()
    out["iso_week"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    return out


def test_daily_shares_sum_to_one_and_trend_direction():
    shares = daily_shares(frame(), "cat")
    assert np.allclose(shares.groupby("date")["share"].sum(), 1.0)
    table = trend_table(shares, "cat", lag=7).set_index("cat")
    assert table.loc["a", "change_pp"] > 0 > table.loc["b", "change_pp"]
    assert table.loc["a", "change_pp"] == pytest.approx(-table.loc["b", "change_pp"])
    assert "p_fdr" in table.columns


def test_week_comparison_uses_first_and_last_two_complete_weeks():
    table = week_comparison(frame(), "cat", complete_weeks(DATES)).set_index("cat")
    assert table.loc["a", "last_weeks_share_pct"] > table.loc["a", "first_weeks_share_pct"]
    assert table["first_weeks_share_pct"].sum() == pytest.approx(100.0)


def test_concentration_and_effective_number():
    hhi, effective = concentration(pd.Series(["US", "UK", None, "US", "UK"]))
    assert hhi == pytest.approx(0.5)
    assert effective == pytest.approx(2.0)


def test_regions_keep_missing_missing():
    regions = region_of(pd.Series(["India", "Atlantis", None]))
    assert regions.tolist()[:2] == ["South Asia", UNMAPPED_REGION] and pd.isna(regions.iloc[2])
    assert COUNTRY_REGION["United States"] == "North America"


def flags_for(titles: list[str]) -> pd.DataFrame:
    """Rules 1.0 on raw titles, keyed the same way as the cleaning step."""
    cleaned = [clean_title(t)[0] for t in titles]
    keys = pd.Series([title_key(c) for c in cleaned], index=titles)
    return arrangement_flags(keys, pd.Series(cleaned, index=titles))


# The labelling guide's own clear examples (guide 1.1): yes = True, no = False.
GUIDE_REMOTE = {"Remote Project Manager": True, "Executive Assistant (Remote)": True,
                "Work from home data entry": True, "Remote IT help with a PC": True,
                "Hybrid (3 days/wk onsite) Business Analyst": True, "Remote analyst - must reside in Texas": True,
                "Remote sensing analysis with Python": False, "Remote control car repair": False,
                "Virtual assistant": False}
GUIDE_ON_SITE = {"Onsite technician needed in Dallas": True, "In-person event staff": True,
                 "Must attend the Austin office three days weekly": True,
                 "Hybrid (3 days/wk onsite) Business Analyst": True, "Remote analyst - must reside in Texas": False,
                 "Must be based in Spain": False, "UK based accountant": False,
                 "Local SEO for a dental clinic": False, "Photographer for a wedding in Rome": False}
GUIDE_TIME_ZONE = {"Executive Assistant - EST Timezone": True, "(PST ONLY) Airbnb response manager": True,
                   "Trainer for a class in GMT+8 timezone": True, "Night shift chat support (US hours)": True,
                   "PST to IMAP migration": False, "Deadline Sunday AEDT": False, "Need it done before 7am EST": False,
                   "Build a UTC-to-EST conversion tool": False}


@pytest.mark.parametrize("column, examples", [("remote_or_home", GUIDE_REMOTE), ("on_site_required", GUIDE_ON_SITE),
                                              ("time_zone_required", GUIDE_TIME_ZONE)])
def test_rules_agree_with_the_guide_examples(column, examples):
    flags = flags_for(list(examples))[column]
    assert flags.to_dict() == examples


def test_technical_zone_codes_and_deadlines_are_not_working_hours():
    flags = flags_for(["Outlook PST migration", "PST hours required", "Work 9 AM-5 PM PST",
                       "Pitch deck edits - need done by 8 AM Mountain Time", "Certified Scrum Master (CST)",
                       "Virtual meeting today only at 8pm EST", "best logo"])["time_zone_required"]
    assert flags.tolist() == [False, True, True, False, False, True, False]     # "best" is not "est"


def test_hybrid_counts_as_both_only_when_it_is_the_arrangement():
    titles = ["Engineer (Hybrid-Bangalore)", "Social engagement and Marketing- Hybrid Role",
              "Data Analyst / Engineer Hybrid - Startup Opportunity", "Business Analyst Hybrid",
              "Hybrid mobile app developer", "Azure Hybrid Cloud setup", "Engineer (Hybrid-Cloud)"]
    flags = flags_for(titles)
    expected = [True, True, True, True, False, False, False]
    assert flags["hybrid_arrangement"].tolist() == expected
    assert flags["remote_or_home"].tolist() == expected and flags["on_site_required"].tolist() == expected


def test_remote_technology_team_seo_and_location_wording():
    flags = flags_for(["Remote desktop support", "Remote team manager", "Remote team manager, fully remote role",
                       "Onsite SEO expert", "Onsite SEO expert, must attend our office", "Must be local to Austin",
                       "Need Election Phone Banker for Local Candidate", "Social media for our in-person event"])
    assert flags["remote_or_home"].tolist()[:3] == [False, False, True]
    assert flags["on_site_required"].tolist()[3:] == [False, True, False, False, False]


def test_reported_series_use_only_rules_1_0(monkeypatch):
    import job_market.arrangement as arrangement
    import job_market.steps.trends as step

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy sampling rules used for a reported series")

    monkeypatch.setattr(arrangement, "legacy_arrangement_flags", forbidden)
    titles = ["Remote analyst", "Onsite technician", "VA - EST timezone", "Hybrid app", "Full time editor"]
    cleaned = [clean_title(t)[0] for t in titles]
    frame = pd.DataFrame({"title_key": [title_key(c) for c in cleaned], "title_clean": cleaned,
                          "iso_week": "2024-W10"})
    out = step.signals(frame).set_index("signal")
    assert list(out.index) == list(SIGNALS)
    assert ARRANGEMENT_RULES_VERSION == "1.0"
    assert out.loc[["remote / home wording", "on-site / in-person wording", "time-zone requirement wording",
                    "full time"], "title_mentions"].tolist() == [1, 1, 1, 1]
    assert "legacy" not in Path(step.__file__).read_text(encoding="utf-8")


def test_wilson_bounds():
    low, high = wilson(5, 1000)
    assert 0 <= low < 0.005 < high <= 1
