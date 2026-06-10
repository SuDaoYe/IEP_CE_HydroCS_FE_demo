# HydroCS 智能灌溉系统 — 前端设计规格

## 项目概述

面向农业灌溉管理的 Web 前端应用，分为管理员端和用户端。管理员负责数据上传、用户田块管理、查看统计；用户通过地图定位框选绑定田块，录入作物信息，查看预测灌溉量。

## 技术栈

| 层面 | 选择 | 理由 |
|------|------|------|
| 框架 | React 18 + TypeScript | 类型安全，生态成熟 |
| 构建 | Vite | 开发启动快，HMR 即时 |
| UI 库 | NextUI (HeroUI) | 暗色原生支持，组件现代，后续可换 shadcn/ui |
| 样式 | Tailwind CSS | 与 NextUI 深度集成，主题切换方便 |
| 地图 | Leaflet + react-leaflet | 轻量，延续 gis.html 技术积累 |
| 数据 | MSW (Mock Service Worker) | 拦截 fetch 返回模拟数据，边界清晰 |
| 认证 | Mock JWT | 完整登录流程，未来迁移零改动 |

## 配色体系

双主题（暗色/亮色），通过 NextUI ThemeProvider 切换。仅使用 3 个灰阶 + 1 个强调色 + 1 个状态色。

| 语义 | 暗色 | 亮色 | 用途 |
|------|------|------|------|
| 页面底色 | `#0a0e17` | `#f5f5f5` | 最底层背景 |
| 面板/卡片 | `#131820` | `#ffffff` | 内容容器 |
| 侧栏底色 | `#0d1117` | `#fafafa` | 左侧菜单区 |
| 分割线 | `#1e2430` | `#e5e5e5` | 边框、分隔 |
| 主文字 | `#c8ccd0` | `#1a1a1a` | 标题、选中菜单 |
| 正文 | `#9ca3af` | `#555555` | 菜单项、表格、标签 |
| 辅助文字 | `#6b7280` | `#999999` | 提示、说明 |
| 强调色 | `#818cf8` | `#6366f1` | 关键数据数字、选中态 |
| 状态绿 | `#34d399` | `#10b981` | 正常状态 |

图标仅限左侧菜单栏使用，其余区域纯文字。底部工具栏按钮等宽等间距。

## 路由结构

```
/login                    — 登录页（admin + user 共用）
/admin                    — 管理员主面板（默认地图视图）
/admin/users              — 用户管理
/admin/fields             — 田块管理
/admin/data               — 数据总表
/admin/settings           — 参数微调
/dashboard                — 用户主面板（默认地图视图）
/dashboard/fields         — 我的田块
```

## 布局

统一三栏结构，管理员端和用户端共用框架：

- **顶部栏**: Logo/名称 + 主题切换 + 用户名 + 退出
- **左侧栏** (200px): 菜单（图标仅在菜单中出现）
- **中间上**: Leaflet 地图（始终显示，含搜索框覆盖层）
- **中间下**: 工具条（等宽按钮，管理员: 上传气象/参数微调/导出；用户: 定位/识别/框选/绑定）
- **右侧栏** (260px): 数据面板

> 地图缩放逻辑：省/市级加载矢量地图，区/县级及以下切换卫星图像（Esri World Imagery），国内田块区域叠加天地图卫星瓦片。

## 模块划分

### Auth 模块
- Mock JWT 登录，localStorage 存 token
- 路由守卫（ProtectedRoute），按角色区分 admin/user
- 预置账号: `admin/admin123`, `farmer1/123456`, `farmer2/123456`

### Map 模块
- Leaflet 地图容器，react-leaflet 封装
- 缩放级别监听，自动切换底图图层
- 搜索定位（地名→经纬度→移动地图中心）
- 田块 GeoJSON 叠加层（模拟附近田块识别结果）
- 用户可点击/框选田块，拖移到已选列表

### Data 模块
- MSW 拦截全部 `/api/*` 请求
- 管理员: 用户 CRUD、田块绑定管理、聚合统计、气象状态
- 用户: 附近田块查询、绑定/解绑、作物信息维护、灌溉预测量查询
- 所有数值为模拟数据（随机但合理范围）

## API 端点

### 认证
- `POST /api/auth/login` — 登录，返回 token + role
- `GET  /api/auth/me` — 当前用户信息

### 管理员
- `GET  /api/admin/users` — 用户列表
- `GET  /api/admin/fields` — 全部田块
- `PUT  /api/admin/fields/:id` — 修改田块绑定
- `GET  /api/admin/stats` — 聚合统计
- `GET  /api/admin/weather` — 气象数据状态

### 用户
- `GET  /api/fields/nearby?lat=&lng=` — 附近田块
- `GET  /api/my/fields` — 我的田块
- `POST /api/my/fields/bind` — 绑定田块（含作物、周期）
- `PUT  /api/my/fields/:id` — 更新田块作物信息
- `GET  /api/my/fields/:id/irrigation` — 灌溉预测量

## 数据模型

```typescript
interface User {
  id: string;
  username: string;
  password: string;     // mock only
  role: "admin" | "user";
  name: string;
  phone: string;
}

interface Field {
  id: string;
  name: string;
  area: number;         // 亩
  bounds: [number, number][];  // GeoJSON polygon
  ownerId: string | null;
  crop: string | null;
  growthStage: string | null;
  plantDate: string | null;
}

interface IrrigationRecord {
  fieldId: string;
  date: string;
  predicted: number;    // m³
  actual: number | null;
  stage: string;
}

interface WeatherStatus {
  lastUpdate: string;
  temperature: number;
  humidity: number;
  rainfall: number;
  status: "normal" | "warning";
}
```

## 状态管理

- **AuthContext** — user, token, login(), logout() — 全局
- **MapContext** — zoom, center, selectedField, layerMode — 地图相关组件
- 页面级数据（列表、统计）由各组件自行 fetch + useState

## 目录结构

```
src/
├── main.tsx
├── App.tsx
├── api/
│   ├── handlers.ts       # MSW request handlers
│   ├── mock-data.ts      # 预置 mock 数据
│   └── auth.ts           # token 生成/验证
├── components/
│   ├── Layout.tsx        # 三栏布局容器
│   ├── Sidebar.tsx       # 左侧菜单
│   ├── MapView.tsx       # Leaflet 地图封装
│   ├── DataPanel.tsx     # 右侧数据面板
│   ├── ToolBar.tsx       # 底部工具条
│   └── ProtectedRoute.tsx
├── pages/
│   ├── Login.tsx
│   ├── admin/
│   │   ├── AdminDashboard.tsx
│   │   ├── UserManage.tsx
│   │   ├── FieldManage.tsx
│   │   ├── DataOverview.tsx
│   │   └── Settings.tsx
│   └── user/
│       ├── UserDashboard.tsx
│       └── MyFields.tsx
├── store/
│   ├── AuthContext.tsx
│   └── MapContext.tsx
└── types/
    └── index.ts
```

## 实现顺序

1. 项目脚手架（Vite + React + TS + Tailwind + NextUI + MSW）
2. Auth 模块（Login 页 + AuthContext + ProtectedRoute + Mock API）
3. 布局框架（Layout + Sidebar + ToolBar + DataPanel）
4. 地图模块（MapView + 图层切换 + 搜索定位）
5. 用户端田块流程（附近识别 → 框选 → 绑定 → 作物录入 → 灌溉预测）
6. 管理员端（用户管理 + 田块管理 + 数据总表 + 气象状态）
7. 主题切换（亮/暗）
8. 收尾（类型检查、构建验证、README）
