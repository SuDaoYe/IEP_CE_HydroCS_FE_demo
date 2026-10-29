# HydroCS 整合版 — 系统架构与接口规格

> 版本 1.0 · 2026-10-30 · 适用目录 `整合demo01/`

## 1. 目标与边界

给农户一个**手机可用**的页面：定位到自家地块 → 卫星影像上自动识别田块 → 手动修正形状 → 得到面积 → 绑定作物与生育期 → 看到未来 7 天的灌溉需水量。

本期交付**可运行的完整闭环**，数据依赖如下：

| 能力 | 数据来源 | 本期状态 |
|---|---|---|
| 田块识别 | YOLO11s-seg（`4.102_best.pt`，单类 farmland） | 已跑通，实测 z18 影像 156 个地块、0.04–2.5 ha，边界贴合 |
| 参考蒸散 ET0 | ERA5 逐小时 6 要素 → FAO-56 Penman–Monteith | 已接入，1827 天 × 33 × 29 |
| 有效降雨 Pe | ERA5 日降水 × 利用系数（上限 35 mm/天） | 已接入，可被管理端固定值覆盖 |
| 观测 ET（对照/降级） | ETMonitor 0.25° 日 ET 网格 2000–2004 | 已接入，仅在 ERA5 资产缺失时参与计算 |
| ET 的 ML 预测（RF/XGB/LSTM…） | ERA5 六要素 → ET | **未接入**，训练权重不在包内；接口预留 |

> 关键判断：需水量走 `Kc × ET0 − Pe` 的教科书口径；ETMonitor 网格降级为兜底。ERA5 只到 2004 年，未来日期的 ET0/Pe 用同日序 5 年气候态，并在响应里标记。

## 2. 架构

```
        手机 H5 / PWA（离线优先）                       服务器（FastAPI, Python 3.12）
┌────────────────────────────────────┐        ┌────────────────────────────────────────┐
│ MapLibre GL  卫星底图 + 田块 GeoJSON │        │ /api/imagery   瓦片代理·磁盘缓存·多源     │
│ Terra-draw 式顶点编辑（触摸友好）     │        │ /api/segment   滑窗 YOLO11s-seg → 多边形 │
│ IndexedDB    我的田块/历史/预测副本   │ HTTPS  │ /api/irrigation ET 网格 × Kc → 需水量    │
│ 同步队列      离线编辑 → 增量合并      │<──────>│ /api/fields    田块权威存储（备份）        │
│ Service Worker 应用外壳 + 瓦片缓存    │        │ /api/auth · /api/sync · /api/admin      │
└────────────────────────────────────┘        │ SQLite(WAL)  →  可平滑迁 PostgreSQL/PostGIS│
                                              └────────────────────────────────────────┘
```

**职责切分**

- **服务器权威**：田块几何与归属、识别结果、需水计算、历史气象库、用户与审计。
- **客户端副本**：IndexedDB 存"我的田块 + 灌溉记录 + 未同步操作"；离线可读、可编辑，联网后按 `op_id` 幂等合并。编辑冲突以服务器 `updated_at` 为准，客户端冲突项进入"待处理"列表由用户裁决。

**为什么不把模型放客户端**：分割权重 20 MB、ET 网格需多年数据、手机端推理 3–10 s 且耗电；且影像密钥不应下发给客户端。客户端只做渲染与轻量几何运算（面积预览、顶点编辑）。

## 3. 技术选型

