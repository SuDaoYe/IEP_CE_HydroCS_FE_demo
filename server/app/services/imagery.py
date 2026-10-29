"""Satellite imagery proxies: provider registry, disk cache, mosaic builder.

The browser never talks to a tile vendor directly: keys stay on the server,
requests are cached on disk, and datums are normalised to WGS84 so that field
geometry lines up with the pixels the segmentation model sees.
"""

from __future__ import annotations

import hashlib
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import requests

from ..config import CACHE_DIR, settings
from . import geo

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class Provider:
    key: str
    label: str
    url: Callable[[int, int, int], str]
    datum: str = "wgs84"
    max_zoom: int = 19
    min_zoom: int = 1
    subdomains: tuple[str, ...] = ()
    note: str = ""
    requires_key: bool = False
    enabled: bool = True


def _esri(z: int, x: int, y: int) -> str:
    return (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/"
        f"MapServer/tile/{z}/{y}/{x}"
    )


def _tianditu(z: int, x: int, y: int) -> str:
    return (
        "https://t{s}.tianditu.gov.cn/DataServer?T=img_w"
        f"&x={x}&y={y}&l={z}&tk={settings.tianditu_key}"
    )


def _amap(z: int, x: int, y: int) -> str:
    return (
        "https://webst0{s}.is.autonavi.com/appmaptile"
        f"?style=6&x={x}&y={y}&z={z}"
    )


def _sentinel2(z: int, x: int, y: int) -> str:
    return (
        "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/"
        f"default/g/{z}/{y}/{x}.jpg"
    )


PROVIDERS: dict[str, Provider] = {
    "esri": Provider(
        key="esri",
        label="Esri World Imagery",
        url=_esri,
        datum="wgs84",
        max_zoom=19,
        note="全球高分影像，WGS84 对齐，无需密钥；农区常见 0.4–0.8 m/px",
    ),
    "tianditu": Provider(
        key="tianditu",
        label="天地图 影像",
        url=_tianditu,
        datum="wgs84",
        max_zoom=18,
        subdomains=tuple("01234567"),
        requires_key=True,
        enabled=bool(settings.tianditu_key),
        note="国内合规影像源，需配置 TIANDITU_KEY",
    ),
    "amap": Provider(
        key="amap",
        label="高德 卫星",
        url=_amap,
        datum="gcj02",
        max_zoom=18,
        subdomains=("1", "2", "3", "4"),
        note="国内速度快，坐标系为 GCJ-02，服务端已做偏移归一",
    ),
    "sentinel2": Provider(
        key="sentinel2",
        label="Sentinel-2 云less",
        url=_sentinel2,
        datum="wgs84",
        max_zoom=15,
        note="10 m 分辨率多光谱时序，用于长势/NDVI 辅助判断",
    ),
}

DEFAULT_PROVIDER = "esri"


def warm_cache(
    lon: float,
    lat: float,
    zoom: int,
    radius: int = 2,
    provider: str = DEFAULT_PROVIDER,
) -> dict:
    """Fetch the tiles around a point (and one zoom out) in parallel.

    The caller fires this right after a map jump; the browser's own tile
    requests then hit a warm disk cache instead of a 1-2 s upstream round trip.
    """
    prov = get_provider(provider)
    levels = [min(prov.max_zoom, max(prov.min_zoom, zoom))]
    if zoom - 1 >= prov.min_zoom:
        levels.append(zoom - 1)

    targets: list[tuple[int, int, int]] = []
    for level in levels:
        cx, cy = geo.lonlat_to_tile_fraction(lon, lat, level)
        base_x, base_y = int(cx), int(cy)
        span = radius if level == levels[0] else 1
        for dy in range(-span, span + 1):
            for dx in range(-span, span + 1):
                targets.append((level, base_x + dx, base_y + dy))

    started = time.time()
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda t: fetch_tile(prov.key, *t), targets))
    ok = sum(1 for item in results if item)
    return {
        "provider": prov.key,
        "zoom": zoom,
        "tiles": len(targets),
        "fetched": ok,
        "ms": int((time.time() - started) * 1000),
    }


