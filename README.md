# HydroCS 智能灌溉管理平台

面向农业灌溉管理的 Web 前端应用，分为管理员端和用户端。

## 技术栈

- React 18 + TypeScript + Vite
- NextUI (HeroUI) + Tailwind CSS
- Leaflet + react-leaflet
- MSW (Mock Service Worker)

## 快速启动

```bash
npm install
npm run dev
```

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |
| farmer1 | 123456 | 农户 |
| farmer2 | 123456 | 农户 |

## 功能概览

### 管理员端
- 地图总览：Leaflet 地图，缩放自动切换卫星图
- 用户管理：查看用户列表
- 田块管理：查看全部田块及绑定状态
- 数据总表：区域灌溉预测数据、需水量统计
- 参数微调：功能按钮占位

### 用户端
- 地图总览：定位、搜索、田块识别叠加
- 田块框选与绑定：选择田块 → 录入作物信息 → 绑定账号
- 灌溉预测：查看不同时期的预测灌溉量（模拟数据）
- 我的田块：已绑定田块管理

## 项目结构

```
src/
├── api/          # MSW handlers + mock data
├── components/   # Layout, Sidebar, MapView, ToolBar, DataPanel
├── pages/        # admin/ + user/ 页面组件
├── store/        # AuthContext, MapContext, ThemeContext
└── types/        # TypeScript 类型定义
```
