"""训练得到的日 ET 预测模型（ERA5 驱动 → ETMonitor 日蒸散）。

`scripts/train_et_model.py` 用 2001–2002 训练、2003 验证选窗、2004 测试，
产出 ``artifacts/models/et_model.joblib``。这里负责加载、按格点预测、
把田块与 0.25° 网格做面积加权，并在超出观测年份时用同日序气候态外推。

预测的是**实际蒸散 ET（mm/day）**，不是参考蒸散 ET0；因此需水链路上它直接
代表作物耗水，不再走"反推 ET0"的近似。
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from ..config import settings
from . import era5, geo, gridmath

log = logging.getLogger(__name__)

_lock = threading.Lock()
_bundle: "ETBundle | None" = None
_error: str | None = None


@dataclass(slots=True)
class ETBundle:
    model: object
    feature_keys: list[str]
    window: int
    feature_count: int
    valid_metrics: dict
    test_metrics: dict
    candidates: list[dict]
    train_years: list[int]
    valid_year: int
    test_year: int
    dates: list[str]

    def to_status(self) -> dict:
        return {
            "available": True,
            "algorithm": "HistGradientBoostingRegressor",
            "window": self.window,
            "features": self.feature_count,
            "train_years": self.train_years,
            "valid_year": self.valid_year,
            "test_year": self.test_year,
            "valid_metrics": self.valid_metrics,
            "test_metrics": self.test_metrics,
            "candidates": self.candidates,
            "target": "ETMonitor 日 ET (mm/day)",
        }


def _model_path() -> Path:
    return Path(getattr(settings, "et_model_path", Path(settings.era5_path).parent / "models" / "et_model.joblib"))


def load() -> ETBundle | None:
    global _bundle, _error
    if _bundle is not None or _error is not None:
        return _bundle
    with _lock:
        if _bundle is not None or _error is not None:
            return _bundle
        path = _model_path()
        if not path.is_file():
            _error = f"模型文件缺失：{path}（运行 scripts/train_et_model.py）"
            log.warning("%s — 退回 Penman–Monteith 参考蒸散", _error)
            return None
        try:
            payload = joblib.load(path)
            _bundle = ETBundle(
                model=payload["model"],
                feature_keys=list(payload["feature_keys"]),
                window=int(payload["window"]),
                feature_count=int(payload.get("feature_count", 0)),
                valid_metrics=payload.get("valid_metrics", {}),
                test_metrics=payload.get("test_metrics", {}),
                candidates=payload.get("candidates", []),
                train_years=payload.get("train_years", []),
                valid_year=payload.get("valid_year", 0),
                test_year=payload.get("test_year", 0),
                dates=payload.get("dates", []),
            )
            log.info(
                "loaded ET model: window %s, %s features, test RMSE %s",
                _bundle.window,
                _bundle.feature_count,
                _bundle.test_metrics.get("rmse"),
            )
        except Exception as exc:  # noqa: BLE001
            _error = f"{exc.__class__.__name__}: {exc}"
            log.warning("failed to load ET model: %s", _error)
    return _bundle


def reset() -> None:
    global _bundle, _error
    with _lock:
        _bundle = None
        _error = None


def status() -> dict:
    bundle = load()
    if bundle is None:
        return {"available": False, "error": _error, "path": str(_model_path())}
    return bundle.to_status()


# --- inference ------------------------------------------------------------


def _feature_matrix(bundle: ETBundle, index: int, rows: np.ndarray, cols: np.ndarray) -> np.ndarray | None:
    """取以 ``index`` 结尾、长度 = window 的特征窗口，形状 (len(rows), window*6)。"""
    dataset = era5.load()
    if dataset is None:
        return None
    start = index - bundle.window + 1
    if start < 0:
        return None
    chunks = []
    for lag in range(bundle.window - 1, -1, -1):
        frame_index = index - lag
        for key in bundle.feature_keys:
            block = getattr(dataset, key)
            chunks.append(block[frame_index][rows, cols].astype(np.float32))
    return np.stack(chunks, axis=1)


def predict_cells(bundle: ETBundle, day: dt.date, cells: list[tuple[int, int, float]]) -> float | None:
    """对一组 (row, col, weight) 格点预测并加权平均。"""
    dataset = era5.load()
    if dataset is None:
        return None
    index = dataset.index_of_date(day)
    if index is None:
        return None
    rows = np.array([cell[0] for cell in cells])
    cols = np.array([cell[1] for cell in cells])
    weights = np.array([cell[2] for cell in cells], dtype=np.float64)
    matrix = _feature_matrix(bundle, index, rows, cols)
    if matrix is None:
        return None
    predictions = np.asarray(bundle.model.predict(matrix), dtype=np.float64)
    finite = np.isfinite(predictions)
    if finite.sum() == 0:
        return None
    weights = weights * finite
    total = weights.sum()
    if total <= 0:
        return None
    value = float((predictions * weights).sum() / total)
    return max(value, 0.0)


def _climatology(bundle: ETBundle, day: dt.date, cells: list[tuple[int, int, float]]) -> float | None:
    """未来日期：取 2000–2004 同一天序的模型预测均值。"""
    dataset = era5.load()
    if dataset is None:
        return None
    doy = day.timetuple().tm_yday
    samples = []
    for index, date in enumerate(dataset.dates):
        if date.timetuple().tm_yday != doy:
            continue
        value = predict_cells(bundle, date, cells)
        if value is not None:
            samples.append(value)
    if not samples:
        return None
    return float(np.mean(samples))


def _cells_for_ring(ring: geo.Ring) -> list[tuple[int, int, float]]:
    dataset = era5.load()
    if dataset is None:
        return []
    return gridmath.overlap_weights(ring, dataset.lon, dataset.lat)


def predict_day(ring: geo.Ring, day: dt.date) -> dict:
    """田块尺度的一天 ET 预测（面积加权）。

    观测年份（2000–2004）直接用当天的 ERA5 历史窗口；超出范围的日期
    （例如"今天"）改用 2000–2004 同一天序的模型预测均值，即气候态外推。
    """
    bundle = load()
    if bundle is None:
        return {"et_mm_day": None, "source": "model-unavailable", "extrapolated": False}

    dataset = era5.load()
    if dataset is None:
        return {"et_mm_day": None, "source": "model-no-era5", "extrapolated": False}

    cells = _cells_for_ring(ring)
    if not cells:
        lon, lat = geo.ring_centroid(ring)
        row = int(np.abs(dataset.lat - lat).argmin())
        col = int(np.abs(dataset.lon - lon).argmin())
        cells = [(row, col, 1.0)]

    if dataset.index_of_date(day) is not None:
        value = predict_cells(bundle, day, cells)
        if value is not None:
            return {"et_mm_day": round(value, 3), "source": "model",
                    "extrapolated": False, "cells": len(cells)}

    value = _climatology(bundle, day, cells)
    if value is not None:
        return {"et_mm_day": round(value, 3), "source": "model-climatology",
                "extrapolated": False, "cells": len(cells)}
    return {"et_mm_day": None, "source": "model-no-features", "extrapolated": False}


def series(ring: geo.Ring, start: dt.date, days: int) -> list[dict]:
    out = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        row = predict_day(ring, day)
        row["date"] = day.isoformat()
        row["dow"] = day.weekday()
        out.append(row)
    return out
