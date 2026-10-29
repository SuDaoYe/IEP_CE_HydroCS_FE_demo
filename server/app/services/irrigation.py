"""Irrigation water requirement engine.

Two balance methods, picked at runtime:

**ERA5 + FAO-56 (preferred)** — with the ERA5 cube we get a proper reference
evapotranspiration and effective rainfall, so the textbook balance applies::

    ETc   = Kc(crop, stage) * ET0 * kc_scale
    net   = max(0, ETc + percolation - Pe)
    gross = net / efficiency
    volume = gross(mm) * area(m²) / 1000        # m³/day

**ETMonitor only (fallback)** — without ERA5 the observed ET field has to stand
in for `ETc`, and ET0 is back-solved assuming a regional crop coefficient::

    ET0   = ET_grid / Kc_reference
    ETc   = Kc * ET0 * kc_scale
    …same net/gross/volume as above, with Pe from the admin parameter.

Every response says which method ran and what was assumed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import era5, et_grid, geo

# FAO-56 style crop coefficients, trimmed to the stages farmers actually pick.
CROPS: dict[str, dict[str, Any]] = {
    "wheat": {
        "label": "冬小麦",
        "stages": [
            ("seedling", "苗期", 0.40),
            ("tillering", "分蘖期", 0.60),
            ("jointing", "拔节期", 1.05),
            ("heading", "抽穗期", 1.15),
            ("filling", "灌浆期", 1.10),
            ("maturity", "成熟期", 0.35),
        ],
    },
    "maize": {
        "label": "夏玉米",
        "stages": [
            ("seedling", "苗期", 0.40),
            ("jointing", "拔节期", 1.00),
            ("tasseling", "抽雄期", 1.20),
            ("filling", "灌浆期", 1.10),
            ("maturity", "成熟期", 0.50),
        ],
    },
    "rice": {
        "label": "水稻",
        "paddy": True,
        "percolation_mm_day": 3.0,
        "stages": [
            ("transplanting", "返青期", 1.10),
            ("tillering", "分蘖期", 1.10),
            ("booting", "拔节孕穗期", 1.20),
            ("heading", "抽穗开花期", 1.20),
            ("filling", "灌浆期", 1.05),
            ("maturity", "成熟期", 0.90),
        ],
    },
    "soybean": {
        "label": "大豆",
        "stages": [
            ("seedling", "苗期", 0.40),
            ("branching", "分枝期", 1.00),
            ("flowering", "开花期", 1.10),
            ("podding", "结荚期", 1.10),
            ("maturity", "成熟期", 0.50),
        ],
    },
    "cotton": {
        "label": "棉花",
        "stages": [
            ("seedling", "苗期", 0.35),
            ("squaring", "蕾期", 0.75),
            ("boll", "花铃期", 1.15),
            ("opening", "吐絮期", 0.85),
        ],
    },
    "rapeseed": {
        "label": "油菜",
        "stages": [
            ("seedling", "苗期", 0.45),
            ("bolting", "抽薹期", 1.00),
            ("flowering", "开花期", 1.15),
            ("podding", "角果期", 1.05),
            ("maturity", "成熟期", 0.40),
        ],
    },
    "potato": {
        "label": "马铃薯",
        "stages": [
            ("seedling", "苗期", 0.45),
            ("vegetative", "发棵期", 0.95),
            ("tuber", "结薯期", 1.15),
            ("maturity", "成熟期", 0.75),
        ],
    },
    "vegetable": {
        "label": "蔬菜",
        "stages": [
            ("seedling", "苗期", 0.60),
            ("vegetative", "生长期", 0.95),
            ("harvest", "采收期", 1.05),
        ],
    },
    "orchard": {
        "label": "果树",
        "stages": [
            ("bud", "萌芽期", 0.50),
            ("bloom", "开花期", 0.75),
            ("fruit", "果实膨大期", 0.90),
            ("maturity", "成熟期", 0.70),
        ],
    },
    "other": {
        "label": "其他",
        "stages": [
            ("seedling", "苗期", 0.45),
            ("vegetative", "生长期", 0.95),
            ("maturity", "成熟期", 0.60),
        ],
    },
}

DEFAULT_KC_REFERENCE = 0.95  # winter wheat mid-season, dominant crop in the domain


def crop_catalog() -> list[dict]:
    return [
        {
            "key": key,
            "label": spec["label"],
            "paddy": spec.get("paddy", False),
            "percolation_mm_day": spec.get("percolation_mm_day", 0.0),
            "stages": [{"key": s[0], "label": s[1], "kc": s[2]} for s in spec["stages"]],
        }
        for key, spec in CROPS.items()
    ]


def stage_kc(crop: str | None, stage_key: str | None) -> tuple[float, str, str]:
    """Return (kc, crop_label, stage_label); falls back to a mid-season value."""
    spec = CROPS.get(crop or "", CROPS["other"])
    stages = spec["stages"]
    for key, label, kc in stages:
        if key == stage_key:
            return kc, spec["label"], label
    if stage_key:
        return stages[len(stages) // 2][2], spec["label"], stages[len(stages) // 2][1]
    return stages[0][2], spec["label"], stages[0][1]


def _bucket(rows: list[dict], label: str) -> dict:
    """Sum one group of daily rows into a period total.

    两个口径都要给出：
    * ``net_volume_m3``  —— 需要灌溉的水量（真正补进根区的水）
    * ``gross_volume_m3``—— 总水量（计入输水/灌溉损失后，从水源实际要取的水）
    """
    days = len(rows)
    gross_volume = sum(row["volume_m3"] for row in rows)
    net_volume = sum(row.get("net_volume_m3") or 0.0 for row in rows)
    net = sum(row["net_mm"] for row in rows)
    gross = sum(row["gross_mm"] for row in rows)
    pe = sum(row["pe_mm"] for row in rows)
    rain = sum(row.get("precip_mm") or 0.0 for row in rows)
    return {
        "label": label,
        "start": rows[0]["date"],
        "end": rows[-1]["date"],
        "days": days,
        # volume_m3 保持为“总水量”，与旧字段兼容
        "volume_m3": round(gross_volume, 1),
        "net_volume_m3": round(net_volume, 1),
        "gross_volume_m3": round(gross_volume, 1),
        "net_mm": round(net, 2),
        "gross_mm": round(gross, 2),
        "pe_mm": round(pe, 2),
        "rain_mm": round(rain, 2),
        "avg_daily_m3": round(gross_volume / days, 2) if days else 0.0,
        "avg_daily_net_m3": round(net_volume / days, 2) if days else 0.0,
    }


def build_aggregates(series: list[dict]) -> dict:
    """Roll the daily series up into 7-day blocks and calendar months.

    Weeks start at the first requested day (a rolling 7-day window), which is
    what a farmer means by "这周要浇多少水"; months are calendar months so the
    figures line up with a water bill.
    """
    if not series:
        return {"weekly": [], "monthly": []}

    weekly = [
        _bucket(series[index:index + 7], f"第{index // 7 + 1}周")
        for index in range(0, len(series), 7)
    ]

    months: dict[str, list[dict]] = {}
    for row in series:
        months.setdefault(row["date"][:7], []).append(row)
    monthly = [
        _bucket(rows, key) for key, rows in sorted(months.items())
    ]

    total = sum(row["volume_m3"] for row in series)
    total_net = sum(row.get("net_volume_m3") or 0.0 for row in series)
    return {
        "weekly": weekly,
        "monthly": monthly,
        "cumulative": {
            "days": len(series),
            "volume_m3": round(total, 1),
            "net_volume_m3": round(total_net, 1),
            "gross_volume_m3": round(total, 1),
            "avg_daily_m3": round(total / len(series), 2),
            "avg_daily_net_m3": round(total_net / len(series), 2),
        },
    }


def merge_series(plans: list[dict]) -> list[dict]:
    """Add several plans' daily rows together by date (for area-level rollups)."""
    merged: dict[str, dict] = {}
    numeric = (
        "volume_m3",
        "net_volume_m3",
        "net_mm",
        "gross_mm",
        "pe_mm",
        "precip_mm",
        "et0_mm",
        "etc_mm",
        "percolation_mm",
    )
    for plan in plans:
        for row in plan["series"]:
            target = merged.setdefault(
                row["date"],
                {"date": row["date"], **{key: 0.0 for key in numeric}},
            )
            for key in numeric:
                target[key] += row.get(key) or 0.0
    return [merged[key] for key in sorted(merged)]


