# HydroCS 智能灌溉管理平台

面向农业灌溉管理的 Web 前端应用，基于 React + TypeScript + Vite 构建，支持管理员端与用户端双角色，以 Leaflet 交互地图为核心，提供田块管理、灌溉预测、数据总览等功能。

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | React 18 + TypeScript 5.5 |
| 构建 | Vite 5.4 |
| UI | HeroUI (NextUI) v2.7 + Tailwind CSS v4 |
| 地图 | Leaflet 1.9 + react-leaflet 4.2 |
| Mock API | MSW 2.3 (Service Worker 级别拦截) |
| 路由 | React Router v6 |
| 认证 | Mock JWT + localStorage |

## 快速启动

```bash
# 安装依赖
npm install

# 启动开发服务器 (默认端口 3000)
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

启动后访问 `http://localhost:3000`。

> 注意：MSW Service Worker 在首次启动时自动生成，如遇 API 请求失败请刷新页面。

## 测试账号

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| `admin` | `admin123` | 管理员 | 查看全部数据、管理用户和田块 |
| `farmer1` | `123456` | 农户 | 已绑定 2 块田（小麦、玉米），有灌溉预测数据 |
| `farmer2` | `123456` | 农户 | 已绑定 2 块田（水稻、大豆），有灌溉预测数据 |

### 账号数据详情

**farmer1（张三）**：
- 田块 A1（3.5 亩，小麦，拔节期）— 有灌溉记录
- 田块 B1（2.8 亩，玉米，苗期）— 有灌溉记录

**farmer2（李四）**：
- 田块 A2（4.2 亩，水稻，分蘖期）— 有灌溉记录
- 田块 B2（1.6 亩，大豆，开花期）— 有灌溉记录

**未绑定田块（任意用户可绑定）**：
- 田块 C1（2.1 亩）
- 田块 C2（5.0 亩）

## 路由结构

| 路由 | 角色 | 页面 | 说明 |
|------|------|------|------|
| `/login` | 公开 | 登录页 | 输入用户名密码登录 |
| `/admin` | 管理员 | 地图总览 | 全部田块地图 + 右侧统计面板 |
| `/admin/users` | 管理员 | 用户管理 | 用户列表，含用户名、姓名、角色、绑定田块数 |
| `/admin/fields` | 管理员 | 田块管理 | 全部田块列表，含名称、面积、绑定用户、作物 |
| `/admin/data` | 管理员 | 数据总表 | 区域灌溉预测数据、需水量统计汇总 |
| `/admin/settings` | 管理员 | 参数微调 | 天气数据上传、模型参数调整等按钮（占位） |
| `/dashboard` | 用户 | 地图总览 | 主地图 + 附近田块识别 + 田块框选绑定 + 灌溉预测 |
| `/dashboard/fields` | 用户 | 我的田块 | 已绑定田块列表 + 各田块灌溉预测记录表 |

## 功能详述

### 管理员端

**地图总览 (`/admin`)**
- 展示全部 6 块田块的地理边界叠加
- 绿色 = 未绑定，黄色 = 已绑定
- 右侧面板：总需水量、活跃用户数、已绑定田块数、覆盖率
- 地图支持搜索定位（村级及以上精度）
- 缩放 ≥ 10 级自动切换卫星影像

**用户管理 (`/admin/users`)**
- 表格列出所有用户：用户名、姓名、手机号、角色、绑定田块数
- 管理员标记为琥珀色高亮

**田块管理 (`/admin/fields`)**
- 表格列出所有田块：名称、面积、绑定用户、作物、生长阶段
- 支持修改绑定关系（模拟）

**数据总表 (`/admin/data`)**
- 区域灌溉汇总统计
- 各田块详细灌溉记录表：日期、作物、生长阶段、预测量、实际量

**参数微调 (`/admin/settings`)**
- 天气数据上传按钮（模拟）
- 模型参数调优按钮（模拟）
- 灌溉阈值设置按钮（模拟）
- 通知推送设置按钮（模拟）

### 用户端

**地图总览 (`/dashboard`)**
- Leaflet 交互地图，支持拖拽缩放
- 缩放 < 10 级：高德矢量地图
- 缩放 ≥ 10 级：Esri 卫星影像
- 搜索框：输入地名 → Nominatim 地理编码定位（支持中文，村级及以上精度）
- 田块叠加层：点击田块查看详情、显示灌溉预测
- "识别周边田块"按钮：列出附近可绑定田块
- 田块绑定流程：选择田块 → 录入作物类型、生长阶段、播种日期 → 绑定
- 已绑定田块以黄色显示，未绑定以绿色显示

**我的田块 (`/dashboard/fields`)**
- 已绑定田块卡片列表
- 每块田显示：名称、面积、作物、生长阶段、播种日期、本周预测灌溉量
- 灌溉预测记录表：日期、生长阶段、预测灌溉量
- "在地图上显示"按钮：点击跳转回地图并自动定位放大到该田块

