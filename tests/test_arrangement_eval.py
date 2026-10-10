"""Work-arrangement audit: evaluation sample and scoring (decision D-041)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import job_market.trends as trends
from job_market.arrangement import QuarantineError, assign_side, title_frame
from job_market.arrangement_eval import (
    LABELS, DesignError, check_rules, design_sha256, evaluation_sample, observed_counts, rules_fingerprint, score,
)
from job_market.config import load_settings

RULES = dict(load_settings().section("arrangement"))
TITLES = (["Remote data entry"] * 3 + ["Onsite technician", "In person translator", "Remote sensing analyst",
          "Must be local to Austin", "Home based typist", "Work from anywhere VA", "Logo design"]
          + [f"Remote role {i}" for i in range(150)] + [f"Generic job {i}" for i in range(400)]
          + [f"Onsite helper {i}" for i in range(30)] + [f"Relocate to office {i}" for i in range(60)])


def frame(titles=TITLES) -> pd.DataFrame:
    jobs = pd.DataFrame({"row_id": np.arange(len(titles)), "title_key": [t.lower() for t in titles],
                         "title_clean": titles, "eligible_for_timeseries": True})
    return title_frame(jobs)


def rules(**changes):
    out = dict(RULES)
    out.update(changes)
    return out


def test_rules_fingerprint_is_frozen_and_detects_any_rule_change(monkeypatch):
    assert rules_fingerprint() == RULES["rules_fingerprint"]
    check_rules(RULES)
    monkeypatch.setattr(trends, "_HOME", trends._HOME + "|homeworker")
    with pytest.raises(DesignError, match="fingerprint"):
        check_rules(RULES)


def test_rules_version_must_match():
    with pytest.raises(DesignError, match="version"):
        check_rules(rules(rules_version="1.1"))


def test_sample_groups_weights_and_exclusions():
    f = frame()
    quarantine = {"remote role 0"}
    sample, summary = evaluation_sample(f, rules(eval_s2=20, eval_s4=10, eval_s5=15), quarantine)
    assert "remote role 0" not in set(sample["title_key"])
    assert sample["title_key"].is_unique
    side = assign_side(sample["title_key"], int(RULES["seed"]), float(RULES["development_share"]))
    assert (side == "evaluation").all()
    by_group = summary.set_index("group")
    for code in ("S1", "S3"):
        assert by_group.loc[code, "census"] and by_group.loc[code, "sampled"] == by_group.loc[code, "title_keys"]
    part = sample[sample["group"] == "S2"]
    assert len(part) == min(20, by_group.loc["S2", "title_keys"])
    assert np.allclose(part["pi"] * part["weight"], 1.0)
    assert sample["sample_id"].iloc[0] == "E001"
    again, _ = evaluation_sample(f, rules(eval_s2=20, eval_s4=10, eval_s5=15), quarantine)
    assert design_sha256(sample) == design_sha256(again)                # reproducible


def test_group_priority_uses_rules_1_0_and_legacy_rules():
    f = frame()
    sample, _ = evaluation_sample(f, rules(eval_s2=10_000, eval_s4=10_000, eval_s5=10_000), set())
    group = sample.set_index("title_key")["group"]
    expected = {"onsite technician": "S1", "in person translator": "S1", "remote data entry": "S2",
                "work from anywhere va": "S2", "remote sensing analyst": "S3", "must be local to austin": "S3",
                "home based typist": "S2", "logo design": "S5"}
    for key, code in expected.items():
        if key in group:                                                 # development side keys are absent
            assert group[key] == code


def test_quarantined_key_drawn_stops_the_sampler(monkeypatch):
    import job_market.arrangement_eval as module
    monkeypatch.setattr(module, "assign_side", lambda keys, *_: pd.Series("evaluation", index=keys.index))
    f = frame()
    with pytest.raises(QuarantineError):
        module.assert_not_quarantined(pd.Series(["logo design"]), {"logo design"})
    sample, _ = module.evaluation_sample(f, rules(eval_s2=5, eval_s4=5, eval_s5=5), {"logo design"})
    assert "logo design" not in set(sample["title_key"])


def test_mixed_prediction_inside_a_sampled_group_stops_the_sampler(monkeypatch):
    import job_market.arrangement_eval as module
    monkeypatch.setattr(module, "assign_side", lambda keys, *_: pd.Series("evaluation", index=keys.index))
    f = frame(TITLES + ["Remote VA EST timezone"])
    with pytest.raises(DesignError, match="not constant"):
        module.evaluation_sample(f, rules(eval_s2=5, eval_s4=5, eval_s5=5), set())


def toy_design():
    """Two census groups and two sampled groups with known answers."""
    summary = pd.DataFrame({"group": ["S1", "S2", "S3", "S4", "S5"], "title_keys": [2, 10, 1, 4, 1000],
                            "postings": [3, 12, 1, 4, 1200], "sampled": [2, 4, 1, 2, 5],
                            "census": [True, False, True, False, False]})
    rows = [("S1", True, False, "yes", "no", 2), ("S1", True, True, "yes", "yes", 1),
            ("S2", False, True, "no", "yes", 1), ("S2", False, True, "no", "yes", 1),
            ("S2", False, True, "no", "unclear", 1), ("S2", False, True, "no", "no", 5),
            ("S3", False, False, "no", "no", 1),
            ("S4", False, False, "no", "yes", 1), ("S4", False, False, "no", "no", 1)]
    rows += [("S5", False, False, "no", "no", 1)] * 5
    labelled = pd.DataFrame(rows, columns=["group", "rule_on_site_required", "rule_remote_or_home",
                                           "on_site_required", "remote_or_home", "postings"])
    labelled["rule_time_zone_required"] = False
    labelled["time_zone_required"] = "no"
    sizes = summary.set_index("group")
    labelled["weight"] = labelled["group"].map(sizes["title_keys"] / sizes["sampled"])
    return labelled, summary


def table(result):
    return result.set_index(["label", "metric", "level"])


def test_census_precision_is_exact_and_sampled_groups_keep_observed_labels():
    labelled, summary = toy_design()
    out = table(score(labelled, summary, draws=20_000, seed=1))
    onsite = out.loc[("on_site_required", "precision", "title key")]
    assert onsite["exact"] and onsite["estimate"] == 1.0
    remote = out.loc[("remote_or_home", "precision", "title key")]
    # S1 has 1 remote match labelled yes; S2 has 10 matches, 2 of 4 labelled yes: 3 to 9 yes in total.
    assert not remote["exact"] and 3 / 11 <= remote["low"] <= remote["estimate"] <= remote["high"] <= 9 / 11
    assert np.isnan(out.loc[("time_zone_required", "precision", "title key"), "estimate"])
    assert np.isnan(out.loc[("time_zone_required", "recall", "title key"), "estimate"])


def test_zero_yes_sample_still_allows_unseen_misses():
    labelled, summary = toy_design()
    out = table(score(labelled, summary, draws=20_000, seed=1))
    missed = out.loc[("on_site_required", "missed_yes_per_1000_unmatched", "title key")]
    assert missed["low"] >= 0 and missed["high"] > 0                   # S5 has 0 of 5 yes, still uncertain


def test_unclear_handling_and_posting_estimates():
    labelled, summary = toy_design()
    strict = table(score(labelled, summary, draws=5_000, seed=1))
    loose = table(score(labelled, summary, draws=5_000, seed=1, unclear_as_yes=True))
    key = ("remote_or_home", "precision", "title key")
    assert loose.loc[key, "estimate"] > strict.loc[key, "estimate"]
    # Posting level: S2 posting weighted yes rate 2/8 times its 12 known postings, plus S1's 1 posting.
    post = strict.loc[("remote_or_home", "precision", "posting (point estimate)"), "estimate"]
    assert post == pytest.approx((1 + 2 / 8 * 12) / (1 + 12))
    counts = observed_counts(labelled).set_index(["group", "label"])
    assert counts.loc[("S2", "remote_or_home"), "yes"] == 2 and counts.loc[("S2", "remote_or_home"), "unclear"] == 1


def test_perfect_labels_give_posting_precision_one():
    labelled, summary = toy_design()
    for label in LABELS:
        labelled[label] = labelled[f"rule_{label}"].map({True: "yes", False: "no"})
    out = table(score(labelled, summary, draws=2_000, seed=1))
    for label in ("remote_or_home", "on_site_required"):
        assert out.loc[(label, "precision", "posting (point estimate)"), "estimate"] == pytest.approx(1.0)


def test_missed_yes_and_recall_have_no_middle_value():
    labelled, summary = toy_design()
    out = table(score(labelled, summary, draws=2_000, seed=1))
    for label in ("remote_or_home", "on_site_required"):
        for metric in ("missed_yes_per_1000_unmatched", "recall"):
            row = out.loc[(label, metric, "title key")]
            assert np.isnan(row["estimate"]) and row["high"] >= row["low"]


def test_diagnostic_counts_are_exact():
    from job_market.arrangement_eval import diagnostic_counts
    labelled = pd.DataFrame({"rule_remote_or_home": [True, True, False, False],
                             "rule_on_site_required": [False] * 4, "rule_time_zone_required": [True, True, True, False],
                             "remote_or_home": ["yes", "no", "yes", "no"], "on_site_required": ["no"] * 4,
                             "time_zone_required": ["yes", "unclear", "no", "yes"]})
    out = diagnostic_counts(labelled).set_index("label")
    assert out.loc["remote_or_home", "precision"] == 0.5 and out.loc["remote_or_home", "non_matches_labelled_yes"] == 1
    assert out.loc["time_zone_required", "matches_labelled_unclear"] == 1
    assert out.loc["time_zone_required", "share_of_yes_matched"] == 0.5
    assert np.isnan(out.loc["on_site_required", "precision"])


def test_read_labels_refuses_changed_titles_or_invalid_values(tmp_path):
    from job_market.arrangement import write_arrangement_sheet
    from job_market.arrangement_eval import read_labels
    from openpyxl import load_workbook
    sample = pd.DataFrame({"sample_id": ["E001", "E002"], "title": ["A title", "B title"]})
    path = write_arrangement_sheet(sample, tmp_path / "s.xlsx")
    book = load_workbook(path)
    rows = book["labels"]
    for r in (2, 3):
        for c in (3, 4, 5):
            rows.cell(r, c).value = "no"
    book.save(path)
    assert len(read_labels(path, sample)) == 2
    rows.cell(3, 4).value = "maybe"
    book.save(path)
    with pytest.raises(DesignError, match="invalid"):
        read_labels(path, sample)
    with pytest.raises(DesignError, match="titles"):
        read_labels(path, sample.assign(title=["A title", "Other"]))
