"""Demo seed: one admin, two farmers, four parcels inside the ET grid domain.

Coordinates sit in the Yellow River Delta farmland (垦利/河口), the area where
the trained segmentation model performs best on Esri imagery.

`scripts/build_seed_fields.py` writes real parcel outlines produced by the
segmentation model into ``seed_fields.json``; this module prefers that file and
falls back to hand-drawn rectangles when it is missing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import db, security
from .services import geo

log = logging.getLogger(__name__)

ACCOUNTS = [
    {
        "username": "admin",
        "password": "admin123",
        "name": "管理员",
        "phone": "13800000000",
        "role": "admin",
    },
    {
        "username": "farmer1",
        "password": "123456",
        "name": "王建国",
        "phone": "13800000001",
        "role": "farmer",
    },
    {
        "username": "farmer2",
        "password": "123456",
        "name": "李秀兰",
        "phone": "13800000002",
        "role": "farmer",
    },
]

# (owner, name, crop, stage, plant_date, ring around the parcel centre)
FIELDS = [
    (
        "farmer1",
        "东片一号田",
        "rice",
        "booting",
        "2026-05-12",
        [
            (118.79763, 37.80069),
            (118.79902, 37.80072),
            (118.79908, 37.79991),
            (118.79767, 37.79988),
        ],
    ),
    (
        "farmer1",
        "东片二号田",
        "wheat",
        "filling",
        "2025-10-08",
        [
            (118.79935, 37.80107),
            (118.80061, 37.80110),
            (118.80066, 37.80036),
            (118.79940, 37.80033),
        ],
    ),
    (
        "farmer2",
        "南洼三号田",
        "maize",
        "tasseling",
        "2026-06-10",
        [
            (118.79811, 37.79858),
            (118.79949, 37.79861),
            (118.79954, 37.79783),
            (118.79816, 37.79780),
        ],
    ),
    (
        "farmer2",
        "南洼四号田",
        "soybean",
        "flowering",
        "2026-06-18",
        [
            (118.80002, 37.79876),
            (118.80128, 37.79879),
            (118.80133, 37.79802),
            (118.80007, 37.79799),
        ],
    ),
]

_SEED_JSON = Path(__file__).with_name("seed_fields.json")
_USING_MODEL_SEED = False


def _load_fields() -> list[tuple[str, str, str, str, str, list[tuple[float, float]]]]:
    """Prefer model-derived parcels, fall back to the built-in rectangles."""
    global _USING_MODEL_SEED
    if not _SEED_JSON.is_file():
        return FIELDS
    try:
        payload = json.loads(_SEED_JSON.read_text(encoding="utf-8"))
        loaded = [
            (
                item["owner"],
                item["name"],
                item["crop"],
                item["stage_key"],
                item["plant_date"],
                [(float(lon), float(lat)) for lon, lat in item["ring"]],
            )
            for item in payload["fields"]
        ]
        if len(loaded) >= 4:
            _USING_MODEL_SEED = True
            log.info("seed parcels loaded from %s (%s)", _SEED_JSON.name, payload.get("backend"))
            return loaded
    except (KeyError, ValueError, OSError) as exc:
        log.warning("seed_fields.json unusable (%s), falling back to rectangles", exc)
    return FIELDS


def ensure_seed() -> None:
    conn = db.get_conn()
    if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] > 0:
        return

    ids: dict[str, str] = {}
    with db.transaction() as txn:
        for account in ACCOUNTS:
            user_id = db.new_id("u_")
            ids[account["username"]] = user_id
            txn.execute(
                "INSERT INTO users(id, username, phone, name, pass_hash, role, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (
                    user_id,
                    account["username"],
                    account["phone"],
                    account["name"],
                    security.hash_password(account["password"]),
                    account["role"],
                    db.now_iso(),
                ),
            )

        for owner, name, crop, stage, planted, ring in _load_fields():
            area = geo.geodesic_area_m2(ring)
            bbox = geo.bbox_of_points(ring)
            txn.execute(
                "INSERT INTO fields(id, owner_id, name, crop, stage_key, plant_date, geom_json,"
                " bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, area_m2, source, confidence,"
                " created_at, updated_at, rev) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (
                    db.new_id("f_"),
                    ids[owner],
                    name,
                    crop,
                    stage,
                    planted,
                    json.dumps(
                        {
                            "type": "Polygon",
                            "coordinates": [
                                [[round(x, 7), round(y, 7)] for x, y in ring + [ring[0]]]
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    bbox[0],
                    bbox[1],
                    bbox[2],
                    bbox[3],
                    area,
                    "segment" if _USING_MODEL_SEED else "manual",
                    None,
                    db.now_iso(),
                    db.now_iso(),
                ),
            )

    db.set_param(
        "irrigation",
        {
            "efficiency": 0.85,
            "kc_reference": 0.95,
            "kc_scale": 1.0,
            "effective_rain_mm_day": 0.0,
            "effective_rain_ratio": 1.0,
        },
    )
    log.info("seeded %s users and %s fields", len(ACCOUNTS), len(FIELDS))


if __name__ == "__main__":  # pragma: no cover
    db.init_db()
    ensure_seed()
    print("seed complete")
