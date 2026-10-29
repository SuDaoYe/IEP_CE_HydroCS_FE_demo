"""Core unit + API tests. Run with: python -m pytest tests -q"""

from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.services import era5, geo, gridmath, irrigation  # noqa: E402


# --- geometry -------------------------------------------------------------


def test_geodesic_area_matches_known_box():
    # A 1°x1° cell at the equator is 12,308.8 km² on the WGS84 ellipsoid.
    ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    area = geo.geodesic_area_m2(ring)
    assert abs(area - 12_308_800_000) / 12_308_800_000 < 0.01


def test_geodesic_area_field_sized():
    # 0.001° x 0.001° near 37.8°N ≈ 9,750 m²
    ring = [(118.800, 37.800), (118.801, 37.800), (118.801, 37.801), (118.800, 37.801)]
    area = geo.geodesic_area_m2(ring)
    expected = 0.001 * 111_320 * math.cos(math.radians(37.8005)) * 0.001 * 110_574
    assert abs(area - expected) / expected < 0.02


def test_gcj02_round_trip_is_metre_accurate():
    lon, lat = 118.7996, 37.7994
    shifted = geo.wgs84_to_gcj02(lon, lat)
    assert shifted != (lon, lat)
    back = geo.gcj02_to_wgs84(*shifted)
    assert math.hypot((back[0] - lon) * 111_320 * 0.79, (back[1] - lat) * 110_574) < 1.0


def test_simplify_ring_keeps_shape():
    ring = [(118.80 + i * 0.00002, 37.80) for i in range(50)]
    ring += [(118.8010, 37.8005), (118.8000, 37.8005)]
    simplified = geo.simplify_ring(ring, 0.000001)
    assert len(simplified) < len(ring)
    assert len(simplified) >= 3


def test_normalize_ring_drops_closure_and_duplicates():
    ring = [(1.0, 2.0), (1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (1.0, 2.0)]
    assert geo.normalize_ring(ring) == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]


def test_tile_range_is_inclusive():
    bbox = (118.79, 37.79, 118.81, 37.81)
    x0, y0, x1, y1 = geo.tile_range(bbox, 18)
    assert x0 <= x1 and y0 <= y1


# --- irrigation -----------------------------------------------------------


def test_crop_catalogue_covers_stages():
    catalog = irrigation.crop_catalog()
    assert len(catalog) >= 8
    for crop in catalog:
        assert crop["stages"], crop["key"]
        for stage in crop["stages"]:
            assert 0.2 <= stage["kc"] <= 1.4


def test_stage_kc_falls_back_to_mid_season():
    kc, _, label = irrigation.stage_kc("rice", "not-a-stage")
    assert kc == 1.20
    assert label


def test_plan_is_internally_consistent():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(
        ring=ring,
        area_m2=area,
        crop="wheat",
        stage_key="jointing",
        days=7,
        start=dt.date(2024, 4, 10),
        params={"efficiency": 0.8, "kc_reference": 0.95, "kc_scale": 1.0},
    )
    assert len(plan["series"]) == 7
    assert plan["totals"]["volume_m3"] > 0
    for row in plan["series"]:
        assert row["volume_m3"] == pytest.approx(row["gross_mm"] * area / 1000, abs=0.02)
        assert row["gross_mm"] == pytest.approx(row["net_mm"] / 0.8, abs=0.005)
        assert row["net_mm"] == pytest.approx(
            max(0.0, row["etc_mm"] + row["percolation_mm"] - row["pe_mm"]), abs=0.005
        )
    assert any("有效降雨" in line for line in plan["assumptions"])


def test_paddy_adds_percolation():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    rice = irrigation.compute_plan(ring, area, "rice", "booting", 3, dt.date(2024, 6, 1), {})
    wheat = irrigation.compute_plan(ring, area, "wheat", "jointing", 3, dt.date(2024, 6, 1), {})
    assert rice["series"][0]["percolation_mm"] == 3.0
    assert wheat["series"][0]["percolation_mm"] == 0.0
    assert rice["series"][0]["net_mm"] > wheat["series"][0]["net_mm"]


def test_summary_aggregates_daily_volumes():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(ring, area, "maize", "jointing", 3, dt.date(2024, 5, 1), {})
    summary = irrigation.summarize([plan, plan])
    assert summary["fields"] == 2
    assert summary["week_m3"] == pytest.approx(plan["totals"]["volume_m3"] * 2, rel=1e-6)
    assert len(summary["by_date"]) == 3


