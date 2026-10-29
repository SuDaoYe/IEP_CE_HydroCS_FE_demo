# 数据资产说明

这个目录随仓库一起发布（约 86 MB），克隆后无需原始压缩包即可直接启动：

```powershell
cd server
python -m uvicorn app.main:app --port 8000
```

## 文件清单

| 文件 | 大小 | 内容 | 生成方式 |
|---|---:|---|---|
| `era5_daily.npz` | 38.5 MB | 2000–2004 日尺度气象 + ET0 + 有效降雨<br>1827 天 × 33 行 × 29 列 × 8 变量 | `python scripts/build_era5_daily.py` |
| `et_grid.npz` | 5.1 MB | ETMonitor 日蒸散观测（ETMonitor.GlobalET）<br>1830 天 × 33 × 29 | `python scripts/build_et_grid.py` |
| `admin/provinces.geojson` | 0.42 MB | 省级边界（简化 0.01°） | `python scripts/build_admin_divisions.py` |
| `admin/cities.geojson` | 1.4 MB | 地级市边界（简化） | 同上 |
| `admin/index.json` | 0.5 MB | 省/市/区县搜索索引（3238 条） | 同上 |
| `admin/towns.json` | 1.1 MB | 乡镇索引（32,199 条，已剔除街道） | 同上 |
| `admin/villages.txt` | 19.7 MB | 村级索引（498,502 条，`名称<TAB>编码<TAB>区县码`） | 同上 |
| `weights/4.102_best.pt` | 19.6 MB | YOLO11s-seg 农田分割权重（单类 farmland） | 来自 `农田识别分割` 交付包 |

## 数据来源

- **ERA5**：2000–2004 逐小时 20 个变量（1.4 GB NetCDF），本仓库只提交由此派生的日尺度立方。
- **ETMonitor**：日蒸散产品，原始 1 km TIFF 与 0.25° 网格 TIFF 共 1.36 GB（rar），本仓库只提交聚合后的网格立方。
- **行政区划**：DataV.GeoAtlas（省/市边界、县区中心）+ `modood/Administrative-divisions-of-China`（乡镇/村名册），编码统一为国标 adcode。
- **分割权重**：`农田识别分割` 交付包中的 `weights/4.102_best.pt`。

## 为什么不放原始压缩包

GitHub 单文件硬上限 100 MB、仓库建议 <1 GB，而原始数据是：

| 原始数据 | 大小 |
|---|---:|
| `2000-2004日尺度蒸散发数据集.rar` | 1.36 GB |
| `农田识别分割.rar`（含训练集图像） | 2.22 GB |
| `2000-2004 era5数据/`（100 个 NC） | 1.4 GB |

这些都超出普通 Git 仓库的承载范围，需要走 **GitHub Release 附件**（单文件上限 2 GB）
或外部数据仓库（Zenodo / 网盘 / 学校 FTP）。

## 校验

```powershell
cd server
python -c "import numpy as np; d=np.load('artifacts/era5_daily.npz'); print(d['dates'][0], d['dates'][-1], d['et0'].shape)"
python -c "import numpy as np; d=np.load('artifacts/et_grid.npz'); print(len(d['dates']), d['et'].shape)"
python -c "from ultralytics import YOLO; m=YOLO('artifacts/weights/4.102_best.pt'); print(m.task, m.names)"
```
