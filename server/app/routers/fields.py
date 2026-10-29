"""Field CRUD, geometry storage and per-field irrigation plans."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from .. import db, deps, repository
from ..schemas import FieldCreate, FieldOut, FieldUpdate
from ..services import geo, irrigation
from ..services import params as parameter_service

router = APIRouter(prefix="/fields", tags=["fields"])


def _raise(exc: repository.FieldError) -> None:
    raise HTTPException(exc.status_code, exc.message)


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [float(p) for p in raw.split(",")]
    if len(parts) != 4:
        raise HTTPException(422, "bbox 需要 4 个数值：minx,miny,maxx,maxy")
    return parts[0], parts[1], parts[2], parts[3]


@router.get("", response_model=list[FieldOut])
def list_my_fields(
    user: deps.CurrentUser,
    bbox: str | None = Query(default=None, description="minx,miny,maxx,maxy"),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    return repository.list_fields(owner_id=user["id"], bbox=_parse_bbox(bbox), limit=limit)


@router.post("", response_model=FieldOut, status_code=status.HTTP_201_CREATED)
def create_field(payload: FieldCreate, user: deps.CurrentUser) -> dict[str, Any]:
    if user["role"] == "admin":
        # Admins own no parcels; they inspect everyone's.
        raise HTTPException(403, "管理员账号不用于录入田块，请使用农户账号")
    try:
        return repository.create_field(user["id"], payload.model_dump(exclude_none=True))
    except repository.FieldError as exc:
        _raise(exc)
        raise  # pragma: no cover


@router.get("/{field_id}", response_model=FieldOut)
def get_field(field_id: str, user: deps.CurrentUser) -> dict[str, Any]:
    try:
        row = repository.get_field(field_id, user["id"], allow_any=user["role"] == "admin")
    except repository.FieldError as exc:
        _raise(exc)
        raise  # pragma: no cover
    return repository.serialize(row, row["owner_name"])


@router.patch("/{field_id}", response_model=FieldOut)
def update_field(field_id: str, payload: FieldUpdate, user: deps.CurrentUser) -> dict[str, Any]:
    try:
        return repository.update_field(
            field_id,
            payload.model_dump(exclude_none=True),
            user["id"],
            allow_any=user["role"] == "admin",
        )
    except repository.FieldError as exc:
        _raise(exc)
        raise  # pragma: no cover


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field(field_id: str, user: deps.CurrentUser) -> Response:
    try:
        repository.delete_field(field_id, user["id"], allow_any=user["role"] == "admin")
    except repository.FieldError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{field_id}/irrigation")
def field_irrigation(
    field_id: str,
    user: deps.CurrentUser,
    days: int = Query(default=7, ge=1, le=180),
    start: str | None = Query(default=None, description="YYYY-MM-DD"),
    stage: str | None = Query(default=None, description="临时覆盖生育期"),
) -> dict[str, Any]:
    try:
        row = repository.get_field(field_id, user["id"], allow_any=user["role"] == "admin")
    except repository.FieldError as exc:
        _raise(exc)
        raise  # pragma: no cover

    rings = geo.rings_from_geojson(json.loads(row["geom_json"]))
    if not rings:
        raise HTTPException(422, "田块几何无效")
    start_date = dt.date.fromisoformat(start) if start else dt.date.today()
    # 系数按田块所在行政区解析：全局 → 省 → 市，就近覆盖
    resolved = parameter_service.resolve_for_ring(rings[0])
    plan = irrigation.compute_plan(
        ring=rings[0],
        area_m2=float(row["area_m2"]),
        crop=row["crop"],
        stage_key=stage or row["stage_key"],
        days=days,
        start=start_date,
        params=parameter_service.params_for_plan(resolved),
    )
    plan["field"] = {
        "id": row["id"],
        "name": row["name"],
        "owner_id": row["owner_id"],
    }
    plan["parameter_scope"] = {
        "scope": resolved.scope,
        "values": resolved.values,
        "sources": resolved.sources,
        "region": resolved.region,
    }
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO irrigation_logs(id, field_id, user_id, computed_at, days, request_json, payload_json)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                db.new_id("irr_"),
                row["id"],
                user["id"],
                db.now_iso(),
                days,
                json.dumps({"days": days, "start": start_date.isoformat(), "stage": stage}),
                json.dumps({"totals": plan["totals"]}, ensure_ascii=False),
            ),
        )
    return plan


@router.get("/catalog/crops")
def crop_catalog() -> list[dict[str, Any]]:
    return irrigation.crop_catalog()