# --- API ------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(db.settings, "database_path", tmp_path / "test.db")
    db._local.__dict__.clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    db._local.__dict__.clear()


def auth_headers(client, username="farmer1", password="123456"):
    token = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_rejects_bad_password(client):
    response = client.post("/api/v1/auth/login", json={"username": "farmer1", "password": "nope"})
    assert response.status_code == 401


def test_field_crud_and_area(client):
    headers = auth_headers(client)
    payload = {
        "name": "测试田",
        "crop": "wheat",
        "stage_key": "jointing",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [118.7960, 37.7970],
                    [118.7968, 37.7970],
                    [118.7968, 37.7976],
                    [118.7960, 37.7976],
                    [118.7960, 37.7970],
                ]
            ],
        },
    }
    created = client.post("/api/v1/fields", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    field = created.json()
    assert field["area_mu"] > 0
    assert field["kc"] == pytest.approx(1.05, abs=0.01)

    listed = client.get("/api/v1/fields", headers=headers).json()
    assert any(item["id"] == field["id"] for item in listed)

    patched = client.patch(
        f"/api/v1/fields/{field['id']}", json={"crop": "rice", "stage_key": "booting"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["crop"] == "rice"

    plan = client.get(f"/api/v1/fields/{field['id']}/irrigation?days=5", headers=headers)
    assert plan.status_code == 200
    body = plan.json()
    assert len(body["series"]) == 5
    assert body["crop"]["key"] == "rice"

    assert client.delete(f"/api/v1/fields/{field['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/fields/{field['id']}", headers=headers).status_code == 404


def test_other_farmers_field_is_hidden(client):
    headers = auth_headers(client, "farmer1", "123456")
    other = auth_headers(client, "farmer2", "123456")
    theirs = client.get("/api/v1/fields", headers=other).json()
    assert theirs
    response = client.get(f"/api/v1/fields/{theirs[0]['id']}", headers=headers)
    assert response.status_code == 404


def test_admin_guard(client):
    headers = auth_headers(client)
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
    admin = auth_headers(client, "admin", "admin123")
    assert client.get("/api/v1/admin/users", headers=admin).status_code == 200


def test_sync_is_idempotent(client):
    headers = auth_headers(client)
    op = {
        "op_id": "op_test_sync_0001",
        "kind": "field.create",
        "payload": {
            "name": "同步田",
            "crop": "maize",
            "stage_key": "jointing",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [118.7961, 37.7971],
                        [118.7966, 37.7971],
                        [118.7966, 37.7976],
                        [118.7961, 37.7976],
                        [118.7961, 37.7971],
                    ]
                ],
            },
        },
        "client_updated_at": db.now_iso(),
    }
    first = client.post("/api/v1/sync", json={"ops": [op]}, headers=headers).json()
    assert op["op_id"] in first["applied"]

    second = client.post("/api/v1/sync", json={"ops": [op]}, headers=headers).json()
    assert op["op_id"] in second["skipped"]
    assert len(second["fields"]) == len(first["fields"])


def test_optimistic_lock_conflict(client):
    headers = auth_headers(client)
    listed = client.get("/api/v1/fields", headers=headers).json()
    field = listed[0]
    ok = client.patch(f"/api/v1/fields/{field['id']}", json={"name": "改名", "rev": field["rev"]}, headers=headers)
    assert ok.status_code == 200
    stale = client.patch(f"/api/v1/fields/{field['id']}", json={"name": "再改", "rev": field["rev"]}, headers=headers)
    assert stale.status_code == 409


# --- ERA5 / FAO-56 --------------------------------------------------------


def test_saturation_vapour_pressure_matches_fao_table():
    assert float(era5.saturation_vapour_pressure(20.0)) == pytest.approx(2.338, abs=0.005)
    assert float(era5.saturation_vapour_pressure(30.0)) == pytest.approx(4.243, abs=0.005)


def test_penman_monteith_reproduces_fao56_example():
    """FAO-56 Example 18 (Davis, 6 July): ET0 ~= 4.0 mm/day."""
    u10 = 1.9 * math.log(67.8 * 10 - 5.42) / 4.87  # convert u2 target back to 10 m wind
    et0 = float(
        era5.penman_monteith(
            temp_c=21.5,
            vpd_kpa=0.50,
            wind10_ms=u10,
            rn_mj=13.28,
            pres_kpa=100.1,
        )
    )
    assert 3.8 <= et0 <= 4.1


