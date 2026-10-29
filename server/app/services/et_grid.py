"""ETMonitor daily-ET grid lookups.

The bundled asset (``artifacts/et_grid.npz``) holds 2000–2004 daily
evapotranspiration on the ERA5 0.25° grid cropped to the North China Plain
(33 rows × 29 columns). Field demand is computed with area-weighted overlap
between the parcel and the grid cells, not a single-point lookup — a 20 ha plot
can straddle four cells.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import settings
from . import geo, gridmath

log = logging.getLogger(__name__)

_lock = threading.Lock()
_data: "ETDataset | None" = None
_load_error: str | None = None


@dataclass(slots=True)
class ETDataset:
    et: np.ndarray           # (days, rows, cols) float32, mm/day, NaN = missing
    dates: list[dt.date]     # length = days
    lon: np.ndarray          # (cols,) ascending
    lat: np.ndarray          # (rows,) descending (row 0 = north)
    source: str

    @property
    def west(self) -> float:
        return float(self.lon[0])

    @property
    def east(self) -> float:
        return float(self.lon[-1])

    @property
    def south(self) -> float:
        return float(self.lat[-1])

    @property
    def north(self) -> float:
        return float(self.lat[0])

    @property
    def cell_size(self) -> float:
        return float(self.lon[1] - self.lon[0]) if len(self.lon) > 1 else 0.25

    def index_of_date(self, day: dt.date) -> int | None:
        try:
            return self.dates.index(day)
        except ValueError:
            return None

    def domain(self) -> dict:
        return {
            "west": self.west,
            "east": self.east,
            "south": self.south,
            "north": self.north,
            "resolution_deg": self.cell_size,
            "rows": int(self.et.shape[1]),
            "columns": int(self.et.shape[2]),
            "days": len(self.dates),
            "start": self.dates[0].isoformat(),
            "end": self.dates[-1].isoformat(),
            "source": self.source,
        }

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def doy_mean(self, doy: int) -> tuple[float, float, float]:
        """Multi-year mean/min/max ET for a day-of-year, averaged across domain."""
        idx = [i for i, d in enumerate(self.dates) if d.timetuple().tm_yday == doy]
        if not idx:
            return 0.0, 0.0, 0.0
        slab = self.et[idx]
        with np.errstate(invalid="ignore"):
            per_day = np.nanmean(slab.reshape(len(idx), -1), axis=1)
        finite = per_day[np.isfinite(per_day)]
        if finite.size == 0:
            return 0.0, 0.0, 0.0
        return float(np.mean(finite)), float(np.min(finite)), float(np.max(finite))


def _load(path: Path) -> ETDataset:
    payload = np.load(path, allow_pickle=False)
    dates = [dt.date.fromisoformat(str(s)) for s in payload["dates"].tolist()]
    dataset = ETDataset(
        et=payload["et"].astype(np.float32),
        dates=dates,
        lon=payload["lon"].astype(np.float64),
        lat=payload["lat"].astype(np.float64),
        source=str(payload["source"]) if "source" in payload else "ETMonitor",
    )
    log.info("loaded ET grid %s: %s days, %sx%s", path.name, len(dates),
             dataset.et.shape[1], dataset.et.shape[2])
    return dataset


def load_dataset() -> ETDataset | None:
    global _data, _load_error
    if _data is not None or _load_error is not None:
        return _data
    with _lock:
        if _data is not None or _load_error is not None:
            return _data
        path = Path(settings.et_grid_path)
        if not path.is_file():
            _load_error = f"ET grid asset missing: {path}"
            log.warning(_load_error)
            return None
        try:
            _data = _load(path)
        except Exception as exc:  # noqa: BLE001
            _load_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("failed to load ET grid: %s", _load_error)
    return _data


def status() -> dict:
    dataset = load_dataset()
    if dataset is None:
        return {"available": False, "error": _load_error, "path": str(settings.et_grid_path)}
    return {"available": True, "error": None, "domain": dataset.domain()}


# --- polygon / grid overlap ----------------------------------------------


def _plain_overlap(ring: geo.Ring, dataset: ETDataset) -> list[tuple[int, int, float]]:
    return gridmath.overlap_weights(ring, dataset.lon, dataset.lat)


def _fallback_et(lon: float, lat: float, doy: int) -> float:
    """Smooth empirical ET field used outside the grid domain."""
    seasonal = 0.5 - 0.5 * math.cos(2 * math.pi * (doy - 20) / 365.0)
    latitude_factor = math.exp(-((lat - 34.0) ** 2) / 90.0)
    return round(0.4 + 4.2 * seasonal * latitude_factor, 3)


def et_for_ring(ring: geo.Ring, day: dt.date) -> dict:
    """Return area-weighted ET (mm/day) for a parcel on a given date."""
    dataset = load_dataset()
    lon, lat = geo.ring_centroid(ring)
    doy = day.timetuple().tm_yday

    if dataset is None:
        value = _fallback_et(lon, lat, doy)
        return {"et_mm_day": value, "source": "synthetic", "extrapolated": True,
                "note": "ET 网格未就绪，使用经验模型"}

    weights = _plain_overlap(ring, dataset)
    idx = dataset.index_of_date(day)
    if idx is not None:
        slab = dataset.et[idx]
        if weights:
            values, wsum = 0.0, 0.0
            for row, col, weight in weights:
                value = float(slab[row, col])
                if math.isfinite(value):
                    values += value * weight
                    wsum += weight
            if wsum > 0.2:
                return {
                    "et_mm_day": round(values / wsum, 3),
                    "source": "etmonitor-grid",
                    "extrapolated": False,
                    "cells": len(weights),
                    "date": day.isoformat(),
                }
        value = float(np.nanmean(slab)) if np.isfinite(np.nanmean(slab)) else _fallback_et(lon, lat, doy)
        return {"et_mm_day": round(value, 3), "source": "etmonitor-domain-mean",
                "extrapolated": False, "date": day.isoformat()}

    # Date outside 2000–2004: use the multi-year climatology for that day-of-year.
    if not dataset.contains(lon, lat):
        value = _fallback_et(lon, lat, doy)
        return {"et_mm_day": value, "source": "synthetic", "extrapolated": True,
                "note": "坐标位于 ET 数据域外（华北大平原以外），使用经验模型"}

    idx = [i for i, d in enumerate(dataset.dates) if d.timetuple().tm_yday == doy]
    if not idx:
        value = _fallback_et(lon, lat, doy)
        return {"et_mm_day": value, "source": "synthetic", "extrapolated": True}

    if weights:
        values, wsum = 0.0, 0.0
        for row, col, weight in weights:
            series = dataset.et[idx, row, col]
            mean = float(np.nanmean(series)) if np.isfinite(series).any() else float("nan")
            if math.isfinite(mean):
                values += mean * weight
                wsum += weight
        if wsum > 0.2:
            return {"et_mm_day": round(values / wsum, 3), "source": "etmonitor-climatology",
                    "extrapolated": False, "cells": len(weights), "doy": doy}

    mean, _, _ = dataset.doy_mean(doy)
    return {"et_mm_day": round(mean, 3), "source": "etmonitor-climatology-domain",
            "extrapolated": False, "doy": doy}


def et_series(ring: geo.Ring, start: dt.date, days: int) -> list[dict]:
    """Daily ET for a parcel plus the 5-year min/max envelope."""
    dataset = load_dataset()
    out: list[dict] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        row = et_for_ring(ring, day)
        row["date"] = day.isoformat()
        row["dow"] = day.weekday()
        envelope = _envelope(dataset, ring, day)
        row.update(envelope)
        out.append(row)
    return out


def _envelope(dataset: ETDataset | None, ring: geo.Ring, day: dt.date) -> dict:
    if dataset is None or not dataset.contains(*geo.ring_centroid(ring)):
        return {"et_min": None, "et_max": None}
    doy = day.timetuple().tm_yday
    idx = [i for i, d in enumerate(dataset.dates) if d.timetuple().tm_yday == doy]
    if not idx:
        return {"et_min": None, "et_max": None}
    weights = _plain_overlap(ring, dataset)
    if not weights:
        return {"et_min": None, "et_max": None}
    yearly_totals: list[float] = []
    for i in idx:
        acc, wsum = 0.0, 0.0
        for row, col, weight in weights:
            value = float(dataset.et[i, row, col])
            if math.isfinite(value):
                acc += value * weight
                wsum += weight
        if wsum > 0.2:
            yearly_totals.append(acc / wsum)
    if not yearly_totals:
        return {"et_min": None, "et_max": None}
    return {
        "et_min": round(min(yearly_totals), 3),
        "et_max": round(max(yearly_totals), 3),
        "years": len(yearly_totals),
    }
