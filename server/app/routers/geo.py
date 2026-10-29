"""Administrative divisions: search-as-you-type and coordinate lookup."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..services import regions

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/status")
def status() -> dict[str, Any]:
    return regions.status()


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=40),
    limit: int = Query(default=8, ge=1, le=20),
    level: str | None = Query(default=None, pattern="^(province|city)$"),
) -> dict[str, Any]:
    results = regions.search(q, limit=limit, level=level)
    return {"query": q, "count": len(results), "results": results}


@router.get("/regions")
def list_regions(
    level: str = Query(default="province", pattern="^(province|city)$"),
    parent: str | None = None,
) -> list[dict[str, Any]]:
    return regions.list_regions(level=level, parent=parent)


@router.get("/locate")
def locate(lat: float, lon: float) -> dict[str, Any]:
    return regions.locate(lon, lat)
