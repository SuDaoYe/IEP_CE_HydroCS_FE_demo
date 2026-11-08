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

WINDOW = 60
START = date(2004, 1, 1)
END = date(2004, 12, 31)
WEATHER_FEATURES = (
    "temperature_c", "vpd_kpa", "wind10_m_s", "net_radiation_mj_m2_day",
    "pressure_kpa", "precipitation_mm_day",
)
PRECIPITATION = WEATHER_FEATURES.index("precipitation_mm_day")
PERIODS = (("day", 0, 1), ("week", 1, 7), ("month", 1, 30))


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
        return ForecastAssets(model, weather, date_index, lat, lon, trained)
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
    start: date, days: int, et_by_date: dict[date, float], net_by_date: dict[date, float],
    area_m2: float, efficiency: float,
) -> dict[str, Any]:
    dates = [start + timedelta(days=i) for i in range(days)]
    et = [et_by_date[day] for day in dates if day in et_by_date]
    net_depths = [net_by_date[day] for day in dates if day in net_by_date]
    net_m3 = sum(net_depths) * area_m2 / 1000 if net_depths else None
    return {
        "start": start.isoformat(),
        "end": dates[-1].isoformat(),
        "days": days,
        "et_days": len(et),
        "irrigation_days": len(net_depths),
        "et_mm": round(sum(et), 3) if et else None,
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

    forecast_dates, windows = [], []
    horizon = max(offset + days for _, offset, days in PERIODS)
    for offset in range(min(horizon, (END - target).days + 1)):
        day = target + timedelta(days=offset)
        history_dates = [first + timedelta(days=offset + i) for i in range(WINDOW)]
        indices = [assets.date_index[d] for d in history_dates if d in assets.date_index]
        if len(indices) != WINDOW:
            continue
        history = assets.weather[np.asarray(indices)[:, None], rows, cols].transpose(1, 0, 2)
        if np.isfinite(history).all():
            forecast_dates.append(day)
            windows.append(history)
    if not forecast_dates or forecast_dates[0] != target:
        raise ValueError("田块网格缺少完整的 60 天历史气象")

    histories = np.concatenate(windows)
    predictions = np.concatenate([
        assets.model.predict(histories[i : i + 512]) for i in range(0, len(histories), 512)
    ]).reshape(len(forecast_dates), len(weights))
    parcel_et = np.average(predictions, axis=1, weights=area_weights)
    et_by_date = dict(zip(forecast_dates, map(float, parcel_et)))

    params = params or {}
    efficiency = params.get("efficiency", 0.85) or 0.85
    rain_ratio = params.get("effective_rain_ratio", 1.0)
    rain_override = params.get("effective_rain_mm_day", 0.0)
    net_by_date = {}
    for day, et_mm in et_by_date.items():
        if rain_override > 0:
            pe_mm = rain_override
        else:
            index = assets.date_index.get(day)
            if index is None:
                continue
            rain = assets.weather[index, rows, cols, PRECIPITATION]
            if not np.isfinite(rain).all():
                continue
            pe_mm = float(np.average(era5.effective_rainfall(rain), weights=area_weights)) * rain_ratio
        net_by_date[day] = max(0.0, et_mm + percolation_mm_day - pe_mm)

    return {
        "date": target.isoformat(),
        "model": "era5-lstm-direct-60d",
        "et_mm_day": round(et_by_date[target], 3),
        "history_start": first.isoformat(),
        "history_end": last.isoformat(),
        "cells": len(weights),
        "efficiency": efficiency,
        "periods": {
            key: _period_totals(
                target + timedelta(days=offset), days, et_by_date, net_by_date, area_m2, efficiency,
            )
            for key, offset, days in PERIODS
        },
    }
