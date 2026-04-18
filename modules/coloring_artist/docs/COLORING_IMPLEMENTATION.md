# 涂色小画家 - 完整实现说明

## 📋 项目概述

**涂色小画家**是紫宝故事园小程序中的核心游戏功能，为3-7岁儿童提供互动式涂色体验。

### 核心功能

1. **模式A - 预设线稿涂色** 📐
   - 30张精心设计的儿童涂色线稿
   - 区域识别点击填充
   - 区域提示和推荐色系
   - AI评价和反馈

2. **模式B - 自由创作涂色** 🎨（可选）
   - 儿童输入想法生成图画
   - 前端调用图生图模型（火山引擎 DreamO）
   - 自主填色
   - 完整工作流支持

### 技术特点

- **区域识别**：通过 regionMap 像素检测快速定位填色区域
- **Canvas多层管理**：paintCanvas（填充）、highlightCanvas（高亮）、regionCanvas（索引）、mergeCanvas（输出）
- **AI评价集成**：复用现有 `/readalong/evaluate` 端点，自定义评价提示词
- **智能推荐**：每个区域提供适配的色系建议
- **保存支持**：PNG导出 + 后端存储 + 本地存储双选

---

## 🏗️ 项目结构

### 前端

```
modules/wechat_frontend/miniprogram1/pages/color/
├── color.js        # 核心逻辑（450+行）
├── color.wxml      # 页面布局
├── color.wxss      # 样式设计
└── color.json      # 页面配置
```

**color.js 要点**：
- 两种模式：列表选择 vs 涂色界面
- Canvas 初始化和多层管理
- 区域识别算法（像素查询）
- 填充历史管理（支持撤销）
- AI 评价并行调用
- PNG 导出和保存流程

### 后端

```
coloring_api.py                    # FastAPI 路由模块
practice/
├── generate_coloring_lineart.py    # 线稿批量生成脚本
├── coloring_prompts.json           # 30张涂色任务定义
└── coloring/
    ├── lineart/                    # 生成的线稿目录
    ├── regionmap/                  # 区域索引图目录
    └── index.json                  # 涂色索引
```

---

## 🚀 快速开始

### 1. 后端集成（Python FastAPI）

#### 添加涂色 API 路由

在你的 `modules/tts_backend/api_v2.py` 或主 FastAPI 应用中：

```python
from coloring_api import router as coloring_router

# 添加到 FastAPI app
app.include_router(coloring_router)
```

#### 确保路由正确注册

```bash
# 测试端点是否可用
curl http://127.0.0.1:9880/coloring/health
```

### 2. 线稿生成（可选）

#### 准备火山引擎配置

在 `wx_api.env` 中确认配置：

```env
VOLC_ACCESSKEY=你的AK
VOLC_SECRETKEY=你的SK
IMAGINE_PROXY=http://127.0.0.1:7890
```

#### 运行生成脚本

```bash
python modules/coloring_artist/practice/generate_coloring_lineart.py

# 或指定自定义目录
python modules/coloring_artist/practice/generate_coloring_lineart.py \
  --prompts practice/coloring_prompts.json \
  --lineart-dir practice/coloring/lineart \
  --regionmap-dir practice/coloring/regionmap \
  --index practice/coloring/index.json
```

**输出**：
- `practice/coloring/lineart/` - 30张线稿 PNG
- `practice/coloring/regionmap/` - 30张区域索引图
- `practice/coloring/index.json` - 更新后的索引

### 3. 前端集成

**在 WeChat DevTools 中：**

1. 导入小程序项目（`modules/wechat_frontend/miniprogram1` 文件夹）
2. 在 `app.js` 中确认后端 API 地址：
   ```javascript
   apiBaseUrl: 'http://127.0.0.1:9880'
   ```
3. 进入 **游乐园 (play)** > **涂色小画家** 开始游戏

---

## 📐 数据格式详解

### 线稿索引 (GET /coloring/get_sketches)

**响应示例**：

```json
{
  "ok": true,
  "total": 30,
  "count": 30,
  "items": [
    {
      "id": "color_001",
      "title": "可爱的小兔子",
      "desc": "草地上可爱的小兔子...",
      "lineart_url": "/practice_static/coloring/lineart/color_001.png",
      "regionmap_url": "/practice_static/coloring/regionmap/color_001_region.png",
      "regions": [
        {
          "id": "head",
          "name": "兔子头",
          "suggest_colors": ["#FFB3D9", "#FFC0E3", "#FFD6EA"]
        },
        {
          "id": "ears",
          "name": "兔子耳朵",
          "suggest_colors": ["#FFD6EA", "#FFEBF0"]
        }
        // ... 更多区域
      ],
      "color_count": 4,
      "age_range": "3-6"
    }
    // ... 更多线稿
  ]
}
```

### 区域标注格式

每个 region 包含：
- `id` - 区域唯一标识符
- `name` - 用户友好的区域名称（中文）
- `suggest_colors` - 推荐填色列表（RGB hex色值）

### AI 评价调用

**端点**：POST `/readalong/evaluate`

**参数**：

```
formData:
  - file: PNG文件（填色完成的作品）
  - expected_text: "评估涂色作品：1)颜色搭配 2)完整性 3)创意...用儿童能理解的口吻"
  - book_id: "coloring_task"
  - sentence_index: "0"
  - audio_format: "png"
  - eval_mode: "coloring_evaluation"
```

**响应**：

```json
{
  "ok": true,
  "stars": 4,
  "feedback": "太棒了！你的颜色搭配很漂亮...",
  "transcript": ""
}
```

### 作品保存 (POST /coloring/save_work)

