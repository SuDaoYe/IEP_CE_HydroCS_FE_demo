"""End-to-end smoke test: boots the app, exercises the main API paths."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = {"username": "admin", "password": "admin123"}
FARMER = {"username": "farmer1", "password": "123456"}


def login(client: TestClient, creds: dict) -> str:
    resp = client.post("/api/v1/auth/login", json=creds)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def main() -> int:
    with TestClient(app) as client:
        health = client.get("/healthz")
        print("healthz:", health.status_code)
        payload = health.json()
        print("  segmentation:", payload["segmentation"]["backend"])
        print("  et_grid:", "ready" if payload["et_grid"]["available"] else "missing")

        token = login(client, FARMER)
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/v1/auth/me", headers=headers).json()
        print("farmer:", me["name"], "fields:", me["field_count"])

        fields = client.get("/api/v1/fields", headers=headers).json()
        print("my fields:", [(f["name"], f["area_mu"], f["crop"]) for f in fields])

        if fields:
            fid = fields[0]["id"]
            started = time.time()
            plan = client.get(f"/api/v1/fields/{fid}/irrigation?days=7", headers=headers)
            elapsed = time.time() - started
            assert plan.status_code == 200, plan.text
            data = plan.json()
            print(f"irrigation [{data['method']}] {elapsed * 1000:.0f} ms")
            print("  totals:", data["totals"])
            day = data["series"][0]
            print(
                "  day0:",
                {k: day.get(k) for k in ("date", "et0_mm", "precip_mm", "pe_mm", "etc_mm", "net_mm", "volume_m3")},
            )
            print("  assumptions:", data["assumptions"][:2])

        started = time.time()
        summary = client.get("/api/v1/irrigation/summary?days=7", headers=headers).json()
        print(f"summary ({time.time() - started:.2f}s):", summary["totals"])

        admin_token = login(client, ADMIN)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        stats = client.get("/api/v1/admin/stats", headers=admin_headers)
        assert stats.status_code == 200, stats.text
        print("admin stats:", {k: stats.json()[k] for k in ("users", "fields", "daily_m3", "week_m3")})
        users = client.get("/api/v1/admin/users", headers=admin_headers).json()
        print("users:", [(u["username"], u["role"], u["field_count"]) for u in users])

        seg_status = client.get("/api/v1/segment/status").json()
        print("segment status:", seg_status["backend"], seg_status["error"])

        bbox = [118.7975, 37.7975, 118.8015, 37.8015]
        seg = client.post(
            "/api/v1/segment",
            json={"bbox": bbox, "zoom": 18, "provider": "esri"},
            headers=headers,
        )
        print("segment:", seg.status_code)
        if seg.status_code == 200:
            body = seg.json()
            print("  count:", body["count"], "backend:", body["backend"],
                  "total_ha:", body["total_area_ha"])
            print("  sample:", json.dumps(body["features"][0]["properties"], ensure_ascii=False)
                  if body["features"] else "none")
        else:
            print("  ", seg.text[:300])

        created = client.post(
            "/api/v1/fields",
            headers=headers,
            json={
                "name": "冒烟测试田",
                "crop": "maize",
                "stage_key": "jointing",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [118.7961, 37.7971], [118.7969, 37.7971],
                        [118.7969, 37.7977], [118.7961, 37.7977], [118.7961, 37.7971],
                    ]],
                },
                "source": "manual",
            },
        )
        print("create field:", created.status_code)
        if created.status_code == 201:
            field = created.json()
            print("  area:", field["area_mu"], "亩 /", field["area_ha"], "ha")
            deleted = client.delete(f"/api/v1/fields/{field['id']}", headers=headers)
            print("  delete:", deleted.status_code)
        else:
            print("  ", created.text[:300])

        search = client.get("/api/v1/imagery/search?q=东营").json()
        print("search:", search["source"], [r["name"] for r in search["results"]][:3])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
