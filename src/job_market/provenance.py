"""Label provenance and the recommender serving approval (decisions D-039, D-040).

Two separate questions, kept apart on purpose:

1. **May these human labels be scored against this build?** Each label sheet
   is bound, in ``data/labels/label_sources.toml``, to its own file hash and
   to the hash of the raw extract it was drawn from. Scoring happens only when
   the sheet exists, the binding is complete and valid, the sheet's bytes
   match the binding, and the current raw extract is that source. Otherwise a
   distinct status is recorded and nothing is scored.

2. **May the app serve a recommendation method?** ``config/recommender_approval.toml``
   records the approved method, the implementation it was approved for
   (code files, settings, library versions) and, separately, the evidence
   that justified it (historical build, source, labels, rankings). Changed
   code or settings stop the app. Different library versions follow the
   project's environment rule: a visible warning, and an error only in
   strict mode (``JOB_MARKET_STRICT=1``). The evidence part describes the
   past and is never compared with a new extract, so a monthly refresh can
   still be served with the historically approved method.

Hashes stop accidental mismatches; they do not prove provenance against a
coordinated edit of both data and records. Review of the Git history
supports provenance but does not guarantee that such an edit is detected.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Settings
from .environment import strict_mode
from .manifest import sha256_file

LABEL_SOURCES_FILE = "label_sources.toml"
APPROVAL_FILE = Path("config") / "recommender_approval.toml"
HISTORICAL_RANKINGS_FILE = "historical_rankings.toml"
RANKING_FIELDS = ["profile_id", "method", "rank", "row_id", "title_key"]

# What the approved recommender implementation consists of. Whole files, so
# every constant and helper inside them is covered.
APPROVAL_CODE_FILES = ("recommend.py", "text.py", "steps/clean.py", "steps/recommend.py")
APPROVAL_SETTING_SECTIONS = ("recommend", "cleaning")
APPROVAL_LIBRARIES = ("numpy", "pandas", "scipy", "scikit-learn")

SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Why the method was approved: required, verifiable fields (never compared with a new extract).
EVIDENCE_TEXT = ("build_id", "rankings_file", "selection_rule")
EVIDENCE_HASHES = ("source_sha256", "labels_sha256", "rankings_sha256")

# Label statuses (one of these is recorded for every sheet).
SCORED = "scored"
MISSING = "missing"
MALFORMED = "malformed"
WRONG_SOURCE = "labels belong to another extract"
NO_IDENTITY = "source identity unavailable"


class ProvenanceError(Exception):
    """Labels and data disagree although the source identity matches: the build must stop."""


class ApprovalError(Exception):
    """The approval file exists but is malformed or does not fit this project."""


class ServingError(Exception):
    """The app must not serve recommendations from this build."""


# ------------------------------------------------------------ label sources

def _read_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_bytes().decode("utf-8"))


def label_status(labels_dir: Path, sheet: str, current_source_sha256: str) -> tuple[str, str]:
    """(status, detail) for one label sheet, checked before any join or score.

    Order: the sheet exists; its binding is present and valid; the sheet's
    bytes match the binding; the current raw extract is the bound source.
    Content validation of the sheet itself follows in the reader (a failure
    there is also ``malformed``).
    """
    path = Path(labels_dir) / sheet
    if not path.is_file():
        return MISSING, f"{sheet} not found"
    sources = Path(labels_dir) / LABEL_SOURCES_FILE
    if not sources.is_file():
        return NO_IDENTITY, f"{LABEL_SOURCES_FILE} is missing"
    try:
        entry = _read_toml(sources).get(sheet)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        return NO_IDENTITY, f"{LABEL_SOURCES_FILE} cannot be read: {error}"
    if not isinstance(entry, dict):
        return NO_IDENTITY, f"{LABEL_SOURCES_FILE} has no entry for {sheet}"
    for key in ("sheet_sha256", "source_sha256"):
        if not SHA256.match(str(entry.get(key, ""))):
            return NO_IDENTITY, f"{LABEL_SOURCES_FILE}: {sheet} has no valid {key}"
    if sha256_file(path) != entry["sheet_sha256"]:
        return MALFORMED, f"{sheet} differs from the file recorded in {LABEL_SOURCES_FILE}"
    if current_source_sha256 != entry["source_sha256"]:
        return WRONG_SOURCE, f"{sheet} was drawn from source {entry['source_sha256'][:12]}, not this extract"
    return SCORED, "source identity verified"


def bind_label_sheet(labels_dir: Path, sheet: str, source_sha256: str, note: str = "") -> Path:
    """Record or replace the binding of one sheet to its file hash and source extract.

    The function records or replaces the binding for a final sheet. The TOML
    file keeps each binding visible in the Git history.
    """
    labels_dir = Path(labels_dir)
    path = labels_dir / LABEL_SOURCES_FILE
    entries = _read_toml(path) if path.is_file() else {}
    entries[sheet] = {"sheet_sha256": sha256_file(labels_dir / sheet), "source_sha256": source_sha256,
                      **({"note": note} if note else {})}
    lines = ["# Each human label sheet, bound to its exact bytes and to the raw extract it",
             "# was drawn from (decision D-039). Labels are scored only against that extract.", ""]
    for name in sorted(entries):
        lines.append(f"[{json.dumps(name)}]")
        lines += [f"{key} = {json.dumps(value)}" for key, value in entries[name].items()]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path


def verify_label_titles(labels: pd.DataFrame, jobs: pd.DataFrame, sheet: str) -> None:
    """Every labelled row_id must still point to the title that was labelled.

    After the source identity matches, any row ID and title mismatch stops the
    build. The check does not assume the cause.
    """
    titles = jobs.set_index("row_id")["title_clean"]
    found = labels["row_id"].map(titles)
    bad = labels.loc[found.isna() | (found.astype(str) != labels["title"].astype(str)), "sample_id"].tolist()
    if bad:
        raise ProvenanceError(f"{sheet}: {len(bad)} labelled rows no longer match their title, e.g. {bad[:5]}")


# ------------------------------------------------------------ approval scope

def approval_code_sha256(package_dir: Path) -> str:
    digest = hashlib.sha256()
    for relative in APPROVAL_CODE_FILES:
        text = (Path(package_dir) / relative).read_bytes().decode("utf-8").replace("\r\n", "\n")
        digest.update(relative.encode("utf-8") + b"\0" + text.encode("utf-8") + b"\0")
    return digest.hexdigest()


def approval_settings_sha256(settings: Settings) -> str:
    sections = {name: settings.section(name) for name in APPROVAL_SETTING_SECTIONS}
    return hashlib.sha256(json.dumps(sections, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def library_versions() -> dict[str, str]:
    return {name: metadata.version(name) for name in APPROVAL_LIBRARIES}


def current_scope(settings: Settings) -> dict[str, Any]:
    return {"code_sha256": approval_code_sha256(settings.root / "src" / "job_market"),
            "settings_sha256": approval_settings_sha256(settings),
            "libraries": library_versions()}


def load_approval(settings: Settings) -> dict[str, Any] | None:
    """The approval record, or None when there is none (approval pending).

    A file that exists but cannot be used raises ApprovalError: it is never
    treated as pending.
    """
    path = settings.root / APPROVAL_FILE
    if not path.is_file():
        return None
    try:
        record = _read_toml(path)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ApprovalError(f"{APPROVAL_FILE.as_posix()} cannot be read: {error}") from error
    method = record.get("approved_method")
    scope, evidence = record.get("scope"), record.get("evidence")
    if not isinstance(method, str) or not isinstance(scope, dict) or not isinstance(evidence, dict):
        raise ApprovalError(f"{APPROVAL_FILE.as_posix()} needs approved_method, [scope] and [evidence]")
    if method not in settings.section("recommend")["methods"]:
        raise ApprovalError(f"approved method {method!r} is not one of the configured methods")
    for key in ("code_sha256", "settings_sha256"):
        if not SHA256.match(str(scope.get(key, ""))):
            raise ApprovalError(f"[scope] has no valid {key}")
    if not isinstance(scope.get("libraries"), dict) or set(scope["libraries"]) != set(APPROVAL_LIBRARIES):
        raise ApprovalError(f"[scope.libraries] must list exactly {list(APPROVAL_LIBRARIES)}")
    for key in EVIDENCE_TEXT:
        if not str(evidence.get(key, "")).strip():
            raise ApprovalError(f"[evidence] has no {key}")
    for key in EVIDENCE_HASHES:
        if not SHA256.match(str(evidence.get(key, ""))):
            raise ApprovalError(f"[evidence] has no valid {key}")
    # Line endings are normalised, so a Windows and a Linux checkout give the same reference.
    record["ref"] = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return record


def approval_text(settings: Settings, method: str, evidence: dict[str, str]) -> str:
    """The approval record for ``method``: scope from the project as it is now, evidence as supplied."""
    scope = current_scope(settings)
    lines = ["# Recommender serving approval (decision D-040). Written after review of the evidence.",
             "# [scope] must match the running implementation; [evidence] records why the",
             "# method was approved and is never compared with a new extract.",
             f"approved_method = {json.dumps(method)}", "", "[scope]",
             f"code_sha256 = {json.dumps(scope['code_sha256'])}",
             f"settings_sha256 = {json.dumps(scope['settings_sha256'])}", "", "[scope.libraries]"]
    lines += [f"{json.dumps(name)} = {json.dumps(version)}" for name, version in scope["libraries"].items()]
    lines += ["", "[evidence]"] + [f"{key} = {json.dumps(str(value))}" for key, value in evidence.items()]
    return "\n".join(lines) + "\n"


def write_approval(settings: Settings, method: str, evidence: dict[str, str]) -> Path:
    """Write the approval record for ``method`` against the current implementation.

    A deliberate act by a person, after reviewing the evidence. The
    ``approve-recommender`` command adds the checks and never overwrites.
    """
    path = settings.root / APPROVAL_FILE
    path.write_text(approval_text(settings, method, evidence), encoding="utf-8", newline="\n")
    return path


def library_difference(approval: dict[str, Any]) -> str | None:
    """A description of library versions that differ from the approval, or None."""
    approved = {str(k): str(v) for k, v in approval["scope"]["libraries"].items()}
    running = library_versions()
    if approved == running:
        return None
    changed = [f"{name} {approved.get(name)} -> {running.get(name)}" for name in APPROVAL_LIBRARIES
               if approved.get(name) != running.get(name)]
    return "library versions differ from the approval: " + ", ".join(changed)


def scope_problems(approval: dict[str, Any], settings: Settings) -> list[str]:
    """Differences that stop serving: changed code or settings, and library
    versions only in strict mode (otherwise they are a warning, see
    ``library_difference``)."""
    current = current_scope(settings)
    scope = approval["scope"]
    problems = []
    if scope["code_sha256"] != current["code_sha256"]:
        problems.append("recommender code changed since approval")
    if scope["settings_sha256"] != current["settings_sha256"]:
        problems.append("recommender or cleaning settings changed since approval")
    libraries = library_difference(approval)
    if libraries and strict_mode():
        problems.append(f"{libraries} (strict mode)")
    return problems


# ------------------------------------------------------------ historical rankings

def historical_rankings(labels_dir: Path) -> tuple[dict[str, Any], pd.DataFrame] | None:
    """The preserved historical ranking artifact and its metadata, if present."""
    meta_path = Path(labels_dir) / HISTORICAL_RANKINGS_FILE
    if not meta_path.is_file():
        return None
    meta = _read_toml(meta_path)
    artifact = Path(labels_dir) / str(meta["file"])
    if sha256_file(artifact) != meta["sha256"]:
        raise ProvenanceError(f"historical ranking artifact {meta['file']} differs from its recorded hash")
    return meta, pd.read_csv(artifact, dtype={"profile_id": str, "method": str, "title_key": str})


def compare_rankings(items: pd.DataFrame, historical: pd.DataFrame) -> list[str]:
    """Differences between current and historical rankings on the defined fields."""
    def norm(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame[RANKING_FIELDS].copy()
        out["rank"] = out["rank"].astype("int64")
        out["row_id"] = out["row_id"].astype("int64")
        out["title_key"] = out["title_key"].astype(str)
        return out.sort_values(["profile_id", "method", "rank"]).reset_index(drop=True)

    a, b = norm(items), norm(historical)
    if len(a) != len(b):
        return [f"{len(a)} ranked results now, {len(b)} historically"]
    diff = (a != b).any(axis=1)
    return [f"{int(diff.sum())} ranked results differ, e.g. {a.loc[diff].head(3).to_dict('records')}"] if diff.any() else []


# ------------------------------------------------------------ serving decision

def serving_decision(settings: Settings, manifest: dict[str, Any]) -> dict[str, Any]:
    """Whether and how the app may serve this build; raises ServingError if not.

    Assumes the caller has already verified code/settings fingerprints and
    output hashes (the app loader and the lineage check both do).
    """
    steps = {step["name"]: step for step in manifest.get("steps", [])}
    metrics = steps.get("recommend", {}).get("metrics", {})
    served = metrics.get("recommend_served_method")
    try:                                    # an unusable approval file is reported first, as the cause
        approval = load_approval(settings)
    except ApprovalError as error:
        raise ServingError(f"approval invalid: {error}") from error
    if not served or served == "none":
        raise ServingError("this build has no method to serve: no current evaluation and no valid approval "
                           f"({metrics.get('recommend_method_status', 'not recorded')})")
    if metrics.get("recommend_winner_mismatch"):
        raise ServingError(f"the evaluation on this data selects {metrics.get('recommend_winner')!r}, "
                           f"but the approved method is {served!r}: a person must decide; nothing switches automatically")
    if approval is None:
        raise ServingError(f"approval pending: no {APPROVAL_FILE.as_posix()}; this build can serve {served!r} "
                           "only after it is approved")
    problems = scope_problems(approval, settings)
    if problems:
        raise ServingError("approval no longer matches the implementation: " + "; ".join(problems))
    if approval["approved_method"] != served:
        raise ServingError(f"approval changed after this build (approves {approval['approved_method']!r}, "
                           f"build used {served!r}); rebuild")
    build_ref = metrics.get("recommend_approval_ref")
    notes = []
    if build_ref is None:
        notes.append("approval recorded after this build")
    elif build_ref != approval["ref"]:
        notes.append("approval record updated after this build (same method)")
    libraries = library_difference(approval)
    if libraries:
        notes.append(f"warning: {libraries}")
    return {"method": served, "method_status": metrics.get("recommend_method_status", ""),
            "approval_note": "; ".join(notes), "approval_ref": approval["ref"], "build_approval_ref": build_ref}
