"""Package the trained 60-day LSTM and its matching ERA5 history for HydroCS."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ARTIFACTS_DIR
from app.services.et_forecast import END, START, WEATHER_FEATURES, WINDOW, LstmForecaster


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-cache", type=Path, required=True)
    parser.add_argument("--lstm-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ARTIFACTS_DIR)
    args = parser.parse_args()

    checkpoint = args.lstm_run / "model_bundle.pt"
    LstmForecaster(checkpoint)
    config = json.loads((args.lstm_run / "run_config.json").read_text(encoding="utf-8"))
    with args.daily_cache.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != config["cache_sha256"]:
            raise ValueError("The ERA5 cache does not match the LSTM run")
    with np.load(args.daily_cache, allow_pickle=False) as data:
        weather, dates = data["x"], data["dates"].astype("datetime64[D]")
        lat, lon = data["latitude"], data["longitude"]
        if tuple(data["features"]) != WEATHER_FEATURES:
            raise ValueError("Unexpected weather feature schema")
    with np.load(args.lstm_run / "final_endpoints.npz", allow_pickle=False) as endpoints:
        trained_cells = np.unique(endpoints["refit"][:, 1])

    rows, cols = len(np.unique(lat)), len(np.unique(lon))
    grid_lat, grid_lon = lat.reshape(rows, cols), lon.reshape(rows, cols)
    if not ((grid_lat == grid_lat[:, :1]).all() and (grid_lon == grid_lon[:1, :]).all()):
        raise ValueError("Expected a rectilinear weather grid")
    trained = np.zeros(len(lat), dtype=bool)
    trained[trained_cells] = True
    history_dates = np.arange(START - timedelta(days=WINDOW), END, dtype="datetime64[D]")
    history = (dates >= history_dates[0]) & (dates <= history_dates[-1])
    if not np.array_equal(dates[history], history_dates):
        raise ValueError("Weather history must have a continuous daily axis")

    args.output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output / "et_forecast_weather.npz",
        weather=weather[history].reshape(-1, rows, cols, len(WEATHER_FEATURES)),
        dates=dates[history], lat=grid_lat[:, 0], lon=grid_lon[0],
        trained=trained.reshape(rows, cols), features=np.array(WEATHER_FEATURES),
    )
    shutil.copyfile(checkpoint, args.output / "et_forecast_lstm.pt")
    print(f"Packaged the 60-day LSTM and {len(history_dates)} days of ERA5 history")


if __name__ == "__main__":
    main()
