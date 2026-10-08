"""Lineage check: prove that every artifact comes from the current build.

The check fails when:

* the raw data, configuration, source code or pinned environment differ
  from the build recorded in the manifest (the outputs are stale);
* an output file is missing or its bytes differ from the manifest hash;
* a generated folder contains a file that the manifest does not list;
* a notebook has a code cell without execution, cells that do not run in
  order 1, 2, 3 ..., an error output, a first code cell that does not call
  ``start()``, or outputs from a different build (``run_id``).

A build or running environment that differs from ``environment.yml`` is a
warning, and an error in strict mode (see ``qa/project_checks.py``).

A check that cannot complete (for example because a file is missing) is
reported as an error; the lineage check itself never stops with a crash.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from ..config import Settings, load_settings
from ..environment import strict_mode
from ..fingerprint import LABELS, current_fingerprints
from ..manifest import load_manifest, sha256_file
from .. import provenance
from . import project_checks
from .findings import ERROR, OK, WARNING, Report
from .notebooks import METADATA_KEY, project_notebooks

RUN_ID_PREFIX = "RUN_ID:"


def check_fingerprints(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    recorded = manifest.get("fingerprints", {})
    current = current_fingerprints(settings)
    for key, label in LABELS.items():
        if recorded.get(key) == current.get(key):
            report.add(OK, "fingerprint", f"{label} matches the build")
        else:
            report.add(
                ERROR, "fingerprint", f"{label} differs from the build; rebuild with `python -m job_market rebuild`"
            )


def check_outputs(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    for entry in manifest["outputs"]:
        path = settings.root / entry["path"]
        if not path.is_file():
            report.add(ERROR, "output", "file listed in the manifest is missing", entry["path"])
        elif sha256_file(path) != entry["sha256"]:
            report.add(ERROR, "output", "file content differs from the manifest hash", entry["path"])
        else:
            report.add(OK, "output", "hash matches", entry["path"])


def check_no_untracked_outputs(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    listed = {entry["path"] for entry in manifest["outputs"]}
    listed.add(settings.relative(settings.path("manifest")))
    for key in ("interim_dir", "processed_dir"):
        folder = settings.path(key)
        if not folder.exists():
            continue
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            relative = settings.relative(path)
            if relative not in listed:
                report.add(ERROR, "untracked", "file is not part of the current build (stale leftover?)", relative)


def _strip_magics(source: str) -> str:
    return "\n".join("" if line.lstrip().startswith(("%", "!")) else line for line in source.splitlines())


def calls_start(source: str) -> bool:
    """True when the code imports ``start`` from ``job_market.notebook`` and calls it,
    or calls ``<alias>.start()`` on an imported ``job_market.notebook`` module."""
    try:
        tree = ast.parse(_strip_magics(source))
    except SyntaxError:
        return False
    start_names: set[str] = set()
    module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "job_market.notebook":
            start_names |= {alias.asname or alias.name for alias in node.names if alias.name == "start"}
        elif isinstance(node, ast.ImportFrom) and node.module == "job_market":
            module_aliases |= {alias.asname or alias.name for alias in node.names if alias.name == "notebook"}
        elif isinstance(node, ast.Import):
            module_aliases |= {
                alias.asname for alias in node.names if alias.name == "job_market.notebook" and alias.asname
            }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in start_names:
            return True
        if isinstance(func, ast.Attribute) and func.attr == "start":
            target = func.value
            if isinstance(target, ast.Name) and target.id in module_aliases:
                return True
            if ast.unparse(target) == "job_market.notebook":
                return True
    return False


def _cell_text(cell: dict[str, Any]) -> tuple[str, list[str]]:
    texts, errors = [], []
    for output in cell.get("outputs", []):
        if output.get("output_type") == "error":
            errors.append(f"{output.get('ename')}: {output.get('evalue')}")
        texts.append("".join(output.get("text", "")))
        texts.append("".join(output.get("data", {}).get("text/plain", "")))
    return "\n".join(texts), errors


def notebook_status(path: Path, manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (level, message) problems for one executed notebook."""
    run_id = manifest["run_id"]
    problems: list[tuple[str, str]] = []
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [(ERROR, f"cannot read notebook: {exc}")]

    code_cells = [
        c for c in notebook.get("cells", []) if c.get("cell_type") == "code" and "".join(c.get("source", "")).strip()
    ]
    if not code_cells:
        return [(WARNING, "notebook has no code cells")]

    # 1. A clean top-to-bottom run: every code cell executes, in order.
    counts = [cell.get("execution_count") for cell in code_cells]
    if any(count is None for count in counts):
        problems.append((ERROR, "some code cells are not executed; run `python -m job_market run-notebooks`"))
    elif counts != list(range(1, len(counts) + 1)):
        problems.append((ERROR, f"execution order is {counts}, not a clean top-to-bottom run 1..{len(counts)}"))

    # 2. No errors, and the first code cell verifies the build.
    if not calls_start("".join(code_cells[0].get("source", ""))):
        problems.append((ERROR, "the first code cell does not call start() from job_market.notebook"))
    cited_per_cell = []
    for cell in code_cells:
        text, errors = _cell_text(cell)
        problems += [(ERROR, f"cell output contains an error: {error}") for error in errors]
        cited_per_cell.append(
            [line.split(RUN_ID_PREFIX, 1)[1].strip() for line in text.splitlines() if RUN_ID_PREFIX in line]
        )
    if not cited_per_cell[0]:
        problems.append((ERROR, "the first code cell does not print the run_id"))

    # 3. The outputs come from the current build.
    recorded = notebook.get("metadata", {}).get(METADATA_KEY, {}).get("run_id")
    cited = {value for values in cited_per_cell for value in values}
    if recorded:
        cited.add(recorded)
    stale = sorted(cited - {run_id})
    if stale:
        problems.append((ERROR, f"notebook outputs come from build {stale}, but the current build is {run_id}"))
    return problems


