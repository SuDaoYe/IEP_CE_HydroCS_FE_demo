"""Admin endpoints for meteorology ingestion and administrative-region rollups."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from .. import db, deps, repository
from ..services import geo, irrigation, meteo, regions
from ..services import params as parameter_service

router = APIRouter(prefix="/admin", tags=["admin-data"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_FIELDS_PER_ROLLUP = 400


# --- meteorology ingest ---------------------------------------------------


@router.get("/meteo/status")
def meteo_status(admin: deps.AdminUser) -> dict[str, Any]:
    inventory = meteo.inbox_inventory()
    inventory["divisions"] = regions.status()
    return inventory


@router.get("/meteo/fs")
def meteo_fs(admin: deps.AdminUser, path: str | None = None) -> dict[str, Any]:
    return meteo.list_directory(path)


@router.post("/meteo/scan")
def meteo_scan(
    admin: deps.AdminUser,
    payload: dict[str, Any],
) -> dict[str, Any]:
    path = (payload or {}).get("path")
    if not path:
        raise HTTPException(422, "需要提供服务器文件夹路径")
    recursive = bool(payload.get("recursive", True))
    ingest = bool(payload.get("ingest", True))
    copy = bool(payload.get("copy", True))
    try:
        files = meteo.collect(str(path), recursive=recursive)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not files:
        raise HTTPException(422, "该文件夹里没有 .nc 文件")
    if copy:
        files = meteo.copy_into_inbox(files)
    if not ingest:
        return {"found": len(files), "files": [f.name for f in files][:40], "ingested": None}
    report = meteo.ingest(files)
    return {"found": len(files), "files": [f.name for f in files][:40], "ingested": report.to_dict()}


@router.post("/meteo/upload")
async def meteo_upload(
    admin: deps.AdminUser,
    files: list[UploadFile] = File(..., description="ERA5 NetCDF 文件"),
    ingest: bool = Query(default=True),
) -> dict[str, Any]:
    if not files:
        raise HTTPException(422, "没有收到文件")
    payloads: list[tuple[str, bytes]] = []
    total = 0
    for upload in files:
        content = await upload.read()
        total += len(content)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "上传总量超过 200 MB，请改用服务器文件夹扫描")
        payloads.append((upload.filename or "upload.nc", content))
    saved = meteo.save_uploads(payloads)
    if not ingest:
        return {"saved": [p.name for p in saved], "ingested": None}
    report = meteo.ingest(saved)
    return {"saved": [p.name for p in saved], "ingested": report.to_dict()}


@router.post("/meteo/rebuild")
def meteo_rebuild(admin: deps.AdminUser) -> dict[str, Any]:
    files = sorted(meteo.settings.meteo_inbox.glob("*.nc"))
    if not files:
        raise HTTPException(422, "收件箱为空，先上传或扫描文件")
    return meteo.ingest(files).to_dict()


# --- administrative regions ----------------------------------------------


@router.get("/regions/status")
def regions_status(admin: deps.AdminUser) -> dict[str, Any]:
    return regions.status()


@router.get("/regions/lookup")
def regions_lookup(admin: deps.AdminUser, lat: float, lon: float) -> dict[str, Any]:
    return regions.locate(lon, lat)


@router.get("/regions/overview")
def regions_overview(
    admin: deps.AdminUser,
    days: int = Query(default=7, ge=1, le=180),
) -> dict[str, Any]:
    """Every city that currently holds parcels, with its aggregated demand."""
    fields = repository.list_fields(owner_id=None, limit=MAX_FIELDS_PER_ROLLUP)
    buckets: dict[str, dict[str, Any]] = {}
    unmatched = 0

    for field in fields:
        rings = geo.rings_from_geojson(field["geometry"])
        if not rings:
            continue
        lon, lat = geo.ring_centroid(rings[0])
        located = regions.locate(lon, lat)
        city = located.get("city")
        key = city["adcode"] if city else "__unassigned__"
        bucket = buckets.setdefault(
            key,
            {
                "adcode": key,
                "name": city["name"] if city else "未匹配行政区",
                "fullname": city["fullname"] if city else "未匹配行政区",
                "province": (located.get("province") or {}).get("name") if located.get("province") else None,
                "fields": 0,
                "area_mu": 0.0,
                "volume_m3": 0.0,
                "net_volume_m3": 0.0,
                "users": set(),
            },
        )
        if city is None:
            unmatched += 1
        bucket["fields"] += 1
        bucket["area_mu"] += field["area_mu"]
        bucket["users"].add(field["owner_id"])
        plan = irrigation.compute_plan(
            ring=rings[0],
            area_m2=field["area_m2"],
            crop=field["crop"],
            stage_key=field["stage_key"],
            days=days,
            params=parameter_service.params_for_plan(
                parameter_service.resolve_for_ring(rings[0])
            ),
        )
        bucket["volume_m3"] += plan["totals"]["volume_m3"]
        bucket["net_volume_m3"] += plan["totals"].get("net_volume_m3", 0.0)

    items = []
    for bucket in buckets.values():
        items.append(
            {
                "adcode": bucket["adcode"],
                "name": bucket["name"],
                "fullname": bucket["fullname"],
                "province": bucket["province"],
                "fields": bucket["fields"],
                "users": len(bucket["users"]),
                "area_mu": round(bucket["area_mu"], 2),
                "volume_m3": round(bucket["volume_m3"], 1),
                "net_volume_m3": round(bucket["net_volume_m3"], 1),
            }
        )
    items.sort(key=lambda item: -item["volume_m3"])
    return {
        "days": days,
        "regions": items,
        "unmatched": unmatched,
        "divisions": regions.status(),
    }


@router.get("/regions/summary")
def regions_summary(
    admin: deps.AdminUser,
    code: str = Query(..., description="行政区 adcode，例如 370500"),
    days: int = Query(default=7, ge=1, le=180),
    include_children: bool = Query(default=True, description="省级时是否汇总各地级市"),
) -> dict[str, Any]:
    region = regions.get_region(code)
    if region is None:
        raise HTTPException(404, f"未知行政区：{code}（行政边界资产可能未生成）")

    child_codes: set[str] = set()
    if include_children and region.level == "province":
        child_codes = {child["adcode"] for child in regions.children(region.adcode)}

    fields = repository.list_fields(owner_id=None, limit=MAX_FIELDS_PER_ROLLUP)
    matched: list[dict[str, Any]] = []
    by_user: dict[str, dict[str, Any]] = {}
    by_city: dict[str, dict[str, Any]] = {}
    crop_mix: dict[str, float] = {}
    totals = {
        "fields": 0,
        "area_mu": 0.0,
        "volume_m3": 0.0,
        "net_volume_m3": 0.0,
        "net_mm": 0.0,
        "gross_mm": 0.0,
    }
    by_date: dict[str, float] = {}

    for field in fields:
        rings = geo.rings_from_geojson(field["geometry"])
        if not rings:
            continue
        lon, lat = geo.ring_centroid(rings[0])
        located = regions.locate(lon, lat)
        city = located.get("city")
        if not _in_region(region, child_codes, lon, lat, city):
            continue

        plan = irrigation.compute_plan(
            ring=rings[0],
            area_m2=field["area_m2"],
            crop=field["crop"],
            stage_key=field["stage_key"],
            days=days,
            params=parameter_service.params_for_plan(
                parameter_service.resolve_for_ring(rings[0])
            ),
        )
        volume = plan["totals"]["volume_m3"]
        totals["fields"] += 1
        totals["area_mu"] += field["area_mu"]
        totals["volume_m3"] += volume
        totals["net_volume_m3"] += plan["totals"].get("net_volume_m3", 0.0)
        totals["net_mm"] += plan["totals"]["net_mm"]
        totals["gross_mm"] += plan["totals"]["gross_mm"]
        for row in plan["series"]:
            by_date[row["date"]] = round(by_date.get(row["date"], 0.0) + row["volume_m3"], 2)
        matched.append(
            {
                "id": field["id"],
                "name": field["name"],
                "owner_name": field["owner_name"],
                "area_mu": field["area_mu"],
                "crop_label": field["crop_label"],
                "city": city["name"] if city else None,
                "volume_m3": volume,
            "net_volume_m3": plan["totals"].get("net_volume_m3", 0.0),
            }
        )

        user = by_user.setdefault(
            field["owner_id"],
            {
                "user_id": field["owner_id"],
                "name": field["owner_name"],
                "fields": 0,
                "area_mu": 0.0,
                "volume_m3": 0.0,
                "net_volume_m3": 0.0,
            },
        )
        user["fields"] += 1
        user["area_mu"] += field["area_mu"]
        user["volume_m3"] += volume
        user["net_volume_m3"] += plan["totals"].get("net_volume_m3", 0.0)

        city_key = city["adcode"] if city else "__unassigned__"
        city_bucket = by_city.setdefault(
            city_key,
            {
                "adcode": city_key,
                "name": city["name"] if city else "未匹配",
                "fields": 0,
                "area_mu": 0.0,
                "volume_m3": 0.0,
            },
        )
        city_bucket["fields"] += 1
        city_bucket["area_mu"] += field["area_mu"]
        city_bucket["volume_m3"] += volume

        label = field["crop_label"] or "未录入"
        crop_mix[label] = round(crop_mix.get(label, 0.0) + field["area_mu"], 2)

    users = [
        {
            **user,
            "area_mu": round(user["area_mu"], 2),
            "volume_m3": round(user["volume_m3"], 1),
            "net_volume_m3": round(user["net_volume_m3"], 1),
        }
        for user in sorted(by_user.values(), key=lambda item: -item["volume_m3"])
    ]
    cities = [
        {
            **bucket,
            "area_mu": round(bucket["area_mu"], 2),
            "volume_m3": round(bucket["volume_m3"], 1),
        }
        for bucket in sorted(by_city.values(), key=lambda item: -item["volume_m3"])
    ]

    return {
        "region": region.to_dict(),
        "include_children": bool(child_codes),
        "days": days,
        "totals": {
            "fields": totals["fields"],
            "users": len(users),
            "area_mu": round(totals["area_mu"], 2),
            "volume_m3": round(totals["volume_m3"], 1),
            "net_volume_m3": round(totals["net_volume_m3"], 1),
            "daily_m3": round(totals["volume_m3"] / days, 1) if totals["fields"] else 0.0,
            "net_mm_avg": round(totals["net_mm"] / totals["fields"], 2) if totals["fields"] else 0.0,
        },
        "users": users,
        "cities": cities,
        "fields": matched[:120],
        "crop_mix": [{"crop": k, "area_mu": v} for k, v in sorted(crop_mix.items(), key=lambda kv: -kv[1])],
        "by_date": [{"date": k, "volume_m3": v} for k, v in sorted(by_date.items())],
        "assumptions": [
            "田块按中心点落区（点面判断基于简化后的行政区边界，边界附近约 1 km 误差）",
            f"需水量按 {days} 天、当前模型参数解算，与田块详情页口径一致",
            f"单次汇总最多处理 {MAX_FIELDS_PER_ROLLUP} 块田，超出部分不计入",
        ],
        "generated_at": db.now_iso(),
        "started": (dt.date.today()).isoformat(),
    }


def _in_region(region, child_codes: set[str], lon: float, lat: float, city: dict | None) -> bool:
    if city is not None and city["adcode"] in child_codes:
        return True
    return region.contains(lon, lat)


