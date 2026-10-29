"""Debug: visualise segmentation output and check polygon overlap inflation."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import geo, imagery, segmentation  # noqa: E402

BBOX = (118.7975, 37.7975, 118.8015, 37.8015)


def main() -> None:
    mosaic = imagery.build_mosaic(BBOX, zoom=18, provider="esri")
    print("mosaic", mosaic.width, "x", mosaic.height, "zoom", mosaic.zoom)
    print("extent", round(mosaic.west, 6), round(mosaic.south, 6),
          round(mosaic.east, 6), round(mosaic.north, 6))
    extent_area_ha = geo.geodesic_area_m2([
        (mosaic.west, mosaic.south), (mosaic.east, mosaic.south),
        (mosaic.east, mosaic.north), (mosaic.west, mosaic.north),
    ]) / 1e4
    bbox_area_ha = geo.geodesic_area_m2([
        (BBOX[0], BBOX[1]), (BBOX[2], BBOX[1]), (BBOX[2], BBOX[3]), (BBOX[0], BBOX[3]),
    ]) / 1e4
    print(f"mosaic area {extent_area_ha:.2f} ha, requested bbox {bbox_area_ha:.2f} ha")

    result = segmentation.segment(mosaic, min_area_ha=0.01, conf=0.25)
    total = sum(f["properties"]["area_ha"] for f in result["features"])
    print(f"features {result['count']} total {total:.2f} ha (coverage {total / extent_area_ha * 100:.0f}%)")

    # paint polygons in pixel space to eyeball duplicates / gaps
    canvas = mosaic.image.copy()
    rng = np.random.default_rng(7)
    for feature in result["features"]:
        ring = [(p[0], p[1]) for p in feature["geometry"]["coordinates"][0][:-1]]
        pts = []
        for lon, lat in ring:
            px = (lon - mosaic.west) / (mosaic.east - mosaic.west) * mosaic.width
            py = (mosaic.north - lat) / (mosaic.north - mosaic.south) * mosaic.height
            pts.append([int(px), int(py)])
        color = tuple(int(c) for c in rng.integers(60, 255, 3))
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [np.array(pts, np.int32)], color)
        canvas = cv2.addWeighted(overlay, 0.35, canvas, 0.65, 0)

    out = Path(__file__).parent / "seg_debug.png"
    ok, buf = cv2.imencode(".png", canvas)
    out.write_bytes(buf.tobytes())
    print("wrote", out)


if __name__ == "__main__":
    main()