def get_provider(key: str) -> Provider:
    provider = PROVIDERS.get(key)
    if provider is None:
        raise KeyError(f"unknown provider: {key}")
    if not provider.enabled:
        raise KeyError(f"provider disabled (missing key): {key}")
    return provider


def provider_catalog() -> list[dict]:
    out = []
    for p in PROVIDERS.values():
        out.append(
            {
                "key": p.key,
                "label": p.label,
                "datum": p.datum,
                "min_zoom": p.min_zoom,
                "max_zoom": p.max_zoom,
                "requires_key": p.requires_key,
                "enabled": p.enabled,
                "note": p.note,
            }
        )
    return out


# --- tile cache -----------------------------------------------------------

_TILE_DIR = CACHE_DIR / "tiles"
_TILE_DIR.mkdir(parents=True, exist_ok=True)


def _tile_path(provider: str, z: int, x: int, y: int) -> Path:
    digest = hashlib.sha1(f"{provider}/{z}/{x}/{y}".encode()).hexdigest()
    sub = _TILE_DIR / provider / f"{z}" / digest[:2]
    sub.mkdir(parents=True, exist_ok=True)
    return sub / f"{digest}.img"


def _fresh(path, ttl_days: int) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) < ttl_days * 86_400
    except FileNotFoundError:
        return False


def fetch_tile(provider_key: str, z: int, x: int, y: int, _allow_fallback: bool = True) -> bytes | None:
    """Return raw tile bytes, using (and refreshing) the on-disk cache.

    Vendors answer "no imagery at this zoom" with a tiny placeholder instead of a
    404 — that is why jumping to a random location can look like a blank map. If a
    deep-zoom tile is suspiciously small we retry one zoom level out, all the way
    down to ``PLACEHOLDER_MIN_ZOOM``, so the map keeps showing *something*.
    """
    provider = get_provider(provider_key)
    clamped = max(provider.min_zoom, min(provider.max_zoom, z))
    path = _tile_path(provider.key, clamped, x, y)
    if path.exists() and _fresh(path, settings.tile_cache_ttl_days):
        payload = path.read_bytes()
        if len(payload) > settings.tile_placeholder_bytes or not _allow_fallback:
            return payload

    subdomains = provider.subdomains or ("",)
    payload: bytes | None = None
    for attempt in range(settings.tile_retries):
        sub = subdomains[attempt % len(subdomains)]
        try:
            url = provider.url(clamped, x, y).replace("{s}", sub)
            resp = requests.get(
                url,
                headers={"User-Agent": _UA, "Referer": "https://www.arcgis.com/"},
                timeout=(settings.tile_connect_timeout, settings.tile_request_timeout),
            )
            if resp.status_code == 200 and len(resp.content) > 1000:
                payload = resp.content
                break
        except requests.RequestException:
            time.sleep(0.25 * (attempt + 1))

    if payload is None:
        if path.exists():  # stale but better than nothing
            return path.read_bytes()
        return None

    is_placeholder = len(payload) < settings.tile_placeholder_bytes
    if is_placeholder and _allow_fallback and clamped > settings.tile_placeholder_min_zoom:
        cropped = _parent_quadrant(provider.key, clamped, x, y)
        if cropped is not None:
            path.write_bytes(cropped)
            return cropped

    path.write_bytes(payload)
    return payload


