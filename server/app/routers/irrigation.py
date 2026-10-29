"""Aggregate irrigation views across a user's fields."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from fastapi import APIRouter, Query

from .. import deps, repository
from ..services import geo, irrigation
from ..services import params as parameter_service

router = APIRouter(prefix="/irrigation", tags=["irrigation"])


@router.get("/crops")
def crops() -> list[dict[str, Any]]:
    return irrigation.crop_catalog()


@router.get("/summary")
def summary(
    user: deps.CurrentUser,
    days: int = Query(default=7, ge=1, le=180),
    start: str | None = None,
) -> dict[str, Any]:
    fields = repository.list_fields(owner_id=user["id"])
    start_date = dt.date.fromisoformat(start) if start else dt.date.today()
    plans: list[dict[str, Any]] = []
    scopes: dict[str, Any] = {}
    for field in fields:
        rings = geo.rings_from_geojson(field["geometry"])
        if not rings:
            continue
        resolved = parameter_service.resolve_for_ring(rings[0])
        scopes[resolved.scope] = {
            "values": resolved.values,
            "sources": resolved.sources,
            "region": resolved.region,
        }
        plan = irrigation.compute_plan(
            ring=rings[0],
            area_m2=float(field["area_m2"]),
            crop=field["crop"],
            stage_key=field["stage_key"],
            days=days,
            start=start_date,
            params=parameter_service.params_for_plan(resolved),
        )
        plan["field"] = {
            "id": field["id"],
            "name": field["name"],
            "area_mu": field["area_mu"],
            "crop": field["crop"],
            "crop_label": field["crop_label"],
            "stage_label": field["stage_label"],
        }
        plan["parameter_scope"] = resolved.scope
        plans.append(plan)

    totals = irrigation.summarize(plans)
    return {
        "start": start_date.isoformat(),
        "days": days,
        "params": next(iter(scopes.values()), {}).get("values", parameter_service.DEFAULTS),
        "parameter_scopes": scopes,
        "totals": totals,
        "fields": [
            {
                "field": plan["field"],
                "series": plan["series"],
                "totals": plan["totals"],
                "crop": plan["crop"],
                "area": plan["area"],
                "aggregates": plan["aggregates"],
            }
            for plan in plans
        ],
        "assumptions": plans[0]["assumptions"] if plans else [],
    }


@router.get("/params")
def params() -> dict[str, Any]:
    """Current defaults plus the regional parameter catalogue."""
    return {
        "current": parameter_service.DEFAULTS,
        "catalog": parameter_service.catalog(),
        "scopes": parameter_service.list_scopes(),
    }


@router.get("/logs")
def logs(user: deps.CurrentUser, limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    from .. import db

    rows = db.get_conn().execute(
        "SELECT l.id, l.field_id, l.computed_at, l.days, l.payload_json, f.name AS field_name"
        " FROM irrigation_logs l JOIN fields f ON f.id = l.field_id"
        " WHERE l.user_id = ? ORDER BY l.computed_at DESC LIMIT ?",
        (user["id"], limit),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "field_id": row["field_id"],
            "field_name": row["field_name"],
            "computed_at": row["computed_at"],
            "days": row["days"],
            "totals": json.loads(row["payload_json"]).get("totals", {}),
        }
        for row in rows
    ]
