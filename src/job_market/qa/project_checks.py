"""Project-specific lineage checks, registered in one explicit place.

``run_lineage_check`` imports this module directly, so every check here
always runs; nothing depends on some other module happening to be imported
first. Later project stages add their checks (database row counts, dashboard
data, API outputs) to this file.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..environment import ENVIRONMENT_FILE, compare, current_problems, read_pins, strict_mode
from ..fingerprint import verify_installed_package
from .findings import ERROR, OK, WARNING, Report


def _mismatch_level() -> str:
    """Environment differences are warnings, and errors in strict mode."""
    return ERROR if strict_mode() else WARNING


def _report_mismatches(report: Report, label: str, problems: list[str]) -> None:
    """One finding per environment, listing every package that differs."""
    if problems:
        listed = "; ".join(problems)
        report.add(_mismatch_level(), "environment", f"{label} differs from {ENVIRONMENT_FILE} in {len(problems)} "
                   f"package(s): {listed}")


def check_build_environment(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    """The environment that builds the outputs must match environment.yml."""
    pins = read_pins(settings.root)
    if pins is None:
        report.add(ERROR, "environment", f"{ENVIRONMENT_FILE} is missing, so the build environment is not reproducible")
        return
    problems = compare(pins, manifest.get("environment", {}), label="build")
    if not problems:
        report.add(OK, "environment", f"build environment matches all {len(pins)} pins")
    _report_mismatches(report, "the build environment", problems)


def check_current_environment(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    """The environment running this check must match environment.yml too."""
    problems = current_problems(settings.root)
    if problems is None:
        return  # the missing file is already reported by check_build_environment
    if not problems:
        report.add(OK, "environment", "running environment matches all pins")
    _report_mismatches(report, "the running environment", problems)


def check_installed_package(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    """The code running this check must be this project's own src/job_market."""
    verify_installed_package(settings)
    report.add(OK, "package", "installed job_market package matches src/job_market")


def check_database(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    """The SQLite database's build_info must carry the current build's input fingerprints."""
    from ..database import DATABASE_FILE, build_info, matches_build

    path = settings.path("processed_dir") / DATABASE_FILE
    if settings.relative(path) not in {entry["path"] for entry in manifest["outputs"]}:
        return                                          # this build has no database step
    if not path.is_file():
        report.add(ERROR, "database", "database file is missing", settings.relative(path))
        return
    if matches_build(build_info(path), manifest):
        report.add(OK, "database", "build_info fingerprints match the current build")
    else:
        report.add(ERROR, "database", "database build_info fingerprints differ from the current build; rebuild")


ARRANGEMENT_AUDIT = "reports/arrangement_audit"


def check_arrangement_audit(settings: Settings, manifest: dict[str, Any], report: Report) -> None:
    """The scored D-041 results must still describe the label sheets they were scored on."""
    import json

    from ..manifest import sha256_file

    folder = settings.root / ARRANGEMENT_AUDIT
    record_path = folder / "scoring_record.json"
    if not record_path.is_file():
        if folder.is_dir() and any(p.is_file() for p in folder.iterdir()):
            report.add(ERROR, "arrangement", "saved arrangement results have no scoring_record.json: "
                       "incomplete audit evidence", ARRANGEMENT_AUDIT)
        else:
            report.add(OK, "arrangement", "arrangement evaluation not scored in this project")
        return
    record = json.loads(record_path.read_text(encoding="utf-8"))
    labels = settings.path("labels_dir")
    problems = []
    for name, key in (("arrangement_eval.xlsx", "evaluation_labels_sha256"),
                      ("arrangement_diagnostic.xlsx", "diagnostic_labels_sha256")):
        path = labels / name
        if not path.is_file():
            problems.append(f"{settings.relative(path)} is missing")
        elif sha256_file(path) != record.get(key):
            problems.append(f"{settings.relative(path)} differs from the labels the D-041 results were scored on")
    if not (folder / "results.csv").is_file():
        problems.append(f"{ARRANGEMENT_AUDIT}/results.csv is missing")
    for problem in problems:
        report.add(ERROR, "arrangement", problem)
    if not problems:
        report.add(OK, "arrangement", "arrangement label sheets match the scoring record; results.csv present")


CHECKS = (check_build_environment, check_current_environment, check_installed_package, check_database,
          check_arrangement_audit)