def compute_plan(
    ring: geo.Ring,
    area_m2: float,
    crop: str | None,
    stage_key: str | None,
    days: int = 7,
    start: dt.date | None = None,
    params: dict[str, Any] | None = None,
) -> dict:
    params = params or {}
    efficiency = float(params.get("efficiency", 0.85)) or 0.85
    kc_reference = float(params.get("kc_reference", DEFAULT_KC_REFERENCE)) or DEFAULT_KC_REFERENCE
    kc_scale = float(params.get("kc_scale", 1.0)) or 1.0
    rain_ratio = params.get("effective_rain_ratio", 1.0)
    rain_ratio = 1.0 if rain_ratio is None else float(rain_ratio)
    rain_override = float(params.get("effective_rain_mm_day", 0.0) or 0.0)

    start = start or dt.date.today()
    days = max(1, min(int(days), 180))

    kc, crop_label, stage_label = stage_kc(crop, stage_key)
    spec = CROPS.get(crop or "", CROPS["other"])
    percolation = float(spec.get("percolation_mm_day", 0.0)) if spec.get("paddy") else 0.0

    have_era5 = era5.load() is not None
    method = "era5-pm" if have_era5 else "etmonitor-inverse"

    series: list[dict] = []
    cumulative = 0.0
    extrapolated = False

    if have_era5:
        rows = era5.series(ring, start, days)
        for row in rows:
            et0 = float(row["et0_mm"])
            precip = float(row.get("precip_mm") or 0.0)
            pe = rain_override if rain_override > 0 else float(row.get("pe_mm") or 0.0) * rain_ratio
            etc = kc * et0 * kc_scale
            net = max(0.0, etc + percolation - pe)
            gross = net / efficiency
            net_volume = net * area_m2 / 1000.0
            volume = gross * area_m2 / 1000.0
            cumulative += volume
            extrapolated = extrapolated or bool(row.get("extrapolated"))
            envelope = era5.envelope(ring, dt.date.fromisoformat(row["date"]))
            series.append(
                {
                    "date": row["date"],
                    "et0_mm": round(et0, 3),
                    "precip_mm": round(precip, 3),
                    "pe_mm": round(pe, 3),
                    "kc": round(kc, 3),
                    "etc_mm": round(etc, 3),
                    "percolation_mm": round(percolation, 3),
                    "net_mm": round(net, 3),
                    "gross_mm": round(gross, 3),
                    "net_volume_m3": round(net_volume, 2),
                    "volume_m3": round(volume, 2),
                    "cumulative_m3": round(cumulative, 2),
                    "t2m_c": row.get("t2m_c"),
                    "vpd_kpa": row.get("vpd_kpa"),
                    "et0_min": envelope.get("et0_min"),
                    "et0_max": envelope.get("et0_max"),
                    "precip_max": envelope.get("precip_max"),
                    "source": row.get("source"),
                    "extrapolated": row.get("extrapolated", False),
                }
            )
    else:
        et_rows = et_grid.et_series(ring, start, days)
        for row in et_rows:
            et_value = float(row["et_mm_day"])
            et0 = et_value / kc_reference if kc_reference else et_value
            etc = kc * et0 * kc_scale
            pe = rain_override
            net = max(0.0, etc + percolation - pe)
            gross = net / efficiency
            net_volume = net * area_m2 / 1000.0
            volume = gross * area_m2 / 1000.0
            cumulative += volume
            extrapolated = extrapolated or bool(row.get("extrapolated"))
            series.append(
                {
                    "date": row["date"],
                    "et0_mm": round(et0, 3),
                    "et_grid_mm": round(et_value, 3),
                    "precip_mm": None,
                    "pe_mm": round(pe, 3),
                    "kc": round(kc, 3),
                    "etc_mm": round(etc, 3),
                    "percolation_mm": round(percolation, 3),
                    "net_mm": round(net, 3),
                    "gross_mm": round(gross, 3),
                    "net_volume_m3": round(net_volume, 2),
                    "volume_m3": round(volume, 2),
                    "cumulative_m3": round(cumulative, 2),
                    "et0_min": row.get("et_min"),
                    "et0_max": row.get("et_max"),
                    "source": row.get("source"),
                    "extrapolated": row.get("extrapolated", False),
                }
            )

    total_net_mm = sum(r["net_mm"] for r in series)
    total_gross_mm = sum(r["gross_mm"] for r in series)
    total_volume = sum(r["volume_m3"] for r in series)
    total_net_volume = sum(r.get("net_volume_m3") or 0.0 for r in series)
    total_rain = sum(r.get("precip_mm") or 0.0 for r in series)
    total_pe = sum(r["pe_mm"] for r in series)
    mu = area_m2 * geo.MU_PER_M2

    assumptions: list[str] = []
    if have_era5:
        assumptions.append(
            "ET0 由 ERA5 逐小时数据按 FAO-56 Penman–Monteith 计算（日均气温、饱和差、风速、净辐射、气压）"
        )
        assumptions.append(
            "有效降雨 Pe 由 ERA5 日降水按"
            f"利用系数 {rain_ratio:.2f}、上限 35 mm/天 估算"
            + (f"；管理端已改为固定 {rain_override:.1f} mm/天" if rain_override > 0 else "")
        )
        assumptions.append("逐日 ET0 与降水按田块与 0.25° 网格的面积重叠加权，不是单点取值")
    else:
        assumptions.append("ET 取自 ETMonitor 2000–2004 日蒸散网格（未能加载 ERA5 资产，已退回近似法）")
        assumptions.append(
            f"网格 ET 视为主导作物（Kc≈{kc_reference:.2f}）的实际蒸散，据此反推参考蒸散 ET0 后再按本作物的 Kc 缩放"
        )
        assumptions.append("有效降雨 Pe 尚未接入 ERA5 降水，按 0 计（保守估计，会高估需水量）")

    if spec.get("paddy"):
        assumptions.append(f"水田渗漏按 {percolation:.1f} mm/天 计入")
    if extrapolated:
        assumptions.append("部分日期超出 2000–2004 观测范围或位于数据域外，已用同日序气候态/经验模型外推")
    assumptions.append(f"灌溉水利用系数 η={efficiency:.2f}，可通过管理端调整")

    return {
        "window": {
            "start": series[0]["date"] if series else start.isoformat(),
            "days": days,
        },
        "method": method,
        "crop": {
            "key": crop or "other",
            "label": crop_label,
            "stage_key": stage_key,
            "stage_label": stage_label,
            "kc": round(kc, 3),
            "kc_scale": kc_scale,
            "paddy": bool(spec.get("paddy")),
        },
        "area": {
            "m2": round(area_m2, 1),
            "mu": round(mu, 3),
            "ha": round(area_m2 / 10_000.0, 4),
        },
        "params": {
            "efficiency": efficiency,
            "kc_reference": kc_reference,
            "effective_rain_ratio": rain_ratio,
            "effective_rain_mm_day": rain_override,
        },
        "series": series,
        "totals": {
            "net_mm": round(total_net_mm, 2),
            "gross_mm": round(total_gross_mm, 2),
            "rain_mm": round(total_rain, 2),
            "pe_mm": round(total_pe, 2),
            # 需要灌溉的水量（净）——真正补进根区的部分
            "net_volume_m3": round(total_net_volume, 1),
            # 总水量（毛）——计入输水/灌溉损失后从水源实际抽取
            "gross_volume_m3": round(total_volume, 1),
            # 兼容旧字段：volume_m3 一直是总水量
            "volume_m3": round(total_volume, 1),
            "daily_avg_m3": round(total_volume / days, 2),
            "daily_avg_net_m3": round(total_net_volume / days, 2),
            "per_mu_m3": round(total_volume / mu, 1) if mu > 0 else None,
            "per_mu_net_m3": round(total_net_volume / mu, 1) if mu > 0 else None,
        },
        "assumptions": assumptions,
        "domain": {"et_grid": et_grid.status(), "era5": era5.status()},
        "aggregates": build_aggregates(series),
    }


