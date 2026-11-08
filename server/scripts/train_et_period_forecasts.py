"""Package causal ERA5/ETMonitor period samples and train the two LSTMs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ARTIFACTS_DIR
from app.services.era5 import effective_rainfall
from app.services.et_forecast import WEATHER_FEATURES
from app.services.period_forecast import SCHEMA, SCALES, TARGETS, aggregate_weather, make_network, run_network

SPLITS = {
    "train": ("2001-01-01", "2002-12-31"),
    "validation": ("2003-01-01", "2003-12-31"),
    "test": ("2004-01-01", "2004-12-31"),
}
BATCH_SIZE = 2048
HIDDEN = 48


def package_dataset(source: Path, destination: Path) -> dict:
    with np.load(source, allow_pickle=False) as archive:
        weather, et = archive["x"], archive["y"]
        dates = archive["dates"].astype("datetime64[D]")
        if tuple(archive["features"]) != WEATHER_FEATURES:
            raise ValueError("Unexpected ERA5 feature order")
        data = {"dates": dates, "latitude": archive["latitude"], "longitude": archive["longitude"]}
    if not np.all(np.diff(dates) == np.timedelta64(1, "D")):
        raise ValueError("The daily data must use a continuous calendar")
    targets = np.stack((et, effective_rainfall(weather[..., -1])), axis=-1)
    data.update(targets=targets, features=np.array(WEATHER_FEATURES), target_names=np.array(TARGETS))
    invalid_targets = ~np.isfinite(targets).all(axis=-1)
    bad_prefix = np.vstack((
        np.zeros((1, targets.shape[1]), dtype=np.int32),
        np.cumsum(invalid_targets, axis=0, dtype=np.int32),
    ))
    for scale, (horizon, blocks) in SCALES.items():
        windows = np.lib.stride_tricks.sliding_window_view(weather, horizon, axis=0).swapaxes(-1, -2)
        block_data = aggregate_weather(windows)
        data[f"{scale}_weather"] = block_data
        valid_blocks = np.isfinite(block_data).all(axis=-1)
        issue = np.arange(horizon * blocks, len(dates) - horizon)
        history_offsets = np.arange(-horizon * blocks, 0, horizon)
        complete = valid_blocks[issue[:, None] + history_offsets].all(axis=1)
        complete &= bad_prefix[issue + horizon + 1] == bad_prefix[issue + 1]
        for split, (first, last) in SPLITS.items():
            in_split = (dates[issue] >= np.datetime64(first)) & (dates[issue + horizon] <= np.datetime64(last))
            date_row, cell = np.nonzero(complete & in_split[:, None])
            data[f"{scale}_{split}"] = np.column_stack((issue[date_row], cell)).astype(np.int32)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination, **data)
    print(f"Packaged {destination}", flush=True)
    return data


def sample_arrays(data: dict, scale: str, endpoints: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    horizon, blocks = SCALES[scale]
    issue, cell = endpoints.T
    starts = issue[:, None] + np.arange(-horizon * blocks, 0, horizon)
    target_days = issue[:, None] + np.arange(1, horizon + 1)
    x = data[f"{scale}_weather"][starts, cell[:, None]]
    y = data["targets"][target_days, cell[:, None]]
    return x, y


def loss_for(prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    # Retain day-level supervision for the water balance and optimize the period totals.
    return F.smooth_l1_loss(prediction, target) + F.mse_loss(prediction.mean(1), target.mean(1))


def train(data: dict, scale: str, output: Path, device: torch.device, epochs: int) -> dict:
    horizon, blocks = SCALES[scale]
    rng = np.random.default_rng(42)
    torch.manual_seed(42)
    train_pool = data[f"{scale}_train"]
    val_pool = data[f"{scale}_validation"]
    train_rows = train_pool[rng.choice(len(train_pool), min(len(train_pool), 160_000), replace=False)]
    val_rows = val_pool[rng.choice(len(val_pool), min(len(val_pool), 32_000), replace=False)]
    x, y = sample_arrays(data, scale, train_rows)
    x_mean, x_std = x.mean(axis=(0, 1), dtype=np.float64).astype(np.float32), x.std(axis=(0, 1), dtype=np.float64).astype(np.float32)
    y_mean, y_std = y.mean(axis=(0, 1), dtype=np.float64).astype(np.float32), y.std(axis=(0, 1), dtype=np.float64).astype(np.float32)
    tx = torch.as_tensor((x - x_mean) / x_std, device=device)
    ty = torch.as_tensor((y - y_mean) / y_std, device=device)
    x, y = sample_arrays(data, scale, val_rows)
    vx = torch.as_tensor((x - x_mean) / x_std, device=device)
    vy = torch.as_tensor((y - y_mean) / y_std, device=device)
    model = make_network(len(WEATHER_FEATURES), horizon, HIDDEN).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.002)
    best_loss, best_state, best_epoch = float("inf"), None, 0
    for epoch in range(1, epochs + 1):
        model.train()
        for batch in torch.randperm(len(tx), device=device).split(BATCH_SIZE):
            optimizer.zero_grad(set_to_none=True)
            loss_for(run_network(model, tx[batch]), ty[batch]).backward()
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            val = sum(
                loss_for(run_network(model, bx), by).item() * len(bx)
                for bx, by in zip(vx.split(BATCH_SIZE), vy.split(BATCH_SIZE))
            ) / len(vx)
        print(f"{scale}: epoch {epoch}/{epochs}, validation loss {val:.4f}", flush=True)
        if val < best_loss:
            best_loss, best_epoch = val, epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    if best_state is None:
        raise ValueError("Training produced no finite validation loss")
    model.load_state_dict(best_state)

    def totals(profiles: np.ndarray) -> np.ndarray:
        et, rain = profiles[..., 0], profiles[..., 1]
        return np.stack((et.sum(1), rain.sum(1), np.maximum(et - rain, 0).sum(1)), axis=-1)

    test = data[f"{scale}_test"]
    error = []
    with torch.inference_mode():
        for offset in range(0, len(test), BATCH_SIZE):
            x, y = sample_arrays(data, scale, test[offset : offset + BATCH_SIZE])
            bx = torch.as_tensor((x - x_mean) / x_std, device=device)
            prediction = np.maximum(run_network(model, bx).cpu().numpy() * y_std + y_mean, 0)
            prediction[..., 1] = np.minimum(prediction[..., 1], 35.0)
            error.append(totals(prediction) - totals(y))
    errors = np.concatenate(error).astype(np.float64)
    rmse = np.sqrt(np.mean(errors**2, axis=0))
    mae = np.mean(np.abs(errors), axis=0)
    metrics = {
        "history_days": blocks * horizon, "horizon_days": horizon, "best_epoch": best_epoch,
        "training_pool": len(train_pool), "training_used": len(train_rows),
        "validation_used": len(val_rows), "test_n": len(test),
        "test_first_issue": str(data["dates"][test[0, 0]]), "test_last_issue": str(data["dates"][test[-1, 0]]),
        "metrics_mm_per_period": {
            key: {"rmse": float(rmse[i]), "mae": float(mae[i])}
            for i, key in enumerate(("et", "effective_rain", "net_replenishment"))
        },
    }
    torch.save({
        "schema": SCHEMA, "scale": scale, "features": WEATHER_FEATURES, "targets": TARGETS,
        "horizon": horizon, "blocks": blocks, "hidden": HIDDEN,
        "input_last_offset": -1, "target_first_offset": 1, "trained_through": SPLITS["train"][1],
        "state_dict": best_state,
        "scaler": dict(x_mean=x_mean.tolist(), x_std=x_std.tolist(), y_mean=y_mean.tolist(), y_std=y_std.tolist()),
    }, output / f"et_forecast_{scale}.pt")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-cache", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", default=ARTIFACTS_DIR, type=Path)
    parser.add_argument("--epochs", default=8, type=int)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    torch.set_num_threads(4)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = package_dataset(args.daily_cache, args.dataset)
    args.output.mkdir(parents=True, exist_ok=True)
    metrics = {scale: train(data, scale, args.output, device, args.epochs) for scale in SCALES}
    report = {"schema": SCHEMA, "splits": SPLITS, "seed": 42, "periods": metrics}
    rendered = json.dumps(report, indent=2) + "\n"
    (args.output / "et_forecast_period_metrics.json").write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, flush=True)


if __name__ == "__main__":
    main()
