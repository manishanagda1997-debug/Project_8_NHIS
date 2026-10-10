"""Work-arrangement wording audit: evaluation sample and scoring (decision D-041).

1. ``rules_fingerprint``: SHA-256 of the rules 1.0 source (rule functions and
   their word lists). The sampler and the scorer stop unless it equals the
   frozen value in the configuration.
2. ``evaluation_groups``: one group per evaluation side title key, S1 to S5,
   by fixed priority, using rules 1.0 and the legacy sampling rules.
3. ``evaluation_sample``: S1 and S3 in full; seeded simple random samples in
   S2, S4 and S5. Each key keeps its inclusion probability and weight.
4. ``diagnostic_sample``: the quarantined titles in groups G1 to G3.
5. ``score``: title key results with a Jeffreys posterior and a finite
   population simulation for the sampled groups; posting level weighted point
   estimates.

The sheets show only the sample ID and the title; group, rule result and
quarantine reason never appear in them.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any

import numpy as np
import pandas as pd

from . import trends
from .arrangement import (
    QUARANTINE_GROUPS, QuarantineError, assert_not_quarantined, assign_side, candidate_mask, legacy_arrangement_flags,
)

LABELS = ("remote_or_home", "on_site_required", "time_zone_required")
GROUPS = (
    ("S1", "rules 1.0 on site match"),
    ("S2", "rules 1.0 remote or home match, not S1"),
    ("S3", "legacy match, no rules 1.0 match"),
    ("S4", "candidate wording, no match"),
    ("S5", "all other keys"),
)
SIZE_KEYS = {"S2": "eval_s2", "S4": "eval_s4", "S5": "eval_s5"}       # S1 and S3: all keys
_RULE_FUNCTIONS = ("_words", "_has", "hybrid_arrangement", "arrangement_flags")
_RULE_CONSTANTS = ("ARRANGEMENT_RULES_VERSION", "_REMOTE_TECH", "_HOME", "_HYBRID_TECH", "_ATTEND", "_IN_PERSON_EVENT",
                   "_ZONE_CODES", "_TZ_WORDS", "_TZ_PHRASES", "_DEADLINE", "_TIME_MARK", "_AVAILABILITY", "_TECHNICAL",
                   "_WORK_TIME")


class DesignError(ValueError):
    """The rules, the pool or a group does not match the frozen evaluation design."""


def rules_fingerprint() -> str:
    """SHA-256 of the rules 1.0 source: the rule functions and their word lists."""
    parts = [inspect.getsource(getattr(trends, name)).replace("\r\n", "\n") for name in _RULE_FUNCTIONS]
    parts.append(json.dumps({name: getattr(trends, name) for name in _RULE_CONSTANTS}, sort_keys=True))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def check_rules(rules: dict[str, Any]) -> None:
    if trends.ARRANGEMENT_RULES_VERSION != str(rules["rules_version"]):
        raise DesignError(f"rules version {trends.ARRANGEMENT_RULES_VERSION}, expected {rules['rules_version']}")
    found = rules_fingerprint()
    if found != str(rules["rules_fingerprint"]):
        raise DesignError(f"rules fingerprint {found} does not match the frozen rules 1.0 ({rules['rules_fingerprint']})")


def evaluation_pool(frame: pd.DataFrame, rules: dict[str, Any], quarantine: set[str]) -> pd.DataFrame:
    """Evaluation side title keys minus the quarantine, with rules 1.0 predictions and a group."""
    side = assign_side(frame["title_key"], int(rules["seed"]), float(rules["development_share"]))
    pool = frame[(side == "evaluation") & ~frame["title_key"].isin(quarantine)].copy()
    predicted = trends.arrangement_flags(pool["title_key"], pool["title"])
    for label in LABELS:
        pool[f"rule_{label}"] = predicted[label]
    legacy = legacy_arrangement_flags(pool["title_key"]).any(axis=1)
    candidate = candidate_mask(pool["title_key"], list(rules["candidate_patterns"]))
    choices = [predicted["on_site_required"], predicted["remote_or_home"], legacy, candidate]
    pool["group"] = np.select(choices, ["S1", "S2", "S3", "S4"], default="S5")
    return pool


def evaluation_sample(frame: pd.DataFrame, rules: dict[str, Any], quarantine: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(sample, group summary). Stops if the rules, the quarantine or a group breaks the design."""
    check_rules(rules)
    pool = evaluation_pool(frame, rules, quarantine)
    rng = np.random.default_rng(int(rules["eval_seed"]))
    parts, summary = [], []
    for code, description in GROUPS:
        members = pool[pool["group"] == code].sort_values("title_key")       # sorted: reproducible draws
        size = len(members)
        n = size if code not in SIZE_KEYS else min(int(rules[SIZE_KEYS[code]]), size)
        if code in SIZE_KEYS:
            # Inside a sampled group every key has the same rule prediction for every label.
            for label in LABELS:
                if members[f"rule_{label}"].nunique() > 1:
                    raise DesignError(f"{code}: rule prediction for {label} is not constant")
        chosen = members if n == size else members.iloc[np.sort(rng.choice(size, size=n, replace=False))]
        parts.append(chosen.assign(group_size=size, sampled=n, pi=n / size if size else 0.0,
                                   weight=size / n if n else 0.0))
        summary.append({"group": code, "description": description, "title_keys": size,
                        "postings": int(members["postings"].sum()), "sampled": n, "census": n == size})
    sample = pd.concat(parts, ignore_index=True)
    assert_not_quarantined(sample["title_key"], quarantine)
    if (assign_side(sample["title_key"], int(rules["seed"]), float(rules["development_share"])) != "evaluation").any():
        raise DesignError("a development title key is in the evaluation sample")
    sample = sample.iloc[rng.permutation(len(sample))].reset_index(drop=True)
    sample.insert(0, "sample_id", [f"E{i + 1:03d}" for i in range(len(sample))])
    columns = ["sample_id", "title_key", "title", "postings", "group", "group_size", "sampled", "pi", "weight",
               *[f"rule_{label}" for label in LABELS]]
    return sample[columns], pd.DataFrame(summary)


