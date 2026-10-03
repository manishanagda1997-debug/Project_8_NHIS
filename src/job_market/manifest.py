"""Run manifest: a machine-readable record of one pipeline build.

The manifest answers "which exact inputs, code and settings produce these
outputs?". It records the source file hash, the configuration hash, a
fingerprint of the source code, package versions, row counts, and the path,
size and SHA-256 hash of every output file. Notebooks, reports, the dashboard
and the database all cite the manifest ``run_id``, and the lineage check
compares every artifact against it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .io import read_json, write_json

MANIFEST_VERSION = 1
CHUNK_SIZE = 1 << 20


def sha256_file(path: Path) -> str:
    """Hash a file in chunks, so large files never load fully into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_fingerprint(package_dir: Path) -> str:
    """Hash every ``.py`` file of the package in a stable order.

    Line endings are normalised first, so a Windows checkout and a Linux
    checkout of the same code give the same fingerprint. Any code change
    produces a new fingerprint, which marks older outputs as stale.
    """
    digest = hashlib.sha256()
    for path in sorted(Path(package_dir).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(package_dir).as_posix()
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        digest.update(relative.encode("utf-8") + b"\0" + text.encode("utf-8") + b"\0")
    return digest.hexdigest()


def describe_output(path: Path, root: Path, rows: int | None = None) -> dict[str, Any]:
    """Describe one output file for the manifest."""
    path = Path(path)
    entry: dict[str, Any] = {
        "path": path.resolve().relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if rows is not None:
        entry["rows"] = int(rows)
    return entry


class IntegrityError(RuntimeError):
    """Raised when a file differs from the build recorded in the manifest."""


def verify_output(entry: dict[str, Any], root: Path) -> Path:
    """Return the path of one manifest output after checking its hash.

    Raises ``IntegrityError`` when the file is missing or its bytes differ
    from the recorded SHA-256 hash, so an edited or swapped file never counts
    as a genuine build output.
    """
    path = Path(root) / entry["path"]
    if not path.is_file():
        raise IntegrityError(f"{entry['path']} is missing; rebuild with `python -m job_market rebuild`")
    if sha256_file(path) != entry["sha256"]:
        raise IntegrityError(
            f"{entry['path']} differs from the recorded build (hash mismatch); "
            "rebuild with `python -m job_market rebuild`"
        )
    return path


@dataclass
class StepRecord:
    """What one pipeline step produces: output files and headline metrics."""

    name: str
    description: str
    seconds: float = 0.0
    outputs: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "seconds": round(self.seconds, 3),
            "outputs": self.outputs,
            "metrics": self.metrics,
        }


def build_run_id(fingerprints: dict[str, str | None], started: datetime) -> str:
    """Combine a UTC timestamp with a short content fingerprint.

    The timestamp keeps every run distinct. The content part hashes the raw
    data, configuration, code and pinned-environment fingerprints, so it shows
    at a glance whether two runs share all four inputs.
    """
    joined = "|".join(f"{key}={fingerprints[key]}" for key in sorted(fingerprints))
    content = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"{started.strftime('%Y%m%dT%H%M%SZ')}-{content[:10]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def write_manifest(payload: dict[str, Any], path: Path) -> Path:
    return write_json(payload, path)


def load_manifest(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"No run manifest at {path}. Build the project first with: python -m job_market rebuild"
        )
    manifest = read_json(path)
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError(
            f"Manifest version {manifest.get('manifest_version')} does not match "
            f"the expected version {MANIFEST_VERSION}"
        )
    return manifest


__all__ = [
    "IntegrityError",
    "MANIFEST_VERSION",
    "StepRecord",
    "__version__",
    "build_run_id",
    "code_fingerprint",
    "describe_output",
    "load_manifest",
    "sha256_file",
    "utc_now",
    "verify_output",
    "write_manifest",
]
