"""Step 8 - recommend: job recommendations from title text (Task 5, decision D-034).

The step indexes every job in the 37-day time-series window, then:

1. writes the job table the API and notebook use (``recommend_jobs.parquet``),
   with the repost flag that keeps the newest posting of each chain;
2. runs the label-free checks for every profile, method and filter scenario:
   result counts (coverage / zero results), distinct titles and filter
   violations. These files hold counts only, never titles, so they reveal
   nothing about which method finds which job;
3. scores the methods against the blinded relevance sheet
   (``data/labels/relevance_labels.xlsx``) only when the sheet is bound to
   this raw extract (decision D-039). A missing, malformed or other-extract
   sheet is not scored, and its status is recorded. On the bound extract, a
   sheet that no longer covers the retrieved titles stops the build;
4. on the designated historical extract, requires the rankings to equal the
   preserved historical rankings (decision D-040);
5. records the method this build serves. It comes from the approval record
   (``config/recommender_approval.toml``); without one, the scored winner is
   recorded as pending approval. A scored winner that differs from the
   approved method is recorded as a mismatch: the app then refuses to start,
   and nothing switches automatically. Related keywords use the served method.

The winner rule is frozen in the configuration: highest mean graded nDCG@5;
differences below the tie threshold go to strict Precision@5 (only label 2
counts); a full tie goes to the simpler method.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import Settings
from ..io import write_csv
from ..labels import LabelSheetError, read_relevance_sheet
from ..manifest import StepRecord, describe_output, sha256_file
from .. import provenance
from ..recommend import (
    Index, build_index, choose_winner, describe_keyword, filter_mask, ndcg_at_k, newest_in_repost_chain, pool_mask,
    recommend, related_keywords, scores, strict_precision_at_k,
)

NAME = "recommend"
DESCRIPTION = "Job recommendations: index, label-free checks and the blind relevance evaluation (Task 5)."

RELEVANCE_SHEET = "relevance_labels.xlsx"
JOB_COLUMNS = ["row_id", "title_clean", "title_key", "link", "posted_at", "posted_date", "contract_type", "hourly_low",
               "hourly_high", "budget", "country", "pay_signature"]


def build_jobs(context: dict[str, Any]) -> pd.DataFrame:
    clean = context["clean"]
    frame = clean.loc[clean["eligible_for_timeseries"] & clean["eligible_for_text_analysis"], JOB_COLUMNS]
    frame = frame.merge(context["categories"][["row_id", "primary_category"]], on="row_id", how="left",
                        validate="one_to_one")
    frame = frame.astype({"title_clean": object, "title_key": object, "pay_signature": object,
                          "contract_type": str, "primary_category": str})
    frame = frame.sort_values(["posted_at", "row_id"], kind="mergesort").reset_index(drop=True)
    frame["newest_in_chain"] = newest_in_repost_chain(frame)
    return frame


def evaluation_results(index: Index, rules: dict) -> pd.DataFrame:
    """Top-k results per profile and method on the frozen pool, without filters."""
    candidates = (pool_mask(index.jobs, int(rules["pool_days"])) & index.jobs["newest_in_chain"]).to_numpy()
    k = int(rules["eval_top_k"])
    rows = []
    for profile in rules["profiles"]:
        for method in rules["methods"]:
            top = recommend(index, profile["skills"], method, candidates, k)
            for item in top.itertuples(index=False):
                rows.append({"profile_id": profile["id"], "method": method, "rank": int(item.rank),
                             "row_id": int(item.row_id), "title_key": item.title_key, "title": item.title_clean,
                             "posted_at": item.posted_at})
    return pd.DataFrame(rows, columns=["profile_id", "method", "rank", "row_id", "title_key", "title", "posted_at"])


def relevance_items(results: pd.DataFrame, seed: int) -> pd.DataFrame:
    """The blinded sheet rows: one per (profile, title key), shuffled within each profile.

    The displayed title is the newest pooled job with that key. Method, rank
    and score are dropped.
    """
    unique = (results.sort_values("posted_at", ascending=False)
              .drop_duplicates(["profile_id", "title_key"])[["profile_id", "title_key", "title"]])
    parts = [part.sample(frac=1.0, random_state=seed + i)
             for i, (_, part) in enumerate(unique.groupby("profile_id", sort=True))]
    items = pd.concat(parts, ignore_index=True) if parts else unique.iloc[[]]
    items.insert(0, "item_id", [f"R{i:03d}" for i in range(1, len(items) + 1)])
    return items[["item_id", "profile_id", "title", "title_key"]]


def label_free_checks(index: Index, rules: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Coverage, diversity and filter checks for every profile x method x scenario (counts only)."""
    jobs = index.jobs
    kept = jobs["newest_in_chain"].to_numpy()
    pool = pool_mask(jobs, int(rules["pool_days"])).to_numpy()
    k = int(rules["results"])
    pools = []
    for days in rules["pool_day_options"]:
        mask = pool_mask(jobs, int(days)).to_numpy()
        pools.append({"pool_days": int(days), "label": "all" if int(days) == 0 else f"last {int(days)} days",
                      "jobs": int(mask.sum()), "jobs_after_reposts": int((mask & kept).sum())})
    rows = []
    for profile in rules["profiles"]:
        for method in rules["methods"]:
            values = scores(index, profile["skills"], method)
            for scenario in rules["check_scenarios"]:
                options = {key: scenario.get(key) for key in ("contract", "min_hourly", "min_budget")}
                allowed = filter_mask(jobs, **options).to_numpy()
                candidates = pool & kept & allowed
                top = recommend(index, profile["skills"], method, candidates, k, all_scores=values)
                violations = int((~filter_mask(top, **options)).sum()) if len(top) else 0
                outside = int((~pool_mask(jobs, int(rules["pool_days"])).loc[top.index]).sum()) if len(top) else 0
                rows.append({
                    "profile_id": profile["id"], "method": method, "scenario": scenario["name"],
                    "candidates": int(candidates.sum()), "matching_candidates": int((values[candidates] > 0).sum()),
                    "results": len(top), "distinct_titles": int(top["title_key"].nunique()) if len(top) else 0,
                    "has_5": len(top) >= 5, "has_10": len(top) >= 10, "zero_results": len(top) == 0,
                    "filter_violations": violations, "outside_pool": outside,
                })
    return pd.DataFrame(rows), pd.DataFrame(pools)


