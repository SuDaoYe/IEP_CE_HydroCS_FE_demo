"""Shared ERA5 → daily-cube builder.

Used by ``scripts/build_era5_daily.py`` (one-shot build from the archive) and by
``app/services/meteo.py`` (admin-triggered ingest of freshly downloaded files),
so both paths produce byte-identical logic.

netCDF4 on Windows cannot open non-ASCII absolute paths, so files are read into
memory and opened from a buffer instead of by path.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .era5 import effective_rainfall, penman_monteith, saturation_vapour_pressure

log = logging.getLogger(__name__)

VARIABLE_PATTERNS = {
    "t2m": "*2m_temperature_Y{y}*.nc",
    "d2m": "*dewpoin*Y{y}*.nc",
    "u10": "*10u_Y{y}*.nc",
    "v10": "*10v_Y{y}*.nc",
    "sp": "*surface_pressure_Y{y}*.nc",
    "tp": "*total_precipitation_Y{y}*.nc",
    "ssr": "*ssr_Y{y}*.nc",
    "str": "*str_Y{y}*.nc",
}
# Substrings that identify each variable in an ERA5 file name. Order matters:
# "2m_dewpoin_temperature" also contains "2m_temperature", so d2m is tested first.
VARIABLE_ALIASES = {
    "d2m": "dewpoin",
    "t2m": "2m_temperature",
    "u10": "10u",
    "v10": "10v",
    "sp": "surface_pressure",
    "tp": "total_precipitation",
    "ssr": "ssr",
    "str": "str",
}
DERIVED = ("t2m", "vpd", "wind", "rn", "pres", "precip", "et0", "pe")


@dataclass(slots=True)
class YearCube:
    year: int
    dates: list[str]
    arrays: dict[str, np.ndarray]
    warnings: list[str] = field(default_factory=list)


def open_dataset_bytes(path: Path):
    import netCDF4

    return netCDF4.Dataset("inmemory.nc", mode="r", memory=path.read_bytes())


def detect_variable(path: Path) -> tuple[str, int] | None:
    """Guess (variable key, year) from an ERA5 file name."""
    name = path.name.lower()
    year = None
    marker = "_y"
    index = name.find(marker)
    if index >= 0:
        candidate = name[index + 2:index + 6]
        if candidate.isdigit():
            year = int(candidate)
    if year is None:
        import re

        match = re.search(r"(19|20)\d{2}", name)
        if match:
            year = int(match.group(0))
    if year is None:
        return None
    for key, alias in VARIABLE_ALIASES.items():
        if alias in name:
            return key, year
    return None


def _timestamps(dataset) -> np.ndarray:
    variable = dataset.variables["valid_time"] if "valid_time" in dataset.variables else dataset.variables["time"]
    units = variable.getncattr("units")
    if not units.startswith("seconds since"):
        raise ValueError(f"unsupported time units: {units}")
    return np.asarray(variable[:], dtype=np.int64)


def _daily_mean(values: np.ndarray, stamps: np.ndarray, days: list[dt.date]) -> np.ndarray:
    index = {day: i for i, day in enumerate(days)}
    out = np.full((len(days),) + values.shape[1:], np.nan, dtype=np.float32)
    counts = np.zeros(len(days), dtype=np.int32)
    day_numbers = (stamps // 86400).astype(np.int64)
    uniques, inverse = np.unique(day_numbers, return_inverse=True)
    for position, day_number in enumerate(uniques):
        day = dt.date(1970, 1, 1) + dt.timedelta(days=int(day_number))
        target = index.get(day)
        if target is None:
            continue
        block = values[inverse == position]
        counts[target] = block.shape[0]
        with np.errstate(invalid="ignore"):
            out[target] = np.nanmean(block, axis=0)
    out[counts < 24] = np.nan
    return out


def _daily_sum(values: np.ndarray, stamps: np.ndarray, days: list[dt.date]) -> np.ndarray:
    index = {day: i for i, day in enumerate(days)}
    out = np.full((len(days),) + values.shape[1:], np.nan, dtype=np.float32)
    counts = np.zeros(len(days), dtype=np.int32)
    day_numbers = (stamps // 86400).astype(np.int64)
    uniques, inverse = np.unique(day_numbers, return_inverse=True)
    for position, day_number in enumerate(uniques):
        day = dt.date(1970, 1, 1) + dt.timedelta(days=int(day_number))
        target = index.get(day)
        if target is None:
            continue
        block = values[inverse == position]
        counts[target] = block.shape[0]
        with np.errstate(invalid="ignore"):
            out[target] = np.nansum(block, axis=0)
    out[counts < 24] = np.nan
    return out


def read_variable(path: Path, key: str) -> tuple[np.ndarray, np.ndarray]:
    with open_dataset_bytes(path) as dataset:
        if key not in dataset.variables:
            raise KeyError(f"{path.name}: variable {key!r} not found")
        values = dataset.variables[key][:].astype(np.float64)
        stamps = _timestamps(dataset)
    return values, stamps


def build_year(files: dict[str, Path], year: int, pe_ratio: float = 0.8, pe_cap: float = 35.0) -> YearCube:
    """Turn one year of hourly ERA5 files into the daily derived cube."""
    fields: dict[str, np.ndarray] = {}
    stamps: np.ndarray | None = None
    for key, path in files.items():
        values, time_stamps = read_variable(path, key)
        fields[key] = values
        if stamps is None:
            stamps = time_stamps
        elif not np.array_equal(stamps, time_stamps):
            raise ValueError(f"{year}: {key} 的时间轴与其他变量不一致")
    if stamps is None:
        raise ValueError(f"{year}: 没有可用文件")

    days = [
        dt.date(1970, 1, 1) + dt.timedelta(days=int(number))
        for number in np.unique(stamps // 86400)
    ]
    days = [day for day in days if day.year == year]

    t2m = _daily_mean(fields["t2m"], stamps, days) - 273.15
    dew = _daily_mean(fields["d2m"], stamps, days) - 273.15
    u10 = _daily_mean(fields["u10"], stamps, days)
    v10 = _daily_mean(fields["v10"], stamps, days)
    sp = _daily_mean(fields["sp"], stamps, days) / 1000.0
    wind = np.sqrt(u10**2 + v10**2)
    vpd = np.maximum(saturation_vapour_pressure(t2m) - saturation_vapour_pressure(dew), 0.0)

    tp = _daily_sum(fields["tp"], stamps - 3600, days) * 1000.0
    ssr = _daily_sum(fields["ssr"], stamps - 3600, days) / 1e6
    str_ = _daily_sum(fields["str"], stamps - 3600, days) / 1e6
    rn = ssr + str_
    precip = np.maximum(tp, 0.0)

    et0 = penman_monteith(t2m, vpd, wind, rn, sp)
    pe = effective_rainfall(precip, pe_ratio, pe_cap)

    arrays = {
        "t2m": t2m.astype(np.float32),
        "vpd": vpd.astype(np.float32),
        "wind": wind.astype(np.float32),
        "rn": rn.astype(np.float32),
        "pres": sp.astype(np.float32),
        "precip": precip.astype(np.float32),
        "et0": et0.astype(np.float32),
        "pe": pe.astype(np.float32),
    }
    return YearCube(year=year, dates=[day.isoformat() for day in days], arrays=arrays)


def group_files(paths: list[Path]) -> tuple[dict[int, dict[str, Path]], list[str]]:
    """Bucket files into ``{year: {variable: path}}``, reporting what was skipped."""
    buckets: dict[int, dict[str, Path]] = {}
    warnings: list[str] = []
    for path in paths:
        detected = detect_variable(path)
        if detected is None:
            warnings.append(f"无法识别变量或年份：{path.name}")
            continue
        key, year = detected
        bucket = buckets.setdefault(year, {})
        if key in bucket:
            warnings.append(f"重复的 {key} {year} 文件，使用 {path.name}")
        bucket[key] = path
    return buckets, warnings


def read_coordinates(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with open_dataset_bytes(path) as dataset:
        lat = np.asarray(dataset.variables["latitude"][:], dtype=np.float64)
        lon = np.asarray(dataset.variables["longitude"][:], dtype=np.float64)
    return lat, lon
