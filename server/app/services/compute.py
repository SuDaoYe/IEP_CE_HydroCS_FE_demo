"""计算后端探测：有原生 CUDA 就用，没有就退到 ONNX / DirectML / CPU。

这个模块只做**能力探测与选择**，不加载任何模型。识别服务据此决定用哪条推理链：

| 优先级 | 后端 | 触发条件 | 说明 |
|---|---|---|---|
| 1 | `cuda` | 装的是 CUDA 版 torch 且 `torch.cuda.is_available()` | 直接跑 `.pt`，可用 fp16 |
| 2 | `onnx-cuda` | `onnxruntime` 提供 CUDAExecutionProvider | 跑 `.onnx`，兼容 onnxruntime-gpu |
| 3 | `onnx-dml` | 提供 DmlExecutionProvider（`onnxruntime-directml`） | Windows 上任意 DX12 显卡（NVIDIA / AMD / Intel 核显） |
| 4 | `torch-cpu` | 兜底 | `.pt` 在 CPU 上跑 |
| 5 | `onnx-cpu` | 兜底备选 | `.onnx` 在 CPU 上跑，线程可调 |
| - | `heuristic` | 权重缺失或全部失败 | 纯 OpenCV 规则识别 |

用环境变量 `HYDROCS_SEG_BACKEND` 可以钉死某一条（`auto|cuda|onnx-cuda|onnx-dml|torch-cpu|onnx-cpu`）。
"""

from __future__ import annotations

import logging
import os
import platform
import threading
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_lock = threading.Lock()
_probe: dict | None = None

#: 自动模式下的尝试顺序
AUTO_ORDER = ("cuda", "onnx-cuda", "onnx-dml", "torch-cpu", "onnx-cpu")

LABELS = {
    "cuda": "CUDA（原生 GPU）",
    "onnx-cuda": "ONNX Runtime CUDA",
    "onnx-dml": "ONNX Runtime DirectML",
    "torch-cpu": "PyTorch CPU",
    "onnx-cpu": "ONNX Runtime CPU",
    "heuristic": "规则识别（无模型）",
}


@dataclass(slots=True)
class Backend:
    """一个可用的推理后端。"""

    key: str
    available: bool
    device: str = "cpu"
    provider: str | None = None
    fp16: bool = False
    reason: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "backend": self.key,
            "label": LABELS.get(self.key, self.key),
            "device": self.device,
            "provider": self.provider,
            "fp16": self.fp16,
            "reason": self.reason,
        }


def _torch_info() -> dict:
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "error": f"{exc.__class__.__name__}: {exc}"}
    info = {
        "installed": True,
        "version": torch.__version__,
        "cuda_build": torch.version.cuda,
        "cuda_available": bool(torch.cuda.is_available()),
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "threads": torch.get_num_threads(),
    }
    if info["cuda_available"]:
        props = torch.cuda.get_device_properties(0)
        info["gpu"] = props.name
        info["gpu_memory_gb"] = round(props.total_memory / 1e9, 1)
        info["compute_capability"] = f"{props.major}.{props.minor}"
    return info


def _onnx_info() -> dict:
    try:
        import onnxruntime
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "providers": [], "error": f"{exc.__class__.__name__}: {exc}"}
    providers = list(onnxruntime.get_available_providers())
    return {
        "installed": True,
        "version": onnxruntime.__version__,
        "providers": providers,
        "has_cuda": "CUDAExecutionProvider" in providers or "TensorrtExecutionProvider" in providers,
        "has_dml": "DmlExecutionProvider" in providers,
        "has_openvino": "OpenVINOExecutionProvider" in providers,
    }


def probe(refresh: bool = False) -> dict:
    """探测本机算力（进程内缓存，`refresh=True` 重新探测）。"""
    global _probe
    if _probe is not None and not refresh:
        return _probe
    with _lock:
        if _probe is not None and not refresh:
            return _probe
        torch_info = _torch_info()
        onnx_info = _onnx_info()
        cores = os.cpu_count() or 1
        _probe = {
            "platform": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "cpu_cores": cores,
            "torch": torch_info,
            "onnxruntime": onnx_info,
            "preference": os.getenv("HYDROCS_SEG_BACKEND", "auto").strip().lower() or "auto",
        }
    return _probe


