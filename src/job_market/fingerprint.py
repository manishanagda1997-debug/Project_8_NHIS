"""The four fingerprints that identify a build.

A build is defined by its raw data, its configuration, its source code and
its pinned analysis environment. The pipeline records these four hashes in
the manifest; the lineage check and every notebook recompute them with this
same function and compare. A change in any of the four marks the build stale.
"""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .database import sql_sha256
from .environment import ENVIRONMENT_FILE, environment_sha256
from .manifest import code_fingerprint, sha256_file

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
}


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
    }


def stale_parts(recorded: dict[str, str | None], current: dict[str, str | None]) -> list[str]:
    """Human-readable names of the fingerprints that differ."""
    return [LABELS[key] for key in LABELS if recorded.get(key) != current.get(key)]
