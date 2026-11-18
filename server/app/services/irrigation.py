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

from . import era5, et_grid, et_model, geo

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
KC_REFERENCE = DEFAULT_KC_REFERENCE
DEFAULT_EFFICIENCY = 0.85  # 灌溉水利用系数（固定，不再作为可调参数）


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


def _et_for_day(ring: geo.Ring, day: dt.date) -> tuple[float | None, str, str | None]:
    """按"模型 → Penman–Monteith → ETMonitor"的顺序取一天的 ET。"""
    if et_model.load() is not None:
        row = et_model.predict_day(ring, day)
        if row.get("et_mm_day") is not None:
            return float(row["et_mm_day"]), "model", row.get("source")
    if era5.load() is not None:
        row = era5.day_values(ring, day)
        if row.get("et0_mm") is not None:
            return float(row["et0_mm"]), "pm", row.get("source")
    row = et_grid.et_for_ring(ring, day)
    if row.get("et_mm_day") is not None:
        return float(row["et_mm_day"]), "etmonitor", row.get("source")
    return None, "none", None


def compute_plan(
    ring: geo.Ring,
    area_m2: float,
    crop: str | None,
    stage_key: str | None,
    days: int = 7,
    start: dt.date | None = None,
    params: dict[str, Any] | None = None,
) -> dict:
    """按"训练模型优先"的顺序解算需水量。

    三种 ET 来源，优先级从高到低：

    1. ``model-hgb``  —— 训练好的日 ET 模型（ERA5 驱动，2004 测试 RMSE ≈0.52 mm/day）
    2. ``era5-pm``    —— 模型缺失时退回 FAO-56 Penman–Monteith 参考蒸散
    3. ``etmonitor``  —— ERA5 也缺失时用 ETMonitor 观测格点反推

    系数不再可调（参数微调功能已下线）。``params`` 仅为测试保留 η 覆盖，
    其余键一律忽略。
    """
    efficiency = float((params or {}).get("efficiency", DEFAULT_EFFICIENCY)) or DEFAULT_EFFICIENCY
    start = start or dt.date.today()
    days = max(1, min(int(days), 180))

    kc, crop_label, stage_label = stage_kc(crop, stage_key)
    spec = CROPS.get(crop or "", CROPS["other"])
    percolation = float(spec.get("percolation_mm_day", 0.0)) if spec.get("paddy") else 0.0

    have_era5 = era5.load() is not None

    # 用户作物相对参考作物的系数：模型/网格给的是像素实际蒸散
    crop_factor = kc / KC_REFERENCE if KC_REFERENCE else kc

    series: list[dict] = []
    cumulative = 0.0
    extrapolated = False

    bases: list[str] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)

        et_value, et_basis, et_source = _et_for_day(ring, day)
        if et_value is None:
            continue
        bases.append(et_basis)
        et_label = {"model": "ET_pred_mm", "pm": "et0_mm"}.get(et_basis, "et_grid_mm")

        rain = era5.day_values(ring, day) if have_era5 else {"precip_mm": None, "pe_mm": 0.0}
        precip = float(rain.get("precip_mm") or 0.0)
        pe = float(rain.get("pe_mm") or 0.0)

        etc = et_value * crop_factor
        net = max(0.0, etc + percolation - pe)
        gross = net / efficiency
        net_volume = net * area_m2 / 1000.0
        volume = gross * area_m2 / 1000.0
        cumulative += volume
        extrapolated = extrapolated or bool(rain.get("extrapolated"))

        entry = {
            "date": day.isoformat(),
            "et_mm": round(et_value, 3),
            "precip_mm": round(precip, 3),
            "pe_mm": round(pe, 3),
            "kc": round(kc, 3),
            "crop_factor": round(crop_factor, 4),
            "etc_mm": round(etc, 3),
            "percolation_mm": round(percolation, 3),
            "net_mm": round(net, 3),
            "gross_mm": round(gross, 3),
            "net_volume_m3": round(net_volume, 2),
            "volume_m3": round(volume, 2),
            "cumulative_m3": round(cumulative, 2),
            "source": et_source,
            "et_basis": et_basis,
        }
        # 兼容前端既有字段名
        entry[et_label] = round(et_value, 3)
        if et_basis == "pm":
            entry["et0_min"] = None
            entry["et0_max"] = None
        series.append(entry)

    if not series:
        raise ValueError("没有可用的 ET 数据，无法解算")

    unique_bases = set(bases)
    if unique_bases == {"model"}:
        method = "model-hgb"
    elif unique_bases == {"pm"}:
        method = "era5-pm"
    elif unique_bases == {"etmonitor"}:
        method = "etmonitor"
    else:
        method = "mixed"

    total_net_mm = sum(r["net_mm"] for r in series)
    total_gross_mm = sum(r["gross_mm"] for r in series)
    total_volume = sum(r["volume_m3"] for r in series)
    total_net_volume = sum(r.get("net_volume_m3") or 0.0 for r in series)
    total_rain = sum(r.get("precip_mm") or 0.0 for r in series)
    total_pe = sum(r["pe_mm"] for r in series)
    mu = area_m2 * geo.MU_PER_M2
    days = len(series)

    assumptions: list[str] = []
    if method == "model-hgb":
        bundle = et_model.load()
        metrics = bundle.test_metrics if bundle else {}
        assumptions.append(
            "ET 由训练好的日蒸散模型给出（ERA5 六要素 30 天窗口 → ETMonitor 日 ET，"
            f"{bundle.valid_year if bundle else ''}/{bundle.test_year if bundle else ''} 测试集 RMSE "
            f"{metrics.get('rmse', '—')} mm/day、R² {metrics.get('r2', '—')}）"
        )
        assumptions.append(
            f"模型输出的是该格点实际蒸散，按本作物 Kc({kc:.2f}) 与参考作物 Kc({KC_REFERENCE:.2f}) 的比值缩放"
        )
    elif method == "era5-pm":
        assumptions.append("模型不可用，退回 FAO-56 Penman–Monteith 参考蒸散 ET0")
        assumptions.append(f"ET0 按作物系数 Kc({kc:.2f}) 与参考作物 Kc({KC_REFERENCE:.2f}) 的比值换算")
    else:
        assumptions.append("模型与 ERA5 均不可用，退回 ETMonitor 观测格点（近似法）")

    if have_era5:
        assumptions.append("有效降雨 Pe 由 ERA5 日降水换算（利用系数 0.8、日上限 35 mm），按田块与网格面积重叠加权")
    else:
        assumptions.append("缺少 ERA5 降水，有效降雨按 0 计（保守上界）")
    assumptions.append("逐日 ET 与降水按田块与 0.25° 网格的面积重叠加权，不是单点取值")
    if spec.get("paddy"):
        assumptions.append(f"水田渗漏按 {percolation:.1f} mm/天 计入")
    if extrapolated:
        assumptions.append("部分日期超出 2000–2004 观测范围或位于数据域外，已用同日序气候态外推")
    assumptions.append(f"灌溉水利用系数 η={efficiency:.2f}（固定值，参数微调功能已下线）")

    return {
        "window": {"start": series[0]["date"], "days": days},
        "method": method,
        "et_source": {
            "basis": series[0].get("et_basis"),
            "model": et_model.status(),
            "era5": era5.status(),
        },
        "crop": {
            "key": crop or "other",
            "label": crop_label,
            "stage_key": stage_key,
            "stage_label": stage_label,
            "kc": round(kc, 3),
            "crop_factor": round(crop_factor, 4),
            "paddy": bool(spec.get("paddy")),
        },
        "area": {
            "m2": round(area_m2, 1),
            "mu": round(mu, 3),
            "ha": round(area_m2 / 10_000.0, 4),
        },
        "params": {
            "efficiency": efficiency,
            "kc_reference": KC_REFERENCE,
            "effective_rain_ratio": 1.0,
            "effective_rain_mm_day": 0.0,
        },
        "series": series,
        "totals": {
            "net_mm": round(total_net_mm, 2),
            "gross_mm": round(total_gross_mm, 2),
            "rain_mm": round(total_rain, 2),
            "pe_mm": round(total_pe, 2),
            "net_volume_m3": round(total_net_volume, 1),
            "gross_volume_m3": round(total_volume, 1),
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