| 层 | 选择 | 理由 |
|---|---|---|
| 前端框架 | React 18 + TypeScript + Vite | 复用 `前端demo01` 积累的组件思路 |
| 地图 | **MapLibre GL JS** | WebGL 渲染，手机上缩放/拖拽流畅；原生支持栅格底图与 GeoJSON 编辑图层；Leaflet 在触摸设备上绘制体验与性能都偏弱 |
| 样式 | Tailwind CSS v4 | 移动优先断点、容器查询；去掉 HeroUI 以减小包体 |
| 状态 | Zustand | 地图/选中/草稿/同步四类状态互相独立，避免 Context 层层嵌套 |
| 本地存储 | `idb`（IndexedDB） | 结构化查询 + 事务；localStorage 容量不足 |
| 后端 | **FastAPI + uvicorn** | Python 侧直接复用 YOLO 与 ET 模型；`/docs` 自动生成接口文档（答辩/软著友好） |
| 数据库 | SQLite（WAL）+ 原生 SQL | 零运维、单文件备份；几何存 GeoJSON 文本 + bbox 列，面积在服务端算 |
| 鉴权 | JWT（HS256, PyJWT）+ PBKDF2 口令散列 | 无额外依赖 |
| 识别 | Ultralytics YOLO11s-seg | 已有训练权重；CPU 单张 768×768 约 1–2 s |
| 几何 | 自研球面测地线面积 + Douglas–Peucker | 避免 pyproj/shapely 在 Windows 上的安装负担（shapely 可选增强） |

## 4. 影像源与坐标系

| 源 | 分辨率 | 坐标系 | 密钥 | 说明 |
|---|---|---|---|---|
| `esri`（默认） | z19 ≈ 0.26 m/px（城区），农区 z17–18 ≈ 0.4–0.8 m/px | WGS84 | 无 | 实测可达，与田块几何天然对齐 |
| `tianditu` | ≈ 0.5–1 m | WGS84 | 需 `TIANDITU_KEY` | 国内合规首选，未配 key 时自动跳过 |
| `amap` | ≈ 0.5 m | **GCJ-02** | 无需（已有 AMAP key 供 POI） | 与 WGS84 有 ~500 m 偏移，必须走 datum 转换 |
| `sentinel2`（EOX） | 10 m | WGS84 | 无 | 时序 NDVI/长势，不做边界识别 |

**坐标系策略**：服务器对每个 provider 声明 `datum`。`wgs84` 直出；`gcj02` 由 `/api/fields?datum=gcj02` 在响应里做 WGS84→GCJ-02 变换，提交时反向变换。客户端不感知细节。

**为什么不用 Leaflet/Gaode JS 直接加载瓦片**：会暴露 key、无法统一缓存、跨域受限。所有瓦片经服务器代理，按 `provider/z/x/y` 落盘缓存 30 天。

## 5. 识别流水线

```
bbox + zoom
  → 计算瓦片范围 → 并发下载（磁盘缓存，失败重试 2 次 + 备用主机）
  → 拼接大图（含 extent 元数据）
  → 滑窗推理：1024 px 窗口、128 px 重叠（大图分块，避免直接缩放丢细节）
  → 掩膜 → 轮廓（cv2.findContours）→ 多边形简化（approxPolyDP, 0.8% 周长）
  → 像素 → 经纬度（Web Mercator 反解，按行做纬度修正）
  → 面积（球面测地线）过滤 < 0.01 ha，重叠 IoU > 0.6 去重（保留置信度高者）
  → GeoJSON FeatureCollection（含 area_m2 / area_mu / confidence）
```

失败降级顺序：`yolo` → `heuristic`（LAB 色彩聚类 + 形态学 + 连通域，无需模型）→ `503` 并说明原因。响应里始终带 `backend` 字段，前端据此提示"当前为规则识别，建议手动修正"。

## 6. 灌溉需水量

设田块面积 `A`（m²，测地线），生育期作物系数 `Kc`，灌溉水利用系数 `η`：

