"""Chinese administrative divisions: lookup, fuzzy search and parcel assignment.

The bundled asset (``artifacts/admin/``) is built by
``scripts/build_admin_divisions.py`` from DataV.GeoAtlas polygons, which use
国家统计局 adcodes — the same codes as the community
``modood/Administrative-divisions-of-China`` list, but with geometry attached so
a parcel can be assigned to a 地级市 by point-in-polygon.
"""

from __future__ import annotations

import json
import logging
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import settings
from . import geo

log = logging.getLogger(__name__)

_lock = threading.Lock()
_loaded = False
_provinces: dict[str, dict] = {}
_cities: dict[str, dict] = {}
_index: list[dict] = []
_load_error: str | None = None

# 乡镇 / 村：只有名称与编码，坐标用所属区县中心代替（DataV 不提供这两级几何）
_subdistrict_lock = threading.Lock()
_subdistrict_loaded = False
_subdistrict_error: str | None = None
_towns: list[tuple[str, str, str]] = []      # (name, code, areaCode)
_villages: list[tuple[str, str, str]] = []
_center_by_code: dict[str, tuple[float, float]] = {}


@dataclass(slots=True)
class Region:
    adcode: str
    name: str
    level: str
    parent: str | None
    fullname: str
    center: tuple[float, float] | None
    bbox: tuple[float, float, float, float] | None
    rings: list[geo.Ring]

    def to_dict(self) -> dict[str, Any]:
        return {
            "adcode": self.adcode,
            "name": self.name,
            "level": self.level,
            "parent": self.parent,
            "fullname": self.fullname,
            "center": list(self.center) if self.center else None,
            "bbox": list(self.bbox) if self.bbox else None,
        }

    def contains(self, lon: float, lat: float) -> bool:
        if self.bbox:
            minx, miny, maxx, maxy = self.bbox
            if not (minx <= lon <= maxx and miny <= lat <= maxy):
                return False
        return any(geo.point_in_ring(lon, lat, ring) for ring in self.rings)


def _rings_from_geometry(geometry: dict) -> list[geo.Ring]:
    gtype = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    rings: list[geo.Ring] = []
    if gtype == "Polygon":
        if coordinates:
            rings.append([(float(p[0]), float(p[1])) for p in coordinates[0]])
    elif gtype == "MultiPolygon":
        for polygon in coordinates:
            if polygon:
                rings.append([(float(p[0]), float(p[1])) for p in polygon[0]])
    return [ring for ring in rings if len(ring) >= 3]


def _load() -> None:
    global _loaded, _load_error
    if _loaded or _load_error is not None:
        return
    with _lock:
        if _loaded or _load_error is not None:
            return
        base = Path(settings.admin_dir)
        province_path = base / "provinces.geojson"
        city_path = base / "cities.geojson"
        index_path = base / "index.json"
        if not (province_path.is_file() and city_path.is_file() and index_path.is_file()):
            _load_error = f"行政边界资产缺失：{base}（运行 scripts/build_admin_divisions.py）"
            log.warning(_load_error)
            return
        try:
            for path, bucket, level in (
                (province_path, _provinces, "province"),
                (city_path, _cities, "city"),
            ):
                payload = json.loads(path.read_text(encoding="utf-8"))
                for feature in payload.get("features", []):
                    props = feature.get("properties", {})
                    code = str(props.get("adcode", ""))
                    if not code:
                        continue
                    rings = _rings_from_geometry(feature.get("geometry") or {})
                    if not rings:
                        continue
                    bbox = geo.bbox_of_points([point for ring in rings for point in ring])
                    region = Region(
                        adcode=code,
                        name=props.get("name", ""),
                        level=level,
                        parent=props.get("parent"),
                        fullname=props.get("name", ""),
                        center=None,
                        bbox=bbox,
                        rings=rings,
                    )
                    bucket[code] = region

            payload = json.loads(index_path.read_text(encoding="utf-8"))
            for entry in payload.get("entries", []):
                code = str(entry.get("adcode", ""))
                if not code:
                    continue
                center = entry.get("center")
                if isinstance(center, list) and len(center) == 2:
                    parsed = (float(center[0]), float(center[1]))
                elif isinstance(center, str) and "," in center:
                    lon, lat = center.split(",")[:2]
                    parsed = (float(lon), float(lat))
                else:
                    parsed = None
                _index.append({**entry, "adcode": code, "center": parsed})
                if parsed is not None:
                    _center_by_code[code] = parsed
                bucket = _provinces if entry.get("level") == "province" else _cities
                region = bucket.get(code)
                if region is not None:
                    region.center = parsed
                    region.fullname = entry.get("fullname") or region.name

            _loaded = True
            log.info("loaded admin divisions: %s provinces, %s cities", len(_provinces), len(_cities))
        except Exception as exc:  # noqa: BLE001
            _load_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("failed to load admin divisions: %s", _load_error)


