"""Build ``artifacts/era5_daily.npz`` from the ERA5 hourly NetCDF archive.

Thin CLI over :mod:`app.services.era5_build`, so the one-shot build and the
admin "ingest newly downloaded files" path run exactly the same aggregation.

Derived daily cube (33 x 29, 0.25°, same grid as the ETMonitor asset):

    t2m    日均气温            °C
    vpd    日均饱和差           kPa
    wind   日均 10 m 风速       m/s
    rn     日净辐射            MJ/m2/d   (ssr + str，累计量按前一小时归日)
    pres   日均气压            kPa
    precip 日降水              mm/d      (tp)
    et0    FAO-56 参考蒸散      mm/d
    pe     日有效降雨           mm/d

Usage::

    python scripts/build_era5_daily.py
    python scripts/build_era5_daily.py --era-dir "D:/era5" --years 2000 2001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

from app.services import era5_build  # noqa: E402

ARTIFACTS = SERVER_DIR / "artifacts"
WORKSPACE = SERVER_DIR.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--era-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ARTIFACTS / "era5_daily.npz")
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument("--pe-ratio", type=float, default=0.8)
    parser.add_argument("--pe-cap", type=float, default=35.0)
    args = parser.parse_args()

    era_dir = args.era_dir
    if era_dir is None:
        candidates = [p for p in WORKSPACE.iterdir() if p.is_dir() and "era5" in p.name.lower()]
        if not candidates:
            raise SystemExit("ERA5 directory not found; pass --era-dir")
        era_dir = candidates[0]
    era_dir = era_dir.resolve()
    print(f"ERA5 source: {era_dir}")

    files = sorted(p for p in era_dir.glob("*.nc"))
    buckets, warnings = era5_build.group_files(files)
    for warning in warnings[:10]:
        print("  !", warning)

    years = args.years or sorted(buckets)
    print(f"years: {years}")

    dates: list[str] = []
    blocks: dict[str, list[np.ndarray]] = {key: [] for key in era5_build.DERIVED}
    lat = lon = None

    for year in years:
        available = buckets.get(year, {})
        missing = [key for key in era5_build.VARIABLE_PATTERNS if key not in available]
        if missing:
            print(f"  {year}: 缺少 {', '.join(missing)}，跳过")
            continue
        cube = era5_build.build_year(available, year, args.pe_ratio, args.pe_cap)
        if lat is None:
            lat, lon = era5_build.read_coordinates(next(iter(available.values())))
        dates.extend(cube.dates)
        for key in era5_build.DERIVED:
            blocks[key].append(cube.arrays[key])
        with np.errstate(invalid="ignore"):
            print(
                f"  {year}: {len(cube.dates)} days | T {np.nanmean(cube.arrays['t2m']):5.1f}°C "
                f"| VPD {np.nanmean(cube.arrays['vpd']):4.2f} kPa "
                f"| P {np.nanmean(cube.arrays['precip']):5.2f} mm "
                f"| ET0 {np.nanmean(cube.arrays['et0']):5.2f} mm "
                f"| Pe {np.nanmean(cube.arrays['pe']):5.2f} mm"
            )

    if not dates or lat is None:
        raise SystemExit("没有可用的年份数据")

    order = np.argsort(dates)
    dates = [dates[i] for i in order]
    arrays = {
        key: np.concatenate(chunks, axis=0)[order].astype(np.float32)
        for key, chunks in blocks.items()
    }
    usable = int(np.isfinite(arrays["et0"]).any(axis=(1, 2)).sum())
    print(f"\ncube {arrays['et0'].shape}, {len(dates)} dates, usable {usable}")
    print(f"dates {dates[0]} .. {dates[-1]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        dates=np.array(dates, dtype="U10"),
        lat=lat,
        lon=lon,
        **arrays,
    )
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024 / 1024:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
