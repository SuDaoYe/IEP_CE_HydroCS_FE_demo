"""Fit direct irrigation-deficit heads on the existing week and month LSTM encoders."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ARTIFACTS_DIR
from app.services.period_forecast import (
    DEFICIT_SCHEMA, PADDY_SCALE, SCALES, deficit_start, expected_deficit, make_deficit_head, make_network,
)
from train_et_period_forecasts import BATCH_SIZE, SPLITS, sample_arrays


class Encoder:
    def __init__(self, path: Path, scale: str, device: torch.device):
        self.scale = scale
        self.horizon = SCALES[scale][0]
        self.device = device
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        bundle = torch.load(path, map_location="cpu", weights_only=True)
        self.hidden = bundle["hidden"]
        self.network = make_network(len(bundle["features"]), self.horizon, self.hidden).to(device)
        self.network.load_state_dict(bundle["state_dict"])
        self.network.eval()
        self.scaler = {key: torch.tensor(value, device=device) for key, value in bundle["scaler"].items()}

    @torch.no_grad()
    def samples(self, data: dict, rows: np.ndarray) -> tuple[torch.Tensor, torch.Tensor]:
        x, labels = sample_arrays(data, self.scale, rows)
        x = torch.as_tensor(x, device=self.device)
        x = (x - self.scaler["x_mean"]) / self.scaler["x_std"]
        encoded = [self.network["body"](batch)[0][:, -1].contiguous() for batch in x.split(BATCH_SIZE)]
        return torch.cat(encoded), torch.as_tensor(labels, device=self.device)

    def profiles(self, encoded: torch.Tensor) -> torch.Tensor:
        profile = self.network["output"](encoded).reshape(len(encoded), self.horizon, 2)
        return (profile * self.scaler["y_std"] + self.scaler["y_mean"]).clamp_min(0)


def training_conditions(n: int, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    ratio = torch.where(
        torch.rand(n, device=device) < 0.65,
        1.0,
        torch.rand(n, device=device) * 1.2,
    )
    percolation = (torch.rand(n, device=device) < 0.30).float() * PADDY_SCALE
    return ratio, percolation


def measured_deficit(labels: torch.Tensor, ratio: torch.Tensor, percolation: torch.Tensor) -> torch.Tensor:
    return (labels[..., 0] + percolation[:, None] - labels[..., 1] * ratio[:, None]).clamp_min(0)


def fit(data: dict, encoder: Encoder, epochs: int) -> tuple[torch.nn.Module, int]:
    rng = np.random.default_rng(42)
    torch.manual_seed(42)
    scale = encoder.scale
    start = deficit_start(scale)
    train_pool = data[f"{scale}_train"]
    val_pool = data[f"{scale}_validation"]
    train_rows = train_pool[rng.choice(len(train_pool), min(len(train_pool), 160_000), replace=False)]
    val_rows = val_pool[rng.choice(len(val_pool), min(len(val_pool), 32_000), replace=False)]
    tx, ty = encoder.samples(data, train_rows)
    vx, vy = encoder.samples(data, val_rows)
    vr, vp = training_conditions(len(vx), encoder.device)
    validation_target = measured_deficit(vy[:, start:], vr, vp).mean(1)
    head = make_deficit_head(encoder.hidden).to(encoder.device)
    optimizer = torch.optim.AdamW(head.parameters(), lr=0.002)
    best_loss, best_state, best_epoch = float("inf"), None, 0
    for epoch in range(1, epochs + 1):
        head.train()
        for batch in torch.randperm(len(tx), device=encoder.device).split(BATCH_SIZE):
            ratio, percolation = training_conditions(len(batch), encoder.device)
            target = measured_deficit(ty[batch, start:], ratio, percolation).mean(1)
            optimizer.zero_grad(set_to_none=True)
            F.mse_loss(expected_deficit(head, tx[batch], ratio, percolation), target).backward()
            optimizer.step()
        head.eval()
        with torch.inference_mode():
            loss = F.mse_loss(expected_deficit(head, vx, vr, vp), validation_target).item()
        if loss < best_loss:
            best_loss, best_epoch = loss, epoch
            best_state = {key: value.detach().cpu().clone() for key, value in head.state_dict().items()}
    if best_state is None:
        raise ValueError("Training produced no finite validation loss")
    head.load_state_dict(best_state)
    print(f"{scale}: best epoch {best_epoch}, validation MSE {best_loss:.4f}", flush=True)
    return head, best_epoch


@torch.no_grad()
def score(data: dict, scale: str, encoders: dict, heads: dict) -> dict:
    encoder = encoders[scale]
    rows = data[f"{scale}_test"]
    errors = []
    start = deficit_start(scale)
    for offset in range(0, len(rows), BATCH_SIZE):
        batch = rows[offset : offset + BATCH_SIZE]
        x, y = encoder.samples(data, batch)
        ratio, leakage = x.new_ones((len(x),)), x.new_zeros((len(x),))
        profiles = encoder.profiles(x)
        old = (profiles[..., 0] - profiles[..., 1].clamp_max(35)).clamp_min(0).sum(1)
        new = expected_deficit(heads[scale], x, ratio, leakage).clamp_min(0) * (encoder.horizon - start)
        new = torch.minimum(new, profiles[:, start:, 0].sum(1))
        if start:
            week_x, _ = encoders["week"].samples(data, batch)
            week_et = encoders["week"].profiles(week_x)[..., 0].sum(1)
            week_net = expected_deficit(heads["week"], week_x, ratio, leakage).clamp_min(0) * start
            new += torch.minimum(week_net, week_et)
        truth = measured_deficit(y, ratio, leakage).sum(1)
        errors.append(torch.stack((old - truth, new - truth), dim=1).cpu().numpy())
    errors = np.concatenate(errors).astype(np.float64)
    return {
        "test_n": len(rows),
        **{
            key: {
                "rmse_mm": float(np.sqrt(np.mean(errors[:, i] ** 2))),
                "mae_mm": float(np.mean(np.abs(errors[:, i]))),
                "mean_bias_mm": float(np.mean(errors[:, i])),
            }
            for i, key in enumerate(("mean_rain_then_deficit", "direct_deficit"))
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--models", default=ARTIFACTS_DIR, type=Path)
    parser.add_argument("--output", default=ARTIFACTS_DIR, type=Path)
    parser.add_argument("--epochs", default=12, type=int)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    torch.set_num_threads(4)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with np.load(args.dataset, allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    encoders = {key: Encoder(args.models / f"et_forecast_{key}.pt", key, device) for key in SCALES}
    fits = {key: fit(data, encoder, args.epochs) for key, encoder in encoders.items()}
    heads = {key: item[0] for key, item in fits.items()}
    scores = {key: {**score(data, key, encoders, heads), "best_epoch": fits[key][1]} for key in SCALES}
    args.output.mkdir(parents=True, exist_ok=True)
    for key, head in heads.items():
        torch.save({
            "schema": DEFICIT_SCHEMA, "scale": key,
            "target_first_offset": deficit_start(key) + 1, "target_last_offset": encoders[key].horizon,
            "input_last_offset": -1,
            "encoder_sha256": encoders[key].sha256,
            "state_dict": {name: value.detach().cpu() for name, value in head.state_dict().items()},
        }, args.output / f"et_forecast_{key}_deficit.pt")
    report = {"schema": DEFICIT_SCHEMA, "splits": SPLITS, "test_rain_ratio": 1.0, "test_percolation_mm_day": 0.0, "periods": scores}
    rendered = json.dumps(report, indent=2) + "\n"
    (args.output / "et_forecast_deficit_metrics.json").write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered)


if __name__ == "__main__":
    main()