def score_relevance(results: pd.DataFrame, labels: pd.DataFrame, rules: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str, str]:
    """Join the judgements to every method's results and compute nDCG@5 and strict P@5."""
    k = int(rules["eval_top_k"])
    judged = labels[["profile_id", "title_key", "relevance"]]
    items = results.merge(judged, on=["profile_id", "title_key"], how="left", validate="many_to_one")
    if items["relevance"].isna().any():
        missing = items.loc[items["relevance"].isna(), ["profile_id", "title_key"]].drop_duplicates()
        raise LabelSheetError(f"{len(missing)} retrieved titles are not in the relevance sheet; "
                              "the sheet does not match the current retrieval")
    by_profile = []
    for profile in rules["profiles"]:
        pid = profile["id"]
        pooled = judged.loc[judged["profile_id"] == pid, "relevance"].tolist()
        for method in rules["methods"]:
            ranked = items[(items["profile_id"] == pid) & (items["method"] == method)].sort_values("rank")
            labels_ranked = ranked["relevance"].tolist()
            by_profile.append({"profile_id": pid, "profile": profile["name"], "method": method,
                               "results": len(ranked), "ndcg_at_5": ndcg_at_k(labels_ranked, pooled, k),
                               "strict_precision_at_5": strict_precision_at_k(labels_ranked, k),
                               "relevant": int(sum(v == 2 for v in labels_ranked)),
                               "partly_relevant": int(sum(v == 1 for v in labels_ranked))})
    by_profile = pd.DataFrame(by_profile)
    summary = (by_profile.groupby("method", sort=False)
               .agg(mean_ndcg=("ndcg_at_5", "mean"), mean_precision=("strict_precision_at_5", "mean"),
                    profiles=("profile_id", "nunique"))
               .reindex(rules["methods"]).reset_index())
    winner, reason = choose_winner(summary, list(rules["methods"]), float(rules["tie_threshold"]))
    summary["winner"] = summary["method"].eq(winner)
    return items[["profile_id", "method", "rank", "row_id", "title_key", "title", "relevance"]], by_profile, summary, winner, reason


RELATED_COLUMNS = ["profile_id", "profile", "method", "keyword", "matching_jobs", "lift", "pay_pct",
                   "trend_relative_pct", "sentence"]


