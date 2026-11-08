"""Compare direct ET forecasts from the preceding 60 days of ERA5."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ARTIFACTS_DIR
from app.services.et_forecast import END, MEAN_WINDOWS, START, WEATHER_FEATURES, WINDOW, rf_inputs


def metrics(observed: np.ndarray, predicted: np.ndarray) -> dict:
    return {
        "n": len(observed),
        "rmse": root_mean_squared_error(observed, predicted),
        "mae": mean_absolute_error(observed, predicted),
        "r2": r2_score(observed, predicted),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-cache", type=Path, required=True)
    parser.add_argument("--lstm-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ARTIFACTS_DIR)
    args = parser.parse_args()

    with np.load(args.daily_cache, allow_pickle=False) as data:
        weather, observed = data["x"], data["y"]
        dates = data["dates"].astype("datetime64[D]")
        lat, lon = data["latitude"], data["longitude"]
        if tuple(data["features"]) != WEATHER_FEATURES:
            raise ValueError("Unexpected weather feature schema")
    with np.load(args.lstm_run / "final_endpoints.npz", allow_pickle=False) as endpoints:
        train, test = endpoints["refit"], endpoints["test"]
    train_dates = dates[train[:, 0]]
    test_dates = dates[test[:, 0]]
    if train_dates.min() < np.datetime64("2001-01-01") or train_dates.max() >= np.datetime64(START):
        raise ValueError("Expected 2001–2003 refit endpoints")
    if test_dates.min() < np.datetime64(START) or test_dates.max() > np.datetime64(END):
        raise ValueError("Expected 2004 holdout endpoints")
    if not np.all(np.diff(dates) == np.timedelta64(1, "D")):
        raise ValueError("Weather history must have a continuous daily axis")
    if train[:, 0].min() < WINDOW or test[:, 0].min() < WINDOW:
        raise ValueError("Not enough meteorological history for the benchmark")

    def matrix(indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        features = np.empty((len(indices), len(MEAN_WINDOWS) * len(WEATHER_FEATURES)), dtype=np.float32)
        for offset in range(0, len(indices), 4096):
            batch = indices[offset : offset + 4096]
            target, cell = batch.T
            history = weather[target[:, None] + np.arange(-WINDOW, 0), cell[:, None]]
            features[offset : offset + len(batch)] = rf_inputs(history)
        target, cell = indices.T
        return features, observed[target, cell]

    x_train, y_train = matrix(train)
    model = RandomForestRegressor(
        n_estimators=150, max_depth=14, min_samples_leaf=5, max_features=0.7, max_samples=100_000,
        random_state=42, n_jobs=8,
    )
    print(f"Fitting direct RF on a pool of {len(train):,} endpoints", flush=True)
    model.fit(x_train, y_train)
    del x_train, y_train
    x_test, y_test = matrix(test)
    prediction = model.predict(x_test)

    lstm = pd.read_csv(args.lstm_run / "test_daily_predictions.csv", dtype={
        "observed_et": np.float32, "predicted_et": np.float32,
    })
    if not (
        np.array_equal(lstm["date"], test_dates.astype(str))
        and np.array_equal(lstm["cell"], test[:, 1])
        and np.array_equal(lstm["observed_et"], y_test)
    ):
        raise ValueError("The LSTM predictions do not match the benchmark endpoints and labels")
    lstm["rf"] = prediction
    lstm["month"] = pd.PeriodIndex(lstm["date"], freq="M")
    groups = lstm.groupby(["cell", "month"])
    monthly = groups[["observed_et", "predicted_et", "rf"]].sum()
    monthly = monthly[groups.size().to_numpy() == monthly.index.get_level_values("month").days_in_month]
    results = {
        "train_pool_n": len(train),
        "rf_samples_per_tree": model.max_samples,
        "daily": {
            "rf_direct": metrics(y_test, prediction),
            "lstm": metrics(y_test, lstm["predicted_et"]),
        },
        "monthly": {
            "rf_direct": metrics(monthly["observed_et"], monthly["rf"]),
            "lstm": metrics(monthly["observed_et"], monthly["predicted_et"]),
        },
    }
    print(json.dumps(results, indent=2), flush=True)
    rows, cols = len(np.unique(lat)), len(np.unique(lon))
    grid_lat, grid_lon = lat.reshape(rows, cols), lon.reshape(rows, cols)
    if not ((grid_lat == grid_lat[:, :1]).all() and (grid_lon == grid_lon[:1, :]).all()):
        raise ValueError("Expected a rectilinear weather grid")
    trained = np.zeros(len(lat), dtype=bool)
    trained[np.unique(train[:, 1])] = True
    history = (dates >= np.datetime64(START - timedelta(days=WINDOW))) & (dates < np.datetime64(END))
    args.output.mkdir(parents=True, exist_ok=True)
    model.n_jobs = 1
    joblib.dump(model, args.output / "et_forecast_rf.joblib", compress=3)
    np.savez_compressed(
        args.output / "et_forecast_weather.npz",
        weather=weather[history].reshape(-1, rows, cols, len(WEATHER_FEATURES)),
        dates=dates[history], lat=grid_lat[:, 0], lon=grid_lon[0],
        trained=trained.reshape(rows, cols), features=np.array(WEATHER_FEATURES),
    )
    (args.output / "et_forecast_benchmark.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n",
    )


if __name__ == "__main__":
    main()
