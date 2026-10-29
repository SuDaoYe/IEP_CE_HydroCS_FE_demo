"""Farmland segmentation endpoint."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import deps
from ..config import settings
from ..schemas import SegmentRequest
from ..services import geo, imagery, segmentation

router = APIRouter(tags=["segment"])

_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}


def _cache_key(payload: SegmentRequest) -> tuple:
    return (
        payload.provider,
        round(payload.bbox[0], 5),
        round(payload.bbox[1], 5),
        round(payload.bbox[2], 5),
        round(payload.bbox[3], 5),
        payload.zoom,
        payload.min_area_ha,
        payload.conf,
        payload.datum,
    )


@router.post("/segment")
def segment(payload: SegmentRequest, user: deps.CurrentUser) -> dict[str, Any]:
    key = _cache_key(payload)
    cached = _cache.get(key)
    ttl = settings.segment_cache_ttl_minutes * 60
    if cached and (time.time() - cached[0]) < ttl:
        return {**cached[1], "cached": True}

    try:
        mosaic = imagery.build_mosaic(
            payload.bbox,
            zoom=payload.zoom,
            provider=payload.provider,
            target_px=1024,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        result = segmentation.segment(
            mosaic,
            min_area_ha=payload.min_area_ha,
            conf=payload.conf,
        )
    except RuntimeError as exc:
        raise HTTPException(503, f"识别服务不可用：{exc}") from exc

    if payload.datum == "gcj02":
        for feature in result["features"]:
            ring = [(p[0], p[1]) for p in feature["geometry"]["coordinates"][0][:-1]]
            shifted = geo.transform_ring(ring, "gcj02")
            coords = [[[round(lon, 7), round(lat, 7)] for lon, lat in shifted]]
            coords[0].append(coords[0][0])
            feature["geometry"]["coordinates"] = coords

    result["bbox_requested"] = list(payload.bbox)
    result["cached"] = False
    _cache[key] = (time.time(), result)
    return result


@router.get("/segment/status")
def segment_status() -> dict[str, Any]:
    return {
        **segmentation.backend_status(),
        "imgsz": settings.yolo_imgsz,
        "window": settings.yolo_window,
        "overlap": settings.yolo_overlap,
        "min_area_ha": settings.segment_min_area_ha,
    }