def check_notebooks(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    folder = settings.path("notebooks_dir")
    notebooks = project_notebooks(folder) if folder.exists() else []
    if not notebooks:
        report.add(ERROR, "notebook", "no notebooks found; the project evidence lives in notebooks")
        return
    for path in notebooks:
        location = settings.relative(path)
        problems = notebook_status(path, manifest)
        if not problems:
            report.add(OK, "notebook", "clean top-to-bottom run of the current build", location)
        for level, message in problems:
            report.add(level, "notebook", message, location)


def check_labels_and_serving(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    """Label provenance statuses and the recommender serving decision (decisions D-039, D-040)."""
    steps = {step["name"]: step for step in manifest.get("steps", [])}
    statuses = {
        "dev labels": steps.get("evaluate", {}).get("metrics", {}).get("dev_labels"),
        "blind labels": steps.get("evaluate", {}).get("metrics", {}).get("blind_labels"),
        "relevance labels": steps.get("recommend", {}).get("metrics", {}).get("relevance_labels"),
    }
    for name, status in statuses.items():
        if status is None or status in (provenance.SCORED, provenance.MISSING):
            report.add(OK, "labels", f"{name}: {status or 'not used in this build'}")
        elif status.startswith(provenance.WRONG_SOURCE):
            report.add(WARNING, "labels", f"{name}: {status}")
        else:
            report.add(ERROR, "labels", f"{name}: {status}")
    recommend = steps.get("recommend", {}).get("metrics", {})
    if "recommend_served_method" not in recommend:
        report.add(OK, "serving", "recommender not built in this build")
        return
    try:
        decision = provenance.serving_decision(settings, manifest)
    except provenance.ServingError as error:
        level = WARNING if str(error).startswith("approval pending") else ERROR
        report.add(level, "serving", str(error))
    else:
        report.add(OK, "serving", f"serves {decision['method']}: {decision['method_status']}")


def run_lineage_check(settings: Settings | None = None) -> Report:
    settings = settings or load_settings()
    report = Report("Lineage check", strict=strict_mode())
    try:
        manifest = load_manifest(settings.path("manifest"))
    except (FileNotFoundError, ValueError) as exc:
        report.add(ERROR, "manifest", str(exc))
        return report
    report.add(OK, "manifest", f"run_id {manifest['run_id']}")
    core = (check_fingerprints, check_outputs, check_no_untracked_outputs, check_notebooks, check_labels_and_serving)
    for check in (*core, *project_checks.CHECKS):
        try:
            check(settings, manifest, report)
        except Exception as exc:  # a failing check is a finding, never a crash
            report.add(ERROR, check.__name__.removeprefix("check_"), f"check cannot complete: {exc}")
    return report


def run_notebook_check(settings: Settings | None = None) -> Report:
    """Check only the saved notebooks against the recorded manifest.

    This needs the manifest but not the raw data, so continuous integration
    can confirm that every committed notebook is a clean, error-free run of
    the committed build.
    """
    settings = settings or load_settings()
    report = Report("Notebook check", strict=strict_mode())
    try:
        manifest = load_manifest(settings.path("manifest"))
    except (FileNotFoundError, ValueError) as exc:
        report.add(ERROR, "manifest", str(exc))
        return report
    try:
        check_notebooks(settings, manifest, report)
    except Exception as exc:  # a failing check is a finding, never a crash
        report.add(ERROR, "notebooks", f"check cannot complete: {exc}")
    return report
