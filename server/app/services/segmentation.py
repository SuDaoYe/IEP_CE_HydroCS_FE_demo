"""Farmland segmentation: YOLO11s-seg with a classical-CV fallback.

The trained model is a single-class (``farmland``) instance segmentation net.
Large requests are processed in overlapping windows so the effective ground
resolution stays high. Masks are painted into a shared label image in
confidence order — first writer wins — which stops neighbouring instances from
double-counting the pixels on a shared boundary. Labels are then vectorised,
simplified and de-duplicated across window seams.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import settings
from . import compute, geo, seg_engine
from .imagery import Mosaic

log = logging.getLogger(__name__)

#: 设 HYDROCS_SEG_PROFILE=1 时打印各阶段耗时（排查并发退化用）
_PROFILE = os.getenv("HYDROCS_SEG_PROFILE", "").lower() in {"1", "true", "yes"}

#: 进程内推理闸门：CPU 上并发推理只会互相抢核，GPU 上过多并发会把显存/带宽打满
_infer_lock = threading.Lock()
_infer_gate: threading.BoundedSemaphore | None = None
_infer_gate_size = 0


def _gate() -> threading.BoundedSemaphore:
    """限制并发推理数（进程内）。

    实测：ultralytics 的 `predict` 在多线程下会互相拖慢（同一 predictor 内部状态 +
    CUDA 同步），4 路并发的 p50 反而比串行慢 8 倍。所以默认**串行推理**，
    横向扩展靠多进程（`uvicorn --workers N`），每个进程独占一份模型。
    """
    global _infer_gate, _infer_gate_size
    configured = int(getattr(settings, "seg_max_concurrency", 0) or 0)
    with _infer_lock:
        if _infer_gate is None:
            size = max(1, configured) if configured else 1
            _infer_gate = threading.BoundedSemaphore(size)
            _infer_gate_size = size
            log.info("segment inference gate: %s concurrent", size)
        return _infer_gate


def backend_status() -> dict:
    engine = seg_engine.get()
    status = seg_engine.status()
    gate_size = _gate()._initial_value if engine is not None else 0
    return {
        "backend": f"yolo11s-seg · {engine.key}" if engine is not None else "heuristic",
        "weights": str(settings.yolo_weights),
        "weights_present": settings.has_yolo_weights,
        "error": status["error"],
        "engine": engine.describe() if engine is not None else None,
        "device": engine.device if engine is not None else "cpu",
        "concurrency": gate_size,
        "options": status["options"],
    }


@dataclass(slots=True)
class Candidate:
    ring: geo.Ring
    area_m2: float
    confidence: float
    source: str

    def to_feature(self, datum: str = "wgs84") -> dict:
        ring = geo.transform_ring(self.ring, datum)
        return geo.polygon_feature(
            ring,
            {
                "area_m2": round(self.area_m2, 2),
                "area_mu": round(self.area_m2 * geo.MU_PER_M2, 3),
                "area_ha": round(self.area_m2 / 10_000.0, 4),
                "confidence": round(self.confidence, 3),
                "source": self.source,
            },
        )


# --- mask -> polygon ------------------------------------------------------


def _mask_to_candidates(
    mask: np.ndarray,
    mosaic: Mosaic,
    offset: tuple[int, int],
    min_area_m2: float,
    confidence: float,
    source: str,
) -> list[Candidate]:
    mask_u8 = np.ascontiguousarray(mask.astype(np.uint8) * 255)
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ox, oy = offset
    out: list[Candidate] = []
    for contour in contours:
        if cv2.contourArea(contour) < 60:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.008 * perimeter, True)
        if len(approx) < 3:
            continue
        ring = geo.normalize_ring(
            [
                mosaic.pixel_to_lonlat(float(px) + ox, float(py) + oy)
                for px, py in approx.reshape(-1, 2)
            ]
        )
        if len(ring) < 3:
            continue
        area = geo.geodesic_area_m2(ring)
        if area < min_area_m2:
            continue
        out.append(Candidate(ring=ring, area_m2=area, confidence=confidence, source=source))
    return out


def _bbox_of(ring: geo.Ring) -> tuple[float, float, float, float]:
    return geo.bbox_of_points(ring)


def _bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _raster_iou(a: geo.Ring, b: geo.Ring, size: int = 96) -> float:
    """IoU of two rings rasterised into a shared local frame."""
    box_a, box_b = _bbox_of(a), _bbox_of(b)
    min_lon, min_lat = min(box_a[0], box_b[0]), min(box_a[1], box_b[1])
    max_lon, max_lat = max(box_a[2], box_b[2]), max(box_a[3], box_b[3])
    span_lon = max(max_lon - min_lon, 1e-9)
    span_lat = max(max_lat - min_lat, 1e-9)

    def raster(ring: geo.Ring) -> np.ndarray:
        canvas = np.zeros((size, size), np.uint8)
        pts = np.array(
            [
                [int((lon - min_lon) / span_lon * (size - 1)),
                 int((lat - min_lat) / span_lat * (size - 1))]
                for lon, lat in ring
            ],
            dtype=np.int32,
        )
        cv2.fillPoly(canvas, [pts], 1)
        return canvas

    ra, rb = raster(a), raster(b)
    union = int(np.logical_or(ra, rb).sum())
    return int(np.logical_and(ra, rb).sum()) / union if union else 0.0


def _dedupe(candidates: list[Candidate], iou_threshold: float = 0.30) -> list[Candidate]:
    """Merge parcels detected twice at a window seam."""
    if len(candidates) <= 1:
        return candidates
    ordered = sorted(candidates, key=lambda c: (-c.area_m2, -c.confidence))
    boxes = [_bbox_of(c.ring) for c in ordered]
    kept: list[int] = []
    for index, cand in enumerate(ordered):
        duplicate = False
        for other_index in kept:
            other = ordered[other_index]
            smaller = min(cand.area_m2, other.area_m2)
            larger = max(cand.area_m2, other.area_m2)
            if larger > smaller * 1.6:
                continue  # different objects, not a seam duplicate
            if _bbox_iou(boxes[index], boxes[other_index]) < 0.20:
                continue
            if _raster_iou(cand.ring, other.ring) >= iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(index)
    return [ordered[i] for i in kept]


# --- inference paths ------------------------------------------------------


def _windows(width: int, height: int, window: int, overlap: int) -> list[tuple[int, int, int, int]]:
    if width <= window and height <= window:
        return [(0, 0, width, height)]
    stride = max(64, window - overlap)
    xs = list(range(0, max(1, width - window + 1), stride))
    ys = list(range(0, max(1, height - window + 1), stride))
    if xs[-1] + window < width:
        xs.append(max(0, width - window))
    if ys[-1] + window < height:
        ys.append(max(0, height - window))
    return [(x, y, min(window, width - x), min(window, height - y)) for y in ys for x in xs]


def _run_model(mosaic: Mosaic, min_area_m2: float, conf: float) -> list[Candidate]:
    engine = seg_engine.get()
    if engine is None:
        raise RuntimeError(seg_engine.status().get("error") or "识别引擎不可用")

    height, width = mosaic.height, mosaic.width
    labels = np.zeros((height, width), np.int32)
    scores: dict[int, float] = {}
    # 每个实例只记「标签 → 在 mosaic 坐标系里的外接框」，矢量化时按框裁切，
    # 避免对整幅图逐标签做 astype / findContours（旧实现的主要耗时点）。
    boxes_by_label: dict[int, tuple[int, int, int, int]] = {}
    next_label = 1
    infer_ms = paint_ms = 0.0

    for x, y, w, h in _windows(width, height, settings.yolo_window, settings.yolo_overlap):
        crop = mosaic.image[y:y + h, x:x + w]
        if crop.size == 0:
            continue
        started = time.perf_counter()
        masks, box_scores, boxes = engine.predict(crop, conf=conf)
        infer_ms += (time.perf_counter() - started) * 1000
        if masks.shape[0] == 0:
            continue
        started = time.perf_counter()
        order = np.argsort(-box_scores) if box_scores.size else np.arange(len(masks))
        for index in order:
            mask = masks[index]
            if mask.shape[:2] != (h, w):
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            box = boxes[index] if boxes.shape[0] > index else np.array([0, 0, w, h])
            x0, y0 = int(max(0, np.floor(box[0]))), int(max(0, np.floor(box[1])))
            x1, y1 = int(min(w, np.ceil(box[2]))), int(min(h, np.ceil(box[3])))
            if x1 - x0 < 2 or y1 - y0 < 2:
                x0, y0, x1, y1 = 0, 0, w, h
            binary = mask[y0:y1, x0:x1] > 0.5
            region = labels[y + y0:y + y1, x + x0:x + x1]
            free = binary & (region == 0)
            if np.count_nonzero(free) < 40:
                continue
            region[free] = next_label
            scores[next_label] = float(box_scores[index]) if index < box_scores.size else conf
            boxes_by_label[next_label] = (x + x0, y + y0, x1 - x0, y1 - y0)
            next_label += 1
        paint_ms += (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    candidates: list[Candidate] = []
    for label, score in scores.items():
        ox, oy, bw, bh = boxes_by_label[label]
        sub = labels[oy:oy + bh, ox:ox + bw] == label
        if np.count_nonzero(sub) < 40:
            continue
        candidates.extend(
            _mask_to_candidates(sub, mosaic, (ox, oy), min_area_m2, score, "yolo11s-seg")
        )
    if _PROFILE:
        log.info(
            "profile[%s]: %d windows · infer %.0f ms · paint %.0f ms · vectorize %.0f ms",
            threading.current_thread().name,
            len(_windows(width, height, settings.yolo_window, settings.yolo_overlap)),
            infer_ms,
            paint_ms,
            (time.perf_counter() - started) * 1000,
        )
    return candidates


def _run_heuristic(mosaic: Mosaic, min_area_m2: float) -> list[Candidate]:
    """Edge/texture-based parcel detection for deployments without weights."""
    image = mosaic.image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    grad = cv2.GaussianBlur(grad, (9, 9), 0)
    grad_norm = grad / (np.percentile(grad, 95) + 1e-6)
    smooth = np.clip(1.0 - grad_norm, 0.0, 1.0)

    # Local colour variance separates fields (uniform) from orchards/buildings.
    mean = cv2.blur(gray, (15, 15))
    sq_mean = cv2.blur(gray * gray, (15, 15))
    std = np.sqrt(np.maximum(sq_mean - mean * mean, 0))
    uniform = np.clip(1.0 - std / 22.0, 0.0, 1.0)

    score = 0.55 * smooth + 0.45 * uniform
    mask = (score > 0.55).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    total_px = mask.size
    candidates: list[Candidate] = []
    for label in range(1, count):
        x, y, w, h, area_px = stats[label]
        if area_px < 1500 or area_px > total_px * 0.45:
            continue
        component = (labels == label).astype(np.uint8)
        candidates.extend(
            _mask_to_candidates(component, mosaic, (0, 0), min_area_m2, 0.35, "heuristic")
        )
    return candidates


def reset() -> None:
    """测试用：丢掉已加载的引擎。"""
    seg_engine.reset()


def warmup() -> dict:
    """加载引擎并跑一次最小推理，把模型/上下文初始化成本挪到启动阶段。"""
    import numpy as _np

    engine = seg_engine.get()
    if engine is None:
        return {"ok": False, "error": seg_engine.status().get("error")}
    started = time.perf_counter()
    dummy = _np.zeros((512, 512, 3), _np.uint8)
    engine.predict(dummy, conf=0.9)
    return {
        "ok": True,
        "backend": engine.key,
        "device": engine.device,
        "ms": round((time.perf_counter() - started) * 1000, 1),
    }


def status() -> dict:
    """给管理端/健康检查用的完整状态。"""
    from . import imagery as _imagery

    return {
        **backend_status(),
        "options": seg_engine.status()["options"],
        "mosaic_cache": _imagery.mosaic_cache_info(),
    }


def segment(
    mosaic: Mosaic,
    min_area_ha: float | None = None,
    conf: float | None = None,
    allow_heuristic: bool = True,
) -> dict:
    """Run segmentation over a mosaic and return a serialisable result."""
    min_area_m2 = (min_area_ha if min_area_ha is not None else settings.segment_min_area_ha) * 10_000
    conf = conf if conf is not None else settings.yolo_conf

    engine = seg_engine.get()
    used = f"yolo11s-seg · {engine.key}" if engine is not None else "yolo11s-seg"
    error: str | None = None
    candidates: list[Candidate] = []
    try:
        candidates = _run_model(mosaic, min_area_m2, conf)
    except Exception as exc:  # noqa: BLE001
        error = f"{exc.__class__.__name__}: {exc}"
        log.warning("model inference failed: %s", error)
        if not allow_heuristic:
            raise

    # 规则兜底与去重也放进闸门：它们同样是 GIL 密集的 numpy/Python 工作，
    # 多线程并行只会把彼此拖慢（实测 4 路并发的 p50 是串行的 5-8 倍）。
    with _gate():
        if not candidates and allow_heuristic:
            used = "heuristic"
            candidates = _run_heuristic(mosaic, min_area_m2)
        candidates = _dedupe(candidates)
    candidates.sort(key=lambda c: c.area_m2, reverse=True)
    total_area = sum(c.area_m2 for c in candidates)
    mosaic_area = geo.geodesic_area_m2(
        [
            (mosaic.west, mosaic.south),
            (mosaic.east, mosaic.south),
            (mosaic.east, mosaic.north),
            (mosaic.west, mosaic.north),
        ]
    )

    return {
        "backend": used,
        "error": error,
        "zoom": mosaic.zoom,
        "provider": mosaic.provider,
        "bbox": list(mosaic.bbox()),
        "image": {
            "width": mosaic.width,
            "height": mosaic.height,
            "mpp_x": round(mosaic.mpp_x, 3),
            "mpp_y": round(mosaic.mpp_y, 3),
        },
        "count": len(candidates),
        "total_area_ha": round(total_area / 10_000, 3),
        "coverage_pct": round(total_area / mosaic_area * 100, 1) if mosaic_area else None,
        "features": [c.to_feature() for c in candidates],
    }
