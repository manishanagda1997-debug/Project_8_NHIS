"""Load the pipeline configuration and resolve project paths.

Every analytical threshold lives in ``config/pipeline.toml``. This module turns
that file into a read-only ``Settings`` object so the rest of the code never
hard-codes a path or a threshold.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_RELATIVE_PATH = Path("config") / "pipeline.toml"
ROOT_ENV_VAR = "JOB_MARKET_ROOT"


def find_project_root(start: Path | None = None) -> Path:
    """Return the folder that contains ``config/pipeline.toml``.

    The search starts at ``start`` (or the current folder) and walks upwards,
    so notebooks inside ``notebooks/`` and scripts at the root both find the
    same project. The ``JOB_MARKET_ROOT`` environment variable overrides the
    search, which Docker uses.
    """
    override = os.environ.get(ROOT_ENV_VAR)
    if override:
        root = Path(override).resolve()
        if not (root / CONFIG_RELATIVE_PATH).is_file():
            raise FileNotFoundError(f"{ROOT_ENV_VAR} points to {root}, which has no {CONFIG_RELATIVE_PATH}")
        return root
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_RELATIVE_PATH).is_file():
            return candidate
    raise FileNotFoundError(
        f"No {CONFIG_RELATIVE_PATH} in {current} or any parent folder. Run commands from inside the project folder."
    )


@dataclass(frozen=True)
class Settings:
    """Read-only view of ``config/pipeline.toml`` plus resolved paths."""

    root: Path
    raw: dict[str, Any] = field(repr=False)
    config_sha256: str

    def section(self, name: str) -> dict[str, Any]:
        """Return one TOML section, or raise a clear error if it is missing."""
        if name not in self.raw:
            raise KeyError(f"config/pipeline.toml has no [{name}] section")
        return self.raw[name]

    def path(self, key: str) -> Path:
        """Resolve a ``[paths]`` entry to an absolute path inside the project."""
        return (self.root / self.section("paths")[key]).resolve()

    def relative(self, path: Path) -> str:
        """Express an absolute path relative to the project root, with forward slashes."""
        return Path(path).resolve().relative_to(self.root).as_posix()

    @property
    def random_seed(self) -> int:
        return int(self.section("project")["random_seed"])

    @property
    def taxonomy_version(self) -> str:
        return str(self.section("taxonomy")["version"])


GENERATED_DIR_KEYS = ("interim_dir", "processed_dir")
# Configured paths that hold source material or deliverables.
PROTECTED_PATH_KEYS = ("raw_csv", "notebooks_dir", "reports_dir", "labels_dir")
# Standard folders that hold source material. A generated folder may never
# equal, contain, or sit inside any protected path.
PROTECTED_FOLDERS = ("config", "src", "tests", "docs", "app", "reports", ".git")


class LayoutError(ValueError):
    """Raised when configured paths could put source material at risk."""


def _overlaps(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def validate_layout(settings: "Settings") -> None:
    """Refuse any configuration where emptying a generated folder could
    delete raw data, configuration, code, notebooks, reports, tests or docs.

    Rules:

    * every configured path lies strictly inside the project root;
    * the raw CSV sits in a sub-folder, never directly in the root;
    * a generated folder never equals, contains or sits inside a protected
      path - the configured raw CSV and its folder, notebooks and reports
      folders, and the standard source folders;
    * the two generated folders do not overlap, and the manifest lives
      inside the processed folder.

    The check runs whenever settings load, so it runs before the pipeline
    deletes anything.
    """
    root = settings.root
    problems = []
    for key in settings.section("paths"):
        path = settings.path(key)
        if path == root or root not in path.parents:
            problems.append(f"{key} must lie inside the project root, not at {path}")
    if problems:
        raise LayoutError("Unsafe path configuration - " + "; ".join(problems))

    raw_csv = settings.path("raw_csv")
    if raw_csv.parent == root:
        problems.append("raw_csv must sit in a sub-folder such as data/raw, not directly in the project root")
    protected = {key: settings.path(key) for key in PROTECTED_PATH_KEYS}
    protected["folder of raw_csv"] = raw_csv.parent
    protected.update({name: (root / name).resolve() for name in PROTECTED_FOLDERS})
    generated = {key: settings.path(key) for key in GENERATED_DIR_KEYS}

    for key, folder in generated.items():
        for label, item in protected.items():
            if _overlaps(folder, item):
                problems.append(f"{key} = {settings.relative(folder)} overlaps {label} ({settings.relative(item)})")
    if _overlaps(generated["interim_dir"], generated["processed_dir"]):
        problems.append("interim_dir and processed_dir must not overlap")
    if generated["processed_dir"] not in settings.path("manifest").parents:
        problems.append("manifest must live inside processed_dir")
    if problems:
        raise LayoutError("Unsafe path configuration - " + "; ".join(problems))


def load_settings(root: Path | None = None) -> Settings:
    """Read ``config/pipeline.toml`` from the project root."""
    project_root = Path(root).resolve() if root else find_project_root()
    config_path = project_root / CONFIG_RELATIVE_PATH
    text = config_path.read_bytes().decode("utf-8")
    parsed = tomllib.loads(text)
    # Line endings are normalised before hashing, so Windows (CRLF) and
    # Linux (LF) checkouts of the same file produce the same fingerprint.
    normalised = text.replace("\r\n", "\n").encode("utf-8")
    settings = Settings(
        root=project_root,
        raw=parsed,
        config_sha256=hashlib.sha256(normalised).hexdigest(),
    )
    validate_layout(settings)
    return settings
