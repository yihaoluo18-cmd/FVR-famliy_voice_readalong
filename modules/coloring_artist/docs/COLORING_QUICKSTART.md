# 涂色小画家 - 快速启动指南

## ⚡ 5分钟快速启动

### 步骤 1: 后端集成 (1分钟)

打开 `modules/tts_backend/api_v2.py`，在导入部分添加：

```python
from coloring_api import router as coloring_router

# 在  app 初始化后添加
app.include_router(coloring_router)
```

### 步骤 2: 启动测试 (2分钟)

```bash
# 1. 确保后端运行
./start_wx_api.sh --wx-only

# 2. 在另一个终端测试
curl http://127.0.0.1:9880/coloring/health

# 预期输出：
# {"ok": true, "module": "coloring", "sketches_available": 5}
```

### 步骤 3: 前端测试 (2分钟)

1. 打开 WeChat DevTools
2. 导入项目（若未导入）：`modules/wechat_frontend/miniprogram1` 文件夹
3. 进入 **游乐园** > **涂色小画家**

---

## 📋 完整部署清单

### 前置要求
- [ ] Node.js 已安装（小程序开发）
- [ ] Python 3.8+ 已安装
- [ ] FastAPI 依赖已安装：`pip install fastapi uvicorn`
- [ ] volcengine SDK（可选）：`pip install volcengine`

### 配置

1. **检查后端 API 基础地址**
   - 文件：`modules/wechat_frontend/miniprogram1/pages/color/color.js`
   - 确认：`apiBaseUrl` 匹配你的后端地址（默认 `http://127.0.0.1:9880`）

2. **检查火山引擎配置**（可选，用于生成线稿）
   - 文件：`wx_api.env`
   - 需要：`VOLC_ACCESSKEY` 和 `VOLC_SECRETKEY`

### 线稿准备

#### 选项 A：使用预先生成的线稿（推荐用于测试）

不需要任何操作！`practice/coloring/index.json` 已包含 5 个示例项目。

#### 选项 B：生成完整线稿（30张）

```bash
cd /path/to/test1

# 运行生成脚本
python modules/coloring_artist/practice/generate_coloring_lineart.py

# 预期时间：30-60分钟（取决于网络）
# 输出位置：
#   - practice/coloring/lineart/
#   - practice/coloring/regionmap/
#   - practice/coloring/index.json (更新)
```

### 部署步骤

1. **后端**
   ```bash
   # 1. 集成到 modules/tts_backend/api_v2.py（见步骤1）
   # 2. 重启 API 服务
   ./start_wx_api.sh --wx-only
   ```

2. **前端**
   ```
   - 在 WeChat DevTools 中编译小程序
   - 无需额外编译步骤
   ```

3. **验证**
   ```bash
   # 测试 API 是否可用
   curl http://127.0.0.1:9880/coloring/get_sketches

   # 预期返回：
   # {
   #   "ok": true,
   #   "total": 30,
   #   "items": [...]
   # }
   ```

---

## 🎮 使用场景

### 场景 1：用户开始游戏

```
用户点击【游乐园】→ 【涂色小画家】
    ↓
前端 GET /coloring/get_sketches（加载30张线稿）
    ↓
展示网格化线稿列表
    ↓
用户点击某个线稿
    ↓
进入涂色模式
```

### 场景 2：用户涂色

```
用户点击线稿中的某个区域
    ↓
前端识别区域（通过 regionMap 像素查询）
    ↓
高亮区域 + 显示推荐色
    ↓
用户选择颜色
    ↓
填充区域（绘制到 paintCanvas）
    ↓
继续 or 完成
```

### 场景 3：完成涂色

```
用户点击【完成】
    ↓
前端合成 PNG（paintCanvas + 线稿）
    ↓
POST /readalong/evaluate（上传 AI 评价）
    ↓
显示星级 + 反馈
    ↓
选择保存位置（云端 / 本地）
    ↓
POST /coloring/save_work（保存记录）
    ↓
获得星星奖励
```

---

## 🔧 常用命令

```bash
# 启动后端 API
./start_wx_api.sh --wx-only

# 生成线稿（首次完整部署）
python modules/coloring_artist/practice/generate_coloring_lineart.py

# 更新索引（线稿更新后）
curl -X POST http://127.0.0.1:9880/coloring/regenerate_index

# 获取线稿列表
curl http://127.0.0.1:9880/coloring/get_sketches

# 获取用户作品
curl http://127.0.0.1:9880/coloring/get_user_works/user_123

# 健康检查
curl http://127.0.0.1:9880/coloring/health
```

---

## 📁 关键文件速查

| 需要修改的文件 | 用途 | 优先级 |
|--------------|------|--------|
| `modules/tts_backend/api_v2.py` | 导入并注册 coloring router | 🔴 必须 |
| `modules/wechat_frontend/miniprogram1/pages/color/color.js` | 前端逻辑，可以改 API 地址和提示词 | 🟡 可选 |
| `practice/coloring_prompts.json` | 自定义线稿内容 | 🟢 可选 |
| `wx_api.env` | 火山引擎配置（生成线稿用） | 🟢 可选 |

---

## ✅ 验收标准

你的部署成功的标志：

- [ ] 后端 API 健康检查通过（`/coloring/health` 返回 `ok: true`）
- [ ] 小程序能加载线稿列表（至少看到 5-30 个线稿卡片）
- [ ] 点击线稿进入涂色模式（显示线稿 + 颜色选择器）
- [ ] 点击区域能高亮显示（有视觉反馈）
- [ ] 填充颜色能显示（看到彩色填充）
- [ ] 点击完成触发评价弹窗（获得星级反馈）
- [ ] 保存作品成功（后端日志无错误）

---

## 🐛 故障排查

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| API 返回 404 | 未注册 router | 检查 `modules/tts_backend/api_v2.py` 中的导入和注册 |
| 线稿加载失败 | 前端 API 地址错误 | 修改 `color.js` 的 `apiBaseUrl` |
| 涂色没反应 | Canvas 初始化失败 | 检查微信开发者工具 Console |
| 评价无法调用 | `/readalong/evaluate` 不可用 | 确保主 API 已启动 |
| 生成线稿超时 | 网络慢或火山引擎 API 限流 | 重试或稍后运行 |

---

## 📞 需要帮助？

1. **检查日志**
   ```
   微信开发者工具：Console 标签
   后端服务器：终端输出
   ```

2. **查看完整文档**
   ```
   COLORING_IMPLEMENTATION.md  # 详细设计文档
   coloring_api.py              # API 代码和注释
   modules/coloring_artist/practice/generate_coloring_lineart.py  # 线稿生成逻辑
   ```

3. **联系支持**
   - 检查 `color.js` 中的 TODO 注释
   - 查看 API 返回的错误信息

---

**快速启动完成！** 🎉

接下来你可以：
- 在小程序中测试涂色功能
- 生成完整的 30 张线稿（可选）
- 自定义提示词和推荐色系
- 集成到完整的小程序工作流
