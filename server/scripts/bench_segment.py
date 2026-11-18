"""识别推理后端基准：torch CPU / ONNX Runtime CPU / ONNX Runtime DML / CUDA。

用法（在 server 目录下）：

    python scripts/bench_segment.py                       # 自动检测可用后端
    python scripts/bench_segment.py --runs 5 --engine all

脚本会复用磁盘缓存里的影像（首次需要联网），对同一块 mosaic 计时，
输出每个后端的 P50/P90 延迟、每秒窗口数、以及检测到的地块数，
用来判断「有 CUDA 走 CUDA、没有就转译到 ONNX/DirectML」是否值得。

ONNX 权重按需导出（`artifacts/models/4.102_best.onnx`），导出后常驻复用。
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import imagery, segmentation  # noqa: E402

DEMO_BBOX = [118.7975, 37.7975, 118.8015, 37.8015]


def _onnx_path() -> Path:
    return settings.yolo_weights.with_suffix(".onnx")


def ensure_onnx(imgsz: int = 1024, force: bool = False) -> Path:
    """导出 ONNX（静态形状、含 simplify），已存在则直接复用。"""
    target = _onnx_path()
    if target.is_file() and not force:
        print(f"  onnx reuse: {target.name} ({target.stat().st_size / 1e6:.1f} MB)")
        return target
    from ultralytics import YOLO

    print("  exporting onnx ...")
    started = time.time()
    model = YOLO(str(settings.yolo_weights))
    model.export(format="onnx", imgsz=imgsz, opset=17, simplify=True, dynamic=False)
    print(f"  exported in {time.time() - started:.1f}s → {target.name}")
    return target


def providers() -> list[str]:
    try:
        import onnxruntime
    except Exception:  # noqa: BLE001
        return []
    return list(onnxruntime.get_available_providers())


def load_engine(name: str, imgsz: int):
    """返回 ultralytics YOLO 对象（pt 或 onnx），设备由后端名决定。"""
    from ultralytics import YOLO

    if name == "torch-cpu":
        return YOLO(str(settings.yolo_weights))
    if name == "torch-cuda":
        return YOLO(str(settings.yolo_weights))
    if name == "onnx-cpu":
        return YOLO(str(ensure_onnx(imgsz)))
    if name == "onnx-cuda":
        return YOLO(str(ensure_onnx(imgsz)))
    raise SystemExit(f"unknown engine {name}")


def run(name: str, image: np.ndarray, imgsz: int, runs: int, warmup: int) -> dict:
    model = load_engine(name, imgsz)
    device = "cuda" if name.endswith("cuda") else "cpu"
    timings: list[float] = []
    count = 0
    for index in range(warmup + runs):
        started = time.perf_counter()
        result = model.predict(
            image,
            imgsz=imgsz,
            conf=settings.yolo_conf,
            iou=settings.yolo_iou,
            device=device,
            verbose=False,
        )[0]
        elapsed = time.perf_counter() - started
        if result.masks is not None:
            count = len(result.masks.data)
        if index >= warmup:
            timings.append(elapsed)
    return {
        "engine": name,
        "p50_ms": round(statistics.median(timings) * 1000, 1),
        "p90_ms": round(sorted(timings)[max(0, int(len(timings) * 0.9) - 1)] * 1000, 1),
        "fps": round(len(timings) / sum(timings), 2),
        "masks": count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--imgsz", type=int, default=settings.yolo_imgsz)
    parser.add_argument("--engine", default="auto", help="auto | all | 具体后端名")
    args = parser.parse_args()

    available = providers()
    try:
        import torch

        torch_ver = torch.__version__
        cuda_ok = torch.cuda.is_available()
    except Exception:  # noqa: BLE001
        torch_ver, cuda_ok = "missing", False

    print(f"torch {torch_ver} · cuda={cuda_ok}")
    print(f"onnxruntime providers: {available or 'missing'}")

    candidates: list[str] = []
    if args.engine in {"auto", "all"}:
        if cuda_ok:
            candidates.append("torch-cuda")
        candidates.append("torch-cpu")
        if available:
            if "CUDAExecutionProvider" in available:
                candidates.append("onnx-cuda")
            if "DmlExecutionProvider" in available:
                candidates.append("onnx-dml")
            candidates.append("onnx-cpu")
    else:
        candidates = [args.engine]

    print(f"\nbuilding mosaic {DEMO_BBOX} ...")
    mosaic = imagery.build_mosaic(DEMO_BBOX, zoom=18, provider="esri", target_px=1024)
    print(f"  mosaic {mosaic.width}x{mosaic.height} @ z{mosaic.zoom} ({mosaic.mpp_x:.2f} m/px)")

    windows = segmentation._windows(mosaic.width, mosaic.height, settings.yolo_window, settings.yolo_overlap)
    print(f"  windows per request: {len(windows)}")

    # 分块计时：整块 mosaic 只取第一个窗口，避免多窗口放大绝对耗时
    x, y, w, h = windows[0]
    crop = mosaic.image[y:y + h, x:x + w]
    print(f"  bench crop: {w}x{h}\n")

    rows = []
    for name in candidates:
        if name in {"onnx-dml", "onnx-cuda"}:
            print(f"  {name}: 需要对应的 onnxruntime 构建（DirectML / GPU），本次跳过")
            continue
        try:
            row = run(name, crop, args.imgsz, args.runs, args.warmup)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name} failed: {exc.__class__.__name__}: {exc}")
            continue
        rows.append(row)
        print(f"  {row['engine']:12s} p50 {row['p50_ms']:7.1f} ms  p90 {row['p90_ms']:7.1f} ms  "
              f"{row['fps']:5.2f}/s  masks {row['masks']}")

    if len(rows) >= 2:
        base = rows[-1]
        for row in rows[:-1]:
            gain = base["p50_ms"] / row["p50_ms"]
            print(f"\n{row['engine']} vs {base['engine']}: {gain:.2f}× faster (p50)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