```
# ERA5 逐小时 -> 日尺度（累计量按前一小时归日，缺 24 小时记 NaN）
T   = mean(t2m) - 273.15 ；VPD = es(T) - es(Td) ；u2 = u10*4.87/ln(67.8*10-5.42)
Rn  = (ssr + str)/1e6           # 净辐射 MJ/m2/day
ET0 = [0.408Δ(Rn-G) + γ·900/(T+273)·u2·VPD] / [Δ + γ(1+0.34u2)]   # G≈0
Pe  = min(P * 降雨利用系数, 35)  # 日有效降雨

# 田块 -> 网格：按与 0.25° 网格的面积重叠加权（不是单点取值）
ET0_field = Σ(w_i · ET0_i) / Σ w_i ；Pe_field 同理
ETc      = Kc(作物, 生育期) · ET0_field · kc_scale
净需水   In = max(0, ETc + 渗漏 - Pe_field)   # mm/day，水田渗漏 3 mm/天
毛需水   Ig = In / η                          # mm/day
日水量   V  = Ig(m) * A(m2) / 1000            # m3/day
```

- `Pe`（有效降雨）：ERA5 日降水 × `effective_rain_ratio`（默认 1.0）并封顶 35 mm/天；管理端可用 `effective_rain_mm_day` 强制固定值。
- **系数作用域**：`Kc` 校准、降雨利用系数、灌溉水利用系数按 `global → province:XXX → city:XXX` 继承
  （`services/params.py`），田块解算时按其所在市解析；响应里 `parameter_scope` 给出取值与来源。
- 降级：`era5_daily.npz` 缺失时自动退回 ETMonitor 近似法（区域 Kc 反推 ET0、Pe 记 0），响应 `method` 字段区分。
- 预测：取 2000–2004 年**同一天序**的 ET0/降水均值作为未来 7 天期望曲线，并给出 5 年最小/最大包络作为不确定性带；域外坐标退化为纬度-月序正弦经验模型并标记 `extrapolated=true`。
- 输出同时给 `m³/day`、`m³/week`、`亩均方量`，农户看得懂的量纲优先。

## 7. API

统一前缀 `/api/v1`，JSON；错误 `{"detail": "..."}`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/register` | 注册（手机号 + 口令） |
| POST | `/auth/login` | 返回 `access_token` + 用户 |
| GET | `/auth/me` | 当前用户 |
| GET | `/imagery/providers` | 影像源能力表 |
| GET | `/imagery/tiles/{provider}/{z}/{x}/{y}` | 瓦片代理（带缓存） |
| POST | `/segment` | `{bbox, zoom, provider}` → 候选田块 GeoJSON |
| GET | `/fields` | 我的田块（`?bbox=` 可选） |
| POST | `/fields` | 新建（含几何） |
| GET/PATCH/DELETE | `/fields/{id}` | 详情 / 改属性或几何 / 删除（软删） |
| GET | `/fields/{id}/irrigation?days=7` | 田块需水曲线 + `aggregates`（周/月滚存），days ≤ 180 |
| GET | `/irrigation/summary` | 全部田块汇总（日/周总量） |
| GET | `/history?from=&to=` | 灌溉记录 / 历次计算 |
| POST | `/sync` | 批量推送离线操作，返回权威副本 |
| GET | `/admin/users` `PATCH` `/admin/users/{id}` | 用户管理 |
| GET | `/admin/fields` | 全部田块 + 归属 |
| GET | `/admin/stats` | 覆盖率、活跃用户、区域总需水 |
| GET/PATCH | `/admin/params?scope=` | 区域化系数（global / province / city 三级继承） |
| GET | `/geo/search` `/geo/locate` `/geo/regions` | 行政区模糊搜索 / 坐标反查 / 层级列表 |
| GET | `/admin/regions/overview` `/admin/regions/summary` | 行政区需水汇总与用水户统计 |
| GET/POST | `/admin/meteo/status` `/fs` `/upload` `/scan` `/rebuild` | 气象数据运维 |

## 7.5 行政区划与气象运维

**行政区划**（`services/regions.py` + `artifacts/admin/`）

```
DataV.GeoAtlas ────────────────┐
                               ├─► provinces.geojson (0.42 MB)
