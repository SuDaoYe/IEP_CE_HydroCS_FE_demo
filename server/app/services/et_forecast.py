"""Daily LSTM evapotranspiration and historical irrigation replenishment estimates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from pickle import UnpicklingError
from typing import Any

import numpy as np

from ..config import ARTIFACTS_DIR
from . import era5, geo, gridmath
from .period_forecast import SCALES, PeriodForecaster

WINDOW = 60
START = date(2004, 1, 1)
END = date(2004, 12, 31)
WEATHER_FEATURES = (
    "temperature_c", "vpd_kpa", "wind10_m_s", "net_radiation_mj_m2_day",
    "pressure_kpa", "precipitation_mm_day",
)
PRECIPITATION = WEATHER_FEATURES.index("precipitation_mm_day")


class ForecastUnavailable(Exception):
    """The bundled model or meteorological history cannot be loaded."""


class LstmForecaster:
    def __init__(self, path: Path):
        import torch
        from torch import nn

        bundle = torch.load(path, map_location="cpu", weights_only=True)
        contract = bundle["contract"]
        if (
            bundle["kind"] != "lstm" or bundle["window"] != WINDOW
            or contract["schema"] != "past60_daily_et_v1"
            or contract["window_days"] != WINDOW
            or (contract["input_first_day_offset"], contract["input_last_day_offset"]) != (-WINDOW, -1)
            or tuple(contract["features"]) != WEATHER_FEATURES
            or bundle["trained_through"] != (START - timedelta(days=1)).isoformat()
        ):
            raise ValueError("unexpected 60-day LSTM checkpoint")
        params = bundle["params"]
        self.network = nn.ModuleDict({
            "body": nn.LSTM(len(WEATHER_FEATURES), params["hidden"], params["layers"], batch_first=True),
            "output": nn.Linear(params["hidden"], 1),
        })
        self.network.load_state_dict(bundle["state_dict"])
        self.network.eval()
        scaler = bundle["scaler"]
        self.x_mean = np.asarray(scaler["x_mean"], dtype=np.float32)
        self.x_std = np.asarray(scaler["x_std"], dtype=np.float32)
        self.y_mean = float(scaler["y_mean"])
        self.y_std = float(scaler["y_std"])
        if (
            self.x_mean.shape != (len(WEATHER_FEATURES),) or self.x_std.shape != self.x_mean.shape
            or not np.isfinite(self.x_mean).all() or not np.isfinite(self.x_std).all()
            or (self.x_std <= 0).any()
            or not np.isfinite([self.y_mean, self.y_std]).all() or self.y_std <= 0
        ):
            raise ValueError("invalid LSTM normalization parameters")

    def predict(self, history: np.ndarray) -> np.ndarray:
        import torch

        normalized = ((history - self.x_mean) / self.x_std).astype(np.float32)
        with torch.inference_mode():
            encoded, _ = self.network["body"](torch.from_numpy(normalized))
            values = self.network["output"](encoded[:, -1]).squeeze(-1).numpy()
        return np.maximum(values * self.y_std + self.y_mean, 0)


@dataclass(frozen=True)
class ForecastAssets:
    model: LstmForecaster
    period_models: dict[str, PeriodForecaster]
    weather: np.ndarray
    date_index: dict[date, int]
    lat: np.ndarray
    lon: np.ndarray
    trained: np.ndarray


@lru_cache(maxsize=1)
def load() -> ForecastAssets:
    try:
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
        model = LstmForecaster(ARTIFACTS_DIR / "et_forecast_lstm.pt")
        period_models = {
            scale: PeriodForecaster(ARTIFACTS_DIR / f"et_forecast_{scale}.pt", scale, WEATHER_FEATURES)
            for scale in SCALES
        }
        return ForecastAssets(model, period_models, weather, date_index, lat, lon, trained)
    except (OSError, EOFError, ImportError, ValueError, KeyError, RuntimeError, UnpicklingError) as exc:
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


def _period_totals(
    start: date, days: int, et_mm: float, net_mm: float | None, area_m2: float, efficiency: float,
) -> dict[str, Any]:
    net_m3 = net_mm * area_m2 / 1000 if net_mm is not None else None
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(days=days - 1)).isoformat(),
        "days": days,
        "et_days": days,
        "irrigation_days": days if net_m3 is not None else 0,
        "et_mm": round(et_mm, 3),
        "net_volume_m3": round(net_m3, 2) if net_m3 is not None else None,
        "gross_volume_m3": round(net_m3 / efficiency, 2) if net_m3 is not None else None,
    }


def predict(
    rings: list[geo.Ring],
    target: date,
    *,
    params: dict[str, float] | None = None,
    percolation_mm_day: float = 0.0,
) -> dict[str, Any]:
    if not START <= target <= END:
        raise ValueError(f"历史演示支持 {START} 至 {END}")
    assets = load()
    first = target - timedelta(days=WINDOW)
    last = target - timedelta(days=1)
    weights = parcel_weights(rings, assets)
    rows, cols = np.asarray(list(weights)).T
    area_weights = list(weights.values())
    area_m2 = sum(area_weights)

    indices = [assets.date_index.get(first + timedelta(days=i)) for i in range(WINDOW)]
    if None in indices:
        raise ValueError("田块网格缺少完整的 60 天历史气象")
    history = assets.weather[np.asarray(indices)[:, None], rows, cols].transpose(1, 0, 2)
    if not np.isfinite(history).all():
        raise ValueError("田块网格缺少完整的 60 天历史气象")

    params = params or {}
    efficiency = params.get("efficiency", 0.85) or 0.85
    rain_ratio = params.get("effective_rain_ratio", 1.0)
    rain_override = params.get("effective_rain_mm_day", 0.0)
    daily_et = float(np.average(assets.model.predict(history), weights=area_weights))
    rain_today = rain_override if rain_override > 0 else None
    rain_index = assets.date_index.get(target)
    if rain_today is None and rain_index is not None:
        rain = assets.weather[rain_index, rows, cols, PRECIPITATION]
        if np.isfinite(rain).all():
            rain_today = float(np.average(era5.effective_rainfall(rain), weights=area_weights)) * rain_ratio
    net_today = max(0.0, daily_et + percolation_mm_day - rain_today) if rain_today is not None else None
    periods = {
        "day": {
            **_period_totals(target, 1, daily_et, net_today, area_m2, efficiency),
            "method": "daily-replay",
            "history_start": first.isoformat(),
            "history_end": last.isoformat(),
        },
    }
    interval_totals = {}
    for scale, model in assets.period_models.items():
        totals = model.predict_totals(
            history[:, -model.history_days :], rain_ratio, percolation_mm_day, rain_override,
        )
        interval_totals[scale] = np.average(totals, axis=0, weights=area_weights)
    # Both cards use the same first week. The monthly model adds only days 8–30.
    interval_totals["month"] += interval_totals["week"]
    for scale, model in assets.period_models.items():
        et_mm, net_mm = map(float, interval_totals[scale])
        periods[scale] = {
            **_period_totals(
                target + timedelta(days=1), model.horizon, et_mm, net_mm, area_m2, efficiency,
            ),
            "method": "period-lstm",
            "history_start": (target - timedelta(days=model.history_days)).isoformat(),
            "history_end": last.isoformat(),
        }

    return {
        "date": target.isoformat(),
        "model": "era5-lstm-direct-60d",
        "et_mm_day": round(daily_et, 3),
        "history_start": first.isoformat(),
        "history_end": last.isoformat(),
        "cells": len(weights),
        "efficiency": efficiency,
        "periods": periods,
    }
