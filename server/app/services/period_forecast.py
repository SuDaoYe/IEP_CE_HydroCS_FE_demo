"""Shared weather aggregation and LSTM inference for fixed forecast horizons."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

SCALES = {"week": (7, 8), "month": (30, 2)}  # horizon / block size, number of history blocks
TARGETS = ("et_mm_day", "effective_rain_mm_day")
SCHEMA = "era5_etmonitor_period_profiles_v1"
DEFICIT_SCHEMA = "era5_expected_deficit_v1"
WEEK_DAYS = SCALES["week"][0]
PADDY_SCALE = 3.0


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


def deficit_start(scale: str) -> int:
    return WEEK_DAYS if scale == "month" else 0


def make_deficit_head(hidden: int):
    from torch import nn

    return nn.Sequential(nn.Linear(hidden + 2, hidden), nn.ReLU(), nn.Linear(hidden, 1))


def expected_deficit(head, features, rain_ratio, percolation):
    """Predict the mean daily positive deficit in the model's assigned interval."""
    import torch

    x = torch.cat((features, rain_ratio[:, None], percolation[:, None] / PADDY_SCALE), dim=1)
    return head(x).squeeze(-1)


class PeriodForecaster:
    def __init__(self, path: Path, scale: str, features: tuple[str, ...]):
        import torch

        self.horizon, self.blocks = SCALES[scale]
        self.history_days = self.horizon * self.blocks
        self.skip_days = deficit_start(scale)
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
        deficit = torch.load(path.with_name(f"{path.stem}_deficit.pt"), map_location="cpu", weights_only=True)
        if (
            deficit["schema"] != DEFICIT_SCHEMA or deficit["scale"] != scale
            or deficit["target_first_offset"] != self.skip_days + 1
            or deficit["target_last_offset"] != self.horizon
            or deficit["input_last_offset"] != -1
            or deficit["encoder_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise ValueError("unexpected irrigation deficit checkpoint")
        self.deficit_head = make_deficit_head(bundle["hidden"])
        self.deficit_head.load_state_dict(deficit["state_dict"])
        self.deficit_head.eval()
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

    def predict_totals(
        self, weather: np.ndarray, rain_ratio: float, percolation: float, fixed_rain: float,
    ) -> np.ndarray:
        """Return each cell's ET and expected net deficit depth for this interval."""
        import torch

        blocks = weather.reshape(len(weather), self.blocks, self.horizon, weather.shape[-1])
        inputs = (aggregate_weather(blocks) - self.x_mean) / self.x_std
        with torch.inference_mode():
            sequence, _ = self.network["body"](torch.from_numpy(inputs))
            features = sequence[:, -1]
            profile = self.network["output"](features).reshape(len(inputs), self.horizon, len(TARGETS))
            et = np.maximum(profile[:, self.skip_days :, 0].numpy() * self.y_std[0] + self.y_mean[0], 0)
            if fixed_rain > 0 or rain_ratio == 0:
                deficit = np.maximum(et + percolation - fixed_rain, 0).sum(axis=1)
            else:
                ratio = features.new_full((len(features),), rain_ratio)
                leakage = features.new_full((len(features),), percolation)
                net = expected_deficit(self.deficit_head, features, ratio, leakage).numpy()
                deficit = np.clip(net * et.shape[1], 0, (et + percolation).sum(axis=1))
        return np.column_stack((et.sum(axis=1), deficit))
