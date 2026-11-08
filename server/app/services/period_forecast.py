"""Shared weather aggregation and LSTM inference for fixed forecast horizons."""

from __future__ import annotations

from pathlib import Path

import numpy as np

SCALES = {"week": (7, 8), "month": (30, 2)}  # horizon / block size, number of history blocks
TARGETS = ("et_mm_day", "effective_rain_mm_day")
SCHEMA = "era5_etmonitor_period_profiles_v1"


def aggregate_weather(blocks: np.ndarray) -> np.ndarray:
    """The first five weather variables use block means, precipitation uses sums."""
    result = blocks.mean(axis=-2)
    result[..., -1] = blocks[..., -1].sum(axis=-1)
    return result


def make_network(features: int, horizon: int, hidden: int):
    from torch import nn

    return nn.ModuleDict({
        "body": nn.LSTM(features, hidden, batch_first=True),
        "output": nn.Linear(hidden, horizon * len(TARGETS)),
    })


def run_network(network, x):
    sequence, _ = network["body"](x)
    return network["output"](sequence[:, -1]).reshape(len(x), -1, len(TARGETS))


class PeriodForecaster:
    def __init__(self, path: Path, scale: str, features: tuple[str, ...]):
        import torch

        self.horizon, self.blocks = SCALES[scale]
        self.history_days = self.horizon * self.blocks
        bundle = torch.load(path, map_location="cpu", weights_only=True)
        if (
            bundle["schema"] != SCHEMA or bundle["scale"] != scale
            or tuple(bundle["features"]) != features or tuple(bundle["targets"]) != TARGETS
            or (bundle["horizon"], bundle["blocks"]) != SCALES[scale]
            or bundle["input_last_offset"] != -1 or bundle["target_first_offset"] != 1
            or bundle["trained_through"] > "2003-12-31"
        ):
            raise ValueError("unexpected period LSTM checkpoint")
        self.network = make_network(len(features), self.horizon, bundle["hidden"])
        self.network.load_state_dict(bundle["state_dict"])
        self.network.eval()
        scaler = bundle["scaler"]
        self.x_mean, self.x_std, self.y_mean, self.y_std = (
            np.asarray(scaler[key], dtype=np.float32)
            for key in ("x_mean", "x_std", "y_mean", "y_std")
        )
        if (
            self.x_mean.shape != (len(features),) or self.x_std.shape != self.x_mean.shape
            or self.y_mean.shape != (len(TARGETS),) or self.y_std.shape != self.y_mean.shape
            or not np.isfinite(np.concatenate([self.x_mean, self.x_std, self.y_mean, self.y_std])).all()
            or (self.x_std <= 0).any() or (self.y_std <= 0).any()
        ):
            raise ValueError("invalid period LSTM normalization parameters")

    def predict(self, weather: np.ndarray) -> np.ndarray:
        import torch

        blocks = weather.reshape(len(weather), self.blocks, self.horizon, weather.shape[-1])
        inputs = (aggregate_weather(blocks) - self.x_mean) / self.x_std
        with torch.inference_mode():
            profiles = run_network(self.network, torch.from_numpy(inputs)).numpy()
        profiles = np.maximum(profiles * self.y_std + self.y_mean, 0)
        profiles[..., 1] = np.minimum(profiles[..., 1], 35.0)
        return profiles