def status() -> dict:
    _load()
    if not _loaded:
        return {"available": False, "error": _load_error}
    base = Path(settings.admin_dir)
    towns_file = (base / "towns.json").is_file()
    villages_file = (base / "villages.txt").is_file()
    return {
        "available": True,
        "provinces": len(_provinces),
        "cities": len(_cities),
        "entries": len(_index),
        "subdistrict_available": towns_file,
        "subdistrict_loaded": _subdistrict_loaded,
        "towns": len(_towns) if _subdistrict_loaded else None,
        "villages": len(_villages) if _subdistrict_loaded else None,
        "villages_file": villages_file,
        "subdistrict_error": _subdistrict_error,
        "source": "DataV.GeoAtlas 边界 + modood/Administrative-divisions-of-China 乡镇村（国标 adcode）",
    }


# --- lookup ---------------------------------------------------------------


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip().lower()


def _score(query: str, entry: dict) -> float:
    """Rank search hits: exact > prefix > substring > subsequence."""
    name = _normalise(entry.get("name", ""))
    fullname = _normalise(entry.get("fullname", ""))
    q = query
    if not q:
        return 0.0
    if name == q or fullname == q:
        return 100.0
    if entry.get("adcode", "").startswith(q):
        return 92.0
    if name.startswith(q):
        return 88.0 - (len(name) - len(q)) * 0.3
    if fullname.startswith(q):
        return 84.0 - (len(fullname) - len(q)) * 0.3
    position = fullname.find(q)
    if position >= 0:
        return 72.0 - position - (len(fullname) - len(q)) * 0.4
    # subsequence match (e.g. "东营垦" -> 东营市垦利区)
    cursor = 0
    hits = 0
    for char in q:
        found = fullname.find(char, cursor)
        if found < 0:
            break
        cursor = found + 1
        hits += 1
    if hits == len(q):
        return 40.0 + len(q) * 1.5 - (len(fullname) - len(q)) * 0.4
    return 0.0


def _load_subdistrict() -> None:
    global _subdistrict_loaded, _subdistrict_error
    if _subdistrict_loaded or _subdistrict_error is not None:
        return
    with _subdistrict_lock:
        if _subdistrict_loaded or _subdistrict_error is not None:
            return
        base = Path(settings.admin_dir)
        towns_path = base / "towns.json"
        villages_path = base / "villages.txt"
        if not towns_path.is_file():
            _subdistrict_error = f"乡镇索引缺失：{towns_path}"
            return
        try:
            for code, name, area in json.loads(towns_path.read_text(encoding="utf-8")):
                _towns.append((str(name), str(code), str(area)))
            if villages_path.is_file():
                for line in villages_path.read_text(encoding="utf-8").splitlines():
                    parts = line.split("\t")
                    if len(parts) == 3:
                        _villages.append((parts[0], parts[1], parts[2]))
            _subdistrict_loaded = True
            log.info("loaded subdistrict index: %s towns, %s villages", len(_towns), len(_villages))
        except Exception as exc:  # noqa: BLE001
            _subdistrict_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("failed to load subdistrict index: %s", _subdistrict_error)


LEVEL_ORDER = {"province": 0, "city": 1, "district": 2, "town": 3, "village": 4}
SUB_LEVELS = {"town", "village"}


