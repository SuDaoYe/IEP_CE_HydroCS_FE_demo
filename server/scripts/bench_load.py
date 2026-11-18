"""并发压测：对 /api/v1/segment 发并发请求，看吞吐与尾延迟。

用法（服务已启动）：

    python scripts/bench_load.py --concurrency 1,2,4,8 --requests 8

每个请求只改 `min_area_ha`（它在缓存键里），bbox 保持不变，这样影像瓦片全部命中
磁盘缓存、识别结果缓存又不会命中，量到的是**纯计算**时间；服务端返回的
`timing_ms` 同时给出 mosaic / infer 两段耗时，便于定位瓶颈在取图还是在推理。
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8000/api/v1"
DEMO = [118.7975, 37.7975, 118.8015, 37.8015]
#: 每次请求换一个 min_area_ha，避免命中结果缓存
_TICKET = itertools.count(int(time.time()) % 500_000)


def login(username: str, password: str) -> str:
    payload = json.dumps({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        f"{BASE}/auth/login", data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())["access_token"]


def segment(
    token: str, bbox: list[float], min_area_ha: float | None = None, timeout: float = 300
) -> tuple[float, int, dict]:
    payload: dict = {"bbox": bbox, "zoom": 18, "provider": "esri"}
    if min_area_ha is not None:
        payload["min_area_ha"] = min_area_ha
    request = urllib.request.Request(
        f"{BASE}/segment",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read())
    return (time.perf_counter() - started), body.get("count", -1), body.get("timing_ms", {})


def run_level(token: str, concurrency: int, requests: int) -> dict:
    counter = {"n": 0}
    lock = threading.Lock()
    latencies: list[float] = []
    counts: list[int] = []
    infer: list[float] = []
    mosaic: list[float] = []

    def worker() -> None:
        while True:
            with lock:
                if counter["n"] >= requests:
                    return
                counter["n"] += 1
            min_area = 0.01 + next(_TICKET) * 1e-6
            try:
                elapsed, count, timing = segment(token, DEMO, min_area_ha=min_area)
                latencies.append(elapsed)
                counts.append(count)
                infer.append(timing.get("infer", float("nan")) / 1000.0)
                mosaic.append(timing.get("mosaic", float("nan")) / 1000.0)
            except Exception as exc:  # noqa: BLE001
                latencies.append(float("nan"))
                print("  request failed:", exc.__class__.__name__, exc)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for _ in range(concurrency):
            pool.submit(worker)
    wall = time.perf_counter() - started

    def p50(values: list[float]) -> float | None:
        clean = [value for value in values if value == value]
        return round(statistics.median(clean) * 1000, 1) if clean else None

    ok = [value for value in latencies if value == value]
    return {
        "concurrency": concurrency,
        "requests": len(ok),
        "wall_s": round(wall, 2),
        "throughput_rps": round(len(ok) / wall, 2) if wall else 0,
        "p50_ms": p50(latencies),
        "max_ms": round(max(ok) * 1000, 1) if ok else None,
        "mosaic_ms": p50(mosaic),
        "infer_ms": p50(infer),
        "segments": sorted(set(counts)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="farmer1")
    parser.add_argument("--password", default="123456")
    parser.add_argument("--concurrency", default="1,2,4")
    parser.add_argument("--requests", type=int, default=6)
    args = parser.parse_args()

    token = login(args.user, args.password)
    print("warmup:", round(segment(token, DEMO)[0] * 1000, 1), "ms\n")

    for level in [int(value) for value in args.concurrency.split(",") if value.strip()]:
        requests = max(args.requests, level)
        row = run_level(token, level, requests)
        print(
            f"concurrency {row['concurrency']:2d} | {row['requests']:2d} req in {row['wall_s']:5.2f}s | "
            f"{row['throughput_rps']:5.2f} req/s | client p50 {row['p50_ms']:7.1f} ms | "
            f"mosaic {row['mosaic_ms']} ms | infer {row['infer_ms']} ms | max {row['max_ms']} ms | "
            f"segments {row['segments']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
