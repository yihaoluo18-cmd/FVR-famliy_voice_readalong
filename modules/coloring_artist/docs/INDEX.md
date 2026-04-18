# 🎨 涂色小画家 (Coloring Artist) - 文档导航

> 一个为儿童打造的智能涂色游戏系统，集合了 AI 评价、区域识别、推荐色系等功能。

## 📚 文档导航指南

### 🚀 快速开始 (5-10 分钟)

**新手推荐阅读顺序：**

1. **[快速启动指南](./COLORING_QUICKSTART.md)** ⭐⭐⭐
   - 5 分钟快速上手
   - 后端集成步骤
   - 前端验证方法
   - **需要做什么**: 集成 API → 启动服务 → 测试接口

### 📋 部署与配置

2. **[部署检查表](./COLORING_DEPLOYMENT.md)**
   - 完整部署流程
   - 环境配置检查
   - 常见问题排查
   - **何时使用**: 准备上线前，确保所有依赖已配置

### 🛠️ 详细实现

3. **[实现说明](./COLORING_IMPLEMENTATION.md)**
   - 功能模块详解
   - API 端点文档
   - 前端交互逻辑
   - 数据格式规范
   - **何时使用**: 需要理解具体功能实现细节

### 🏗️ 深度技术

4. **[技术架构](./COLORING_ARCHITECTURE.md)**
   - 4 层 Canvas 系统设计
   - 区域识别算法
   - AI 评价流程
   - 性能优化策略
   - **何时使用**: 需要自定义扩展或优化性能

### 📊 项目总结

5. **[项目报告](./COLORING_PROJECT_REPORT.md)**
   - 完成度统计
   - 技术实现总结
   - 已知限制与未来方向
   - **何时使用**: 项目review或进度汇报

### 📖 完整说明

6. **[README](./README_COLORING.md)**
   - 功能特色概览
   - 项目结构全景
   - 游戏流程演示
   - **何时使用**: 整体了解项目

### 📝 变更记录

- **[变更总结](./COLORING_CHANGES_SUMMARY.md)** - 完整实现过程中的所有修改

---

## 🎯 按角色推荐阅读

### 👨‍💼 产品经理
- [README](./README_COLORING.md) - 功能特色
- [项目报告](./COLORING_PROJECT_REPORT.md) - 完成度统计

### 👨‍💻 后端开发
- [快速启动指南](./COLORING_QUICKSTART.md) - API 集成
- [实现说明](./COLORING_IMPLEMENTATION.md) - API 详解
- [部署检查表](./COLORING_DEPLOYMENT.md) - 部署指南

### 🎨 前端开发
- [快速启动指南](./COLORING_QUICKSTART.md) - 接口位置
- [实现说明](./COLORING_IMPLEMENTATION.md) - 前端逻辑
- [技术架构](./COLORING_ARCHITECTURE.md) - Canvas 细节

### 🔧 运维/DBA
- [部署检查表](./COLORING_DEPLOYMENT.md) - 完整部署流程
- [技术架构](./COLORING_ARCHITECTURE.md) - 系统设计

### 🎓 学习者
1. [README](./README_COLORING.md) - 功能概览
2. [快速启动指南](./COLORING_QUICKSTART.md) - 实践入门
3. [技术架构](./COLORING_ARCHITECTURE.md) - 深度学习
4. [实现说明](./COLORING_IMPLEMENTATION.md) - 细节理解

---

## 📁 项目文件位置

```
项目根目录/
├── modules/coloring_artist/docs/   ← 📚 你在这里
│   ├── INDEX.md                      ← 本文件（文档导航）
│   ├── README_COLORING.md            ← 项目概览
│   ├── COLORING_QUICKSTART.md        ← 快速启动
│   ├── COLORING_DEPLOYMENT.md        ← 部署指南
│   ├── COLORING_IMPLEMENTATION.md    ← 实现详解
│   ├── COLORING_ARCHITECTURE.md      ← 技术架构
│   ├── COLORING_PROJECT_REPORT.md    ← 项目报告
│   └── COLORING_CHANGES_SUMMARY.md   ← 变更记录
│
├── coloring_api.py                   ← FastAPI 路由
├── practice/
│   ├── generate_coloring_lineart.py  ← 线稿生成脚本
│   ├── coloring_prompts.json         ← 任务定义
│   └── coloring/
│       ├── index.json                ← 线稿索引
│       ├── lineart/                  ← 线稿 PNG
│       └── regionmap/                ← 区域索引图
│
└── modules/wechat_frontend/miniprogram1/pages/color/
    ├── color.js                      ← JS 逻辑
    ├── color.wxml                    ← 页面模板
    └── color.wxss                    ← 样式设计
```

---

## 🔗 相关链接

- **后端主服务**: `modules/tts_backend/wx_api.py`（端口 9880）
- **跟读评测服务**: `readalong_api.py`（端口 9881）
- **启动脚本**: `start_wx_api.sh`（一键启动所有服务）
- **环境配置**: `wx_api.env`

---

## ⚡ 快捷命令

### 启动服务
```bash
# 一键启动所有服务（推荐）
./start_wx_api.sh

# 仅启动主服务（不启动跟读评测）
./start_wx_api.sh --wx-only

# 仅启动跟读评测服务
./start_wx_api.sh --readalong-only

# 重启跟读评测服务
./start_wx_api.sh --restart-readalong
```

### 健康检查
```bash
# 检查涂色 API
curl http://127.0.0.1:9880/coloring/health

# 检查跟读评测 API
curl http://127.0.0.1:9881/readalong/health
```

### 生成线稿
```bash
# 生成 30 张线稿和区域索引图
python modules/coloring_artist/practice/generate_coloring_lineart.py
```

---

## ✅ 部署检查清单

- [ ] 已集成 `modules/coloring_artist/backend/coloring_api.py` 到主 API 应用
- [ ] 已配置 Volcano Engine 密钥（或本地代理）
- [ ] 已使用 `start_wx_api.sh --restart-readalong` 启动服务
- [ ] `/coloring/health` 端点响应正常
- [ ] 前端 `/pages/color/` 已集成
- [ ] 30 张线稿已生成

---

## 📞 常见问题

### Q: 涂色模块在哪？
**A**: 前端在 `modules/wechat_frontend/miniprogram1/pages/color/`，后端在 `modules/coloring_artist/backend/coloring_api.py`

### Q: 如何生成线稿？
**A**: 执行 `python modules/coloring_artist/practice/generate_coloring_lineart.py`（需要 Volcano Engine 密钥）

### Q: 我需要自定义颜色/区域？
**A**: 编辑 `practice/coloring_prompts.json`，然后重新运行生成脚本

### Q: AI 评价如何调整语气？
**A**: 查看 [实现说明](./COLORING_IMPLEMENTATION.md) 中的"AI 评价" 章节

### Q: 如何查看完整 API 文档？
**A**: 启动后访问 `http://127.0.0.1:9880/docs` 或 `http://127.0.0.1:9880/redoc`

---

**最后更新**: 2025-03-18  
**版本**: v2.0 (完整实现版)  
**维护者**: AI Assistant
