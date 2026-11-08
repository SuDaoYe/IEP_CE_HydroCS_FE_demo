"""One-day ETMonitor-scale forecasts from the preceding 60 days of ERA5."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import numpy as np

from ..config import ARTIFACTS_DIR
from . import geo, gridmath

WINDOW = 60
START = date(2004, 1, 1)
END = date(2004, 12, 31)
WEATHER_FEATURES = (
    "temperature_c", "vpd_kpa", "wind10_m_s", "net_radiation_mj_m2_day",
    "pressure_kpa", "precipitation_mm_day",
)
MEAN_WINDOWS = (1, 3, 7, 14, 30, WINDOW)


class ForecastUnavailable(Exception):
    """The bundled model or meteorological history cannot be loaded."""


def rf_inputs(history: np.ndarray) -> np.ndarray:
    """Build rolling means of the six weather variables for direct ET prediction."""
    return np.concatenate([history[:, -days:].mean(axis=1) for days in MEAN_WINDOWS], axis=1)


@dataclass(frozen=True)
class ForecastAssets:
    model: Any
    weather: np.ndarray
    date_index: dict[date, int]
    lat: np.ndarray
    lon: np.ndarray
    trained: np.ndarray


@lru_cache(maxsize=1)
def load() -> ForecastAssets:
    try:
        import joblib

        with np.load(ARTIFACTS_DIR / "et_forecast_weather.npz", allow_pickle=False) as data:
            weather, lat, lon, trained = (data[key] for key in ("weather", "lat", "lon", "trained"))
            date_index = {date.fromisoformat(day): i for i, day in enumerate(data["dates"].astype(str))}
            if tuple(data["features"]) != WEATHER_FEATURES:
                raise ValueError("unexpected weather feature schema")
        if (
            weather.shape != (len(date_index), len(lat), len(lon), len(WEATHER_FEATURES))
            or trained.shape != (len(lat), len(lon))
        ):
            raise ValueError("unexpected weather grid shape")
        # This fixed path is for the model shipped with the server. User uploads never use it.
        model = joblib.load(ARTIFACTS_DIR / "et_forecast_rf.joblib")
        if model.n_features_in_ != len(WEATHER_FEATURES) * len(MEAN_WINDOWS):
            raise ValueError("unexpected random forest feature count")
        return ForecastAssets(model, weather, date_index, lat, lon, trained)
    except (OSError, EOFError, ImportError, ValueError, KeyError, AttributeError) as exc:
        raise ForecastUnavailable("蒸散发模型或历史气象资产无法加载") from exc


def parcel_weights(rings: list[geo.Ring], assets: ForecastAssets) -> dict[tuple[int, int], float]:
    weights: dict[tuple[int, int], float] = defaultdict(float)
    half_cell = abs(float(assets.lon[1] - assets.lon[0])) / 2
    for ring in rings:
        west, south, east, north = geo.bbox_of_points(ring)
        if (
            west < assets.lon[0] - half_cell or east > assets.lon[-1] + half_cell
            or south < assets.lat[-1] - half_cell or north > assets.lat[0] + half_cell
        ):
            raise ValueError("田块超出模型覆盖的气象网格")
        area = geo.geodesic_area_m2(ring)
        for row, col, share in gridmath.overlap_weights(ring, assets.lon, assets.lat):
            weights[row, col] += share * area
    if not weights or not all(assets.trained[row, col] for row, col in weights):
        raise ValueError("田块包含模型未覆盖的网格")
    return weights


def predict(rings: list[geo.Ring], target: date) -> dict[str, Any]:
    if not START <= target <= END:
        raise ValueError(f"历史演示支持 {START} 至 {END}")
    assets = load()
    first = target - timedelta(days=WINDOW)
    last = target - timedelta(days=1)
    days = [assets.date_index.get(first + timedelta(days=i)) for i in range(WINDOW)]
    if None in days:
        raise ValueError("预测日期缺少连续 60 天的历史气象")
    weights = parcel_weights(rings, assets)
    rows, cols = np.asarray(list(weights)).T
    history = assets.weather[np.asarray(days)[:, None], rows, cols].transpose(1, 0, 2)
    if not np.isfinite(history).all():
        raise ValueError("田块网格缺少完整的 60 天历史气象")
    daily_et = assets.model.predict(rf_inputs(history))
    return {
        "date": target.isoformat(),
        "model": "era5-rf-direct-60d",
        "et_mm_day": round(float(np.average(daily_et, weights=list(weights.values()))), 3),
        "history_start": first.isoformat(),
        "history_end": last.isoformat(),
        "cells": len(weights),
    }