## Mock API 端点

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/auth/login` | 登录，返回 token + user | 无 |
| GET | `/api/auth/me` | 获取当前用户信息 | Bearer Token |
| GET | `/api/admin/users` | 用户列表 | 管理员 |
| GET | `/api/admin/fields` | 全部田块 | 管理员 |
| PUT | `/api/admin/fields/:id` | 更新田块绑定 | 管理员 |
| GET | `/api/admin/stats` | 汇总统计数据 | 管理员 |
| GET | `/api/admin/weather` | 天气状态 | 管理员 |
| GET | `/api/fields/nearby?lat=&lng=` | 查询附近田块（带距离） | 用户 |
| GET | `/api/my/fields` | 我的田块（按 ownerId 过滤） | 用户 |
| POST | `/api/my/fields/bind` | 绑定田块（已绑定返回 409） | 用户 |
| PUT | `/api/my/fields/:id` | 更新我的田块（作物/生长阶段） | 用户 |
| GET | `/api/my/fields/:id/irrigation` | 田块灌溉预测记录 | 用户 |

## 项目结构

```
src/
├── api/
│   ├── auth.ts              # Token 管理（生成/存储/清除）
│   ├── handlers.ts          # MSW 请求处理器（12 个端点）
│   └── mock-data.ts         # 模拟数据（3 用户、6 田块、6 灌溉记录）
├── components/
│   ├── DataPanel.tsx         # 右侧数据面板（260px，响应主题切换）
│   ├── Layout.tsx            # 三栏布局：左菜单 + 中内容 + 右数据
│   ├── MapView.tsx           # Leaflet 地图组件（搜索、图层切换、田块叠加）
│   ├── ProtectedRoute.tsx    # 路由守卫（认证 + 角色检查）
│   ├── Sidebar.tsx           # 左侧菜单栏（200px，图标 + 文字）
│   └── ToolBar.tsx           # 底部工具栏（统一 130px 按钮）
├── pages/
│   ├── Login.tsx             # 登录页面
│   ├── admin/
│   │   ├── AdminDashboard.tsx # 管理员地图总览
│   │   ├── DataOverview.tsx   # 数据总表
│   │   ├── FieldManage.tsx    # 田块管理
│   │   ├── Settings.tsx       # 参数微调（占位按钮）
│   │   └── UserManage.tsx     # 用户管理
│   └── user/
│       ├── MyFields.tsx       # 我的田块
│       └── UserDashboard.tsx  # 用户地图总览（田块识别+绑定）
├── store/
│   ├── AuthContext.tsx        # 认证状态管理
│   ├── MapContext.tsx         # 地图状态（缩放/中心/图层）
│   └── ThemeContext.tsx       # 主题管理（暗色/亮色切换）
├── types/
│   └── index.ts              # TypeScript 类型定义
├── App.tsx                   # 路由配置
├── index.css                 # 全局样式 + CSS 变量（亮/暗主题）
├── main.tsx                  # 应用入口（MSW 启动 + React 挂载）
└── vite-env.d.ts             # Vite 类型声明
```

## 主题系统

支持亮色/暗色双模式切换，点击右上角按钮即可切换。

- 暗色模式（默认）：`#0a0e17` 深蓝黑背景，柔和蓝灰色前景，柔和对比度
- 亮色模式：`#f5f5f5` 浅灰背景，深灰前景
- 色彩控制：暗色 14 个 CSS 变量，亮色 14 个 CSS 变量，通过 `.dark` class 切换
- ThemeContext 响应式管理，DataPanel 直接读取 isDark 确保可靠切换

## 开发记录

### 开发流程

1. **需求分析与头脑风暴** (2026-06-10)
   - 确定技术栈：React + TypeScript + Vite + HeroUI + Tailwind + Leaflet + MSW
   - 确定布局：左菜单 + 中地图 + 右数据面板 + 下工具栏
   - 确定地图方案：高德矢量 + Esri 卫星，缩放级别自动切换
   - 确定认证方案：Mock JWT + localStorage

2. **设计文档**
   - `docs/superpowers/specs/2026-06-10-hydrocs-frontend-design.md`
   - `docs/superpowers/plans/2026-06-10-hydrocs-frontend.md`

3. **实现阶段** (12 次提交)
   - 项目脚手架：Vite + React + TS + MSW + HeroUI
   - 认证模块：登录页、AuthContext、路由守卫
   - 布局框架：Sidebar、ToolBar、DataPanel、Layout
   - 地图模块：Leaflet、图层切换、搜索、田块叠加
   - 用户端：田块识别 → 框选 → 绑定 → 灌溉预测 → 我的田块
   - 管理员端：用户/田块管理、数据总表、参数微调

### Bug 修复记录

| 提交 | 修复内容 |
|------|----------|
| `f25b714` | MSW handlers: `/auth/me` session 认证修复、`/my/fields` 所有权过滤 |
| `e9f919c` | MSW 启动错误处理、移除无效 favicon 引用 |
| `cf50e63` | 主题切换修复（CSS 变量 + document.documentElement）、登录占位符、田块地图跳转、地图搜索 |
| `36c4c90` | DataPanel 主题响应修复（useTheme + inline styles） |

### 已知限制

- Mock API 数据为静态内存数据，刷新页面后修改丢失
- 地图搜索依赖 Nominatim（OpenStreetMap），需联网
- 地图瓦片加载依赖高德/Esri 服务，需联网
- 默认端口 3000（5173 被占用时备用）
