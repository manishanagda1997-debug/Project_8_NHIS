"""Approve the evaluated recommender for serving (decision D-040).

``python -m job_market approve-recommender`` writes
``config/recommender_approval.toml`` only when all of these hold:

1. the current build is complete and current: code and settings match it,
   every output has its recorded hash, and the environment check passes;
2. the data is the historical evaluation extract (the command approves that
   evaluation, never arbitrary new data);
3. the relevance sheet is bound to this extract and the build recorded a
   completed relevance evaluation with a winner and no mismatch;
4. the build's rankings equal the preserved historical rankings, compared
   row by row here (not only read from the build's status);
5. every evidence hash matches its file.

It shows the evidence and asks for "yes". Before writing it checks again that
nothing changed and that no approval exists, creates the file exclusively
(never replacing one), reads it back with the normal loader, and removes it
again if anything fails. Any other answer writes nothing.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from . import provenance
from .config import Settings
from .environment import EnvironmentMismatchError, current_problems, enforce
from .fingerprint import project_code_sha256
from .manifest import IntegrityError, load_manifest, sha256_file, verify_output
from .steps.recommend import RELEVANCE_SHEET

RELEVANCE_ITEMS = "recommend_relevance_items.csv"


class ApproveError(Exception):
    """The approval cannot be written: the reason is in the message."""


def checked_build(settings: Settings) -> dict[str, Any]:
    """The current build after the same checks the app and the lineage check use."""
    try:
        manifest = load_manifest(settings.path("manifest"))
    except (FileNotFoundError, ValueError) as error:
        raise ApproveError(f"no usable build: {error}") from error
    recorded = manifest.get("fingerprints", {})
    stale = [label for key, label, current in (("code_sha256", "code", project_code_sha256(settings)),
                                               ("config_sha256", "settings", settings.config_sha256))
             if recorded.get(key) != current]
    if stale:
        raise ApproveError(f"the build is stale ({', '.join(stale)} changed since it ran); rebuild first")
    try:
        enforce(current_problems(settings.root), "The approval environment")
    except EnvironmentMismatchError as error:
        raise ApproveError(str(error)) from error
    try:
        for entry in manifest["outputs"]:
            verify_output(entry, settings.root)
    except IntegrityError as error:
        raise ApproveError(f"the build outputs do not match the manifest: {error}") from error
    return manifest


def _recommend_metrics(manifest: dict[str, Any]) -> dict[str, Any]:
    steps = {step["name"]: step for step in manifest.get("steps", [])}
    if "recommend" not in steps:
        raise ApproveError("the build has no recommend step")
    return steps["recommend"].get("metrics", {})


def prepare(settings: Settings) -> dict[str, Any]:
    """Every check, the evidence and a snapshot of the files it rests on. Raises ApproveError."""
    manifest = checked_build(settings)
    metrics = _recommend_metrics(manifest)
    labels_dir = settings.path("labels_dir")
    source = str(manifest.get("fingerprints", {}).get("source_sha256", ""))
    historical_source = str(settings.section("labels")["historical_source_sha256"])

    try:
        historical = provenance.historical_rankings(labels_dir)
    except provenance.ProvenanceError as error:
        raise ApproveError(str(error)) from error
    if historical is None:
        raise ApproveError(f"the historical ranking record {provenance.HISTORICAL_RANKINGS_FILE} is missing")
    record, preserved = historical
    if not (source == historical_source == str(record.get("source_sha256", ""))):
        raise ApproveError("this data is not the historical evaluation extract; this command approves only that "
                           "evaluation (a committed approval carries over to later extracts under D-040)")

    status, detail = provenance.label_status(labels_dir, RELEVANCE_SHEET, source)
    if status != provenance.SCORED:
        raise ApproveError(f"the relevance labels are not usable for this extract: {status}: {detail}")
    winner = metrics.get("recommend_winner")
    if metrics.get("relevance_labels") != provenance.SCORED or not winner:
        raise ApproveError("the build has no completed relevance evaluation (no scored winner recorded)")
    if metrics.get("recommend_winner_mismatch") or metrics.get("recommend_served_method") != winner:
        raise ApproveError("the build's served method differs from its scored winner; a person must decide first")
    if metrics.get("recommend_method_status") != "chosen by the relevance test on this data":
        raise ApproveError(f"unexpected method status: {metrics.get('recommend_method_status')!r}")
    if not str(metrics.get("recommend_historical_rankings", "")).startswith("identical"):
        raise ApproveError(f"the build did not confirm the historical rankings: "
                           f"{metrics.get('recommend_historical_rankings')!r}")

    items_entry = next((o for o in manifest["outputs"] if o["path"].endswith(RELEVANCE_ITEMS)), None)
    if items_entry is None:
        raise ApproveError(f"{RELEVANCE_ITEMS} is not an output of this build")
    items = pd.read_csv(verify_output(items_entry, settings.root),
                        dtype={"profile_id": str, "method": str, "title_key": str})
    differences = provenance.compare_rankings(items, preserved)
    if differences:
        raise ApproveError(f"rankings differ from the historical build {record['build_id']}: {differences[0]}")

    labels_sha = sha256_file(labels_dir / RELEVANCE_SHEET)
    if metrics.get("relevance_labels_sha256") != labels_sha:
        raise ApproveError("the relevance sheet differs from the one this build scored")
    rankings_path = labels_dir / str(record["file"])
    rankings_sha = sha256_file(rankings_path)
    if rankings_sha != record["sha256"]:
        raise ApproveError("the historical ranking file differs from its recorded hash")

    tie = settings.section("recommend")["tie_threshold"]
    rule = (f"highest mean nDCG@5; differences below {tie} by strict Precision@5; then the simpler method "
            f"(frozen at tag recommender-1.0); this build: {metrics.get('recommend_winner_reason', '')}")
    evidence = {"build_id": str(record["build_id"]), "source_sha256": source, "labels_sha256": labels_sha,
                "rankings_file": str(record["file"]), "rankings_sha256": rankings_sha, "selection_rule": rule}
    snapshot = {name: sha256_file(path) for name, path in (
        ("manifest", settings.path("manifest")), ("relevance sheet", labels_dir / RELEVANCE_SHEET),
        ("label sources", labels_dir / provenance.LABEL_SOURCES_FILE),
        ("historical record", labels_dir / provenance.HISTORICAL_RANKINGS_FILE), ("historical rankings", rankings_path))}
    return {"method": winner, "current_build": manifest["run_id"], "evidence": evidence, "snapshot": snapshot,
            "ndcg_at_5": metrics.get("recommend_winner_ndcg_at_5"), "rows": len(items)}


def summary(prepared: dict[str, Any]) -> list[str]:
    evidence = prepared["evidence"]
    return [
        f"Method to approve:        {prepared['method']}",
        f"Current build:            {prepared['current_build']}",
        f"Historical evaluation:    {evidence['build_id']}",
        f"Mean nDCG@5 (this build): {prepared['ndcg_at_5']}",
        f"Rankings:                 {prepared['rows']} rows, identical to the historical build",
        f"Selection rule:           {evidence['selection_rule']}",
        f"Source extract:           {evidence['source_sha256']}",
        f"Relevance labels:         {evidence['labels_sha256']}",
        f"Historical rankings file: {evidence['rankings_file']} ({evidence['rankings_sha256']})",
        "Checks passed: current build, output hashes, environment, historical extract, label binding,",
        "completed evaluation, no winner mismatch, rankings identical, evidence hashes.",
    ]


def write_exclusive(settings: Settings, method: str, evidence: dict[str, str]):
    """Create the approval file without ever replacing one, then read it back; remove it if anything fails."""
    path = settings.root / provenance.APPROVAL_FILE
    text = provenance.approval_text(settings, method, evidence)
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as error:
        raise ApproveError(f"{provenance.APPROVAL_FILE.as_posix()} already exists; it is never replaced") from error
    except OSError:
        path.unlink(missing_ok=True)
        raise
    try:
        loaded = provenance.load_approval(settings)
        if loaded is None or loaded["approved_method"] != method:
            raise ApproveError("the written approval could not be read back")
    except (provenance.ApprovalError, ApproveError) as error:
        path.unlink(missing_ok=True)
        raise ApproveError(f"the written approval is not valid and was removed: {error}") from error
    return path


def approve(settings: Settings, confirm: Callable[[str], str] = input, out: Callable[[str], None] = print) -> int:
    """Run the checks, show the evidence, and write the approval after "yes". Returns an exit code."""
    approval_path = settings.root / provenance.APPROVAL_FILE
    try:
        if approval_path.exists():
            raise ApproveError(f"{provenance.APPROVAL_FILE.as_posix()} already exists; it is never replaced")
        prepared = prepare(settings)
        for line in summary(prepared):
            out(line)
        answer = confirm("Type yes to approve this method for serving: ")
        if answer.strip().lower() != "yes":
            out("Cancelled. Nothing was written.")
            return 1
        again = prepare(settings)                       # nothing may change between the summary and the write
        if again["snapshot"] != prepared["snapshot"] or again["evidence"] != prepared["evidence"]:
            raise ApproveError("the build or the evidence changed after the summary; nothing was written")
        path = write_exclusive(settings, prepared["method"], prepared["evidence"])
    except ApproveError as error:
        out(f"Not approved: {error}")
        return 1
    out(f"wrote {settings.relative(path)}: approval of {prepared['method']}")
    out("Next: commit this file, rebuild, then start the app.")
    return 0
