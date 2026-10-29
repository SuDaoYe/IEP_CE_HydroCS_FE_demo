"""Build ``artifacts/et_grid.npz`` from the ETMonitor daily-ET archive.

The archive ships one 33x29 float32 GeoTIFF per day (2000-2004). We extract only
the ERA5-grid folder (7.6 MB) instead of the 1.4 GB 1 km tiles, then pack the
whole cube into a single npz the API can load in milliseconds.

Usage::

    python scripts/build_et_grid.py                # auto-detect the rar
    python scripts/build_et_grid.py --tif-dir <dir>
    python scripts/build_et_grid.py --rar <path> --keep-src
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import tifffile

SERVER_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS = SERVER_DIR / "artifacts"
WORKSPACE = SERVER_DIR.parent.parent

BANDIZIP_CANDIDATES = [
    Path(r"C:\Program Files\Bandizip\bz.exe"),
    Path(r"C:\Program Files (x86)\Bandizip\bz.exe"),
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files\WinRAR\UnRAR.exe"),
]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise SystemExit(f"command failed: {(result.stderr or result.stdout).strip()[:400]}")


def _run_raw(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return (result.stdout or "") + (result.stderr or "")


def list_entries(tool: Path, rar: Path, needle: str) -> list[str]:
    """Return archive member paths containing ``needle``."""
    output = _run_raw([str(tool), "l", str(rar)])
    entries = []
    for line in output.splitlines():
        if needle not in line or not line.strip():
            continue
        # Bandizip listing columns end with the member name after the size.
        parts = line.rsplit(None, 1)
        if len(parts) == 2 and ("\\" in parts[1] or "/" in parts[1]):
            entries.append(parts[1].replace("/", "\\"))
    return entries


def extract_archive(rar: Path, dest: Path) -> Path:
    """Extract only the ERA5-grid members, returning the destination root."""
    dest.mkdir(parents=True, exist_ok=True)
    entry = r"2000-2004日尺度蒸散发数据集\ERA5网格"

    for tool in BANDIZIP_CANDIDATES:
        if not tool.is_file():
            continue
        print(f"using {tool.name} ...")

        if tool.name.lower().startswith("7z"):
            run([str(tool), "x", str(rar), entry + r"\*", f"-o{dest}", "-y"])
        elif tool.name.lower() == "unrar.exe":
            run([str(tool), "x", "-y", str(rar), entry + r"\*", str(dest)])
        else:
            # Bandizip CLI cannot filter by folder, so feed explicit member lists.
            members = [m for m in list_entries(tool, rar, "ERA5网格") if m.lower().endswith(".tif")]
            print(f"archive lists {len(members)} ERA5-grid TIFFs")
            batch = 120
            for start in range(0, len(members), batch):
                chunk = members[start:start + batch]
                result = subprocess.run(
                    [str(tool), "x", "-y", str(rar), *chunk],
                    cwd=dest,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                done = min(start + batch, len(members))
                if result.returncode != 0:
                    print(f"  batch {start}-{done} returned {result.returncode}")
                print(f"  extracted {done}/{len(members)}")

        found = sorted(dest.rglob("*.tif"))
        if found:
            print(f"extracted {len(found)} TIFFs")
            return dest
        print("  no TIFFs produced by this tool, trying the next one")
    raise SystemExit("no archive tool worked; extract the rar manually and pass --tif-dir")


def read_grid(tif_path: Path) -> tuple[np.ndarray, tuple[float, float, float, float], float]:
    with tifffile.TiffFile(tif_path) as handle:
        page = handle.pages[0]
        data = page.asarray().astype(np.float32)
        tags = {tag.name: tag.value for tag in page.tags.values()}
    scale = tags.get("ModelPixelScaleTag", (0.25, 0.25, 0.0))
    tie = tags.get("ModelTiepointTag", (0.0, 0.0, 0.0, 113.875, 40.125, 0.0))
    res = float(scale[0])
    ulx, uly = float(tie[3]), float(tie[4])
    # Move from the upper-left corner of the raster to pixel centres.
    west = ulx + res / 2
    north = uly - res / 2
    return data, (west, north, res, 0.0), res


def build(tif_root: Path, out_path: Path, source_label: str) -> None:
    tifs = sorted(tif_root.rglob("*.tif"))
    if not tifs:
        raise SystemExit(f"no TIFF files under {tif_root}")
    print(f"found {len(tifs)} daily grids under {tif_root}")

    dates: list[str] = []
    stack: list[np.ndarray] = []
    shape: tuple[int, int] | None = None
    west = north = res = None

    for tif in tifs:
        data, meta, resolution = read_grid(tif)
        if shape is None:
            shape = data.shape
            west, north, res = meta[0], meta[1], resolution
            print(f"grid {shape[1]} cols x {shape[0]} rows, res {res}°, origin ({west}, {north})")
        elif data.shape != shape:
            print(f"  skip {tif.name}: shape {data.shape} != {shape}")
            continue
        # ETMonitor day-of-year naming: YYYYDDD
        stem = tif.stem
        parts = stem.split(".")
        year_doy = next((p for p in parts if len(p) == 7 and p.isdigit()), None)
        if year_doy is None:
            print(f"  skip {tif.name}: cannot parse date")
            continue
        day = dt.date(int(year_doy[:4]), 1, 1) + dt.timedelta(days=int(year_doy[4:]) - 1)
        stack.append(np.where(np.isfinite(data), data, np.nan))
        dates.append(day.isoformat())

    if not stack:
        raise SystemExit("no usable grids parsed")

    cube = np.stack(stack).astype(np.float32)
    order = np.argsort(dates)
    cube = cube[order]
    dates = [dates[i] for i in order]

    lon = np.round(west + res * np.arange(shape[1]), 4)
    lat = np.round(north - res * np.arange(shape[0]), 4)

    valid = int(np.isfinite(cube).sum())
    print(f"cube {cube.shape}, {len(dates)} days {dates[0]}..{dates[-1]}, valid cells {valid:,}")
    print(f"ET range {np.nanmin(cube):.3f}..{np.nanmax(cube):.3f} mm/day")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        et=cube,
        dates=np.array(dates, dtype="U10"),
        lon=lon.astype(np.float64),
        lat=lat.astype(np.float64),
        source=np.array(source_label, dtype="U64"),
    )
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"wrote {out_path} ({size_mb:.2f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rar", type=Path, default=None, help="source archive")
    parser.add_argument("--tif-dir", type=Path, default=None, help="already extracted ERA5 grid folder")
    parser.add_argument("--out", type=Path, default=ARTIFACTS / "et_grid.npz")
    parser.add_argument("--keep-src", action="store_true", help="keep the extracted TIFFs")
    args = parser.parse_args()

    if args.tif_dir:
        build(args.tif_dir, args.out, "ETMonitor 2000-2004 (extracted)")
        return

    rar = args.rar
    if rar is None:
        candidates = sorted(WORKSPACE.glob("*蒸散发数据集*.rar"))
        if not candidates:
            raise SystemExit("archive not found; pass --rar or --tif-dir")
        rar = candidates[0]
    if not rar.is_file():
        raise SystemExit(f"archive not found: {rar}")

    tmp = ARTIFACTS / ".et_src"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        root = extract_archive(rar, tmp)
        build(root, args.out, f"ETMonitor ({rar.name})")
    finally:
        if not args.keep_src and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            print("cleaned temporary extraction")


if __name__ == "__main__":
    sys.exit(main())
