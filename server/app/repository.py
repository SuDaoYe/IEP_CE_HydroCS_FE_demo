"""Field persistence and serialisation (shared by fields, sync and admin routes)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import db
from .services import geo, irrigation

_ALLOWED_PATCH = {"name", "crop", "stage_key", "plant_date", "note"}


class FieldError(Exception):
    """Domain error carrying an HTTP status code."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _normalise_geometry(geometry: dict[str, Any]) -> tuple[dict[str, Any], tuple[float, float, float, float], float]:
    rings = geo.rings_from_geojson(geometry)
    if not rings:
        raise FieldError("几何无效：没有有效的多边形顶点", 422)
    cleaned = []
    for ring in rings:
        normalised = geo.normalize_ring(ring)
        if len(normalised) < 3:
            raise FieldError("几何无效：至少需要 3 个顶点", 422)
        cleaned.append(normalised)
    polygons = [
        [[[round(lon, 7), round(lat, 7)] for lon, lat in ring + [ring[0]]]] for ring in cleaned
    ]
    if len(polygons) == 1:
        normalised_geometry: dict[str, Any] = {"type": "Polygon", "coordinates": polygons[0]}
    else:
        normalised_geometry = {"type": "MultiPolygon", "coordinates": polygons}
    bbox = geo.bbox_of_points([p for ring in cleaned for p in ring])
    area = sum(geo.geodesic_area_m2(ring) for ring in cleaned)
    if area <= 0.5:
        raise FieldError("面积过小，请重新绘制", 422)
    return normalised_geometry, bbox, area


def serialize(row: sqlite3.Row, owner_name: str | None = None) -> dict[str, Any]:
    area_m2 = float(row["area_m2"])
    crop = row["crop"]
    stage_key = row["stage_key"]
    kc, crop_label, stage_label = irrigation.stage_kc(crop, stage_key)
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "owner_name": owner_name,
        "name": row["name"],
        "crop": crop,
        "stage_key": stage_key,
        "plant_date": row["plant_date"],
        "note": row["note"],
        "geometry": json.loads(row["geom_json"]),
        "area_m2": round(area_m2, 1),
        "area_mu": round(area_m2 * geo.MU_PER_M2, 3),
        "area_ha": round(area_m2 / 10_000.0, 4),
        "source": row["source"],
        "confidence": row["confidence"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "rev": row["rev"],
        "kc": round(kc, 3),
        "crop_label": crop_label,
        "stage_label": stage_label,
    }


_OWNER_JOIN = (
    "SELECT f.*, u.name AS owner_name FROM fields f "
    "JOIN users u ON u.id = f.owner_id "
)


def list_fields(
    owner_id: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    include_deleted: bool = False,
    limit: int = 500,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("f.deleted_at IS NULL")
    if owner_id:
        clauses.append("f.owner_id = ?")
        params.append(owner_id)
    if bbox:
        clauses.append("f.bbox_maxx >= ? AND f.bbox_minx <= ? AND f.bbox_maxy >= ? AND f.bbox_miny <= ?")
        params.extend([bbox[0], bbox[2], bbox[1], bbox[3]])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"{_OWNER_JOIN}{where} ORDER BY f.updated_at DESC LIMIT ?"
    params.append(limit)
    rows = db.get_conn().execute(sql, params).fetchall()
    return [serialize(row, row["owner_name"]) for row in rows]


def get_field(field_id: str, user_id: str | None = None, allow_any: bool = False) -> sqlite3.Row:
    sql = f"{_OWNER_JOIN}WHERE f.id = ?"
    params: list[Any] = [field_id]
    if not allow_any and user_id:
        sql += " AND f.owner_id = ?"
        params.append(user_id)
    row = db.get_conn().execute(sql, params).fetchone()
    if row is None or (row["deleted_at"] is not None and not allow_any):
        raise FieldError("田块不存在或无权访问", 404)
    return row


def create_field(owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    geometry, bbox, area = _normalise_geometry(payload["geometry"])
    field_id = payload.get("id") or db.new_id("f_")
    stamp = db.now_iso()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO fields(id, owner_id, name, crop, stage_key, plant_date, geom_json,"
            " bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, area_m2, source, confidence, note,"
            " created_at, updated_at, rev) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (
                field_id,
                owner_id,
                payload.get("name") or "未命名田块",
                payload.get("crop"),
                payload.get("stage_key"),
                payload.get("plant_date"),
                json.dumps(geometry, ensure_ascii=False),
                bbox[0],
                bbox[1],
                bbox[2],
                bbox[3],
                area,
                payload.get("source", "manual"),
                payload.get("confidence"),
                payload.get("note"),
                payload.get("created_at") or stamp,
                stamp,
            ),
        )
    return serialize(get_field(field_id, allow_any=True), None)


def update_field(field_id: str, payload: dict[str, Any], user_id: str, allow_any: bool = False) -> dict[str, Any]:
    row = get_field(field_id, user_id, allow_any=allow_any)
    sets: list[str] = []
    params: list[Any] = []

    geometry = payload.get("geometry")
    if geometry:
        normalised, bbox, area = _normalise_geometry(geometry)
        sets += ["geom_json = ?", "bbox_minx = ?", "bbox_miny = ?", "bbox_maxx = ?",
                 "bbox_maxy = ?", "area_m2 = ?"]
        params += [json.dumps(normalised, ensure_ascii=False), bbox[0], bbox[1], bbox[2], bbox[3], area]
        if payload.get("source"):
            sets.append("source = ?")
            params.append(payload["source"])

    for key in _ALLOWED_PATCH:
        if key in payload and payload[key] is not None:
            sets.append(f"{key} = ?")
            params.append(payload[key])

    if not sets:
        return serialize(row, row["owner_name"] if "owner_name" in row.keys() else None)

    expected_rev = payload.get("rev")
    where = "id = ? AND deleted_at IS NULL"
    params_where: list[Any] = [field_id]
    if expected_rev is not None:
        where += " AND rev = ?"
        params_where.append(int(expected_rev))

    sets.append("updated_at = ?")
    params.append(db.now_iso())
    sets.append("rev = rev + 1")
    params.extend(params_where)

    with db.transaction() as conn:
        cursor = conn.execute(f"UPDATE fields SET {', '.join(sets)} WHERE {where}", params)
        if cursor.rowcount == 0 and expected_rev is not None:
            raise FieldError("田块已被其他设备修改，请刷新后重试", 409)
    return serialize(get_field(field_id, user_id, allow_any=allow_any), None)


def delete_field(field_id: str, user_id: str, allow_any: bool = False) -> None:
    get_field(field_id, user_id, allow_any=allow_any)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE fields SET deleted_at = ?, updated_at = ?, rev = rev + 1 WHERE id = ?",
            (db.now_iso(), db.now_iso(), field_id),
        )


def owner_name(owner_id: str) -> str | None:
    row = db.get_conn().execute("SELECT name FROM users WHERE id = ?", (owner_id,)).fetchone()
    return row["name"] if row else None