modood/Administrative-divisions┤   cities.geojson    (1.40 MB)
  streets.json / villages.json ├─► index.json        (0.52 MB, 3238 条)
                               ├─► towns.json        (1.13 MB, 3.2 万)
                               └─► villages.txt      (19.7 MB, 49.9 万)
```

- 省/市带多边形（简化 0.01°），区县只有名称与中心点；乡镇/村只有名称与编码。
- `search()` 打分：全等 100 > adcode 前缀 92 > 名称前缀 88 > 子串 72 > 子序列 40+；
  乡镇/村只做前四档（不做子序列，避免 50 万条噪声），命中数上限 `limit*6` 早停。
- 乡/村坐标取 `areaCode` 对应的区县中心，响应标 `precision: district-center`。
- `locate()` 先用 bbox 预筛再做点在多边形，返回 (省, 市)；田块按中心点落区。

**气象导入**（`services/meteo.py` + `services/era5_build.py`）

```
上传/扫描 ──► data/meteo_inbox/ ──► group_files() 按年份配对 8 变量
          ──► build_year()  逐小时 → 日尺度派生（与 build 脚本同一实现）
          ──► merge()   union(dates)，新值覆盖旧值，其余保持
          ──► era5_daily.npz 原子写 + era5.reset() 热重载
```

- 只有 8 个变量齐全的年份才会重算，缺项写入 `skipped` 而不是猜值。
- 合并是幂等的：重复导入同一年只覆盖对应日期，不会产生重复行。

## 8. 数据模型

```
users(id, phone, username, pass_hash, name, role=['admin','farmer'], created_at)
fields(id, owner_id, name, crop, stage_key, plant_date, geom_json, bbox_minx/miny/maxx/maxy,
       area_m2, source=['segment','manual','segment+edited'], confidence,
       created_at, updated_at, deleted_at, rev)
irrigation_logs(id, field_id, computed_at, days, payload_json, request_json)
sync_ops(op_id PK, user_id, kind, entity_id, payload_json, applied_at)   -- 幂等去重
params(key PK, value_json, updated_at)
```

## 9. 前端布局（三形态）

| 断点 | 布局 |
|---|---|
| ≥ 1024 px（桌面/平板横屏） | 左工具栏 64 px · 中地图 · 下次级表（可折叠 200→320 px）· 右详情 340 px |
| 768–1023 px | 左工具栏 56 px · 中地图 · 右详情 300 px（下滑面板） |
| < 768 px（手机竖屏） | 地图全屏；工具栏收为左侧悬浮竖排图标（可展开）；次级表为底部可拖拽面板（三档吸附 96/320/70vh）；详情为覆盖抽屉 |

触摸规范：可点目标 ≥ 44×44 px；地图编辑手柄 12 px 视觉 + 24 px 命中区；底部面板用 `dvh` 而非 `vh`，避免移动浏览器地址栏跳动。

## 10. 目录

```
整合demo01/
├─ docs/            架构与接口文档
├─ server/          FastAPI 服务
│  ├─ app/{routers,services,schemas,core}
│  ├─ scripts/      资产生成（ET 网格、种子数据）
│  ├─ artifacts/    et_grid.npz、yolo 权重（gitignore）
│  └─ tests/
└─ web/             React PWA
   ├─ src/{components,lib,store,pages}
   └─ public/
```

## 11. 验收标准

1. `python -m uvicorn app.main:app` 起来后 `/docs` 可交互；`/healthz` 返回 `{ok: true, backends: {...}}`。
2. `POST /api/v1/segment` 对 37.80,118.80 的 z18 影像返回 ≥ 10 个多边形，面积量级 0.05–2 ha。
3. `GET /api/v1/fields/{id}/irrigation` 返回 7 天曲线，数值在 0–12 mm/day 且带 `assumptions`。
4. 前端 `npm run build` 通过；手机宽度 390 px 下主视图占满、四个功能入口均可触达。
5. 离线：断网后刷新仍能看到已缓存田块，编辑后联网自动同步。
