"""Image proxy, provider catalogue and place search."""

from __future__ import annotations

from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query, Response

from ..config import settings
from ..services import geo, imagery

router = APIRouter(prefix="/imagery", tags=["imagery"])


@router.get("/providers")
def providers() -> list[dict[str, Any]]:
    return imagery.provider_catalog()


@router.get("/warm")
def warm(
    lat: float,
    lon: float,
    zoom: int = Query(default=16, ge=3, le=19),
    radius: int = Query(default=2, ge=0, le=4),
    provider: str = "esri",
) -> dict[str, Any]:
    """Pre-fetch tiles around a point so the map paints immediately after a jump.

    Without this, flying to a new area means the browser waits on 30-60 cold
    upstream requests, which reads as "the satellite image disappeared".
    """
    try:
        return imagery.warm_cache(lon, lat, zoom, radius=radius, provider=provider)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/tiles/{provider}/{z}/{x}/{y}")
def tile(provider: str, z: int, x: int, y: int) -> Response:
    try:
        payload = imagery.fetch_tile(provider, z, x, y)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if payload is None:
        raise HTTPException(502, "影像瓦片获取失败，请稍后重试")
    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/staticmap")
def staticmap(
    bbox: str = Query(..., description="minx,miny,maxx,maxy"),
    zoom: int | None = None,
    provider: str = "esri",
    size: int = Query(1024, ge=256, le=2048),
) -> Response:
    try:
        values = tuple(float(v) for v in bbox.split(","))
        if len(values) != 4:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "bbox 格式应为 minx,miny,maxx,maxy") from exc
    try:
        mosaic = imagery.build_mosaic(values, zoom=zoom, provider=provider, target_px=size)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(content=imagery.mosaic_png(mosaic), media_type="image/jpeg")


@router.get("/locate")
def locate(lat: float, lon: float) -> dict[str, Any]:
    """Report which providers cover a point and the local ground resolution."""
    out = []
    for provider in imagery.provider_catalog():
        if not provider["enabled"]:
            continue
        out.append(
            {
                "provider": provider["key"],
                "label": provider["label"],
                "max_zoom": provider["max_zoom"],
                "mpp_at_max_zoom": round(geo.meters_per_pixel(lat, provider["max_zoom"]), 3),
            }
        )
    return {"lat": lat, "lon": lon, "providers": out}


# --- place search ---------------------------------------------------------

_FALLBACK_PLACES = [
    {"name": "山东省东营市垦利区黄河口镇", "lon": 118.8000, "lat": 37.8000, "level": "乡镇"},
    {"name": "山东省东营市", "lon": 118.4965, "lat": 37.4341, "level": "地级市"},
    {"name": "山东省潍坊市", "lon": 119.1618, "lat": 36.7069, "level": "地级市"},
    {"name": "山东省济南市", "lon": 117.1201, "lat": 36.6512, "level": "地级市"},
    {"name": "山东省德州市平原县", "lon": 116.4341, "lat": 37.1653, "level": "县"},
    {"name": "江苏省徐州市", "lon": 117.1848, "lat": 34.2618, "level": "地级市"},
    {"name": "江苏省盐城市射阳县", "lon": 120.2539, "lat": 33.7750, "level": "县"},
    {"name": "河南省商丘市", "lon": 115.6505, "lat": 34.4145, "level": "地级市"},
    {"name": "河北省衡水市", "lon": 115.6707, "lat": 37.7392, "level": "地级市"},
    {"name": "安徽省宿州市", "lon": 116.9642, "lat": 33.6461, "level": "地级市"},
]


def _amap_search(keyword: str, limit: int = 8) -> list[dict[str, Any]]:
    key = settings.amap_key
    if not key:
        return []
    try:
        resp = requests.get(
            "https://restapi.amap.com/v3/place/text",
            params={
                "key": key,
                "keywords": keyword,
                "types": "190100|190101|190102|190103",
                "offset": limit,
                "page": 1,
                "extensions": "base",
            },
            timeout=8,
        )
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return []
    if str(payload.get("status")) != "1":
        return []
    results = []
    for poi in payload.get("pois", [])[:limit]:
        location = poi.get("location") or ""
        if "," not in location:
            continue
        lon_str, lat_str = location.split(",")[:2]
        try:
            lon, lat = float(lon_str), float(lat_str)
        except ValueError:
            continue
        # Amap returns GCJ-02; convert so the map and the geometry agree.
        lon, lat = geo.gcj02_to_wgs84(lon, lat)
        results.append(
            {
                "name": poi.get("name"),
                "address": "".join(poi.get("pname") or "") + (poi.get("cityname") or "") + (poi.get("adname") or ""),
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "level": "POI",
                "source": "amap",
            }
        )
    return results


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=40)) -> dict[str, Any]:
    keyword = q.strip()
    exact = [p for p in _FALLBACK_PLACES if keyword in p["name"]]
    remote = _amap_search(keyword)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in remote + exact:
        key = f"{round(item['lon'], 3)},{round(item['lat'], 3)}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= 8:
            break
    source = "amap" if remote else ("builtin" if exact else "none")
    if not merged and keyword:
        # nearest built-in name for a helpful miss
        best = min(
            _FALLBACK_PLACES,
            key=lambda p: abs(len(p["name"]) - len(keyword)),
        )
        merged = [{**best, "source": "builtin-suggest"}]
        source = "builtin-suggest"
    return {"query": keyword, "source": source, "results": merged}
