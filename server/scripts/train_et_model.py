"""训练日尺度 ET 预测模型（ERA5 特征 → ETMonitor 日 ET）。

复刻 ``daily_et_window_study`` 的实验协议，只是把模型换成 CPU 上更快收敛的
梯度提升树（HistGradientBoostingRegressor，原生支持缺测、训练稳定）：

    训练 2001–2002 · 验证 2003（早停 + 选窗口） · 测试 2004

产出 ``artifacts/models/et_model.joblib``，内含模型、特征清单、窗口长度与指标，
供 ``app/services/et_model.py`` 直接加载。

用法::

    python scripts/train_et_model.py
    python scripts/train_et_model.py --windows 7 30 --train-samples 150000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np

SERVER_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS = SERVER_DIR / "artifacts"

FEATURE_KEYS = ("t2m", "vpd", "wind", "rn", "pres", "precip")
TRAIN_YEARS = (2001, 2002)
VALID_YEAR = 2003
TEST_YEAR = 2004


def load_cubes() -> tuple[np.ndarray, dict[str, np.ndarray], list[str], np.ndarray, np.ndarray]:
    et = np.load(ARTIFACTS / "et_grid.npz")
    era = np.load(ARTIFACTS / "era5_daily.npz")

    et_dates = [str(d) for d in et["dates"].tolist()]
    era_dates = [str(d) for d in era["dates"].tolist()]
    common = sorted(set(et_dates) & set(era_dates))

    et_index = {d: i for i, d in enumerate(et_dates)}
    era_index = {d: i for i, d in enumerate(era_dates)}

    target = np.stack([et["et"][et_index[d]] for d in common]).astype(np.float32)
    blocks = {
        key: np.stack([era[key][era_index[d]] for d in common]).astype(np.float32)
        for key in FEATURE_KEYS
    }
    return target, blocks, common, np.asarray(et["lat"]), np.asarray(et["lon"])


def build_xy(
    target: np.ndarray,
    blocks: dict[str, np.ndarray],
    samples: np.ndarray,
    window: int,
) -> tuple[np.ndarray, np.ndarray]:
    """把 (时间, 格点) 端点展开成窗口特征矩阵。"""
    times = samples[:, 0]
    cells = samples[:, 1]
    rows, cols = target.shape[1], target.shape[2]
    flat_cells = cells

    chunks = []
    for lag in range(window - 1, -1, -1):
        frame = times - lag
        for key in FEATURE_KEYS:
            values = blocks[key].reshape(len(blocks[key]), rows * cols)[frame, flat_cells]
            chunks.append(values.astype(np.float32))
    x = np.stack(chunks, axis=1)
    y = target.reshape(len(target), rows * cols)[times, flat_cells].astype(np.float32)
    return x, y


def sample_endpoints(
    target: np.ndarray,
    years: np.ndarray,
    wanted_years: tuple[int, ...],
    window: int,
    count: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """在指定年份里抽取 (时间, 格点) 端点，要求目标有效且窗口完整。"""
    time_mask = np.isin(years, wanted_years)
    valid = np.isfinite(target) & time_mask[:, None, None]
    valid[: window - 1] = False
    times, cells = np.nonzero(valid.reshape(len(target), -1))
    if len(times) == 0:
        raise SystemExit("没有可用样本")
    if count and len(times) > count:
        pick = rng.choice(len(times), size=count, replace=False)
        times, cells = times[pick], cells[pick]
    return np.stack([times, cells], axis=1)


def metrics(observed: np.ndarray, predicted: np.ndarray) -> dict:
    mask = np.isfinite(observed) & np.isfinite(predicted)
    obs, pred = observed[mask], predicted[mask]
    residual = pred - obs
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((obs - obs.mean()) ** 2))
    return {
        "n": int(mask.sum()),
        "rmse": round(float(np.sqrt(np.mean(residual**2))), 4),
        "mae": round(float(np.mean(np.abs(residual))), 4),
        "r2": round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else None,
        "mbe": round(float(np.mean(residual)), 4),
        "obs_mean": round(float(obs.mean()), 3),
        "pred_mean": round(float(pred.mean()), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=int, nargs="*", default=[1, 7, 30])
    parser.add_argument("--train-samples", type=int, default=150000)
    parser.add_argument("--eval-samples", type=int, default=40000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ARTIFACTS / "models" / "et_model.joblib")
    args = parser.parse_args()

    from sklearn.ensemble import HistGradientBoostingRegressor

    target, blocks, dates, lat, lon = load_cubes()
    years = np.asarray([int(d[:4]) for d in dates])
    rng = np.random.default_rng(args.seed)
    print(f"cube {target.shape}, {len(dates)} 天, 有效目标 {np.isfinite(target).mean() * 100:.1f}%", flush=True)

    best: dict | None = None
    results = []
    for window in args.windows:
        started = time.time()
        train_samples = sample_endpoints(target, years, TRAIN_YEARS, window, args.train_samples, rng)
        valid_samples = sample_endpoints(target, years, (VALID_YEAR,), window, args.eval_samples, rng)
        test_samples = sample_endpoints(target, years, (TEST_YEAR,), window, args.eval_samples, rng)

        x_train, y_train = build_xy(target, blocks, train_samples, window)
        x_valid, y_valid = build_xy(target, blocks, valid_samples, window)
        x_test, y_test = build_xy(target, blocks, test_samples, window)

        model = HistGradientBoostingRegressor(
            max_iter=400,
            learning_rate=0.06,
            max_depth=None,
            max_leaf_nodes=31,
            min_samples_leaf=40,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.12,
            n_iter_no_change=25,
            random_state=args.seed,
        )
        model.fit(x_train, y_train)

        valid_metrics = metrics(y_valid, model.predict(x_valid))
        test_metrics = metrics(y_test, model.predict(x_test))
        elapsed = time.time() - started
        results.append(
            {"window": window, "features": x_train.shape[1],
             "train_samples": len(x_train), "valid": valid_metrics, "test": test_metrics,
             "fit_seconds": round(elapsed, 1)}
        )
        print(
            f"window {window:3d}: valid RMSE {valid_metrics['rmse']:.4f} R2 {valid_metrics['r2']:.3f} "
            f"| test RMSE {test_metrics['rmse']:.4f} R2 {test_metrics['r2']:.3f} "
            f"| {elapsed:.0f}s",
            flush=True,
        )
        if best is None or valid_metrics["rmse"] < best["valid"]["rmse"]:
            best = {"window": window, "model": model, "valid": valid_metrics, "test": test_metrics,
                    "features": x_train.shape[1], "train_samples": len(x_train),
                    "fit_seconds": round(elapsed, 1)}

    assert best is not None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": best["model"],
        "feature_keys": list(FEATURE_KEYS),
        "window": best["window"],
        "feature_count": best["features"],
        "train_years": list(TRAIN_YEARS),
        "valid_year": VALID_YEAR,
        "test_year": TEST_YEAR,
        "valid_metrics": best["valid"],
        "test_metrics": best["test"],
        "candidates": results,
        "dates": [dates[0], dates[-1]],
        "target": "ETMonitor 日 ET (mm/day)",
        "seed": args.seed,
    }
    joblib.dump(payload, args.out, compress=3)
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"\nbest window = {best['window']} 天")
    print(f"valid 2003: {json.dumps(best['valid'], ensure_ascii=False)}")
    print(f"test  2004: {json.dumps(best['test'], ensure_ascii=False)}")
    print(f"wrote {args.out} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
