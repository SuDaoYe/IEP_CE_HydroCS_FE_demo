# 算力与并发：实测数据与部署建议

目标：C/S 部署时**有原生 CUDA 就用 CUDA，没有就把模型转译成 ONNX 交给
ORT（DirectML / CPU）跑**，并在多用户并发下保持吞吐稳定。下面全部是本机实测数字，
复现脚本在 `server/scripts/`。

## 1. 测试环境

| 项 | 值 |
|---|---|
| 系统 | Windows 11（build 26200） |
| CPU | AMD Ryzen 9 7940HS（16 线程） |
| 独显 | NVIDIA GeForce RTX 4060 Laptop（8.6 GB，驱动 CUDA UMD 13.4） |
| 核显 | AMD Radeon 780M（DirectML 可用） |
| 软件 | torch 2.12.1+cu130 / onnxruntime 1.20.1（CPU）/ onnxruntime-directml 1.24.4 / ultralytics 8.4.192 |
| 负载 | 演示田 bbox @ z18 → 拼图 1024×1280、2 个推理窗口、55–56 个地块 |

## 2. 后端对比（同一张图、同一套后处理）

`python scripts/bench_segment.py` + `python .scratch/probe_pipeline.py`：

| 后端 | 1024² 前向 | 单请求端到端（拼图 + 推理 + 矢量化） | 相对 CPU |
|---|---|---|---|
| `cuda`（.pt, fp16） | **25.7 ms** | **145 ms** | **7.8×** |
| `onnx-dml`（.onnx, DirectML） | **21.9 ms** | **449 ms** | **2.5×** |
| `torch-cpu`（.pt） | 501 ms | 1130 ms | 1× |
| `onnx-cpu`（.onnx） | 718 ms | 1572 ms | 0.72× |

（`onnx-dml` 的 449 ms 是走完整 HTTP 接口实测：`timing_ms={"mosaic":12.6,"infer":436.5,"total":449.1}`，
56 个地块 / 23.33 ha；DirectML 那 22 ms 只是前向，掩膜重建仍在 CPU 上做。）

结论：

- **CUDA 是数量级提升**，且不必改代码 —— 装 CUDA 版 torch 后自动选中。
- **DirectML 是「没有 CUDA 时」的最优解**：一张 `onnxruntime-directml`（约 40 MB）
  就能让任意 DX12 显卡（NVIDIA / AMD / Intel 核显）跑起来，比 CPU 快 2.5×，
  精度与 CPU 版一致（掩膜 IoU 0.97–0.99）。
- **ONNX-CPU 比 torch-CPU 慢**（718 ms vs 501 ms），所以纯 CPU 机器不要为了「转译」
  而转译：默认顺序里 torch-CPU 排在 onnx-CPU 前面，就是这个原因。

## 3. 顺带做掉的后处理优化

矢量化原来对每个实例在**整幅图**上做 `labels == id` + `astype` + `findContours`，
55 个实例就是 55 次全图扫描。改成按检测框裁剪后再矢量化：

| 版本 | 端到端（CUDA） |
|---|---|
| 优化前 | 470 ms |
| 优化后 | **145 ms** |

输出完全一致（55 块 / 23.344 ha / 覆盖率 80.5%），纯属白送的 3.2×。

## 4. 并发：为什么「多线程」反而更慢

`python scripts/bench_load.py --concurrency 1,2,4`（单进程，推理闸门 = 1）：

| 后端 | 并发 | p50 延迟 | 吞吐 |
|---|---|---|---|
| CUDA | 1 | 141 ms | **7.1 req/s** |
| CUDA | 2 | 188 ms | 5.9 req/s |
| CUDA | 4 | 328 ms | 4.3 req/s |
| DirectML | 1 | 441 ms | 2.3 req/s |
| DirectML | 2 | 704 ms | 2.9 req/s |

单进程内再开并发只会**降低吞吐**：推理之外还有大量 GIL 密集的 numpy/Python
（掩膜上色、轮廓、测地线面积、去重），线程越多互相抢锁越严重（实测 4 路并发的
p50 一度是串行的 8 倍）。所以：

