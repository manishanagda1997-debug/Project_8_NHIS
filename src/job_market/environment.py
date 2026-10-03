"""Read the pinned analysis environment and compare environments with it.

``environment.yml`` pins the Python minor version and the exact version of
every package that can change a result. It is a pinned analysis
environment, not a full lock of every transitive dependency; the manifest
records the exact Python patch release and package versions of each build.

Two environments are compared with the pins: the one that builds the
outputs (recorded in the manifest) and the one running right now.

A difference is a WARNING by default, so the project still runs with
compatible package versions. Strict mode (``JOB_MARKET_STRICT=1``, used by
continuous integration and the final verification) turns every difference
into an error.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

ENVIRONMENT_FILE = "environment.yml"
# Strict mode: any difference from the pins stops the run. CI sets it.
STRICT_ENV_VAR = "JOB_MARKET_STRICT"


def strict_mode() -> bool:
    """True when ``JOB_MARKET_STRICT`` is set to 1, true or yes."""
    return os.environ.get(STRICT_ENV_VAR, "").strip().lower() in {"1", "true", "yes"}


class EnvironmentMismatchError(RuntimeError):
    """Raised when an environment differs from environment.yml."""


PIN = re.compile(r"^\s*-\s*([A-Za-z0-9_.\-]+)\s*=\s*([A-Za-z0-9_.\-]+)\s*$")
NOT_PACKAGES = {"pip"}


def read_pins(root: Path) -> dict[str, str] | None:
    """Return {package: version} from environment.yml, or None if the file is absent.

    Only simple ``- name=version`` lines count as pins; the file stays
    readable by conda without any YAML library.
    """
    path = Path(root) / ENVIRONMENT_FILE
    if not path.is_file():
        return None
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PIN.match(line.split("#", 1)[0])
        if match and match.group(1) not in NOT_PACKAGES:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def environment_sha256(root: Path) -> str | None:
    """Hash environment.yml after normalising line endings; None if absent."""
    path = Path(root) / ENVIRONMENT_FILE
    if not path.is_file():
        return None
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def installed_version(package: str) -> str | None:
    if package == "python":
        return platform.python_version()
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def version_matches(package: str, pinned: str, installed: str | None) -> bool:
    """Python matches on the pinned minor version (``python=3.11`` accepts any
    3.11.x patch release); every other package must match its pin exactly, so
    ``2.2.3`` rejects ``2.2.4`` and ``2.2.3.post1``."""
    if installed is None:
        return False
    if package == "python":
        return installed == pinned or installed.startswith(pinned + ".")
    return installed == pinned


def snapshot(root: Path) -> dict[str, Any]:
    """Python, platform and the installed version of every pinned package."""
    pins = read_pins(root) or {}
    packages = {name: installed_version(name) for name in sorted(pins) if name != "python"}
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "executable": Path(sys.executable).name,
        "pins_file": ENVIRONMENT_FILE if pins else None,
        "packages": packages,
    }


def compare(pins: dict[str, str], recorded: dict[str, Any], label: str = "build") -> list[str]:
    """Return one message per recorded version that differs from its pin."""
    problems = []
    for name, pinned in sorted(pins.items()):
        actual = recorded.get("python") if name == "python" else recorded.get("packages", {}).get(name)
        if not version_matches(name, pinned, actual):
            problems.append(f"{name} {actual or 'not installed'} (pinned {pinned})")
    return problems


def current_problems(root: Path) -> list[str] | None:
    """Differences between the running environment and the pins; None if no pins file."""
    pins = read_pins(root)
    if pins is None:
        return None
    return compare(pins, snapshot(root), label="running")


def enforce(problems: list[str] | None, subject: str, warn=print) -> list[str]:
    """Report differences from the pins: a warning by default, an error in strict mode.

    Returns the list of differences (empty when everything matches), so the
    caller can record whether the run matches the pins.
    """
    if problems is None:
        raise EnvironmentMismatchError(f"{ENVIRONMENT_FILE} is missing; the analysis environment is not defined")
    if not problems:
        return problems
    listed = "; ".join(problems)
    if strict_mode():
        raise EnvironmentMismatchError(
            f"{subject} differs from {ENVIRONMENT_FILE} (strict mode):\n  {listed}\n"
            "Activate the pinned environment (conda activate jobmarket), then rebuild or restart the kernel."
        )
    warn(
        f"WARNING: {subject} differs from {ENVIRONMENT_FILE}:\n  {listed}\n"
        "Results can differ slightly from the official build. "
        "Use the pinned environment (conda activate jobmarket) for official results."
    )
    return problems
