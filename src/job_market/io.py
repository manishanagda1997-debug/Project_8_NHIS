"""Deterministic file writers.

Every output passes through these helpers, so the same inputs always produce
byte-identical files on Windows, macOS and Linux. Identical bytes give
identical SHA-256 hashes, which is what the run manifest relies on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    """Write a CSV with LF line endings, UTF-8 encoding and no index column."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return path


def write_parquet(frame: pd.DataFrame, path: Path) -> Path:
    """Write a Parquet file with pyarrow, without the pandas index.

    Parquet keeps column types (timestamps stay timestamps, flags stay
    booleans) and loads far faster than CSV. With the same pinned pyarrow
    version, the same data gives byte-identical files.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, engine="pyarrow", index=False, compression="snappy")
    return path


def read_parquet(path: Path, **kwargs: Any) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow", **kwargs)


def write_json(payload: Any, path: Path) -> Path:
    """Write pretty, key-sorted JSON with LF line endings and a final newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=_json_default)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text + "\n")
    return path


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _json_default(value: Any) -> Any:
    """Convert numpy and pandas scalars into plain JSON types."""
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serialisable")
