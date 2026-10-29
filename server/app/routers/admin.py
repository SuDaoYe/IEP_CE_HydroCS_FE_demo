"""Administrator endpoints: users, all fields, statistics and model parameters."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import db, deps, repository
from ..schemas import ParamsUpdate, UserOut
from ..services import era5, et_grid, geo, irrigation, segmentation
from ..services import params as parameter_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(admin: deps.AdminUser) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT u.*, (SELECT COUNT(*) FROM fields f WHERE f.owner_id = u.id AND f.deleted_at IS NULL)"
        " AS field_count FROM users u ORDER BY u.created_at"
    ).fetchall()
    return [
        {
            "id": r["id"],
            "username": r["username"],
            "name": r["name"],
            "phone": r["phone"],
            "role": r["role"],
            "created_at": r["created_at"],
            "field_count": r["field_count"],
        }
        for r in rows
    ]


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: dict[str, Any], admin: deps.AdminUser) -> dict[str, Any]:
    allowed = {"name", "phone", "role"}
    updates = {k: v for k, v in payload.items() if k in allowed and v is not None}
    if not updates:
        raise HTTPException(422, "没有可更新的字段")
    if "role" in updates and updates["role"] not in {"admin", "farmer"}:
        raise HTTPException(422, "角色只能是 admin 或 farmer")
    if user_id == admin["id"] and updates.get("role") == "farmer":
        raise HTTPException(422, "不能降级当前登录的管理员")
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with db.transaction() as conn:
        conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", [*updates.values(), user_id])
    row = db.get_conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "用户不存在")
    return {"id": row["id"], "username": row["username"], "name": row["name"],
            "phone": row["phone"], "role": row["role"], "created_at": row["created_at"]}


@router.get("/fields")
def list_all_fields(admin: deps.AdminUser, limit: int = Query(default=500, ge=1, le=1000)) -> list[dict]:
    return repository.list_fields(owner_id=None, limit=limit)


@router.get("/stats")
def stats(admin: deps.AdminUser, days: int = Query(default=7, ge=1, le=180)) -> dict[str, Any]:
    conn = db.get_conn()
    users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    farmers = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'farmer'").fetchone()["n"]
    field_rows = conn.execute(
        "SELECT f.*, u.name AS owner_name FROM fields f JOIN users u ON u.id = f.owner_id"
        " WHERE f.deleted_at IS NULL"
    ).fetchall()
    fields = [repository.serialize(r, r["owner_name"]) for r in field_rows]

    total_area = sum(f["area_m2"] for f in fields)
    with_crop = [f for f in fields if f["crop"]]
    crop_mix: dict[str, float] = {}
    for field in fields:
        key = field["crop_label"] or "未录入"
        crop_mix[key] = round(crop_mix.get(key, 0.0) + field["area_mu"], 2)

    plans = []
    scope_summary: dict[str, int] = {}
    for field in fields:
        rings = geo.rings_from_geojson(field["geometry"])
        if not rings:
            continue
        resolved = parameter_service.resolve_for_ring(rings[0])
        scope_summary[resolved.scope] = scope_summary.get(resolved.scope, 0) + 1
        plans.append(
            irrigation.compute_plan(
                ring=rings[0],
                area_m2=field["area_m2"],
                crop=field["crop"],
                stage_key=field["stage_key"],
                days=days,
                params=parameter_service.params_for_plan(resolved),
            )
        )
    totals = irrigation.summarize(plans)

    return {
        "users": users,
        "farmers": farmers,
        "fields": len(fields),
        "fields_with_crop": len(with_crop),
        "coverage_pct": round(len(with_crop) / len(fields) * 100, 1) if fields else 0.0,
        "total_area_mu": round(total_area * geo.MU_PER_M2, 1),
        "total_area_ha": round(total_area / 10_000, 2),
        "daily_m3": totals["daily_m3"],
        "week_m3": totals["week_m3"],
        "by_date": totals["by_date"],
        "crop_mix": [{"crop": k, "area_mu": v} for k, v in sorted(crop_mix.items(), key=lambda kv: -kv[1])],
        "parameter_scopes": scope_summary,
        "segmentation": segmentation.backend_status(),
        "et_grid": et_grid.status(),
        "era5": era5.status(),
    }


@router.get("/params")
def get_params(admin: deps.AdminUser, scope: str = "global") -> dict[str, Any]:
    """生效值 + 每一项来自哪一层（global / province / city）。"""
    try:
        payload = parameter_service.describe(scope)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        **payload,
        "scopes": parameter_service.list_scopes(),
        "crops": irrigation.crop_catalog(),
        "segmentation": {
            **segmentation.backend_status(),
            "conf": 0.25,
            "imgsz": 1024,
        },
    }


@router.patch("/params")
def patch_params(payload: ParamsUpdate, admin: deps.AdminUser) -> dict[str, Any]:
    """写某个作用域的覆盖值；传 null 表示删除该层覆盖、回退到上一层。"""
    try:
        updated = parameter_service.update(
            payload.scope, payload.values, admin["id"]
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**updated, "scopes": parameter_service.list_scopes()}


@router.get("/logs")
def recent_logs(admin: deps.AdminUser, limit: int = Query(default=40, ge=1, le=200)) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT l.*, f.name AS field_name, u.name AS user_name FROM irrigation_logs l"
        " JOIN fields f ON f.id = l.field_id JOIN users u ON u.id = l.user_id"
        " ORDER BY l.computed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "field_name": r["field_name"],
            "user_name": r["user_name"],
            "computed_at": r["computed_at"],
            "days": r["days"],
            "totals": json.loads(r["payload_json"]).get("totals", {}),
        }
        for r in rows
    ]