def summarize(plans: list[dict]) -> dict:
    """Aggregate several field plans into a daily/weekly/monthly summary.

    同样给出两个口径：``daily_net_m3`` / ``week_net_m3`` 是需要灌溉的水量，
    带 ``week_m3`` 后缀的是计入损失后的总水量。
    """
    if not plans:
        return {
            "fields": 0,
            "area_mu": 0.0,
            "daily_m3": 0.0,
            "daily_net_m3": 0.0,
            "week_m3": 0.0,
            "week_net_m3": 0.0,
            "by_date": [],
            "aggregates": {"weekly": [], "monthly": [], "cumulative": {"days": 0, "volume_m3": 0.0}},
        }

    daily_total = 0.0
    daily_net = 0.0
    week_total = 0.0
    week_net = 0.0
    area_mu = 0.0
    for plan in plans:
        area_mu += plan["area"]["mu"]
        first = plan["series"][0] if plan["series"] else None
        daily_total += first["volume_m3"] if first else 0.0
        daily_net += (first.get("net_volume_m3") or 0.0) if first else 0.0
        week_total += plan["totals"]["volume_m3"]
        week_net += plan["totals"].get("net_volume_m3", plan["totals"]["volume_m3"])

    merged = merge_series(plans)
    by_date = [
        {
            "date": row["date"],
            "volume_m3": round(row["volume_m3"], 2),
            "net_volume_m3": round(row.get("net_volume_m3") or 0.0, 2),
        }
        for row in merged
    ]

    return {
        "fields": len(plans),
        "area_mu": round(area_mu, 2),
        "daily_m3": round(daily_total, 1),
        "daily_net_m3": round(daily_net, 1),
        "week_m3": round(week_total, 1),
        "week_net_m3": round(week_net, 1),
        "by_date": by_date,
        "aggregates": build_aggregates(merged),
    }