def _subdistrict_results(query: str, limit: int, level: str | None) -> list[dict]:
    """Match township/village names. Coordinates fall back to the district centre."""
    _load_subdistrict()
    if not _subdistrict_loaded:
        return []
    wanted: list[tuple[str, list[tuple[str, str, str]]]] = []
    if level in (None, "town", "all"):
        wanted.append(("town", _towns))
    if level in (None, "village", "all"):
        wanted.append(("village", _villages))

    scored: list[tuple[float, str, str, str]] = []
    budget = max(limit * 6, 30)
    for kind, bucket in wanted:
        for name, code, area in bucket:
            lowered = name.lower()
            if name == query or lowered == query:
                score = 100.0
            elif lowered.startswith(query):
                score = 88.0 - (len(name) - len(query)) * 0.3
            else:
                position = lowered.find(query)
                if position < 0:
                    continue
                score = 72.0 - position - (len(name) - len(query)) * 0.4
            scored.append((score, kind, name, code + "\t" + area))
            if len(scored) >= budget * 4:
                break
        if len(scored) >= budget * 4:
            break

    scored.sort(key=lambda item: -item[0])
    results = []
    for score, kind, name, payload in scored[:limit]:
        code, area = payload.split("\t")
        center = _center_by_code.get(area)
        results.append(
            {
                "adcode": code,
                "name": name,
                "fullname": name,
                "level": kind,
                "parent": area,
                "lon": round(center[0], 6) if center else None,
                "lat": round(center[1], 6) if center else None,
                "score": round(score, 1),
                "has_geometry": False,
                "precision": "district-center",
            }
        )
    return results


def search(query: str, limit: int = 8, level: str | None = None) -> list[dict]:
    _load()
    if not _loaded:
        return []
    q = _normalise(query)
    if not q:
        return []

    results: list[dict] = []
    if level not in SUB_LEVELS:
        for entry in _index:
            if level and entry.get("level") != level:
                continue
            score = _score(q, entry)
            if score <= 0:
                continue
            region = _provinces.get(entry["adcode"]) or _cities.get(entry["adcode"])
            center = entry.get("center")
            if center is None and region is not None:
                center = region.center
            results.append(
                {
                    "adcode": entry["adcode"],
                    "name": entry.get("name"),
                    "fullname": entry.get("fullname"),
                    "level": entry.get("level"),
                    "parent": entry.get("parent"),
                    "lon": round(center[0], 6) if center else None,
                    "lat": round(center[1], 6) if center else None,
                    "score": round(score, 1),
                    "has_geometry": region is not None,
                    "precision": "polygon" if region is not None else "district-center",
                }
            )

    if level in (None, "town", "village", "all"):
        results.extend(_subdistrict_results(q, limit, level))

    results.sort(key=lambda item: (-item["score"], LEVEL_ORDER.get(item["level"], 9), len(item["name"])))
    return results[:limit]


def get_region(adcode: str) -> Region | None:
    _load()
    return _cities.get(adcode) or _provinces.get(adcode)


def list_regions(level: str = "province", parent: str | None = None) -> list[dict]:
    _load()
    bucket = _provinces if level == "province" else _cities
    items = []
    for region in bucket.values():
        if parent and region.parent != parent:
            continue
        items.append(region.to_dict())
    items.sort(key=lambda item: item["adcode"])
    return items


def _point_in_region(lon: float, lat: float, region: Region) -> bool:
    if region.bbox:
        minx, miny, maxx, maxy = region.bbox
        if not (minx <= lon <= maxx and miny <= lat <= maxy):
            return False
    for ring in region.rings:
        if geo.point_in_ring(lon, lat, ring):
            return True
    return False


def locate(lon: float, lat: float) -> dict[str, Any]:
    """Resolve a coordinate to (province, city) using the bundled polygons."""
    _load()
    if not _loaded:
        return {"available": False, "error": _load_error, "province": None, "city": None}

    city = next((region for region in _cities.values() if _point_in_region(lon, lat, region)), None)
    province = next(
        (region for region in _provinces.values() if _point_in_region(lon, lat, region)), None
    )
    if province is None and city is not None:
        province = _provinces.get(city.parent or "")
    return {
        "available": True,
        "province": province.to_dict() if province else None,
        "city": city.to_dict() if city else None,
    }


def children(adcode: str) -> list[dict]:
    return list_regions(level="city", parent=adcode)
