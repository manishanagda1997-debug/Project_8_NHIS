import pandas as pd
import pytest

from job_market.steps.ingest import (
    SchemaError,
    daily_coverage,
    parse_timestamps,
    read_raw,
    validate_schema,
)

REQUIRED = ["title", "link", "published_date", "is_hourly", "hourly_low", "hourly_high", "budget", "country"]


def test_raw_file_loads_with_expected_types(mini_project):
    frame = read_raw(mini_project.path("raw_csv"), REQUIRED)
    assert len(frame) == 6
    assert frame["is_hourly"].dtype == bool
    for column in ("hourly_low", "hourly_high", "budget"):
        assert frame[column].dtype == "float64"


def test_text_na_is_a_value_not_a_missing_cell(mini_project):
    frame = read_raw(mini_project.path("raw_csv"), REQUIRED)
    # "NA" is a real country code (Namibia); only the empty cell is missing.
    assert "NA" in set(frame["country"].dropna())
    assert frame["country"].isna().sum() == 1
    assert frame["title"].isna().sum() == 1


def test_html_entities_stay_untouched_at_ingest(mini_project):
    frame = read_raw(mini_project.path("raw_csv"), REQUIRED)
    assert "SEO &amp; content writer" in set(frame["title"])


def test_missing_column_fails():
    frame = pd.DataFrame({c: [] for c in REQUIRED if c != "budget"})
    with pytest.raises(SchemaError, match="missing columns"):
        validate_schema(frame, REQUIRED)


def test_unexpected_column_fails():
    frame = pd.DataFrame({c: [] for c in [*REQUIRED, "surprise"]})
    with pytest.raises(SchemaError, match="unexpected columns"):
        validate_schema(frame, REQUIRED)


def test_unknown_contract_flag_fails(mini_project):
    path = mini_project.path("raw_csv")
    text = path.read_text(encoding="utf-8").replace(",False,", ",maybe,", 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SchemaError, match="is_hourly"):
        read_raw(path, REQUIRED)


def test_timestamps_are_utc_and_bad_values_become_missing():
    parsed = parse_timestamps(pd.Series(["2024-03-01 09:00:00+00:00", "not a date"]))
    assert str(parsed.dt.tz) == "UTC"
    assert parsed.isna().tolist() == [False, True]


def test_daily_coverage_reports_span_per_utc_day():
    ts = parse_timestamps(
        pd.Series(["2024-03-01 01:00:00+00:00", "2024-03-01 23:00:00+00:00", "2024-03-02 05:00:00+00:00"])
    )
    coverage = daily_coverage(ts)
    assert coverage["date"].tolist() == ["2024-03-01", "2024-03-02"]
    assert coverage["postings"].tolist() == [2, 1]
    assert coverage["observed_span_hours"].tolist() == [22.0, 0.0]
