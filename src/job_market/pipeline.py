"""Run every pipeline step in order and write the run manifest.

One command rebuilds every generated file from the raw CSV:

    python -m job_market rebuild

The generated-data folders start empty on every run, so no file from an older
build can survive and be mistaken for current evidence.
"""

from __future__ import annotations

import shutil
import time
from typing import Any, Callable

from . import __version__
from .config import GENERATED_DIR_KEYS, Settings, load_settings, validate_layout
from .environment import current_problems, enforce
from .environment import snapshot as environment_snapshot
from .fingerprint import current_fingerprints, verify_installed_package
from .manifest import (
    MANIFEST_VERSION,
    StepRecord,
    build_run_id,
    utc_now,
    write_manifest,
)
from .steps import STEPS


def reset_generated_dirs(settings: Settings) -> None:
    """Empty the generated-data folders before a build, keeping the folders.

    ``validate_layout`` runs first, so a configuration that points a generated
    folder at raw data, configuration, code, notebooks, tests or docs stops
    the build before anything is deleted.
    """
    validate_layout(settings)
    for key in GENERATED_DIR_KEYS:
        folder = settings.path(key)
        folder.mkdir(parents=True, exist_ok=True)
        # Empty the folder but keep the folder itself: deleting the folder
        # fails on Windows when a sync client such as OneDrive holds it open.
        for item in folder.iterdir():
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()


def run_pipeline(
    settings: Settings | None = None,
    steps: tuple = STEPS,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Rebuild all generated outputs and return the manifest dictionary."""
    settings = settings or load_settings()
    started = utc_now()
    raw_path = settings.path("raw_csv")
    if not raw_path.is_file():
        raise FileNotFoundError(f"Raw CSV not found at {raw_path}")

    # The build runs with this project's own code. A difference from the
    # pinned environment is a warning (an error in strict mode), and the
    # manifest records whether the build matches the pins.
    verify_installed_package(settings)
    environment_problems = enforce(current_problems(settings.root), "The build environment")
    fingerprints = current_fingerprints(settings)
    run_id = build_run_id(fingerprints, started)
    log(f"Run {run_id}: rebuilding outputs from {settings.relative(raw_path)}")

    reset_generated_dirs(settings)
    context: dict[str, Any] = {
        "run_id": run_id,
        "fingerprints": fingerprints,
        "source": {
            "path": settings.relative(raw_path),
            "sha256": fingerprints["source_sha256"],
            "bytes": raw_path.stat().st_size,
        },
    }

    records: list[StepRecord] = []
    counts: dict[str, Any] = {}
    for step in steps:
        tic = time.perf_counter()
        record = step.run(settings, context)
        record.seconds = time.perf_counter() - tic
        clashes = sorted(set(record.metrics) & set(counts))
        if clashes:
            raise RuntimeError(f"Step '{record.name}' repeats metric names already in use: {clashes}")
        counts.update(record.metrics)
        records.append(record)
        log(f"  {record.name:<12} {record.seconds:6.1f}s  {len(record.outputs)} file(s)")

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "project_version": __version__,
        "run_started_utc": started.isoformat().replace("+00:00", "Z"),
        "run_finished_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "fingerprints": fingerprints,
        "source": context["source"],
        "taxonomy_version": settings.taxonomy_version,
        # Filled by the cleaning step; None means the rule is not part of this build yet.
        "excluded_time_series_dates": context.get("excluded_time_series_dates"),
        "config": settings.raw,
        "environment": environment_snapshot(settings.root),
        "environment_matches_pins": not environment_problems,
        "counts": counts,
        "steps": [record.to_dict() for record in records],
        "outputs": [output for record in records for output in record.outputs],
    }
    manifest_path = write_manifest(manifest, settings.path("manifest"))
    log(f"Manifest written to {settings.relative(manifest_path)}")
    if environment_problems:
        log("Note: this build does not match environment.yml; official results come from the pinned environment")
    return manifest