def related_table(index: Index, rules: dict, method: str, processed) -> pd.DataFrame:
    """Related market keywords to explore for every evaluation profile (descriptive only)."""
    def read(name: str) -> pd.DataFrame:
        path = processed / name
        return pd.read_csv(path) if path.is_file() and path.stat().st_size > 1 else pd.DataFrame()

    pay, trend = read("pay_keywords_hourly.csv"), read("trend_keywords.csv")
    candidates = (pool_mask(index.jobs, int(rules["pool_days"])) & index.jobs["newest_in_chain"]).to_numpy()
    market = index.jobs.loc[candidates, "title_key"]
    rows = []
    for profile in rules["profiles"]:
        top = recommend(index, profile["skills"], method, candidates, int(rules["related_top_jobs"]))
        table = related_keywords(top["title_key"], profile["skills"], pay, trend, int(rules["related_min_jobs"]),
                                 int(rules["related_max_terms"]), float(rules["related_max_q"]), market_titles=market,
                                 min_lift=float(rules["related_min_lift"]),
                                 generic_words=frozenset(rules["related_generic_words"]),
                                 prefix_chars=int(rules["related_prefix_chars"]))
        for _, row in table.iterrows():
            rows.append({"profile_id": profile["id"], "profile": profile["name"], "method": method,
                         **row.to_dict(), "sentence": describe_keyword(row)})
    return pd.DataFrame(rows, columns=RELATED_COLUMNS)


def current_evaluation(labels_dir, source_sha256: str, results, rules: dict):
    """(status, detail, scored) for the relevance evaluation of this build.

    The source identity is checked first and independently: a sheet bound to
    another extract is never scored, even if it happens to cover every
    retrieved title. ``results`` is called only when scoring is allowed. A
    bound sheet that no longer covers the retrieved titles stops the build;
    the cause is not assumed.
    """
    status, detail = provenance.label_status(labels_dir, RELEVANCE_SHEET, source_sha256)
    if status != provenance.SCORED:
        return status, detail, None
    try:
        labels = read_relevance_sheet(labels_dir / RELEVANCE_SHEET)
    except LabelSheetError as error:
        return provenance.MALFORMED, str(error), None
    return status, detail, score_relevance(results(), labels, rules)


def historical_guard(labels_dir, source_sha256: str, items: pd.DataFrame, historical_source_sha256: str) -> str:
    """On the designated historical extract, rankings must equal the preserved artifact.

    The historical extract is designated in the settings, independently of the
    record file, so a deleted or edited record cannot silently skip the check.
    For any other extract the comparison does not apply.
    """
    if source_sha256 != historical_source_sha256:
        return "not applicable: not the historical extract"
    historical = provenance.historical_rankings(labels_dir)
    if historical is None:
        raise provenance.ProvenanceError("this is the historical evaluation extract, but the historical ranking "
                                         f"record ({provenance.HISTORICAL_RANKINGS_FILE}) is missing")
    if historical[0]["source_sha256"] != source_sha256:
        raise provenance.ProvenanceError("the historical ranking record describes another extract than the one "
                                         "designated in the settings")
    differences = provenance.compare_rankings(items, historical[1])
    if differences:
        raise provenance.ProvenanceError(f"rankings on the historical extract differ from build "
                                         f"{historical[0]['build_id']}: {differences[0]}")
    return f"identical to build {historical[0]['build_id']}"


def decide_serving(winner: str | None, label_state: str, approval: dict | None, problem: str | None) -> dict[str, Any]:
    """The method this build serves and its status (recorded in the manifest).

    * valid approval: serve the approved method; a different current winner
      is recorded as a mismatch (the app then refuses);
    * no approval file: serve nothing until approved, but record the current
      winner as the method the build used (approval pending);
    * an approval that exists but is invalid is recorded as invalid, never as pending.

    ``label_state`` is recorded with the labels; the status here does not repeat it.
    """
    if approval is not None and problem is None:
        served = approval["approved_method"]
        evidence = approval["evidence"]
        status = ("chosen by the relevance test on this data" if winner is not None else
                  f"chosen by the earlier relevance test (build {evidence['build_id']}); "
                  "this data has no new relevance test")
        return {"recommend_served_method": served, "recommend_method_status": status,
                "recommend_approval_status": "approved", "recommend_approval_ref": approval["ref"],
                "recommend_winner_mismatch": bool(winner is not None and winner != served)}
    approval_state = "pending" if problem is None else (problem if problem.startswith("invalid") else f"invalid: {problem}")
    # The status says only how the method was chosen; the approval state is a separate field.
    status = "chosen by the relevance test on this data" if winner is not None else "no relevance test on this data"
    return {"recommend_served_method": winner or "none", "recommend_method_status": status,
            "recommend_approval_status": approval_state, "recommend_winner_mismatch": False}


