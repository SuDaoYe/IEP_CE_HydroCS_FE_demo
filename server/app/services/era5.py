"""ERA5 daily meteorology and FAO-56 reference evapotranspiration.

The asset (``artifacts/era5_daily.npz``) is the same 33x29 / 0.25° grid as the
ETMonitor cube, so parcels are resolved the same way. What it adds is the two
things needed for a textbook irrigation balance:

* ``et0`` — Penman–Monteith reference ET, so crop demand is ``Kc x ET0``
  instead of being back-solved from an observed ET field;
* ``pe`` — effective rainfall, so the demand net of rain is
  ``max(0, Kc x ET0 + percolation - Pe)``.
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
_data: "ERA5Dataset | None" = None
_load_error: str | None = None

FIELDS = ("et0", "pe", "precip", "t2m", "vpd", "wind", "rn", "pres")


# --- FAO-56 physics -------------------------------------------------------


def saturation_vapour_pressure(temp_c: np.ndarray) -> np.ndarray:
    """es(T) in kPa (FAO-56 eq. 11)."""
    return 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))


def penman_monteith(
    temp_c: np.ndarray,
    vpd_kpa: np.ndarray,
    wind10_ms: np.ndarray,
    rn_mj: np.ndarray,
    pres_kpa: np.ndarray,
) -> np.ndarray:
    """FAO-56 daily reference evapotranspiration (mm/day), soil heat flux G = 0."""
    u2 = wind10_ms * 4.87 / np.log(67.8 * 10 - 5.42)
    es = saturation_vapour_pressure(temp_c)
    delta = 4098 * es / (temp_c + 237.3) ** 2
    gamma = 0.000665 * pres_kpa
    numerator = 0.408 * delta * rn_mj + gamma * (900 / (temp_c + 273)) * u2 * vpd_kpa
    denominator = delta + gamma * (1 + 0.34 * u2)
    with np.errstate(invalid="ignore", divide="ignore"):
        et0 = numerator / denominator
    return np.where(np.isfinite(et0), np.maximum(et0, 0.0), np.nan)


def effective_rainfall(precip_mm: np.ndarray, ratio: float = 0.8, cap_mm: float = 35.0) -> np.ndarray:
    """Daily effective rainfall: a fixed utilisation ratio, capped per day."""
    with np.errstate(invalid="ignore"):
        return np.minimum(np.maximum(precip_mm, 0.0) * ratio, cap_mm)


@dataclass(slots=True)
class ERA5Dataset:
    et0: np.ndarray
    pe: np.ndarray
    precip: np.ndarray
    t2m: np.ndarray
    vpd: np.ndarray
    wind: np.ndarray
    rn: np.ndarray
    pres: np.ndarray
    dates: list[dt.date]
    lon: np.ndarray
    lat: np.ndarray
    source: str = "ERA5"

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

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def index_of_date(self, day: dt.date) -> int | None:
        try:
            return self.dates.index(day)
        except ValueError:
            return None

    def doy_indices(self, doy: int) -> list[int]:
        return [i for i, d in enumerate(self.dates) if d.timetuple().tm_yday == doy]

    def domain(self) -> dict:
        return {
            "west": self.west,
            "east": self.east,
            "south": self.south,
            "north": self.north,
            "resolution_deg": self.cell_size,
            "rows": int(self.et0.shape[1]),
            "columns": int(self.et0.shape[2]),
            "days": len(self.dates),
            "start": self.dates[0].isoformat(),
            "end": self.dates[-1].isoformat(),
            "source": self.source,
        }


def load() -> ERA5Dataset | None:
    global _data, _load_error
    if _data is not None or _load_error is not None:
        return _data
    with _lock:
        if _data is not None or _load_error is not None:
            return _data
        path = Path(settings.era5_path)
        if not path.is_file():
            _load_error = f"ERA5 asset missing: {path}"
            log.warning("%s — falling back to the ETMonitor-based balance", _load_error)
            return None
        try:
            payload = np.load(path, allow_pickle=False)
            _data = ERA5Dataset(
                et0=payload["et0"].astype(np.float32),
                pe=payload["pe"].astype(np.float32),
                precip=payload["precip"].astype(np.float32),
                t2m=payload["t2m"].astype(np.float32),
                vpd=payload["vpd"].astype(np.float32),
                wind=payload["wind"].astype(np.float32),
                rn=payload["rn"].astype(np.float32),
                pres=payload["pres"].astype(np.float32),
                dates=[dt.date.fromisoformat(str(s)) for s in payload["dates"].tolist()],
                lon=payload["lon"].astype(np.float64),
                lat=payload["lat"].astype(np.float64),
            )
            log.info(
                "loaded ERA5 daily cube %s: %s days %s..%s",
                path.name, len(_data.dates), _data.dates[0], _data.dates[-1],
            )
        except Exception as exc:  # noqa: BLE001
            _load_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("failed to load ERA5 cube: %s", _load_error)
    return _data


def status() -> dict:
    dataset = load()
    if dataset is None:
        return {"available": False, "error": _load_error, "path": str(settings.era5_path)}
    return {"available": True, "error": None, "domain": dataset.domain()}


def reset() -> None:
    """Drop the cached cube so the next lookup reloads a freshly ingested file."""
    global _data, _load_error
    with _lock:
        _data = None
        _load_error = None
    log.info("ERA5 cube cache cleared")


def _fallback_day(lon: float, lat: float, doy: int) -> dict:
    """Smooth empirical climate used only outside the ERA5 domain."""
    seasonal = 0.5 - 0.5 * math.cos(2 * math.pi * (doy - 20) / 365.0)
    latitude_factor = math.exp(-((lat - 34.0) ** 2) / 90.0)
    et0 = 0.6 + 5.2 * seasonal * latitude_factor
    precip = 1.4 + 2.6 * seasonal * latitude_factor
    return {
        "et0_mm": round(et0, 3),
        "precip_mm": round(precip, 3),
        "pe_mm": round(min(precip * 0.8, 35.0), 3),
        "t2m_c": round(-2 + 26 * seasonal, 2),
        "vpd_kpa": None,
        "source": "synthetic",
        "extrapolated": True,
    }


def day_values(ring: geo.Ring, day: dt.date) -> dict:
    """Area-weighted ET0 / rainfall for a parcel on a given date."""
    dataset = load()
    lon, lat = geo.ring_centroid(ring)
    doy = day.timetuple().tm_yday

    if dataset is None:
        return {**_fallback_day(lon, lat, doy), "date": day.isoformat()}

    if not dataset.contains(lon, lat):
        return {**_fallback_day(lon, lat, doy), "date": day.isoformat()}

    weights = gridmath.overlap_weights(ring, dataset.lon, dataset.lat)
    if not weights:
        return {**_fallback_day(lon, lat, doy), "date": day.isoformat()}

    index = dataset.index_of_date(day)
    if index is not None:
        values = {
            field: gridmath.weighted_value(getattr(dataset, field)[index], weights)
            for field in FIELDS
        }
        if values["et0"] is not None:
            return {
                "date": day.isoformat(),
                "et0_mm": round(values["et0"], 3),
                "precip_mm": round(values["precip"] or 0.0, 3),
                "pe_mm": round(values["pe"] or 0.0, 3),
                "t2m_c": round(values["t2m"], 2) if values["t2m"] is not None else None,
                "vpd_kpa": round(values["vpd"], 3) if values["vpd"] is not None else None,
                "wind_ms": round(values["wind"], 3) if values["wind"] is not None else None,
                "rn_mj": round(values["rn"], 2) if values["rn"] is not None else None,
                "source": "era5-pm",
                "extrapolated": False,
                "cells": len(weights),
            }

    # Date outside 2000-2004: use the 5-year climatology for the same day-of-year.
    indices = dataset.doy_indices(doy)
    if not indices:
        return {**_fallback_day(lon, lat, doy), "date": day.isoformat()}

    def climatology(field: str) -> float | None:
        samples = []
        for index in indices:
            value = gridmath.weighted_value(getattr(dataset, field)[index], weights)
            if value is not None:
                samples.append(value)
        return float(np.mean(samples)) if samples else None

    et0 = climatology("et0")
    if et0 is None:
        return {**_fallback_day(lon, lat, doy), "date": day.isoformat()}
    precip = climatology("precip") or 0.0
    return {
        "date": day.isoformat(),
        "et0_mm": round(et0, 3),
        "precip_mm": round(precip, 3),
        "pe_mm": round(climatology("pe") or 0.0, 3),
        "t2m_c": round(climatology("t2m") or 0.0, 2),
        "vpd_kpa": None,
        "source": "era5-climatology",
        "extrapolated": False,
        "years": len(indices),
    }


def series(ring: geo.Ring, start: dt.date, days: int) -> list[dict]:
    out: list[dict] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        row = day_values(ring, day)
        row["dow"] = day.weekday()
        out.append(row)
    return out


def envelope(ring: geo.Ring, day: dt.date) -> dict:
    """Min/max ET0 and rainfall across the 5 observed years for that day-of-year."""
    dataset = load()
    if dataset is None or not dataset.contains(*geo.ring_centroid(ring)):
        return {}
    indices = dataset.doy_indices(day.timetuple().tm_yday)
    weights = gridmath.overlap_weights(ring, dataset.lon, dataset.lat)
    if not indices or not weights:
        return {}
    et0_samples, precip_samples = [], []
    for index in indices:
        et0 = gridmath.weighted_value(dataset.et0[index], weights)
        precip = gridmath.weighted_value(dataset.precip[index], weights)
        if et0 is not None:
            et0_samples.append(et0)
        if precip is not None:
            precip_samples.append(precip)
    if not et0_samples:
        return {}
    return {
        "et0_min": round(min(et0_samples), 3),
        "et0_max": round(max(et0_samples), 3),
        "precip_max": round(max(precip_samples), 3) if precip_samples else None,
        "years": len(et0_samples),
    }
