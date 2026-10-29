"""Region-scoped model parameters.

The tunable numbers are not universal constants — they calibrate the
Penman–Monteith chain for a climate. 华北的冬小麦区、东北的一季玉米区、
西北的干旱灌区，Kc 与降雨有效利用系数本来就不同，所以参数按行政区层级
继承而不是一套全局值：

    global  →  province:370000  →  city:370500

每个参数都记住它是从哪一层"继承"来的，管理端可以只覆盖某一个市。
``kc_reference`` 只在 ERA5 缺失、退回 ETMonitor 近似法时才参与计算。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .. import db
from . import geo, irrigation, regions

log = logging.getLogger(__name__)

PARAMS: list[dict[str, Any]] = [
    {
        "key": "kc_scale",
        "label": "区域 ET 校准系数",
        "hint": "对 Penman–Monteith 结果的系统性校准；干旱区常偏小、湿润区常偏大，±10% 以内属正常",
        "default": 1.0,
        "min": 0.3,
        "max": 2.0,
        "step": 0.02,
        "group": "气象标定",
    },
    {
        "key": "effective_rain_ratio",
        "label": "降雨有效利用系数",
        "hint": "降水中有多少能补进根系层：干旱少雨区偏高（0.85–0.95），湿润多雨区偏低（0.6–0.75）",
        "default": 1.0,
        "min": 0.0,
        "max": 1.2,
        "step": 0.05,
        "group": "气象标定",
    },
    {
        "key": "kc_reference",
        "label": "区域参考作物 Kc",
        "hint": "仅当 ERA5 资产缺失、退回 ETMonitor 近似法时使用（华北冬小麦 ≈ 0.95，南方水稻 ≈ 1.10）",
        "default": irrigation.DEFAULT_KC_REFERENCE,
        "min": 0.2,
        "max": 1.6,
        "step": 0.05,
        "group": "降级路径",
    },
    {
        "key": "effective_rain_mm_day",
        "label": "固定有效降雨（mm/天）",
        "hint": "非 0 时强制覆盖 ERA5 降水估算，用于缺气象数据的老灌区",
        "default": 0.0,
        "min": 0.0,
        "max": 30.0,
        "step": 0.5,
        "group": "降级路径",
    },
    {
        "key": "efficiency",
        "label": "灌溉水利用系数 η",
        "hint": "工程属性（渠灌 0.55–0.65、喷灌 0.75–0.85、滴灌 0.90–0.95），但各区差别大，同样按区域设",
        "default": 0.85,
        "min": 0.3,
        "max": 1.0,
        "step": 0.01,
        "group": "工程",
    },
]

DEFAULTS: dict[str, float] = {item["key"]: float(item["default"]) for item in PARAMS}
PARAM_KEYS = tuple(DEFAULTS)


@dataclass(slots=True)
class Resolved:
    scope: str
    values: dict[str, float]
    sources: dict[str, str]
    region: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "values": self.values,
            "sources": self.sources,
            "region": self.region,
        }


# --- storage --------------------------------------------------------------


def _read_scope(scope: str) -> dict[str, float]:
    rows = db.get_conn().execute(
        "SELECT param, value FROM param_scopes WHERE scope = ?", (scope,)
    ).fetchall()
    return {row["param"]: float(row["value"]) for row in rows}


def _write_scope(scope: str, param: str, value: float | None, user_id: str | None) -> None:
    if value is None:
        with db.transaction() as conn:
            conn.execute("DELETE FROM param_scopes WHERE scope = ? AND param = ?", (scope, param))
        return
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO param_scopes(scope, param, value, updated_at, updated_by)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(scope, param) DO UPDATE SET value=excluded.value,"
            " updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (scope, param, float(value), db.now_iso(), user_id),
        )


def migrate_legacy() -> None:
    """把旧版单一的 ``params['irrigation']`` 迁移成 global 作用域。"""
    existing = db.get_conn().execute("SELECT COUNT(*) AS n FROM param_scopes").fetchone()["n"]
    if existing:
        return
    legacy = db.get_param("irrigation", None)
    if not isinstance(legacy, dict) or not legacy:
        return
    for key, value in legacy.items():
        if key in DEFAULTS and isinstance(value, (int, float)):
            _write_scope("global", key, float(value), None)
    log.info("migrated legacy irrigation params into global scope: %s", list(legacy))


# --- scopes ---------------------------------------------------------------


def parse_scope(scope: str) -> tuple[str, str | None]:
    if not scope or scope == "global":
        return "global", None
    if ":" in scope:
        kind, _, code = scope.partition(":")
        if kind in {"province", "city"} and code:
            return kind, code
    raise ValueError(f"未知参数作用域：{scope}")


def chain_for_city(city_code: str | None) -> list[str]:
    if not city_code:
        return ["global"]
    region = regions.get_region(city_code)
    province = region.parent if region is not None else None
    chain = ["global"]
    if province:
        chain.append(f"province:{province}")
    chain.append(f"city:{city_code}")
    return chain


def chain_for_province(province_code: str) -> list[str]:
    return ["global", f"province:{province_code}"]


def resolve(chain: list[str]) -> Resolved:
    values = dict(DEFAULTS)
    sources = {key: "default" for key in DEFAULTS}
    for scope in chain:
        overrides = _read_scope(scope)
        for key, value in overrides.items():
            if key in values:
                values[key] = value
                sources[key] = scope
    region: dict[str, Any] = {"chain": chain}
    if chain[-1].startswith("city:"):
        found = regions.get_region(chain[-1].split(":", 1)[1])
        region["name"] = found.to_dict() if found else None
    return Resolved(scope=chain[-1], values=values, sources=sources, region=region)


def resolve_for_scope(scope: str) -> Resolved:
    kind, code = parse_scope(scope)
    if kind == "global":
        return resolve(["global"])
    if kind == "province":
        return resolve(chain_for_province(code or ""))
    return resolve(chain_for_city(code))


def resolve_for_point(lon: float, lat: float) -> Resolved:
    located = regions.locate(lon, lat)
    city = located.get("city")
    province = located.get("province")
    if city is None and province is None:
        return resolve(["global"])
    chain = ["global"]
    if province:
        chain.append(f"province:{province['adcode']}")
    if city:
        chain.append(f"city:{city['adcode']}")
    resolved = resolve(chain)
    resolved.region = {
        "chain": chain,
        "province": province["name"] if province else None,
        "city": city["name"] if city else None,
        "adcode": (city or province or {}).get("adcode"),
    }
    return resolved


def resolve_for_ring(ring: geo.Ring) -> Resolved:
    lon, lat = geo.ring_centroid(ring)
    return resolve_for_point(lon, lat)


def params_for_plan(resolved: Resolved) -> dict[str, float]:
    """Shape the resolved values the way ``irrigation.compute_plan`` expects."""
    return {
        "efficiency": resolved.values["efficiency"],
        "kc_reference": resolved.values["kc_reference"],
        "kc_scale": resolved.values["kc_scale"],
        "effective_rain_ratio": resolved.values["effective_rain_ratio"],
        "effective_rain_mm_day": resolved.values["effective_rain_mm_day"],
    }


# --- admin operations -----------------------------------------------------


def catalog() -> list[dict[str, Any]]:
    return PARAMS


def list_scopes() -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT scope, COUNT(*) AS n, MAX(updated_at) AS updated_at"
        " FROM param_scopes WHERE scope != 'global' GROUP BY scope ORDER BY updated_at DESC"
    ).fetchall()
    items = []
    for row in rows:
        kind, code = parse_scope(row["scope"])
        region = regions.get_region(code or "") if code else None
        items.append(
            {
                "scope": row["scope"],
                "kind": kind,
                "adcode": code,
                "name": region.fullname if region is not None else None,
                "overrides": row["n"],
                "updated_at": row["updated_at"],
            }
        )
    return items


def describe(scope: str) -> dict[str, Any]:
    kind, code = parse_scope(scope)
    chain = ["global"] if kind == "global" else (
        chain_for_province(code or "") if kind == "province" else chain_for_city(code)
    )
    resolved = resolve(chain)
    overrides = {level: _read_scope(level) for level in chain}
    region = regions.get_region(code or "") if code else None
    return {
        "scope": resolved.scope,
        "kind": kind,
        "adcode": code,
        "region": region.to_dict() if region is not None else None,
        "chain": chain,
        "values": resolved.values,
        "sources": resolved.sources,
        "overrides": overrides,
        "defaults": DEFAULTS,
        "catalog": PARAMS,
        "divisions": regions.status(),
    }


def update(scope: str, values: dict[str, float | None], user_id: str | None) -> dict[str, Any]:
    kind, code = parse_scope(scope)
    if kind != "global" and not code:
        raise ValueError("省级/市级覆盖需要提供 adcode")
    if kind == "city" and regions.get_region(code or "") is None:
        raise ValueError(f"未知行政区：{code}")
    changed = []
    for key, value in values.items():
        if key not in DEFAULTS:
            raise ValueError(f"未知参数：{key}")
        if value is not None:
            spec = next(item for item in PARAMS if item["key"] == key)
            if not (spec["min"] <= float(value) <= spec["max"]):
                raise ValueError(f"{spec['label']} 超出范围 {spec['min']}–{spec['max']}")
        _write_scope(scope, key, None if value is None else float(value), user_id)
        changed.append(key)
    log.info("param scope %s updated by %s: %s", scope, user_id, changed)
    return describe(scope)


def snapshot() -> str:
    return json.dumps(describe("global"), ensure_ascii=False)