- 进程内用 `BoundedSemaphore` 把「推理 + 后处理 + 去重」整段串行化（`_gate()`），
  并发请求进来排队，延迟线性增长、吞吐保持稳定，不会雪崩。
- 启动时把 OpenCV 线程数收敛到 1、torch CPU 线程数收敛到 min(8, 核数/2)，
  避免每个请求各自开满 16 线程互踩。
- DirectML 因为 GPU 侧的调用是异步的，2 路并发时吞吐反而略升（2.3 → 2.9 req/s），
  但它本身单请求就 441 ms，没有 CUDA 的机器不必追求并发。

**横向扩展靠多进程**（`uvicorn --workers N`，每个进程独占一份模型）：

| 进程数 | 合成吞吐 | 每请求耗时 |
|---|---|---|
| 1 | 7.1 /s | 140 ms |
| 2 | 9.7 /s | 206 ms |
| 3 | 10.8 /s | 278 ms |

2 进程 +37%，3 进程开始饱和（单卡 8.6 GB，每个进程约占 0.6 GB 显存）。
`python .scratch/probe_multi_process.py` 可复现。

## 5. 缓存带来的「秒回」

| 场景 | 延迟 |
|---|---|
| 同一 bbox + 同样参数再识别一次 | **约 2 ms**（结果缓存 180 分钟） |
| bbox 不同但瓦片已在磁盘 | 拼图 **0 ms**（内存 LRU，8 幅）/ 首次约 15 ms |
| 全新区域（要联网抓瓦片） | 0.5–2 s，取决于上游 |

## 6. 部署配方

```powershell
# A. 有 NVIDIA + 能装 CUDA 版 torch（推荐）
python -m pip install --index-url https://download.pytorch.org/whl/cu130 torch==2.12.1+cu130 torchvision==0.27.1+cu130
$env:HYDROCS_SEG_BACKEND = "auto"      # 自动选中 cuda
$env:HYDROCS_WARMUP = "1"              # 启动即预热，首个请求不再等 3 s
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# B. 没有 CUDA（含 AMD/Intel 显卡、纯 CPU 的服务器）
python scripts/export_onnx.py                           # 一次性导出 40 MB ONNX
python -m pip install onnxruntime-directml              # Windows + DX12 显卡
$env:HYDROCS_SEG_BACKEND = "auto"                       # 自动选中 onnx-dml，退到 torch-cpu
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# C. 想钉死某条链路（排障用）
$env:HYDROCS_SEG_BACKEND = "torch-cpu"                  # 或 cuda / onnx-dml / onnx-cpu / onnx-cuda
```

## 7. 相关环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HYDROCS_SEG_BACKEND` | `auto` | `auto` 按 cuda → onnx-cuda → onnx-dml → torch-cpu → onnx-cpu 依次尝试 |
| `HYDROCS_WARMUP` | 关 | 启动时加载模型并跑一次空推理，消掉首请求的 3 s 初始化 |
| `HYDROCS_SEG_CONCURRENCY` | 1 | 进程内推理并发上限；**不建议大于 1**（见第 4 节） |
| `HYDROCS_SEG_TORCH_THREADS` | min(8, 核/2) | torch CPU 线程数（GPU 推理也用得到，因为 NMS 在 CPU） |
| `HYDROCS_SEG_CV_THREADS` | 1 | OpenCV 线程数 |
| `HYDROCS_SEG_ORT_THREADS` | 0（ORT 默认） | 仅 ONNX-CPU 生效 |
| `HYDROCS_MOSAIC_CACHE` | 8 | 拼图内存缓存条数（每条约 4 MB） |
| `HYDROCS_ONNX` | 与 `.pt` 同名 | ONNX 权重路径 |

## 8. 观测

- `GET /healthz` → `segmentation`（当前后端 + 设备 + 闸门大小）、`compute`（torch / ORT 能力与探测原因）。
- `GET /api/v1/segment/status` → 同上 + 每个后端的可用性与不可用原因。
- `POST /api/v1/segment` 的响应里带 `timing_ms: {mosaic, infer, total}`。
- `HYDROCS_SEG_PROFILE=1` 时日志会打印每次识别的 `infer / paint / vectorize` 分段耗时。
- `python scripts/bench_load.py` / `bench_segment.py` 做回归压测。
