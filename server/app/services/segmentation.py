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
import threading
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import settings
from . import geo
from .imagery import Mosaic

log = logging.getLogger(__name__)

_model_lock = threading.Lock()
_model = None
_model_error: str | None = None


def _get_model():
    """Lazy-load the YOLO weights once per process."""
    global _model, _model_error
    if _model is not None or _model_error is not None:
        return _model
    with _model_lock:
        if _model is not None or _model_error is not None:
            return _model
        if not settings.has_yolo_weights:
            _model_error = f"weights not found: {settings.yolo_weights}"
            return None
        try:
            from ultralytics import YOLO

            _model = YOLO(str(settings.yolo_weights))
            log.info("loaded YOLO weights %s (task=%s)", settings.yolo_weights.name, _model.task)
        except Exception as exc:  # pragma: no cover - environment dependent
            _model_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("YOLO unavailable, falling back to heuristic: %s", _model_error)
        return _model


def backend_status() -> dict:
    model = _get_model()
    return {
        "backend": "yolo11s-seg" if model is not None else "heuristic",
        "weights": str(settings.yolo_weights),
        "weights_present": settings.has_yolo_weights,
        "error": _model_error,
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


def _run_yolo(mosaic: Mosaic, min_area_m2: float, conf: float) -> list[Candidate]:
    model = _get_model()
    if model is None:
        raise RuntimeError(_model_error or "model unavailable")

    height, width = mosaic.height, mosaic.width
    labels = np.zeros((height, width), np.int32)
    scores: dict[int, float] = {}
    next_label = 1

    for x, y, w, h in _windows(width, height, settings.yolo_window, settings.yolo_overlap):
        crop = mosaic.image[y:y + h, x:x + w]
        if crop.size == 0:
            continue
        result = model.predict(
            crop,
            imgsz=settings.yolo_imgsz,
            conf=conf,
            iou=settings.yolo_iou,
            verbose=False,
        )[0]
        if result.masks is None:
            continue
        masks = result.masks.data.cpu().numpy()
        box_scores = result.boxes.conf.cpu().numpy() if result.boxes is not None else None
        order = np.argsort(-box_scores) if box_scores is not None else np.arange(len(masks))
        for index in order:
            mask = masks[index]
            if mask.shape[:2] != (h, w):
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            binary = mask > 0.5
            region = labels[y:y + h, x:x + w]
            free = binary & (region == 0)
            if free.sum() < 40:
                continue
            region[free] = next_label
            scores[next_label] = (
                float(box_scores[index]) if box_scores is not None and index < len(box_scores) else conf
            )
            next_label += 1

    candidates: list[Candidate] = []
    for label, score in scores.items():
        mask = labels == label
        if mask.sum() < 40:
            continue
        candidates.extend(
            _mask_to_candidates(mask, mosaic, (0, 0), min_area_m2, score, "yolo11s-seg")
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


def segment(
    mosaic: Mosaic,
    min_area_ha: float | None = None,
    conf: float | None = None,
    allow_heuristic: bool = True,
) -> dict:
    """Run segmentation over a mosaic and return a serialisable result."""
    min_area_m2 = (min_area_ha if min_area_ha is not None else settings.segment_min_area_ha) * 10_000
    conf = conf if conf is not None else settings.yolo_conf

    used = "yolo11s-seg"
    error: str | None = None
    candidates: list[Candidate] = []
    try:
        candidates = _run_yolo(mosaic, min_area_m2, conf)
    except Exception as exc:  # noqa: BLE001
        error = f"{exc.__class__.__name__}: {exc}"
        log.warning("YOLO inference failed: %s", error)
        if not allow_heuristic:
            raise

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