def candidates(info: dict | None = None) -> list[Backend]:
    """按优先级给出所有后端的可用性（不可用的也列出，附原因）。"""
    info = info or probe()
    torch_info = info["torch"]
    onnx_info = info["onnxruntime"]
    gpu_name = torch_info.get("gpu") or "GPU"

    out: list[Backend] = []

    cuda_ok = bool(torch_info.get("cuda_available"))
    out.append(
        Backend(
            key="cuda",
            available=cuda_ok,
            device="cuda:0" if cuda_ok else "cpu",
            fp16=cuda_ok,
            reason=None
            if cuda_ok
            else (
                "torch 是 CPU 版（torch.version.cuda=None）"
                if torch_info.get("installed") and not torch_info.get("cuda_build")
                else "未检测到可用 CUDA 设备"
            ),
            detail={"gpu": gpu_name} if cuda_ok else {},
        )
    )

    out.append(
        Backend(
            key="onnx-cuda",
            available=bool(onnx_info.get("has_cuda")),
            device="cuda:0",
            provider="CUDAExecutionProvider",
            reason=None if onnx_info.get("has_cuda") else "onnxruntime 未提供 CUDAExecutionProvider",
        )
    )

    out.append(
        Backend(
            key="onnx-dml",
            available=bool(onnx_info.get("has_dml")),
            device="dml",
            provider="DmlExecutionProvider",
            reason=None
            if onnx_info.get("has_dml")
            else "未安装 onnxruntime-directml（Windows 可用任意 DX12 显卡）",
        )
    )

    out.append(
        Backend(
            key="torch-cpu",
            available=bool(torch_info.get("installed")),
            device="cpu",
            reason=None if torch_info.get("installed") else "torch 未安装",
            detail={"threads": torch_info.get("threads")},
        )
    )

    out.append(
        Backend(
            key="onnx-cpu",
            available=bool(onnx_info.get("installed")),
            device="cpu",
            provider="CPUExecutionProvider",
            reason=None if onnx_info.get("installed") else "onnxruntime 未安装",
        )
    )
    return out


def choose(info: dict | None = None, weights_present: bool = True) -> Backend:
    """按偏好挑一个后端；全部不可用时返回 heuristic。"""
    info = info or probe()
    if not weights_present:
        return Backend(key="heuristic", available=True, reason="未找到权重文件")

    preference = info.get("preference", "auto")
    table = {backend.key: backend for backend in candidates(info)}

    if preference not in {"auto", ""}:
        backend = table.get(preference)
        if backend and backend.available:
            return backend
        reason = backend.reason if backend else f"未知后端 {preference}"
        log.warning("指定的识别后端 %s 不可用（%s），回退自动选择", preference, reason)
        return choose({**info, "preference": "auto"}, weights_present=weights_present)

    for key in AUTO_ORDER:
        backend = table.get(key)
        if backend and backend.available:
            return backend
    return Backend(key="heuristic", available=True, reason="没有可用的模型后端")


def summary() -> dict:
    """给 /segment/status 与 /healthz 用的可读摘要。"""
    info = probe()
    chosen = choose(info)
    return {
        "chosen": chosen.to_dict(),
        "order": list(AUTO_ORDER),
        "preference": info["preference"],
        "options": [backend.to_dict() | {"available": backend.available} for backend in candidates(info)],
        "cpu_cores": info["cpu_cores"],
        "torch": {
            "version": info["torch"].get("version"),
            "cuda_build": info["torch"].get("cuda_build"),
            "cuda_available": info["torch"].get("cuda_available"),
            "gpu": info["torch"].get("gpu"),
            "gpu_memory_gb": info["torch"].get("gpu_memory_gb"),
        },
        "onnxruntime": {
            "version": info["onnxruntime"].get("version"),
            "providers": info["onnxruntime"].get("providers", []),
        },
    }


def reset() -> None:
    global _probe
    with _lock:
        _probe = None


def configure_threads() -> dict:
    """收敛底层线程数：多请求并发时，每个请求各自开满线程只会互相踩踏。

    * OpenCV：默认按核数开线程，4 路并发就是 64 个线程在抢同样几个核 → 设为 1，
      并行度交给请求级并发控制。
    * PyTorch CPU：同理，按 `HYDROCS_SEG_TORCH_THREADS`（默认 min(8, 核数)）收敛。
    CUDA 路径不受影响。
    """
    result: dict = {}
    try:
        import cv2

        cv2.setNumThreads(max(1, settings_cv_threads()))
        result["opencv_threads"] = cv2.getNumThreads()
    except Exception as exc:  # noqa: BLE001
        result["opencv_threads"] = f"error: {exc}"
    try:
        import torch

        # 注意：即使推理在 GPU 上，NMS / 掩膜重建仍在 CPU torch 里跑，
        # 并发请求会各自开满线程（默认 = 核数），所以这里统一收敛。
        threads = settings_torch_threads()
        torch.set_num_threads(threads)
        result["torch_threads"] = torch.get_num_threads()
        result["cuda"] = bool(torch.cuda.is_available())
    except Exception as exc:  # noqa: BLE001
        result["torch_threads"] = f"error: {exc}"
    log.info("thread tuning: %s", result)
    return result


def settings_cv_threads() -> int:
    from ..config import settings

    return int(getattr(settings, "seg_cv_threads", 1) or 1)


def settings_torch_threads() -> int:
    from ..config import settings

    configured = int(getattr(settings, "seg_torch_threads", 0) or 0)
    if configured > 0:
        return configured
    return max(1, min(8, (os.cpu_count() or 2) // 2))