def _parent_quadrant(provider_key: str, z: int, x: int, y: int) -> bytes | None:
    """Build a usable child tile from its parent by cropping the right quadrant.

    Vendors answer "no imagery at this zoom" with a small placeholder. Returning
    the *whole* parent tile for a child URL would paint a 2x-zoomed-out image in
    the wrong place — the imagery then no longer lines up with the field
    polygons when you zoom in. Cropping the correct quadrant and upscaling keeps
    the geography exact (equivalent to MapLibre's own overzoom).
    """
    parent = fetch_tile(provider_key, z - 1, x // 2, y // 2, _allow_fallback=True)
    if not parent:
        return None
    image = _decode(parent)
    if image is None:
        return None
    height, width = image.shape[:2]
    half_h, half_w = height // 2, width // 2
    offset_x = (x % 2) * half_w
    offset_y = (y % 2) * half_h
    quadrant = image[offset_y:offset_y + half_h, offset_x:offset_x + half_w]
    if quadrant.size == 0:
        return None
    upscaled = cv2.resize(quadrant, (width, height), interpolation=cv2.INTER_CUBIC)
    ok, buffer = cv2.imencode(".jpg", upscaled, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return buffer.tobytes() if ok else None


def _decode(raw: bytes) -> np.ndarray | None:
    buf = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return img


@dataclass(slots=True)
class Mosaic:
    """A stitched tile mosaic plus its WGS84 extent."""

    image: np.ndarray
    west: float
    south: float
    east: float
    north: float
    zoom: int
    provider: str
    tiles: int
    missing: int

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def mpp_x(self) -> float:
        lat = (self.south + self.north) / 2
        return (self.east - self.west) * 111_320.0 * math.cos(math.radians(lat)) / self.width

    @property
    def mpp_y(self) -> float:
        return (self.north - self.south) * 110_574.0 / self.height

    def pixel_to_lonlat(self, px: float, py: float) -> tuple[float, float]:
        lon = self.west + (px / self.width) * (self.east - self.west)
        lat = self.north - (py / self.height) * (self.north - self.south)
        return lon, lat

    def bbox(self) -> tuple[float, float, float, float]:
        return self.west, self.south, self.east, self.north


def build_mosaic(
    bbox: tuple[float, float, float, float],
    zoom: int | None = None,
    provider: str = DEFAULT_PROVIDER,
    target_px: int = 1024,
    max_tiles: int | None = None,
) -> Mosaic:
    """Stitch the tiles covering ``bbox``; zoom is auto-fitted to ``target_px``."""
    prov = get_provider(provider)
    min_lon, min_lat, max_lon, max_lat = bbox
    if max_lon <= min_lon or max_lat <= min_lat:
        raise ValueError("invalid bbox")
    limit = max_tiles or settings.max_mosaic_tiles

    if zoom is None:
        zoom = prov.max_zoom
        while zoom > prov.min_zoom:
            x0, y0, x1, y1 = geo.tile_range(bbox, zoom)
            if max(x1 - x0 + 1, y1 - y0 + 1) * 256 <= target_px * 1.6:
                break
            zoom -= 1
    zoom = max(prov.min_zoom, min(prov.max_zoom, zoom))

    x0, y0, x1, y1 = geo.tile_range(bbox, zoom)
    nx, ny = x1 - x0 + 1, y1 - y0 + 1
    if nx * ny > limit:
        raise ValueError(f"bbox too large at z{zoom}: {nx * ny} tiles > {limit}")

    coords = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        raws = list(pool.map(lambda c: fetch_tile(prov.key, zoom, c[0], c[1]), coords))

    blank = np.full((256, 256, 3), 26, np.uint8)
    tiles: list[np.ndarray] = []
    missing = 0
    for raw in raws:
        img = _decode(raw) if raw else None
        if img is None:
            missing += 1
            img = blank
        elif img.shape[:2] != (256, 256):
            img = cv2.resize(img, (256, 256))
        tiles.append(img)

    rows = [np.hstack(tiles[i * nx:(i + 1) * nx]) for i in range(ny)]
    image = np.vstack(rows)

    west, north = geo.tile_fraction_to_lonlat(x0, y0, zoom)
    east, south = geo.tile_fraction_to_lonlat(x1 + 1, y1 + 1, zoom)

    if prov.datum == "gcj02":
        # Tiles are laid out on the GCJ-02 graticule; shift corners back to WGS84.
        west, south = geo.gcj02_to_wgs84(west, south)
        east, north = geo.gcj02_to_wgs84(east, north)

    return Mosaic(
        image=image,
        west=west,
        south=south,
        east=east,
        north=north,
        zoom=zoom,
        provider=prov.key,
        tiles=len(coords),
        missing=missing,
    )


def mosaic_png(mosaic: Mosaic) -> bytes:
    ok, buf = cv2.imencode(".jpg", mosaic.image, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise RuntimeError("failed to encode mosaic")
    return buf.tobytes()
