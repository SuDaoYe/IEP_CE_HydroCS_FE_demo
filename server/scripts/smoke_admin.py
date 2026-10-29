"""Exercise the new geo / meteo / region admin endpoints."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def main() -> int:
    with TestClient(app) as client:
        admin = {
            "Authorization": "Bearer "
            + client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
            ).json()["access_token"]
        }

        print("--- geo ---")
        for query in ("东营", "垦利", "山东东营", "3705", "黄河口"):
            payload = client.get(f"/api/v1/geo/search?q={query}").json()
            hits = [(r["fullname"], r["level"]) for r in payload["results"][:3]]
            print(f"  {query!r} -> {payload['count']} hits {hits}")

        located = client.get("/api/v1/geo/locate?lat=37.7994&lon=118.7996").json()
        print("  locate demo:", located["province"]["name"] if located["province"] else None,
              "/", located["city"]["name"] if located["city"] else None)

        print("--- region overview ---")
        started = time.time()
        overview = client.get("/api/v1/admin/regions/overview?days=7", headers=admin).json()
        print(f"  {time.time() - started:.2f}s, unmatched={overview['unmatched']}")
        for region in overview["regions"]:
            print(
                f"  {region['fullname']}: {region['fields']} 块 / {region['users']} 户 / "
                f"{region['area_mu']} 亩 / {region['volume_m3']} m³"
            )

        print("--- region summary (370500 东营市) ---")
        started = time.time()
        summary = client.get("/api/v1/admin/regions/summary?code=370500&days=7", headers=admin).json()
        print(f"  {time.time() - started:.2f}s")
        print("  totals:", json.dumps(summary["totals"], ensure_ascii=False))
        print("  users:", [(u["name"], u["fields"], u["volume_m3"]) for u in summary["users"]])
        print("  cities:", [(c["name"], c["volume_m3"]) for c in summary["cities"]])

        print("--- region summary (370000 山东省, include children) ---")
        summary = client.get("/api/v1/admin/regions/summary?code=370000&days=7", headers=admin).json()
        print("  totals:", json.dumps(summary["totals"], ensure_ascii=False))
        print("  cities:", [(c["name"], c["volume_m3"]) for c in summary["cities"]])

        print("--- meteo ---")
        status = client.get("/api/v1/admin/meteo/status", headers=admin).json()
        print("  inbox:", status["inbox"], "files:", status["files"], "cube:", status["cube"]["available"])
        listing = client.get("/api/v1/admin/meteo/fs", headers=admin).json()
        print("  fs root:", listing["path"], "entries:", len(listing["entries"]))
        era_dir = Path(r"C:\Users\win11\Desktop\大创\HydroCS\2000-2004 era5数据")
        listing = client.get(
            "/api/v1/admin/meteo/fs", params={"path": str(era_dir)}, headers=admin
        ).json()
        print("  era5 dir entries:", len(listing["entries"]), "nc files:", listing["nc_count"])

        dry = client.post(
            "/api/v1/admin/meteo/scan",
            json={"path": str(era_dir), "ingest": False, "copy": False},
            headers=admin,
        ).json()
        print("  scan (dry):", dry["found"], "files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
