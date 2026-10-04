"""Helpers that every notebook calls in its first code cell.

``start()`` locates the project, loads the configuration and the run manifest,
and refuses to continue when the raw data, the settings, the code, the pinned
environment definition or any output file differ from the recorded build.
An environment that differs from ``environment.yml`` gives a warning (an
error in strict mode). It then prints the ``run_id``, which links the
notebook's saved outputs to the exact build that produces them.

``Project.read_csv`` checks the file hash again at read time, so a file that
changes after ``start()`` still cannot be read as a genuine build output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Settings, load_settings
from .environment import (
    STRICT_ENV_VAR,
    EnvironmentMismatchError,
    compare,
    current_problems,
    enforce,
    read_pins,
)
from .fingerprint import current_fingerprints, stale_parts, verify_installed_package
from .manifest import IntegrityError, load_manifest, verify_output
from .qa.lineage import RUN_ID_PREFIX

__all__ = ["STRICT_ENV_VAR", "EnvironmentMismatchError", "Project", "StaleBuildError", "start"]


ENVIRONMENT_WARNING = "ENVIRONMENT WARNING: differs from environment.yml"


class StaleBuildError(IntegrityError):
    """Raised when data, settings, code or the environment definition differ from the build."""


@dataclass(frozen=True)
class Project:
    settings: Settings
    manifest: dict[str, Any]

    @property
    def run_id(self) -> str:
        return self.manifest["run_id"]

    @property
    def counts(self) -> dict[str, Any]:
        """Headline numbers of every step, merged into one dictionary."""
        return self.manifest["counts"]

    def step_metrics(self, *names: str) -> dict[str, Any]:
        """Headline numbers of the named steps only, for example ``"ingest", "clean"``."""
        known = {step["name"]: step for step in self.manifest["steps"]}
        missing = [name for name in names if name not in known]
        if missing:
            raise KeyError(f"build {self.run_id} has no step named {', '.join(missing)}")
        merged: dict[str, Any] = {}
        for name in names:
            merged.update(known[name]["metrics"])
        return merged

    def output_entry(self, name: str) -> dict[str, Any]:
        """Return the manifest entry for a processed file, or raise if it is not a build output."""
        relative = self.settings.relative(self.settings.path("processed_dir") / name)
        for entry in self.manifest["outputs"]:
            if entry["path"] == relative:
                return entry
        raise FileNotFoundError(f"{name} is not an output of build {self.run_id}")

    def processed(self, name: str) -> Path:
        """Path of a verified processed file."""
        return verify_output(self.output_entry(name), self.settings.root)

    def read_csv(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Read a processed table after confirming its hash matches the build."""
        return pd.read_csv(self.processed(name), **kwargs)

    def read_parquet(self, name: str, **kwargs: Any) -> pd.DataFrame:
        """Read a processed Parquet file after confirming its hash matches the build."""
        from .io import read_parquet

        return read_parquet(self.processed(name), **kwargs)


def verify_build(settings: Settings, manifest: dict[str, Any]) -> None:
    """Raise if any build input or output differs from the recorded build."""
    stale = stale_parts(manifest.get("fingerprints", {}), current_fingerprints(settings))
    if stale:
        raise StaleBuildError(
            f"The build is stale ({', '.join(stale)} changed). Run `python -m job_market rebuild` first."
        )
    for entry in manifest["outputs"]:
        verify_output(entry, settings.root)


def verify_environments(settings: Settings, manifest: dict[str, Any]) -> list[str]:
    """Compare the build environment and the running one with the pins.

    Differences are warnings by default and errors in strict mode.
    """
    pins = read_pins(settings.root)
    build = compare(pins, manifest.get("environment", {}), label="the build") if pins is not None else None
    problems = enforce(build, "The environment that builds these outputs", warn=lambda _m: None)
    problems += enforce(current_problems(settings.root), "The running environment", warn=lambda _m: None)
    return problems


def start(verbose: bool = True) -> Project:
    """Load the current build, verify it and the environment, and print its identity."""
    settings = load_settings()
    verify_installed_package(settings)
    manifest = load_manifest(settings.path("manifest"))
    verify_build(settings, manifest)
    environment_problems = verify_environments(settings, manifest)
    project = Project(settings, manifest)
    if verbose:
        print(f"{RUN_ID_PREFIX} {project.run_id}")
        print(f"Source: {manifest['source']['path']} ({manifest['source']['rows']:,} rows)")
        print(f"Taxonomy version: {manifest['taxonomy_version']}")
        print(f"Verified outputs: {len(manifest['outputs'])} file(s), all hashes match")
        if environment_problems:
            print(f"{ENVIRONMENT_WARNING} - results can differ slightly from the official build:")
            for problem in environment_problems:
                print(f"  {problem}")
        else:
            print("Environment: matches environment.yml")
    return project
