"""Meteorology ingestion for the admin console.

Two entry points, both ending in the same merge step:

* **上传文件** — ``POST /admin/meteo/upload`` stores the uploaded NetCDF files in
  ``data/meteo_inbox/`` (a browser can do this; it cannot hand over a folder).
* **扫描服务器文件夹** — ``POST /admin/meteo/scan`` walks a server-side directory
  for ``*.nc``. This is what the H5 page cannot do by itself, so the admin
  browses the server filesystem through the API instead.

After either one, ``ingest`` rebuilds the daily cube for every *complete* year
(all 8 variables present) and merges it into ``artifacts/era5_daily.npz``,
overwriting dates that already exist and appending new ones.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..config import settings
from . import era5, era5_build

log = logging.getLogger(__name__)

_ingest_lock = threading.Lock()
_last_report: dict[str, Any] | None = None

REQUIRED = tuple(era5_build.VARIABLE_PATTERNS)
INBOX_EXTENSIONS = {".nc", ".nc4", ".netcdf"}


@dataclass(slots=True)
class IngestResult:
    years_ingested: list[int]
    skipped: list[str]
    warnings: list[str]
    dates_added: int
    dates_replaced: int
    total_dates: int
    coverage: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "years_ingested": self.years_ingested,
            "skipped": self.skipped,
            "warnings": self.warnings,
            "dates_added": self.dates_added,
            "dates_replaced": self.dates_replaced,
            "total_dates": self.total_dates,
            "coverage": self.coverage,
        }


# --- filesystem helpers ---------------------------------------------------


def list_directory(path: str | None) -> dict[str, Any]:
    """Read-only directory listing so the admin can pick a data folder."""
    target = Path(path).expanduser() if path else Path.home()
    if not target.is_absolute():
        target = (Path.home() / target).resolve()
    if not target.is_dir():
        return {"path": str(target), "exists": False, "entries": [], "parents": []}

    entries = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if is_dir:
            entries.append({"name": child.name, "path": str(child), "type": "dir", "size": None})
        elif child.suffix.lower() in INBOX_EXTENSIONS:
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "type": "nc",
                    "size": child.stat().st_size,
                }
            )
        if len(entries) >= 400:
            break

    parents = []
    cursor = target
    for _ in range(6):
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
        parents.append({"name": cursor.name or str(cursor), "path": str(cursor)})

    nc_count = sum(1 for entry in entries if entry["type"] == "nc")
    return {
        "path": str(target),
        "exists": True,
        "entries": entries,
        "parents": list(reversed(parents)),
        "inbox": str(settings.meteo_inbox),
        "nc_count": nc_count,
    }


def collect(path: str, recursive: bool = True) -> list[Path]:
    root = Path(path).expanduser()
    if root.is_file():
        candidates = [root]
    elif root.is_dir():
        pattern = "**/*" if recursive else "*"
        candidates = [p for p in root.glob(pattern) if p.is_file()]
    else:
        raise FileNotFoundError(f"路径不存在：{path}")
    return sorted(p for p in candidates if p.suffix.lower() in INBOX_EXTENSIONS)


def save_uploads(files: list[tuple[str, bytes]]) -> list[Path]:
    """Persist uploaded files into the inbox and return their paths."""
    settings.meteo_inbox.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for name, payload in files:
        safe = Path(name).name
        destination = settings.meteo_inbox / safe
        destination.write_bytes(payload)
        saved.append(destination)
    return saved


# --- merge ----------------------------------------------------------------


def _load_existing(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = np.load(path, allow_pickle=False)
    return {key: payload[key] for key in payload.files}


def _merge(existing: dict[str, Any] | None, cubes: list[era5_build.YearCube],
           lat: np.ndarray, lon: np.ndarray) -> tuple[list[str], dict[str, np.ndarray], int, int]:
    new_dates: list[str] = []
    for cube in cubes:
        new_dates.extend(cube.dates)

    old_dates = [str(d) for d in existing["dates"].tolist()] if existing is not None else []
    all_dates = sorted(set(old_dates) | set(new_dates))
    index = {date: i for i, date in enumerate(all_dates)}

    rows, cols = (lat.size, lon.size)
    replaced = len(set(old_dates) & set(new_dates))
    added = len(set(new_dates) - set(old_dates))

    arrays = {
        key: np.full((len(all_dates), rows, cols), np.nan, dtype=np.float32)
        for key in era5_build.DERIVED
    }
    if existing is not None:
        for key in era5_build.DERIVED:
            if key not in existing:
                continue
            block = existing[key]
            for i, date in enumerate(old_dates):
                arrays[key][index[date]] = block[i]

    for cube in cubes:
        for i, date in enumerate(cube.dates):
            target = index[date]
            for key in era5_build.DERIVED:
                arrays[key][target] = cube.arrays[key][i]

    return all_dates, arrays, added, replaced


def ingest(paths: list[Path], pe_ratio: float = 0.8, pe_cap: float = 35.0) -> IngestResult:
    """Rebuild complete years from ``paths`` and merge into the ERA5 cube."""
    global _last_report
    buckets, warnings = era5_build.group_files(paths)
    usable: list[era5_build.YearCube] = []
    skipped: list[str] = []

    for year, files in sorted(buckets.items()):
        missing = [key for key in REQUIRED if key not in files]
        if missing:
            skipped.append(f"{year}：缺少 {', '.join(missing)}")
            continue
        log.info("ingesting ERA5 year %s from %s files", year, len(files))
        usable.append(era5_build.build_year(files, year, pe_ratio, pe_cap))

    if not usable:
        report = IngestResult([], skipped, warnings, 0, 0, 0, "no-op")
        _last_report = report.to_dict()
        return report

    with _ingest_lock:
        sample = next(iter(buckets[sorted(buckets)[0]].values()))
        lat, lon = era5_build.read_coordinates(sample)
        existing = _load_existing(Path(settings.era5_path))
        dates, arrays, added, replaced = _merge(existing, usable, lat, lon)

        payload = {
            "dates": np.array(dates, dtype="U10"),
            "lat": lat,
            "lon": lon,
            **arrays,
        }
        target = Path(settings.era5_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp.npz")
        np.savez_compressed(temp, **payload)
        os.replace(temp, target)

    era5.reset()
    status = era5.status()
    domain = status.get("domain") or {}
    coverage = f"{domain.get('start', '?')} .. {domain.get('end', '?')}"
    report = IngestResult(
        years_ingested=[cube.year for cube in usable],
        skipped=skipped,
        warnings=warnings,
        dates_added=added,
        dates_replaced=replaced,
        total_dates=len(dates),
        coverage=coverage,
    )
    _last_report = report.to_dict()
    log.info("ERA5 ingest done: %s", _last_report)
    return report


def last_report() -> dict[str, Any] | None:
    return _last_report


def target_path() -> str:
    return str(settings.era5_path)


def copy_into_inbox(paths: list[Path]) -> list[Path]:
    """Copy external files into the inbox so the cube rebuild has one source."""
    settings.meteo_inbox.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for path in paths:
        destination = settings.meteo_inbox / path.name
        if path.resolve() != destination.resolve():
            shutil.copy2(path, destination)
        copied.append(destination)
    return copied


def inbox_inventory() -> dict[str, Any]:
    settings.meteo_inbox.mkdir(parents=True, exist_ok=True)
    files = sorted(settings.meteo_inbox.glob("*.nc"))
    buckets, warnings = era5_build.group_files(files)
    return {
        "inbox": str(settings.meteo_inbox),
        "files": len(files),
        "years": {
            str(year): sorted(buckets[year].keys()) for year in sorted(buckets)
        },
        "warnings": warnings[:20],
        "report": _last_report,
        "cube": era5.status(),
        "target": target_path(),
    }


def manifest() -> str:
    """Human-readable snapshot of what the cube currently holds."""
    status = era5.status()
    return json.dumps(status, ensure_ascii=False, indent=2)
