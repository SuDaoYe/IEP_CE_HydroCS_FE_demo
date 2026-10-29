"""Build the bundled Chinese administrative-division dataset.

Geometry comes from DataV.GeoAtlas (阿里云), which mirrors the 民政部 boundary
data and uses 国家统计局 adcodes. Township/village names come from the community
``modood/Administrative-divisions-of-China`` repo (same adcode system) because
DataV stops at the district level.

Outputs (under ``artifacts/admin/``, gitignored):

    provinces.geojson   省级边界（简化）
    cities.geojson      地级市边界（简化）——用于把田块落到行政区
    index.json          省/市/区县搜索索引（名称/级别/上级/中心点/包围盒）
    towns.json          乡镇级索引 [code, name, areaCode]，已剔除“街道/办事处”
    villages.txt        村级索引，每行 name<TAB>code<TAB>areaCode（同样剔除街道下辖）

Usage::

    python scripts/build_admin_divisions.py
    python scripts/build_admin_divisions.py --tolerance 0.01 --no-districts
    python scripts/build_admin_divisions.py --no-subdistrict    # 只建到区县
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

SERVER_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = SERVER_DIR / "artifacts" / "admin"

BASE = "https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (HydroCS admin-division builder)"}


def fetch(code: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            response = requests.get(BASE.format(code=code), headers=HEADERS, timeout=30)
            if response.status_code == 200:
                return response.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.4 * (attempt + 1))
    return None


def fetch_districts(city_code: str, city_name: str, province_name: str) -> list[dict]:
    """District/county names + centres (no polygons) for the search index."""
    payload = fetch(city_code)
    if not payload:
        return []
    entries = []
    for feature in payload.get("features") or []:
        props = feature.get("properties", {})
        code = str(props.get("adcode", ""))
        name = props.get("name", "")
        if not code or not name or code == city_code:
            continue
        center = props.get("center") or props.get("centroid")
        entries.append(
            {
                "adcode": code,
                "name": name,
                "fullname": f"{province_name}{city_name}{name}",
                "level": "district",
                "parent": city_code,
                "center": center,
                "bbox": None,
            }
        )
    return entries


def simplify_ring(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    """Douglas–Peucker on a lon/lat ring (closure preserved)."""
    if len(ring) <= 4:
        return ring
    closed = ring[0] == ring[-1]
    points = ring[:-1] if closed else ring

    def dp(points: list[list[float]]) -> list[list[float]]:
        if len(points) < 3:
            return points
        first, last = points[0], points[-1]
        dx, dy = last[0] - first[0], last[1] - first[1]
        norm = (dx * dx + dy * dy) ** 0.5
        index, best = 0, 0.0
        for i in range(1, len(points) - 1):
            px, py = points[i]
            if norm == 0:
                dist = ((px - first[0]) ** 2 + (py - first[1]) ** 2) ** 0.5
            else:
                dist = abs(dy * (px - first[0]) - dx * (py - first[1])) / norm
            if dist > best:
                index, best = i, dist
        if best > tolerance:
            left = dp(points[: index + 1])
            right = dp(points[index:])
            return left[:-1] + right
        return [first, last]

    result = dp(points)
    if len(result) < 3:
        return ring
    result.append(result[0])
    return [[round(x, 5), round(y, 5)] for x, y in result]


def simplify_geometry(geometry: dict, tolerance: float) -> dict:
    gtype = geometry.get("type")
    if gtype == "Polygon":
        rings = [simplify_ring(ring, tolerance) for ring in geometry["coordinates"]]
        return {"type": "Polygon", "coordinates": [r for r in rings if len(r) >= 4]}
    if gtype == "MultiPolygon":
        polygons = []
        for polygon in geometry["coordinates"]:
            rings = [simplify_ring(ring, tolerance) for ring in polygon]
            rings = [r for r in rings if len(r) >= 4]
            if rings:
                polygons.append(rings)
        return {"type": "MultiPolygon", "coordinates": polygons}
    return geometry


def bbox_of(geometry: dict) -> list[float]:
    points: list[list[float]] = []

    def walk(node):
        if isinstance(node, list) and node and isinstance(node[0], (int, float)):
            points.append(node)
            return
        if isinstance(node, list):
            for child in node:
                walk(child)

    walk(geometry.get("coordinates", []))
    if not points:
        return [0, 0, 0, 0]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tolerance", type=float, default=0.01, help="简化容差（度）")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--no-districts", action="store_true", help="只到地级市")
    parser.add_argument(
        "--no-subdistrict",
        action="store_true",
        help="不构建乡镇/村索引（只到区县）",
    )
    args = parser.parse_args()

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("fetching province list ...")
    country = fetch("100000")
    if not country:
        raise SystemExit("cannot fetch 100000 (network?)")
    provinces = country["features"]
    print(f"  {len(provinces)} provinces/municipalities")

    province_features: list[dict] = []
    city_features: list[dict] = []
    index: list[dict] = []
    city_triples: list[tuple[str, str, str]] = []

    for position, feature in enumerate(provinces, 1):
        props = feature.get("properties", {})
        code = str(props.get("adcode", ""))
        name = props.get("name", "")
        if not code:
            continue
        geometry = simplify_geometry(feature.get("geometry") or {}, args.tolerance)
        if not geometry.get("coordinates"):
            continue
        province_features.append(
            {
                "type": "Feature",
                "properties": {"adcode": code, "name": name, "level": "province"},
                "geometry": geometry,
            }
        )
        index.append(
            {
                "adcode": code,
                "name": name,
                "fullname": name,
                "level": "province",
                "parent": "100000",
                "center": props.get("center") or props.get("centroid"),
                "bbox": bbox_of(geometry),
            }
        )

        if args.no_districts:
            continue
        payload = fetch(code)
        children = (payload or {}).get("features") or []
        cities = 0
        for child in children:
            child_props = child.get("properties", {})
            child_code = str(child_props.get("adcode", ""))
            child_name = child_props.get("name", "")
            if not child_code or child_props.get("level") not in {"city", "district"}:
                continue
            if child_props.get("level") == "district" and child_code == code:
                continue
            child_geometry = simplify_geometry(child.get("geometry") or {}, args.tolerance)
            if not child_geometry.get("coordinates"):
                continue
            city_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "adcode": child_code,
                        "name": child_name,
                        "level": "city",
                        "parent": code,
                    },
                    "geometry": child_geometry,
                }
            )
            index.append(
                {
                    "adcode": child_code,
                    "name": child_name,
                    "fullname": f"{name}{child_name}",
                    "level": "city",
                    "parent": code,
                    "center": child_props.get("center") or child_props.get("centroid"),
                    "bbox": bbox_of(child_geometry),
                }
            )
            cities += 1
            if child_props.get("level") == "city":
                city_triples.append((child_code, child_name, name))
        print(f"  [{position:02d}/{len(provinces)}] {name} {code}: {cities} cities")

    if not args.no_districts and city_triples:
        print(f"fetching district centres for {len(city_triples)} cities (no polygons) ...")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(lambda item: fetch_districts(item[0], item[1], item[2]), city_triples)
            )
        district_count = 0
        for entries in results:
            index.extend(entries)
            district_count += len(entries)
        print(f"  {district_count} districts indexed")

    # Municipalities (直辖市) report districts directly; keep them searchable too.
    def write(name: str, features: list[dict]) -> None:
        path = out_dir / name
        payload = {"type": "FeatureCollection", "features": features}
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"wrote {path} ({path.stat().st_size / 1024 / 1024:.2f} MB, {len(features)} features)")

    write("provinces.geojson", province_features)
    write("cities.geojson", city_features)

    index_path = out_dir / "index.json"
    index_path.write_text(
        json.dumps({"generated": time.strftime("%Y-%m-%d"), "entries": index},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote {index_path} ({index_path.stat().st_size / 1024:.0f} KB, {len(index)} entries)")

    if not args.no_subdistrict:
        try:
            build_subdistrict(out_dir)
        except Exception as exc:  # noqa: BLE001 - optional enrichment only
            print(f"  ! 乡镇/村索引构建失败（不影响省市区）：{exc}")
    return 0


GITHUB_RAW = "https://raw.githubusercontent.com/modood/Administrative-divisions-of-China/master/dist/"
# “街道/办事处”是城市里的乡级单位，需求只到镇/村，直接剔除能省下约三成体积。
URBAN_SUFFIX = re.compile(r"(街道|办事处)$")


def _download(name: str) -> list[dict]:
    print(f"  downloading {name} ...")
    response = requests.get(GITHUB_RAW + name, headers=HEADERS, timeout=180)
    response.raise_for_status()
    return response.json()


def build_subdistrict(out_dir: Path) -> None:
    """乡镇 + 村两级索引（只有名称与编码，坐标由所属区县中心代替）。"""
    streets = _download("streets.json")
    villages = _download("villages.json")
    print(f"  raw: {len(streets)} townships, {len(villages)} villages")

    towns: list[list[str]] = []
    kept_streets: set[str] = set()
    for row in streets:
        name = (row.get("name") or "").strip()
        code = str(row.get("code") or "")
        area = str(row.get("areaCode") or "")
        if not name or not code or not area:
            continue
        if URBAN_SUFFIX.search(name):
            continue
        towns.append([code, name, area])
        kept_streets.add(code)

    town_path = out_dir / "towns.json"
    town_path.write_text(
        json.dumps(towns, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  wrote {town_path.name} ({town_path.stat().st_size / 1024 / 1024:.2f} MB, {len(towns)} towns)")

    lines: list[str] = []
    for row in villages:
        street = str(row.get("streetCode") or "")
        name = (row.get("name") or "").strip()
        code = str(row.get("code") or "")
        area = str(row.get("areaCode") or "")
        if not name or not code or not street or street not in kept_streets:
            continue
        lines.append(f"{name}\t{code}\t{area}")

    village_path = out_dir / "villages.txt"
    village_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"  wrote {village_path.name} "
        f"({village_path.stat().st_size / 1024 / 1024:.2f} MB, {len(lines)} villages)"
    )


if __name__ == "__main__":
    sys.exit(main())
