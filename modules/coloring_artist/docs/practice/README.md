## 涂色训练素材放置说明

本目录用于“涂色小画家”的训练填涂任务素材（后端静态托管路径前缀为 `/practice_static/`）。

### 目录约定

- `lineart/`：黑白线稿 PNG（建议透明背景或白底都可）
- `regionmap/`：区域索引图 PNG（每个可填区域用唯一纯色编码；用于前端点选区域定位）

### 文件命名

建议与 `practice/color_tasks.json` 的 `id` 一一对应：

- `lineart/<id>.png`
- `regionmap/<id>.png`

例如：

- `lineart/demo001.png`
- `regionmap/demo001.png`