def test_penman_monteith_responds_to_drivers():
    base = dict(temp_c=25.0, vpd_kpa=1.0, wind10_ms=2.5, rn_mj=15.0, pres_kpa=101.3)
    baseline = float(era5.penman_monteith(**base))
    wetter = float(era5.penman_monteith(**{**base, "vpd_kpa": 0.2}))
    sunnier = float(era5.penman_monteith(**{**base, "rn_mj": 22.0}))
    assert baseline > 0
    assert wetter < baseline
    assert sunnier > baseline


def test_effective_rainfall_is_capped():
    values = era5.effective_rainfall(np.array([0.0, 10.0, 100.0]), ratio=0.8, cap_mm=35.0)
    assert values[0] == 0.0
    assert values[1] == pytest.approx(8.0)
    assert values[2] == pytest.approx(35.0)


def test_gridmath_weights_normalise_across_cells():
    lon = np.arange(114.0, 121.01, 0.25)
    lat = np.arange(40.0, 31.99, -0.25)
    # Parcel centred on the cell-corner (118.875, 37.875): equal quarters of 4 cells.
    ring = [(118.76, 37.76), (118.99, 37.76), (118.99, 37.99), (118.76, 37.99)]
    weights = gridmath.overlap_weights(ring, lon, lat)
    assert len(weights) == 4
    assert sum(w for _, _, w in weights) == pytest.approx(1.0, abs=1e-6)
    assert all(w == pytest.approx(0.25, abs=1e-6) for _, _, w in weights)


def test_plan_uses_era5_balance():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(
        ring, area, "wheat", "jointing", 5, dt.date(2003, 4, 10),
        {"efficiency": 0.85, "effective_rain_ratio": 1.0},
    )
    assert plan["method"] == "era5-pm"
    assert plan["totals"]["pe_mm"] >= 0
    for row in plan["series"]:
        assert row["et0_mm"] > 0
        assert row["net_mm"] == pytest.approx(
            max(0.0, row["etc_mm"] + row["percolation_mm"] - row["pe_mm"]), abs=1e-6
        )
        assert row["etc_mm"] == pytest.approx(row["kc"] * row["et0_mm"], abs=0.002)
    assert any("ERA5" in line for line in plan["assumptions"])


def test_rain_override_zeroes_demand_when_generous():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(
        ring, area, "maize", "jointing", 3, dt.date(2003, 7, 1),
        {"efficiency": 0.85, "effective_rain_mm_day": 30.0},
    )
    assert plan["totals"]["volume_m3"] == 0.0


def test_plan_falls_back_to_etmonitor_without_era5(monkeypatch):
    monkeypatch.setattr(irrigation.era5, "load", lambda: None)
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(ring, area, "wheat", "jointing", 3, dt.date(2003, 4, 10), {})
    assert plan["method"] == "etmonitor-inverse"
    assert any("ETMonitor" in line for line in plan["assumptions"])


# --- admin divisions & meteo ingest ---------------------------------------


def test_admin_divisions_search_ranks_and_locates():
    from app.services import regions

    status = regions.status()
    assert status["available"], status
    hits = regions.search("垦利")
    assert hits and hits[0]["level"] == "district"
    assert "垦利" in hits[0]["fullname"]
    assert regions.search("3705")[0]["adcode"].startswith("3705")

    located = regions.locate(118.7996, 37.7994)
    assert located["province"]["adcode"].startswith("37")
    assert located["city"]["adcode"] == "370500"


def test_meteo_group_files_detects_era5_variables(tmp_path):
    from app.services import era5_build

    names = [
        "reanalysis_2m_temperature_Y2003_x.nc",
        "reanalysis_ 2m_dewpoin_temperature_Y2003_x.nc",
        "reanalysis_ 10u_Y2003_x.nc",
        "reanalysis_10v_Y2003_x.nc",
        "reanalysis_ surface_pressure_Y2003_x.nc",
        "reanalysis_ total_precipitation_Y2003_x.nc",
        "reanalysis_ssr_Y2003_x.nc",
        "reanalysis_ str_Y2003_x.nc",
        "notes.txt",
    ]
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"")
        paths.append(path)

    buckets, warnings = era5_build.group_files(paths)
    assert set(buckets) == {2003}
    assert set(buckets[2003]) == set(era5_build.VARIABLE_PATTERNS)
    assert any("notes.txt" in warning for warning in warnings)