def diagnostic_sample(frame: pd.DataFrame, quarantine_table: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """Quarantined title keys in G1 to G3, shuffled with the evaluation seed, numbered Q001 onward."""
    flags = quarantine_table[list(QUARANTINE_GROUPS[:3])].astype(int).astype(bool)
    keys = quarantine_table.loc[flags.any(axis=1), "title_key"]
    chosen = frame[frame["title_key"].isin(set(keys))].sort_values("title_key")
    if len(chosen) != len(keys):
        raise QuarantineError("a quarantined title key is missing from the time series window")
    rng = np.random.default_rng(int(rules["eval_seed"]) + 1)
    chosen = chosen.iloc[rng.permutation(len(chosen))].reset_index(drop=True)
    predicted = trends.arrangement_flags(chosen["title_key"], chosen["title"])
    for label in LABELS:
        chosen[f"rule_{label}"] = predicted[label]
    chosen.insert(0, "sample_id", [f"Q{i + 1:03d}" for i in range(len(chosen))])
    return chosen[["sample_id", "title_key", "title", "postings", *[f"rule_{label}" for label in LABELS]]]


def design_sha256(sample: pd.DataFrame) -> str:
    """Hash of the per-title design (IDs, keys, groups, weights), recorded at creation and checked at scoring."""
    text = sample[["sample_id", "title_key", "group", "group_size", "sampled"]].to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ scoring

def _summary(values: np.ndarray, exact: bool) -> dict[str, Any]:
    if exact:
        value = float(values[0])
        return {"estimate": value, "low": value, "high": value, "exact": True}
    low, mid, high = np.nanquantile(values, [0.025, 0.5, 0.975])
    return {"estimate": float(mid), "low": float(low), "high": float(high), "exact": False}


def score(labelled: pd.DataFrame, summary: pd.DataFrame, draws: int, seed: int, unclear_as_yes: bool = False) -> pd.DataFrame:
    """Title key results (primary) and posting level point estimates (secondary), one row per label and metric.

    ``labelled`` is the evaluation sample with the human labels joined. In S1
    and S3 every key is labelled, so their counts are exact. In a sampled group
    with ``y`` yes labels out of ``n``, ``p ~ Beta(y + 0.5, n - y + 0.5)``
    (Jeffreys) and the unlabelled keys add ``Binomial(N - n, p)`` yes keys.
    """
    rng = np.random.default_rng(seed)
    sizes = summary.set_index("group")["title_keys"].to_dict()
    census = summary.set_index("group")["census"].to_dict()
    rows = []
    for label in LABELS:
        yes = labelled[label].isin(["yes", "unclear"] if unclear_as_yes else ["yes"])
        predicted = labelled[f"rule_{label}"].astype(bool)
        tp = np.zeros(draws)
        fn = np.zeros(draws)
        matches = unmatched = 0
        sampled_part = False
        tp_post = fn_post = 0.0
        group_postings = summary.set_index("group")["postings"].to_dict()
        for code, _ in GROUPS:
            part = labelled["group"] == code
            if not part.any():
                continue
            if census[code]:
                tp += int((yes & predicted & part).sum())
                fn += int((yes & ~predicted & part).sum())
                matches += int((predicted & part).sum())
                unmatched += int((~predicted & part).sum())
            else:
                sampled_part = True
                n, size = int(part.sum()), int(sizes[code])
                y = int((yes & part).sum())
                rate = rng.beta(y + 0.5, n - y + 0.5, size=draws)
                total = y + rng.binomial(size - n, rate)
                if bool(predicted[part].iloc[0]):
                    tp += total
                    matches += size
                else:
                    fn += total
                    unmatched += size
            # Posting level: the posting weighted yes rate of the labelled keys times the
            # group's known postings (exact in a census group).
            postings = labelled.loc[part, "postings"].to_numpy(dtype=float)
            hits = postings * yes[part].to_numpy(dtype=float)
            if census[code]:
                tp_post += float(hits[predicted[part].to_numpy()].sum())
                fn_post += float(hits[~predicted[part].to_numpy()].sum())
            else:
                group_yes = hits.sum() / postings.sum() * float(group_postings[code])
                if bool(predicted[part].iloc[0]):
                    tp_post += group_yes
                else:
                    fn_post += group_yes
        exact = not sampled_part
        metrics = {
            "precision": tp / matches if matches else np.full(draws, np.nan),
            "missed_yes_per_1000_unmatched": 1000 * fn / unmatched if unmatched else np.full(draws, np.nan),
            # With no rule match in the pool (time zone), recall says nothing about the rule.
            "recall": (np.divide(tp, tp + fn, out=np.full(draws, np.nan), where=(tp + fn) > 0) if matches
                       else np.full(draws, np.nan)),
        }
        # Known denominator: postings of every rule match in the pool (census keys and whole sampled groups).
        matched_postings = 0.0
        for code, _ in GROUPS:
            part = (labelled["group"] == code) & predicted
            if census.get(code, False):
                matched_postings += float(labelled.loc[part, "postings"].sum())
            elif part.any():
                matched_postings += float(group_postings[code])
        for metric, values in metrics.items():
            # Precision depends only on the groups that hold rule matches.
            match_groups = set(labelled.loc[predicted, "group"])
            metric_exact = exact or (metric == "precision" and all(census[g] for g in match_groups))
            row = {"label": label, "metric": metric, "level": "title key", "rule_matches": matches,
                   "unmatched": unmatched, "unclear": int((labelled[label] == "unclear").sum())}
            row.update(_summary(values, metric_exact) if matches or metric == "missed_yes_per_1000_unmatched" else
                       {"estimate": np.nan, "low": np.nan, "high": np.nan, "exact": False})
            if metric != "precision" and not row["exact"]:
                # Missed yes and recall: interval only. With few or no observed misses the
                # middle value mainly reflects the Jeffreys prior, so it is not reported.
                row["estimate"] = np.nan
            rows.append(row)
        rows.append({"label": label, "metric": "precision", "level": "posting (point estimate)",
                     "estimate": tp_post / matched_postings if matched_postings else np.nan})
        rows.append({"label": label, "metric": "missed_yes_postings", "level": "posting (point estimate)",
                     "estimate": fn_post})
    return pd.DataFrame(rows)


def observed_counts(labelled: pd.DataFrame, unclear_as_yes: bool = False) -> pd.DataFrame:
    """Yes labels out of labelled keys, per group and label (reported next to every result)."""
    rows = []
    for (code, _), label in ((g, l) for g in GROUPS for l in LABELS):
        part = labelled[labelled["group"] == code]
        yes = part[label].isin(["yes", "unclear"] if unclear_as_yes else ["yes"])
        rows.append({"group": code, "label": label, "labelled": len(part), "yes": int(yes.sum()),
                     "unclear": int((part[label] == "unclear").sum())})
    return pd.DataFrame(rows)



def diagnostic_counts(labelled: pd.DataFrame) -> pd.DataFrame:
    """Exact counts on the diagnostic set (seen during rule development, not blind)."""
    rows = []
    for label in LABELS:
        predicted = labelled[f"rule_{label}"].astype(bool)
        value = labelled[label]
        rows.append({"label": label, "titles": len(labelled), "rule_matches": int(predicted.sum()),
                     "matches_labelled_yes": int((predicted & (value == "yes")).sum()),
                     "matches_labelled_no": int((predicted & (value == "no")).sum()),
                     "matches_labelled_unclear": int((predicted & (value == "unclear")).sum()),
                     "non_matches_labelled_yes": int((~predicted & (value == "yes")).sum()),
                     "labelled_yes": int((value == "yes").sum())})
    out = pd.DataFrame(rows)
    out["precision"] = (out["matches_labelled_yes"] / out["rule_matches"]).where(out["rule_matches"] > 0)
    out["share_of_yes_matched"] = (out["matches_labelled_yes"] / out["labelled_yes"]).where(out["labelled_yes"] > 0)
    return out


def read_labels(path, sample: pd.DataFrame) -> pd.DataFrame:
    """Join a labelled sheet to its design rows; stop on any mismatch or invalid value."""
    sheet = pd.read_excel(path, dtype=str)
    if list(sheet["sample_id"]) != list(sample["sample_id"]) or list(sheet["title"]) != list(sample["title"]):
        raise DesignError(f"{path}: sample IDs or titles differ from the drawn sample")
    for label in LABELS:
        if not sheet[label].isin(["yes", "no", "unclear"]).all():
            raise DesignError(f"{path}: {label} has empty or invalid values")
    return sample.merge(sheet[["sample_id", *LABELS, "note"]], on="sample_id", validate="one_to_one")
