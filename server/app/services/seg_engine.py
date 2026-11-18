"""识别推理引擎：同一套接口，后端可选 CUDA / ONNX(CUDA|DML|CPU) / torch CPU。

两条实现：

* :class:`UltralyticsEngine` —— 直接让 ultralytics 跑 `.pt`（CUDA 或 CPU）。
* :class:`OnnxEngine` —— 自己开 ONNX Runtime 会话跑 `.onnx`，可指定
  CUDA / DirectML / CPU execution provider。前处理（letterbox）与后处理
  （NMS + 掩膜重建）复用 ultralytics 的实现，保证与 torch 路径**同参同果**。

两者都返回 `(masks, scores)`：`masks` 形如 `(n, h, w)` 的 float32（0/1），
`h, w` 就是传入的裁剪图尺寸，调用方无需再做缩放。
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import numpy as np

from ..config import settings
from . import compute

log = logging.getLogger(__name__)

_lock = threading.Lock()
_engine: "BaseEngine | None" = None
_engine_error: str | None = None


def onnx_path() -> Path:
    """ONNX 权重路径（默认与 .pt 同级同名）。"""
    configured = getattr(settings, "yolo_onnx", None)
    if configured:
        return Path(configured)
    return Path(settings.yolo_weights).with_suffix(".onnx")


def _unpad_masks(masks: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """把 letterbox 掩膜裁掉填充边再缩回原图尺寸。

    ultralytics 在 `.pt` 路径上按 stride 对齐成矩形输入（例如 777×555 的裁剪图会变成
    1024×736），掩膜也停在这个带填充的尺寸上。直接 `cv2.resize` 会把填充当成图像内容，
    所以先按比例裁掉右侧/底部的 pad，再缩放到真实尺寸。
    """
    import cv2

    height, width = shape
    if masks.size == 0:
        return np.zeros((0, height, width), np.float32)
    _, ph, pw = masks.shape
    ratio = min(ph / height, pw / width)
    valid_h = int(round(height * ratio))
    valid_w = int(round(width * ratio))
    if (valid_h, valid_w) == (ph, pw) == (height, width):
        return masks
    # auto=False 的方图 letterbox 是居中填充，auto=True 的矩形 letterbox 只补右下，
    # 居中裁剪对两者都成立
    top = max(0, (ph - valid_h) // 2)
    left = max(0, (pw - valid_w) // 2)
    cropped = masks[:, top:top + valid_h, left:left + valid_w]
    if (valid_h, valid_w) == (height, width):
        return cropped
    return np.stack(
        [cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST) for mask in cropped]
    )


class BaseEngine:
    key: str = "base"
    device: str = "cpu"
    provider: str | None = None

    def predict(
        self, crop: np.ndarray, conf: float, iou: float | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """返回 ``(masks, scores, boxes)``：掩膜 ``(n,h,w)`` float32、置信度 ``(n,)``、框 ``(n,4)`` xyxy。"""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"engine": self.key, "device": self.device, "provider": self.provider}


class UltralyticsEngine(BaseEngine):
    """`.pt` → ultralytics（CUDA 或 CPU）。"""

    def __init__(self, backend: compute.Backend) -> None:
        from ultralytics import YOLO

        self.backend = backend
        self.key = backend.key
        self.device = "cuda:0" if backend.key == "cuda" else "cpu"
        self.provider = None
        self.model = YOLO(str(settings.yolo_weights))
        # 新版 ultralytics 用 quantize 表达半精度，旧版用 half（8.4 起 half 会告警）
        from ultralytics.cfg import DEFAULT_CFG_DICT

        self._precision_arg = "quantize" if "quantize" in DEFAULT_CFG_DICT else "half"
        log.info("engine ready: %s (%s)", self.key, self.device)

    def predict(
        self, crop: np.ndarray, conf: float, iou: float | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        extra: dict = {}
        if self.backend.fp16:
            extra[self._precision_arg] = "fp16" if self._precision_arg == "quantize" else True
        result = self.model.predict(
            crop,
            imgsz=settings.yolo_imgsz,
            conf=conf,
            iou=settings.yolo_iou if iou is None else iou,
            device=self.device,
            verbose=False,
            **extra,
        )[0]
        height, width = crop.shape[:2]
        if result.masks is None or result.boxes is None:
            return (
                np.zeros((0, height, width), np.float32),
                np.zeros((0,), np.float32),
                np.zeros((0, 4), np.float32),
            )
        masks = result.masks.data.cpu().numpy().astype(np.float32)
        masks = _unpad_masks(masks, (height, width))
        scores = result.boxes.conf.cpu().numpy().astype(np.float32)
        boxes = result.boxes.xyxy.cpu().numpy().astype(np.float32)
        return masks, scores, boxes

    def describe(self) -> dict:
        return {"engine": self.key, "device": self.device, "provider": self.provider, "weights": str(settings.yolo_weights)}


class OnnxEngine(BaseEngine):
    """`.onnx` → ONNX Runtime，自带 letterbox 前处理与 NMS/掩膜后处理。"""

    def __init__(self, backend: compute.Backend, path: Path) -> None:
        import onnxruntime

        self.backend = backend
        self.key = backend.key
        self.device = backend.device
        self.provider = backend.provider
        self.path = path

        options = onnxruntime.SessionOptions()
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        threads = int(getattr(settings, "seg_ort_threads", 0) or 0)
        if threads > 0 and backend.device == "cpu":
            options.intra_op_num_threads = threads
            options.inter_op_num_threads = 1
        providers = [backend.provider] if backend.provider else None
        if providers:
            providers = [*providers, "CPUExecutionProvider"]
        self.session = onnxruntime.InferenceSession(str(path), options, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [out.name for out in self.session.get_outputs()]
        log.info(
            "engine ready: %s via %s (%s)",
            self.key,
            self.session.get_providers()[0],
            path.name,
        )

    # --- 前处理 ---------------------------------------------------------
    def _preprocess(self, crop: np.ndarray) -> np.ndarray:
        from ultralytics.data.augment import LetterBox

        size = settings.yolo_imgsz
        letterbox = LetterBox((size, size), auto=False)
        padded = letterbox(image=crop)
        blob = padded[:, :, ::-1].transpose(2, 0, 1)[None]
        return np.ascontiguousarray(blob, dtype=np.float32) / 255.0

    # --- 后处理 ---------------------------------------------------------
    def _postprocess(
        self,
        outputs: list[np.ndarray],
        shape: tuple[int, int],
        conf: float,
        iou: float | None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        import torch
        from ultralytics.utils import ops
        from ultralytics.utils.nms import non_max_suppression

        height, width = shape
        size = settings.yolo_imgsz
        raw = torch.from_numpy(outputs[0])
        protos = torch.from_numpy(outputs[1][0]) if len(outputs) > 1 else None
        threshold = settings.yolo_iou if iou is None else iou
        detections = non_max_suppression(raw, conf, threshold, nc=1, max_det=300)
        if not detections or detections[0] is None or len(detections[0]) == 0:
            return (
                np.zeros((0, height, width), np.float32),
                np.zeros((0,), np.float32),
                np.zeros((0, 4), np.float32),
            )
        det = detections[0]
        boxes = det[:, :4]
        scores = det[:, 4]
        if protos is not None and det.shape[1] > 6:
            # 与 ultralytics 一致：掩膜先按 letterbox 尺寸重建，再裁掉填充回到原图
            masks = ops.process_mask(protos, det[:, 6:], boxes, (size, size), upsample=True)
            masks_np = _unpad_masks(masks.cpu().numpy().astype(np.float32), (height, width))
        else:  # 没有掩膜分支时退化成整框掩膜
            masks_np = np.zeros((len(det), height, width), np.float32)
            scaled = ops.scale_boxes((size, size), boxes.clone(), (height, width))
            for index, box in enumerate(scaled.cpu().numpy()):
                x0, y0, x1, y1 = (int(max(0, box[0])), int(max(0, box[1])),
                                  int(min(width, box[2])), int(min(height, box[3])))
                masks_np[index, y0:y1, x0:x1] = 1.0
        boxes_orig = ops.scale_boxes((size, size), boxes.clone(), (height, width))
        return (
            masks_np,
            scores.cpu().numpy().astype(np.float32),
            boxes_orig.cpu().numpy().astype(np.float32),
        )

    def predict(
        self, crop: np.ndarray, conf: float, iou: float | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        blob = self._preprocess(crop)
        outputs = self.session.run(self.output_names, {self.input_name: blob})
        return self._postprocess(outputs, crop.shape[:2], conf, iou)

    def describe(self) -> dict:
        return {
            "engine": self.key,
            "device": self.device,
            "provider": self.session.get_providers()[0],
            "weights": str(self.path),
        }


def _build(backend: compute.Backend) -> BaseEngine:
    if backend.key == "heuristic":
        raise RuntimeError("heuristic 后端不通过引擎调用")
    if backend.key in {"onnx-cuda", "onnx-dml", "onnx-cpu"}:
        path = onnx_path()
        if not path.is_file():
            raise FileNotFoundError(f"缺少 ONNX 权重：{path}（运行 scripts/export_onnx.py）")
        return OnnxEngine(backend, path)
    return UltralyticsEngine(backend)


def get() -> BaseEngine | None:
    """进程内单例；失败时返回 None 并记录原因（调用方回退规则识别）。"""
    global _engine, _engine_error
    if _engine is not None or _engine_error is not None:
        return _engine
    with _lock:
        if _engine is not None or _engine_error is not None:
            return _engine
        backend = compute.choose(weights_present=settings.has_yolo_weights)
        try:
            _engine = _build(backend)
        except Exception as exc:  # noqa: BLE001
            _engine_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("识别引擎不可用（%s）：%s", backend.key, _engine_error)
    return _engine


def reset() -> None:
    global _engine, _engine_error
    with _lock:
        _engine = None
        _engine_error = None


def status() -> dict:
    engine = get()
    info = compute.summary()
    if engine is None:
        return {**info, "ready": False, "error": _engine_error}
    return {**info, "ready": True, "error": None, "engine": engine.describe()}


def ensure_onnx(imgsz: int | None = None, force: bool = False) -> Path:
    """导出 ONNX（幂等）。给 scripts/export_onnx.py 与管理端预热用。"""
    target = onnx_path()
    if target.is_file() and not force:
        return target
    from ultralytics import YOLO

    model = YOLO(str(settings.yolo_weights))
    exported = model.export(
        format="onnx",
        imgsz=imgsz or settings.yolo_imgsz,
        opset=17,
        simplify=True,
        dynamic=False,
    )
    produced = Path(exported)
    if produced.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(produced, target)
    return target


__all__ = ["BaseEngine", "OnnxEngine", "UltralyticsEngine", "ensure_onnx", "get", "onnx_path", "reset", "status"]