def test_meteo_merge_appends_and_overwrites_dates():
    import numpy as np

    from app.services import era5_build, meteo

    lat = np.array([37.0, 36.75])
    lon = np.array([118.0, 118.25, 118.5])
    existing = {
        "dates": np.array(["2020-01-01", "2020-01-02"], dtype="U10"),
        **{
            key: np.arange(2 * 2 * 3, dtype=np.float32).reshape(2, 2, 3)
            for key in era5_build.DERIVED
        },
    }
    cube = era5_build.YearCube(
        year=2020,
        dates=["2020-01-02", "2020-01-03"],
        arrays={
            key: np.full((2, 2, 3), 9.0, dtype=np.float32) for key in era5_build.DERIVED
        },
    )
    dates, arrays, added, replaced = meteo._merge(existing, [cube], lat, lon)
    assert dates == ["2020-01-01", "2020-01-02", "2020-01-03"]
    assert added == 1 and replaced == 1
    assert arrays["et0"].shape == (3, 2, 3)
    # untouched day keeps its original values, the overlapping day is replaced
    assert arrays["et0"][0, 0, 0] == pytest.approx(existing["et0"][0, 0, 0])
    assert arrays["et0"][1, 0, 0] == pytest.approx(9.0)


def test_parent_quadrant_crops_the_right_corner(monkeypatch):
    """A child tile built from its parent must be the correct quadrant, upscaled."""
    import cv2

    from app.services import imagery

    parent = np.zeros((256, 256, 3), dtype=np.uint8)
    colours = {(0, 0): (10, 20, 200), (0, 1): (20, 200, 10), (1, 0): (200, 20, 10), (1, 1): (200, 200, 20)}
    for (row, col), colour in colours.items():
        parent[row * 128:(row + 1) * 128, col * 128:(col + 1) * 128] = colour
    ok, buffer = cv2.imencode(".jpg", parent, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
    assert ok

    monkeypatch.setattr(imagery, "fetch_tile", lambda *args, **kwargs: buffer.tobytes())

    for (row, col), colour in colours.items():
        child_y, child_x = row, col  # parent tile (0,0) has children (0,0),(1,0),(0,1),(1,1)
        cropped = imagery._parent_quadrant("esri", 10, child_x, child_y)
        assert cropped
        image = cv2.imdecode(np.frombuffer(cropped, np.uint8), cv2.IMREAD_COLOR)
        assert image.shape[:2] == (256, 256)
        mean = image[64:192, 64:192].reshape(-1, 3).mean(axis=0)
        expected = np.array(colour, dtype=np.float64)  # BGR
        assert np.allclose(mean, expected, atol=28), (mean, expected)


def test_plan_exposes_weekly_and_monthly_rollups():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(ring, area, "rice", "booting", 30, dt.date(2026, 10, 30), {})
    aggregates = plan["aggregates"]
    total = plan["totals"]["volume_m3"]

    assert len(aggregates["weekly"]) == 5  # 30 days -> 4 full weeks + 2 days
    assert aggregates["weekly"][-1]["days"] == 2
    assert sum(week["volume_m3"] for week in aggregates["weekly"]) == pytest.approx(total, abs=1.5)
    assert [month["label"] for month in aggregates["monthly"]] == ["2026-10", "2026-11"]
    assert sum(month["days"] for month in aggregates["monthly"]) == 30
    assert aggregates["cumulative"]["volume_m3"] == pytest.approx(total, abs=0.5)
    for bucket in aggregates["weekly"] + aggregates["monthly"]:
        assert bucket["volume_m3"] >= 0
        assert bucket["net_mm"] >= 0


def test_summary_merges_rollups_across_fields():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(ring, area, "maize", "jointing", 14, dt.date(2026, 5, 1), {})
    summary = irrigation.summarize([plan, plan])
    assert summary["aggregates"]["cumulative"]["days"] == 14
    assert summary["aggregates"]["weekly"][0]["volume_m3"] == pytest.approx(
        plan["aggregates"]["weekly"][0]["volume_m3"] * 2, rel=0.02
    )


# --- region-scoped parameters --------------------------------------------


def test_param_scope_inheritance(client):
    admin = auth_headers(client, "admin", "admin123")

    base = client.get("/api/v1/admin/params?scope=global", headers=admin).json()
    assert base["values"]["kc_scale"] == pytest.approx(1.0)
    assert base["sources"]["kc_scale"] in {"default", "global"}

    # province override propagates to its cities
    client.patch(
        "/api/v1/admin/params",
        json={"scope": "province:370000", "values": {"kc_scale": 1.2}},
        headers=admin,
    )
    city = client.get("/api/v1/admin/params?scope=city:370500", headers=admin).json()
    assert city["values"]["kc_scale"] == pytest.approx(1.2)
    assert city["sources"]["kc_scale"] == "province:370000"

    # city override wins and is attributed to the city
    client.patch(
        "/api/v1/admin/params",
        json={"scope": "city:370500", "values": {"kc_scale": 0.8}},
        headers=admin,
    )
    city = client.get("/api/v1/admin/params?scope=city:370500", headers=admin).json()
    assert city["values"]["kc_scale"] == pytest.approx(0.8)
    assert city["sources"]["kc_scale"] == "city:370500"

    # clearing the city value falls back to the province
    client.patch(
        "/api/v1/admin/params",
        json={"scope": "city:370500", "values": {"kc_scale": None}},
        headers=admin,
    )
    city = client.get("/api/v1/admin/params?scope=city:370500", headers=admin).json()
    assert city["values"]["kc_scale"] == pytest.approx(1.2)
    assert city["sources"]["kc_scale"] == "province:370000"


def test_param_scope_rejects_bad_values(client):
    admin = auth_headers(client, "admin", "admin123")
    bad = client.patch(
        "/api/v1/admin/params",
        json={"scope": "city:370500", "values": {"kc_scale": 99}},
        headers=admin,
    )
    assert bad.status_code == 422
    unknown = client.patch(
        "/api/v1/admin/params",
        json={"scope": "city:370500", "values": {"nope": 1}},
        headers=admin,
    )
    assert unknown.status_code == 422


def test_field_demand_follows_regional_params(client):
    admin = auth_headers(client, "admin", "admin123")
    farmer = auth_headers(client, "farmer1", "123456")
    field = client.get("/api/v1/fields", headers=farmer).json()[0]

    before = client.get(f"/api/v1/fields/{field['id']}/irrigation?days=7", headers=farmer).json()
    assert before["parameter_scope"]["scope"] == "city:370500"

    client.patch(
        "/api/v1/admin/params",
        json={"scope": "city:370500", "values": {"kc_scale": 2.0}},
        headers=admin,
    )
    after = client.get(f"/api/v1/fields/{field['id']}/irrigation?days=7", headers=farmer).json()
    assert after["parameter_scope"]["values"]["kc_scale"] == pytest.approx(2.0)
    # doubling Kc_scale lifts demand clearly (net of rain + percolation, so < 2x)
    assert after["totals"]["volume_m3"] > before["totals"]["volume_m3"] * 1.3

    # other regions keep the global value
    elsewhere = client.get("/api/v1/admin/params?scope=city:110101", headers=admin).json()
    assert elsewhere["values"]["kc_scale"] == pytest.approx(1.0)


def test_totals_report_both_net_and_gross_volumes():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(
        ring, area, "rice", "booting", 14, dt.date(2026, 5, 1), {"efficiency": 0.8}
    )
    totals = plan["totals"]

    # net = 需要灌溉的水量（补进根区），gross = 总水量（含输水损失）
    assert totals["net_volume_m3"] < totals["gross_volume_m3"]
    assert totals["gross_volume_m3"] == pytest.approx(totals["volume_m3"], rel=1e-6)
    assert totals["gross_volume_m3"] == pytest.approx(totals["net_volume_m3"] / 0.8, rel=0.02)
    assert totals["per_mu_net_m3"] < totals["per_mu_m3"]
    assert totals["daily_avg_net_m3"] < totals["daily_avg_m3"]

    for row in plan["series"]:
        assert row["net_volume_m3"] <= row["volume_m3"] + 1e-6

    aggregates = plan["aggregates"]
    assert sum(w["net_volume_m3"] for w in aggregates["weekly"]) == pytest.approx(
        totals["net_volume_m3"], abs=2.0
    )
    assert sum(m["volume_m3"] for m in aggregates["monthly"]) == pytest.approx(
        totals["gross_volume_m3"], abs=2.0
    )
    assert aggregates["cumulative"]["net_volume_m3"] == pytest.approx(totals["net_volume_m3"], abs=1.0)


def test_summary_reports_net_and_gross():
    ring = [(118.7975, 37.7990), (118.7985, 37.7990), (118.7985, 37.8000), (118.7975, 37.8000)]
    area = geo.geodesic_area_m2(ring)
    plan = irrigation.compute_plan(ring, area, "maize", "jointing", 7, dt.date(2026, 6, 1), {})
    summary = irrigation.summarize([plan])
    assert summary["week_net_m3"] < summary["week_m3"]
    assert summary["daily_net_m3"] <= summary["daily_m3"]
    assert summary["week_m3"] == pytest.approx(plan["totals"]["gross_volume_m3"], abs=1.0)
