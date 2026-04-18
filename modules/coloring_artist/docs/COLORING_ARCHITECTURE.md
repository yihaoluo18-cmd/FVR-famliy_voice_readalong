# 涂色小画家 - 技术架构设计

## 🏗️ 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                    WeChat Mini Program                       │
│                   (modules/wechat_frontend/miniprogram1/pages/color)                 │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │ List Mode    │  │ Coloring Mode │  │ Evaluation Modal │  │
│  │ (30 items)   │  │ (Canvas UI)   │  │ (Stars + Text)   │  │
│  └──────────────┘  └───────────────┘  └──────────────────┘  │
│         │                 │                     │             │
│         └─────────────────┼─────────────────────┘             │
│                           │                                   │
│         ┌─────────────────▼──────────────────┐               │
│         │  color.js (450+ lines)             │               │
│         │  ├─ _loadSketchList()              │               │
│         │  ├─ _initCanvases()                │               │
│         │  ├─ _identifyRegion(x,y)           │               │
│         │  ├─ _fillRegion()                  │               │
│         │  ├─ _exportToPNG()                 │               │
│         │  ├─ _evaluate()                    │               │
│         │  └─ _saveWork()                    │               │
│         └─────────────────┬──────────────────┘               │
│                           │                                   │
└───────────────────────────┼─────────────────────────────────┘
                            │
                            │ HTTP/HTTPS
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    FastAPI Backend                           │
│            (modules/tts_backend/api_v2.py + coloring_api.py)                     │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │ /coloring/*      │  │ /readalong/*     │                 │
│  │ (新增 8 端点)    │  │ (已有 evaluate)  │                 │
│  └──────────────────┘  └──────────────────┘                 │
│         │                     │                              │
│         ├─ GET /get_sketches   ├─ POST /evaluate             │
│         ├─ POST /save_work     │  (AI 评价)                  │
│         ├─ GET /user_works     │                             │
│         ├─ DELETE /work        │                             │
│         └─ etc...              │                             │
│                                                               │
└────────────────────────┬──────────────────────────────────┬─┘
                         │                                  │
                         │                                  │
         ┌───────────────┴──────────────┐                  │
         │                              │                  │
         ▼                              ▼                  ▼
    ┌──────────┐              ┌────────────────┐  ┌─────────────┐
    │ File     │              │ Volcano Engine │  │ /readalong  │
    │ Storage  │              │ (Image Gen)    │  │ (AI Model)  │
    │ JSON     │              │                │  │             │
    │ Users    │              └────────────────┘  └─────────────┘
    │ Works    │
    └──────────┘
```

---

## 🎯 核心设计思想

### 1. 区域识别方案

**问题**: 如何让儿童点击线稿中的任意位置，自动识别是哪个区域？

**解决方案**: 双图策略

```
                  线稿图 (黑白)                区域索引图 (彩色)
                ┌─────────────┐            ┌─────────────────┐
                │  ███    ███ │            │  🔴   🟢  🔴   │
                │  █ █   █ █  │            │  🟡   🟡  🟡   │
                │  ███   ███  │            │  🟠   🔵  🟠   │
                │  ♦ ♦    ○○  │            │  🟢   🟡  🟢   │
                └─────────────┘            └─────────────────┘
                   给用户看                   后端查询用

用户点击 (100, 150)
        ↓
前端询问 regionMap 该位置像素颜色
        ↓
获得颜色值 (RGB)
        ↓
映射到区域 ID
        ↓
查表获得区域名称和推荐色
        ↓
高亮 + 显示推荐
```

**优点**:
- ✅ 无需手工标注区域边界
- ✅ O(1) 查询时间
- ✅ 支持任意形状区域
- ✅ 火山引擎可自动生成

**缺点**:
- 需要额外生成一张索引图
- 对区域颜色相似度敏感（已改进为含容差范围）

---

### 2. Canvas 多层架构

**为什么需要多层？**

```
需求 1: 显示线稿给用户看
需求 2: 存储用户填充颜色
需求 3: 交互时高亮选中区域
需求 4: 导出最终 PNG (线稿 + 填充)

↓ 单 Canvas 不足！
```

**解决方案: 4 层 Canvas**

```
  用户交互        导出 PNG        后端存储
      ↓               ↓               ↓
  
   Layer 3         (合成)
  highlightCanvas               mergeCanvas
  (高亮效果)     ┌────────┐      (最终输出)
                 │        │
   Layer 2       │ 用户   │
  paintCanvas    │ 看到   │      PNG 文件
  (用户填充)     │ 的画面 │
                 │        │
  线稿 Image     └────────┘
  background
                           exportAsImage()
   Layer 1 (隐藏)
  regionCanvas              
  (像素查询用)  collapseCanvas(
```

**工作流程**:

```
1. 初始化时:
   ┌──────────────────────┐
   │ 创建 4 个 Canvas     │
   │ 加载线稿到 Image     │
   │ 加载 regionMap 数据  │
   └──────────────────────┘

2. 用户交互:
   ┌─────────────────────────────────┐
   │ 点击 (x,y)                      │
   │ → regionCanvas 查询像素         │
   │ → 识别区域                      │
   │ → highlightCanvas 绘制高亮      │
   │ → 显示推荐色                    │
   └─────────────────────────────────┘

3. 用户填充:
   ┌─────────────────────────────────┐
   │ 选择颜色                        │
   │ → paintCanvas 填充选中区域      │
   │ → 记录到 fillHistory            │
   │ → 显示更新后的画面              │
   └─────────────────────────────────┘

4. 完成并导出:
   ┌─────────────────────────────────┐
   │ finishColoring()                │
   │ → mergeCanvas 合成所有图层      │
   │ → 应用线稿叠加 (multiply blend) │
   │ → 导出 PNG                      │
   │ → 上传到 AI 评价                │
   └─────────────────────────────────┘
```

**技术细节**:

```javascript
// Canvas 初始化
const regionCanvas = wx.createCanvasContext('region-canvas', this);
const paintCanvas = wx.createCanvasContext('paint-canvas', this);
const highlightCanvas = wx.createCanvasContext('highlight-canvas', this);
const mergeCanvas = wx.createCanvasContext('merge-canvas', this);

// 查询区域
const imageData = regionCanvas.getImageData(x, y, 1, 1);
const [r, g, b] = [
  imageData.data[0],
  imageData.data[1],
  imageData.data[2]
];

// 填充
paintCanvas.fillStyle = selectedColor;
paintCanvas.fillRect(x, y, width, height);
paintCanvas.draw();

// 导出
wx.canvasToTempFilePath({
  canvas: mergeCanvas,
  success: (file) => {
    // 上传评价
  }
});
```

---

### 3. 推荐色系设计

**为什么需要推荐色?**

- 儿童色感未发展完全，容易选择不搭配的颜色
- 推荐色帮助引导美感发展
- AI 评价时会考虑颜色搭配合理性

**推荐色的结构**:

```json
{
  "region_id": "head",
  "name": "兔子头",
  "suggest_colors": [
    "#FFB3D9",  // 浅粉红
    "#FFC0E3",  // 粉红
    "#FFD6EA"   // 浅紫粉
  ]
}
```

**为什么选这些颜色?**

```
考虑因素:
1. 儿童视觉舒适度
   → 避免过饱和、高对比
   → 使用温暖色系为主

2. 逻辑自然度
   → 兔子头应该用粉/白/棕
   → 不应该推荐绿色

3. 搭配协调性
   → 同区域内的粉色系相似
   → 不同区域的颜色有变化但和谐

4. 易于填充
   → 明度适中 (能看清填充边界)
   → 不过浅 (容易看不清)
   → 不过深 (显得压抑)
```

**实现细节**:

```javascript
// 获取推荐色
getRecommendedColors() {
  const suggestColors = this.data.currentSketch.regions.find(
    r => r.id === this.data.selectedRegion
  )?.suggest_colors || [];
  
  // 显示在调色板上
  return suggestColors;
}
```

---

### 4. AI 评价集成

**为什么复用 `/readalong/evaluate`?**

```
优点:
✅ 已有成熟的模型和评价逻辑
✅ 无需重新训练模型
✅ 减少维护成本
✅ 用户体验一致

方案: 修改提示词
   原始提示词    →   修改为涂色评价提示词
   └─ 复用模型评价   └─ 评价涂色作品
```

**涂色评价提示词**:

```
"这是一个儿童涂色作品的截图。
请从以下几个方面给出评价（用小孩子能理解的温暖语气）：

1. 颜色搭配: 选择的颜色是否协调漂亮？
2. 完整性: 是否有空白区域没有涂满？
3. 精细度: 是否有颜色超出线条边界？
4. 创意性: 是否展示了独特的色彩想象力？

请给出1-5颗星的评分，以及温暖鼓励的反馈。"
```

**调用流程**:

```javascript
// 前端:
_evaluate() {
  // 1. 导出涂色作品为 PNG
  const pngFile = this.exportPNG();
  
  // 2. 准备评价参数
  const evaluationPrompt = `这是儿童涂色作品...`;
  
  // 3. 上传到 /readalong/evaluate
  await postEvaluation({
    file: pngFile,
    expected_text: evaluationPrompt,
    eval_mode: 'coloring_evaluation'
  });
  
  // 4. 接收评价结果
  const { stars, feedback } = response;
  
  // 5. 显示弹窗
  this.showScoreModal(stars, feedback);
}

// 后端（无需修改）:
@router.post('/readalong/evaluate')
async def evaluate_readalong(file: UploadFile, expected_text: str):
    # 现有逻辑直接处理
    # 返回 stars 和 feedback
    return {
        "stars": 4,
        "feedback": "..."
    }
```

---

### 5. 保存流程设计

**二元保存策略**:

```
用户完成涂色
        ↓
     ┌──┴──┐
     │     │
   云端   本地
     │     │
     ↓     ↓
  POST    localStorage
    │     │
    ↓     ↓
 后端存   浏览器
    │     │
    ↓     ↓
  JSON   JSON
```

**为什么要提供两种选项?**

| 方案 | 优点 | 缺点 |
|-----|------|------|
| 云端 | ✅ 不丢失<br>✅ 多设备同步<br>✅ 支持分享 | ❌ 需要账户<br>❌ 网络依赖 |
| 本地 | ✅ 离线可用<br>✅ 隐私<br>✅ 快速 | ❌ 仅单设备<br>❌ 容量限制 |

**实现细节**:

```javascript
// 保存到后端
async saveToCloud(workData) {
  const formData = new FormData();
  formData.append('sketch_id', workData.sketchId);
  formData.append('title', workData.title);
  formData.append('user_id', this.getUserId());
  formData.append('evaluation', JSON.stringify(workData.evaluation));
  
  const response = await fetch('/coloring/save_work', {
    method: 'POST',
    body: formData
  });
  
  return response.json();
}

// 保存到本地
saveToLocal(workData) {
  const workId = 'work_' + Date.now();
  const storageKey = 'coloring_work_' + workId;
  
  wx.setStorageSync(storageKey, workData);
  
  return { work_id: workId };
}
```

---

## 🔄 数据流转图

### 用户从入场到完成的数据流

```
1. 用户启动游戏
   ┌─────────────────────────────┐
   │ GET /coloring/get_sketches  │
   │ Response: 30 个线稿列表     │
   └─────────────────────────────┘
              ↓
         展示网格

2. 用户选择线稿
   ┌──────────────────────────────────┐
   │ GET /coloring/get_sketch/{id}    │
   │ Response: 线稿 + 区域定义        │
   └──────────────────────────────────┘
              ↓
         加载涂色界面

3. 用户涂色过程
   前端 Canvas 本地处理 (无网络)
   ├─ regionMap 查询 (client-side)
   ├─ 区域高亮 (client-side)
   └─ 颜色填充 (client-side)

4. 用户完成涂色
   ┌──────────────────────────────────┐
   │ POST /readalong/evaluate         │
   │ 请求: PNG 文件 + 提示词          │
   │ 响应: 星级 + 反馈               │
   └──────────────────────────────────┘
              ↓
         显示评价弹窗

5. 用户保存作品
   ┌──────────────────────────────────┐
   │ POST /coloring/save_work          │
   │ 请求: 元数据 + 评价信息          │
   │ 响应: work_id + 保存路径         │
   └──────────────────────────────────┘
              ↓
         关闭弹窗

6. 用户重新开始或退出
   选项:
   ├─ 查看用户作品: GET /coloring/get_user_works/{id}
   ├─ 删除作品: DELETE /coloring/delete_work/{id}
   └─ 回到列表: GET /coloring/get_sketches
```

---

## 🎨 样式设计系统

### 色彩方案

```
主题色: 紫粉系 (#ec4899)
├─ 主色: #ec4899 (Pink-500)
├─ 浅色: #eba8d1 (Pink-300)
├─ 暗色: #be123c (Pink-900)
└─ 背景: 线性渐变 #fef2f2 → #fff

强调色:
├─ 成功绿: #10b981 (Emerald-500)
├─ 警告黄: #f59e0b (Amber-500)
└─ 错误红: #ef4444 (Red-500)

中性色:
├─ 文字: #2d3436 (Gray-800)
├─ 边框: #e5e7eb (Gray-200)
└─ 背景: #f9fafb (Gray-50)
```

### 动画设计

```
列表视图:
├─ slideDown: 卡片从上向下滑入 (300ms)
├─ scaleIn: 卡片放大进入 (200ms)
└─ hover: lightbox 效果 (150ms)

涂色界面:
├─ highlightRegion: 区域闪烁高亮 (400ms)
├─ fillRegion: 填充色淡出显示 (300ms)
├─ undo: 撤销时褪色 (200ms)
└─ confetti: 完成时彩纸飘飘 (800ms)

模态框:
├─ slideUpModal: 弹窗从下向上 (400ms)
├─ scoreModal: 分数依次显示 (1000ms total)
└─ starPress: 星星按序开陈 (100ms each)
```

---

## 🔐 安全考虑

### 数据安全

```
用户涂色作品 (JSON)
├─ 小敏感: 用户 ID (加密存储)
├─ 非敏感: 涂色数据 (公开可以)
└─ 公开: 作品评分 (可分享)
```

### API 安全

```
POST /coloring/save_work
├─ 验证: 用户认证
├─ 限制: 每分钟最多 10 个请求
├─ 校验: sketch_id 有效性检查
└─ 日志: 记录保存事件
```

### Canvas 安全

```
用户不能:
✅ 修改 regionMap (只读)
✅ 访问其他用户作品 (auth 检查)
✅ 上传文件到任意位置 (固定目录)

系统可以:
✓ 验证 PNG 合法性
✓ 限制文件大小 (最大 5MB)
✓ 自动清理旧文件 (30 天)
```

---

## 📊 性能优化

### 前端优化

```
1. 图像缓存
   ├─ regionMapImageData: 缓存像素数据 (避免重复 getImageData)
   ├─ lineArtImageData: 缓存线稿数据
   └─ regionNameMap: 缓存区域名称映射

2. Canvas 优化
   ├─ 分层绘制: 只更新改变的层
   ├─ 批量操作: 多个填充一次 draw()
   └─ 异步处理: 使用 Promise 避免卡顿

3. 内存管理
   ├─ Canvas 销毁: 离开时释放引用
   ├─ 图像压缩: 大图自动缩放
   └─ 对象池: 复用相同大小的对象
```

### 后端优化

```
1. 数据库查询
   ├─ 索引: sketch_id 和 user_id 加索引
   ├─ 分页: limit/offset 避免大量数据
   └─ 缓存: Redis 缓存热门线稿

2. 文件操作
   ├─ 异步 I/O: aiofiles 提高吞吐
   ├─ 流式读取: 大文件用流而非全量加载
   └─ CDN: 线稿和索引图通过 CDN 分发

3. API 扩展
   └─ Rate limit: 防止滥用
```

---

## 🎓 扩展点

### 后续可以添加的功能

```
1. 社交功能
   ├─ 作品分享
   ├─ 评论系统
   └─ 点赞排行

2. 创意工具
   ├─ 自定义线稿上传
   ├─ 色盘编辑
   └─ 预设主题

3. 学习功能
   ├─ 色彩理论教学
   ├─ 进度追踪
   └─ 成就系统

4. AR 集成
   └─ 3D 模型渲染涂色结果
```

---

## 📚 参考资料

### 相关技术文档

- [WeChat Canvas API](https://developers.weixin.qq.com/miniprogram/en/dev/api/canvas/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [火山引擎图像生成](https://www.volcengine.com/)

### 设计参考

- Material Design (谷歌)
- Ant Design (阿里巴巴)
- 微信小程序设计指南

---

**文档版本**: v1.0  
**最后更新**: 2026年3月18日  
**技术栈**: WeChat Mini Program + FastAPI + Volcano Engine
