"""Work-arrangement wording audit: frame, global split and development sample (decision D-041)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from job_market.arrangement import assign_side, development_sample, selection_record, strata, title_frame
from job_market.config import load_settings

RULES = dict(load_settings().section("arrangement"))
TITLES = (["remote data entry"] * 3 + ["hybrid app developer", "hybrid analyst est hours", "ea est timezone",
          "onsite technician", "work from home sales", "home based typist", "logo design", "video editor",
          "must be local to austin", "pst to imap migration"]
          + [f"generic job {i}" for i in range(300)] + [f"remote role {i}" for i in range(150)]
          + [f"hybrid thing {i}" for i in range(40)])


def jobs(titles=TITLES) -> pd.DataFrame:
    n = len(titles)
    return pd.DataFrame({"row_id": np.arange(n), "title_key": titles, "title_clean": [t.title() for t in titles],
                         "eligible_for_timeseries": True})


def test_frame_is_deduplicated_with_posting_counts():
    frame = title_frame(jobs())
    assert frame["title_key"].is_unique
    assert frame.set_index("title_key").loc["remote data entry", "postings"] == 3


def test_side_depends_only_on_the_key():
    keys = title_frame(jobs())["title_key"]
    a = assign_side(keys, 1, 0.4)
    b = assign_side(keys.sample(frac=1, random_state=3), 1, 0.4)            # other order
    c = assign_side(keys.iloc[:50], 1, 0.4)                                  # other population
    assert a.to_dict() == b.sort_index().to_dict()
    assert (a.iloc[:50] == c).all()
    assert set(a) == {"development", "evaluation"}


def test_strata_are_exclusive_and_follow_the_priority():
    frame = title_frame(jobs())
    codes = strata(frame, RULES).set_axis(frame["title_key"])
    assert codes["hybrid analyst est hours"] == "D1"        # hybrid beats time zone
    assert codes["ea est timezone"] == "D2"
    assert codes["onsite technician"] == "D3"
    assert codes["work from home sales"] == "D4" and codes["remote data entry"] == "D4"
    assert codes["home based typist"] == "D5" and codes["must be local to austin"] == "D3"
    assert codes["logo design"] == "D6"


def test_development_sample_never_contains_evaluation_titles_and_includes_every_hybrid():
    frame = title_frame(jobs())
    sample, summary = development_sample(frame, RULES)
    side = assign_side(frame["title_key"], int(RULES["seed"]), float(RULES["development_share"]))
    dev_keys = set(frame.loc[side == "development", "title_key"])
    assert set(sample["title_key"]) <= dev_keys                              # no evaluation title exposed
    assert sample["title_key"].is_unique
    dev = frame[frame["title_key"].isin(dev_keys)]
    hybrid_dev = set(dev.loc[strata(dev, RULES) == "D1", "title_key"])
    assert hybrid_dev and hybrid_dev <= set(sample["title_key"])            # every development hybrid title
    row = summary.set_index("stratum").loc["D1"]
    assert row["sampled"] == row["development_titles"] == len(hybrid_dev)


def test_sample_is_reproducible_and_records_its_design():
    frame = title_frame(jobs())
    first, summary = development_sample(frame, RULES)
    second, _ = development_sample(frame.sample(frac=1, random_state=9), RULES)
    pd.testing.assert_frame_equal(first, second)
    assert first["pilot"].sum() == min(int(RULES["pilot_titles"]), len(first))
    assert set(first["selection_reason"]) <= set(summary["description"])
    record = selection_record(first, summary, RULES, "a" * 64, "b" * 64, "c" * 64)
    assert record["source_sha256"] == "a" * 64 and record["guide_sha256"] == "c" * 64
    assert record["seed"] == int(RULES["seed"])
    assert sum(s["sampled"] for s in record["strata"]) == len(first) == record["titles"]


def test_sheet_shows_only_the_title_and_refuses_to_overwrite(tmp_path):
    import pytest
    from openpyxl import load_workbook
    from job_market.arrangement import SHEET_COLUMNS, write_arrangement_sheet
    sample, _ = development_sample(title_frame(jobs()), RULES)
    path = write_arrangement_sheet(sample.head(5), tmp_path / "pilot.xlsx")
    rows = list(load_workbook(path)["labels"].values)
    assert list(rows[0]) == SHEET_COLUMNS                                   # no stratum, reason or count
    assert [r[1] for r in rows[1:]] == sample.head(5)["title"].tolist()
    with pytest.raises(FileExistsError):
        write_arrangement_sheet(sample.head(5), path)
