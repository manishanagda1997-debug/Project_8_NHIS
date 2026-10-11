"""The six fingerprints that identify a build.

A build is defined by its raw data, its configuration, its source code, its
pinned analysis environment, its SQL files and the human label files the
pipeline reads. The pipeline records these six hashes in the manifest; the
lineage check and every notebook recompute them with this same function and
compare. A change in any of the six marks the build stale.

The label fingerprint covers only the files the pipeline reads (decision
D-039). The arrangement sheets (scored once outside the pipeline, D-041) and
the recommender approval (which may be recorded after a build, D-040) are
not part of it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .config import Settings
from .database import sql_sha256
from .environment import ENVIRONMENT_FILE, environment_sha256
from .manifest import code_fingerprint, sha256_file
from .provenance import HISTORICAL_RANKINGS_FILE, LABEL_SOURCES_FILE

# The package Python actually imports. It can differ from the project's own
# src/job_market when an editable install points at another copy.
IMPORTED_PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_PACKAGE = Path("src") / "job_market"

LABELS = {
    "source_sha256": "raw data",
    "config_sha256": "configuration",
    "code_sha256": "source code",
    "environment_sha256": f"pinned environment ({ENVIRONMENT_FILE})",
    "sql_sha256": "SQL schema and queries (sql/)",
    "labels_sha256": "label files (data/labels)",
}

# The label inputs the pipeline reads: the category and relevance sheets, their
# source bindings and the historical ranking record. The rankings file that
# record names is added in labels_sha256().
LABEL_INPUT_FILES = ("dev_labels.xlsx", "blind_labels.xlsx", "relevance_labels.xlsx", LABEL_SOURCES_FILE,
                     HISTORICAL_RANKINGS_FILE)
MISSING = "missing"


class MissingSourceError(FileNotFoundError):
    """Raised when the raw CSV named in the configuration does not exist."""


class InstalledPackageMismatchError(RuntimeError):
    """Raised when the imported job_market package is not this project's src/job_market."""


def project_code_sha256(settings: Settings) -> str:
    """Fingerprint of this project's own src/job_market, wherever Python imports from."""
    source = settings.root / SOURCE_PACKAGE
    if not source.is_dir():
        raise FileNotFoundError(f"{SOURCE_PACKAGE.as_posix()} is missing from the project")
    return code_fingerprint(source)


def verify_installed_package(settings: Settings) -> None:
    """The running code must be this project's code.

    A build, a notebook or a check that imports job_market from another copy
    (for example after the project folder moves without reinstalling) would
    run code that the fingerprint does not describe.
    """
    if project_code_sha256(settings) != code_fingerprint(IMPORTED_PACKAGE_DIR):
        raise InstalledPackageMismatchError(
            f"The installed job_market package ({IMPORTED_PACKAGE_DIR}) does not match this project's "
            f"{SOURCE_PACKAGE.as_posix()}. Run: pip install -e . --no-deps"
        )


def labels_sha256(settings: Settings) -> str:
    """One hash over the label inputs: each file's path and content hash, or "missing"."""
    from .config import tomllib

    folder = settings.path("labels_dir")
    names = list(LABEL_INPUT_FILES)
    record = folder / HISTORICAL_RANKINGS_FILE
    if record.is_file():
        try:
            names.append(str(tomllib.loads(record.read_bytes().decode("utf-8"))["file"]))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, KeyError):
            names.append("(historical rankings file not readable from its record)")
    lines = []
    for name in names:
        path = folder / name
        lines.append(f"{settings.relative(path)}\t{sha256_file(path) if path.is_file() else MISSING}\n")
    return hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()


def current_fingerprints(settings: Settings) -> dict[str, str | None]:
    raw = settings.path("raw_csv")
    if not raw.is_file():
        raise MissingSourceError(f"raw file {settings.relative(raw)} is missing")
    return {
        "source_sha256": sha256_file(raw),
        "config_sha256": settings.config_sha256,
        "code_sha256": project_code_sha256(settings),
        "environment_sha256": environment_sha256(settings.root),
        "sql_sha256": sql_sha256(settings.root),
        "labels_sha256": labels_sha256(settings),
    }


def stale_parts(recorded: dict[str, str | None], current: dict[str, str | None]) -> list[str]:
    """Human-readable names of the fingerprints that differ."""
    return [LABELS[key] for key in LABELS if recorded.get(key) != current.get(key)]
