"""Generate realistic demo parcels from the segmentation model.

Runs the same pipeline the API uses, picks four well-formed parcels near the
demo centre, assigns crop/stage metadata and writes ``app/seed_fields.json``.
``seed.py`` prefers this file over its built-in rectangles so the first-run demo
looks like actual field boundaries rather than boxes.

Usage::

    python scripts/build_seed_fields.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER))

from app.services import imagery, segmentation  # noqa: E402

CENTRE = (118.7996, 37.7994)
SPAN = 0.0022  # ≈ 400 m half-width

CROP_PLAN = [
    # (owner, name, crop, stage, plant_date, min_ha, max_ha)
    ("farmer1", "东片一号田", "rice", "booting", "2026-05-12", 0.55, 1.6),
    ("farmer1", "东片二号田", "wheat", "filling", "2025-10-08", 0.45, 1.4),
    ("farmer2", "南洼三号田", "maize", "tasseling", "2026-06-10", 0.45, 1.4),
    ("farmer2", "南洼四号田", "soybean", "flowering", "2026-06-18", 0.35, 1.3),
]


def main() -> int:
    lon, lat = CENTRE
    bbox = (lon - SPAN, lat - SPAN * 0.8, lon + SPAN, lat + SPAN * 0.8)
    print(f"segmenting {bbox} ...")
    mosaic = imagery.build_mosaic(bbox, zoom=18, provider="esri")
    result = segmentation.segment(mosaic, min_area_ha=0.02, conf=0.3)
    print(f"  {result['count']} parcels, {result['total_area_ha']} ha, backend={result['backend']}")

    parcels = []
    for feature in result["features"]:
        props = feature["properties"]
        area_ha = props["area_ha"]
        ring = [(round(p[0], 6), round(p[1], 6)) for p in feature["geometry"]["coordinates"][0][:-1]]
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        parcels.append({"area_ha": area_ha, "ring": ring, "cx": cx, "cy": cy,
                        "confidence": props["confidence"]})

    # Prefer parcels closest to the centre, spread across the four quadrants.
    quadrants: dict[tuple[bool, bool], dict] = {}
    for parcel in sorted(parcels, key=lambda p: -p["area_ha"]):
        key = (parcel["cx"] >= lon, parcel["cy"] >= lat)
        if key in quadrants:
            continue
        for _, _, _, _, _, low, high in CROP_PLAN:
            if low <= parcel["area_ha"] <= high:
                quadrants[key] = parcel
                break
    chosen = list(quadrants.values())
    if len(chosen) < 4:
        for parcel in parcels:
            if parcel not in chosen:
                chosen.append(parcel)
            if len(chosen) == 4:
                break

    records = []
    for (owner, name, crop, stage, planted, *_rest), parcel in zip(CROP_PLAN, chosen):
        records.append(
            {
                "owner": owner,
                "name": name,
                "crop": crop,
                "stage_key": stage,
                "plant_date": planted,
                "ring": parcel["ring"],
                "area_ha": parcel["area_ha"],
                "confidence": parcel["confidence"],
            }
        )
        print(f"  {name}: {parcel['area_ha']:.2f} ha, {len(parcel['ring'])} vertices")

    out = SERVER / "app" / "seed_fields.json"
    payload = {
        "source": "segmentation",
        "centre": list(CENTRE),
        "bbox": list(bbox),
        "backend": result["backend"],
        "fields": records,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