def run(settings: Settings, context: dict[str, Any]) -> StepRecord:
    record = StepRecord(NAME, DESCRIPTION)
    rules = settings.section("recommend")
    processed = settings.path("processed_dir")
    jobs = build_jobs(context)
    if jobs["title_key"].fillna("").str.len().gt(0).sum() < 50:
        record.metrics["recommend_skipped"] = f"only {len(jobs)} indexed jobs"
        return record
    index = build_index(jobs, rules)
    context["recommend_index"] = index

    jobs_path = processed / "recommend_jobs.parquet"
    jobs.to_parquet(jobs_path, index=False)
    record.outputs.append(describe_output(jobs_path, settings.root, rows=len(jobs)))
    checks, pools = label_free_checks(index, rules)
    outputs = {"recommend_checks.csv": checks, "recommend_pool_sizes.csv": pools}
    record.metrics.update({
        "recommender_version": str(rules["recommender_version"]),
        "recommend_indexed_jobs": len(jobs),
        "recommend_pool_jobs": int(pools.loc[pools["pool_days"] == int(rules["pool_days"]), "jobs_after_reposts"].iloc[0]),
        "recommend_filter_violations": int(checks["filter_violations"].sum()),
        "recommend_zero_result_cases": int(checks["zero_results"].sum()),
    })

    item_columns = ["profile_id", "method", "rank", "row_id", "title_key", "title", "relevance"]
    tables = (pd.DataFrame(columns=item_columns), pd.DataFrame(columns=["profile_id", "method"]),
              pd.DataFrame(columns=["method"]))
    related = pd.DataFrame(columns=RELATED_COLUMNS)
    labels_dir = settings.path("labels_dir")
    source_sha256 = context["source"]["sha256"]

    # 1. Current evaluation: only when the relevance sheet is bound to this extract.
    status, detail, scored = current_evaluation(labels_dir, source_sha256, lambda: evaluation_results(index, rules), rules)
    winner = None
    if scored is not None:
        items, by_profile, summary, winner, reason = scored
        tables = (items, by_profile, summary)
        record.metrics.update({
            "relevance_labels_sha256": sha256_file(labels_dir / RELEVANCE_SHEET),
            "recommend_winner": winner, "recommend_winner_reason": reason,
            "recommend_winner_ndcg_at_5": round(float(summary.loc[summary["winner"], "mean_ndcg"].iloc[0]), 4),
            "recommend_historical_rankings": historical_guard(
                labels_dir, source_sha256, items, str(settings.section("labels")["historical_source_sha256"])),
        })
    record.metrics["relevance_labels"] = status if status == provenance.SCORED else f"{status}: {detail}"

    # 2. Which method this build serves, and with what standing.
    try:
        approval = provenance.load_approval(settings)
        problem = None if approval is None else "; ".join(provenance.scope_problems(approval, settings)) or None
    except provenance.ApprovalError as error:
        approval, problem = None, f"invalid: {error}"
    record.metrics.update(decide_serving(winner, status, approval, problem))
    served = None if record.metrics["recommend_served_method"] == "none" else record.metrics["recommend_served_method"]

    # 3. Related keywords use the served method, or are explicitly unavailable.
    if served:
        related = related_table(index, rules, served, processed)
        record.metrics["recommend_related_status"] = f"generated with {served}"
    else:
        record.metrics["recommend_related_status"] = "unavailable: no method to serve"
    outputs.update({"recommend_relevance_items.csv": tables[0], "recommend_relevance_by_profile.csv": tables[1],
                    "recommend_relevance_summary.csv": tables[2], "recommend_related_keywords.csv": related})
    for name, table in outputs.items():
        out = write_csv(table.round(6) if len(table) else table, processed / name)
        record.outputs.append(describe_output(out, settings.root, rows=len(table)))
    return record