**参数**：

```
formData:
  - sketch_id: "color_001"
  - title: "可爱的小兔子"
  - user_id: "user_123"
  - evaluation: "{\"stars\": 4, \"feedback\": \"...\"}"
```

**响应**：

```json
{
  "ok": true,
  "work_id": "work_20260318_123456_color_001",
  "saved_path": "/path/to/work.json"
}
```

---

## 🎨 前端 Canvas 逻辑

### 四层 Canvas 架构

```
┌─────────────────────────────┐
│  highlightCanvas (z:3)      │  ← 点击高亮效果
├─────────────────────────────┤
│  paintCanvas (z:2)          │  ← 用户填充结果
├─────────────────────────────┤
│  线稿image                  │  ← 背景线稿
├─────────────────────────────┤
│  regionCanvas (隐藏)        │  ← 像素→区域映射
└─────────────────────────────┘
```

### 工作流程

```
1. 加载线稿 + regionMap
   ├─ 线稿: 黑白线条
   └─ regionMap: 彩色区域标记

2. 缓存 regionMap 像素数据
   └─ 建立 (x,y) → regionId 映射

3. 用户点击
   ├─ 获取点击坐标 (x, y)
   ├─ 查询 regionMap 像素颜色
   ├─ 识别所属区域
   ├─ 高亮区域
   ├─ 显示推荐色
   └─ 填充颜色

4. 撤销处理
   └─ 管理 fillHistory 栈

5. 完成涂色
   ├─ 导出 PNG (paintCanvas + 线稿)
   ├─ 上传评价 AI
   ├─ 显示评分弹窗
   └─ 保存作品 (后端/本地)
```

---

## 🔌 API 接口清单

### 线稿管理

| 方法 | 端点 | 说明 |
|-----|------|------|
| GET | `/coloring/get_sketches` | 获取线稿列表 |
| GET | `/coloring/get_sketch/{id}` | 获取单个线稿详情 |
| GET | `/coloring/health` | 健康检查 |

### 作品管理

| 方法 | 端点 | 说明 |
|-----|------|------|
| POST | `/coloring/save_work` | 保存涂色作品 |
| GET | `/coloring/get_user_works/{user_id}` | 获取用户作品列表 |
| DELETE | `/coloring/delete_work/{work_id}` | 删除作品 |

### 管理员操作

| 方法 | 端点 | 说明 |
|-----|------|------|
| POST | `/coloring/batch_regenerate_sketches` | 批量生成线稿 |
| POST | `/coloring/regenerate_index` | 重新扫描生成索引 |

---

## 🛠️ 常见问题

### Q1: 线稿还没生成怎么办？

**A**: 使用 `practice/coloring/index.json` 中的示例数据进行开发。线稿生成脚本完成后，运行：

```bash
python modules/coloring_artist/practice/generate_coloring_lineart.py
```

然后调用 `/coloring/regenerate_index` 更新索引。

### Q2: 如何自定义线稿？

**A**: 编辑 `practice/coloring_prompts.json`，修改：
- `title` - 线稿名称
- `lineart_prompt` - 生图提示词
- `regions` - 涂色区域定义
- `suggest_colors` - 推荐色系

### Q3: 如何修改 AI 评价提示词？

**A**: 在前端 `color.js` 的 `_evaluate()` 方法中修改 `expected_text` 字段：

```javascript
expected_text: `评估涂色作品：
  1) 颜色搭配是否协调
  2) 是否有超出线条
  3) 涂色是否完整
  用小孩能理解的温暖语气给出建议。`
```

### Q4: 如何调试 Canvas 绘图？

**A**: 在微信开发者工具中启用调试，查看 Console：

```javascript
// 在 color.js 中添加调试代码
console.log('regionMapData:', this.data.regionMapImageData);
console.log('identifiedRegion:', region);
```

### Q5: 为什么填充没有显示？

**A**: 检查以下几点：
1. regionMap 是否正确加载（查看 Console）
2. Canvas 层是否正确初始化
3. 填充颜色与当前选中颜色是否匹配
4. 区域识别是否成功（logs）

---

## 📚 扩展功能

### 加入自由创作模式

在 `color.js` 中添加：

```javascript
// 切换到自由创作模式
switchToFreeCreation() {
  // 调用火山引擎生图接口
  // 基于用户输入生成线稿
  // 自动生成区域索引图
  // 进入涂色流程
}
```

### 连接 AR 形象生成

保存的 PNG 作品可作为 AR 模块的输入：

```
coloring_work.png
    ↓
[ar-color 模块]
    ↓
3D AR 形象
```

---

## 📝 维护清单

- [ ] 定期检查线稿索引是否完整
- [ ] 监控 AI 评价模型的准确性
- [ ] 收集用户反馈，优化推荐色系
- [ ] 备份用户作品数据
- [ ] 更新火山引擎凭证（定期重置）

---

## 🎯 下一阶段计划

1. **Analytics** - 跟踪用户填色进度和偏好
2. **Leaderboard** - 创意涂色作品排行榜
3. **Sharing** - 分享涂色作品到社交媒体
4. **Customization** - 让家长创建自定义线稿
5. **Voice Narration** - 添加语音指导（通过已有TTS）

---

## 📞 支持

- API 文档：查看 `modules/coloring_artist/backend/coloring_api.py` 的 docstrings
- 线稿生成：参考 `modules/coloring_artist/practice/generate_coloring_lineart.py`
- 前端开发：查看 `modules/wechat_frontend/miniprogram1/pages/color/` 的注释

---

**最后更新**: 2026年3月18日  
**版本**: v1.0  
**贡献者**: AI Assistant
