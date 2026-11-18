"""把 YOLO 权重导出成 ONNX（CUDA 不可用时的「转译」路径）。

    python scripts/export_onnx.py                 # 1024 静态形状 + simplify
    python scripts/export_onnx.py --force         # 覆盖已有文件

导出的 `.onnx` 与 `.pt` 同名同目录（`artifacts/weights/4.102_best.onnx`），
识别引擎在 `HYDROCS_SEG_BACKEND=auto` 且没有 CUDA 时会自动改用它，
配合 `onnxruntime` / `onnxruntime-directml` / `onnxruntime-gpu` 跑在
CPU / DirectML（任意 DX12 显卡）/ CUDA 上。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--imgsz", type=int, default=settings.yolo_imgsz)
    args = parser.parse_args()

    if not settings.yolo_weights.is_file():
        print(f"missing weights: {settings.yolo_weights}")
        return 1

    from app.services import seg_engine

    target = seg_engine.onnx_path()
    if target.is_file() and not args.force:
        print(f"exist: {target} ({target.stat().st_size / 1e6:.1f} MB)")
        return 0

    started = time.time()
    path = seg_engine.ensure_onnx(imgsz=args.imgsz, force=args.force)
    size = path.stat().st_size / 1e6
    print(f"exported: {path} ({size:.1f} MB) in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
