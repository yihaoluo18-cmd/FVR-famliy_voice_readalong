# FVR 部署指南（从 GitHub 到一键启动）

本文档用于从零部署项目，覆盖：

- 从 GitHub 网页下载或命令行克隆代码
- 从 GitHub Release 下载大资源（`GPT_SoVITS` + `assets`）
- 配置环境变量（含 AI Key）
- 执行一键脚本完成资源安装
- 启动服务并验证可用

---

## 1. 准备信息

### 1.1 代码仓库

- 仓库地址：`https://github.com/yihaoluo18-cmd/FVR-famliy_voice_readalong`

### 1.2 Release 资源（需要先在 Release 页面上传）

需要在同一仓库 Release 中包含以下附件（Tag 示例：`v1.0.0`）：

- `GPT_SoVITS_part01.zip`
- `GPT_SoVITS_part02.zip`
- `GPT_SoVITS_part03.zip`
- `GPT_SoVITS_part04.zip`
- `assets_release.zip`

---

## 2. 获取代码（两种方式）

### 方式 A：网页下载 ZIP

1. 打开仓库主页。
2. 点击 `Code` -> `Download ZIP`。
3. 解压到本地目录，例如：
   - Windows：`D:\部署测试\FVR_github`
   - Linux：`/opt/FVR_github`

### 方式 B：命令行克隆（推荐）

```bash
git clone https://github.com/yihaoluo18-cmd/FVR-famliy_voice_readalong.git
cd FVR-famliy_voice_readalong
```

---

## 3. 配置 Python 运行环境

### 3.1 Windows（推荐用 CMD/PowerShell 执行）

在项目根目录执行：

```powershell
.\setup_env.cmd
```

若需重建环境：

```powershell
.\setup_env.cmd --recreate
```

### 3.2 Linux/macOS

```bash
chmod +x ./setup_env.sh
./setup_env.sh
```

若需重建环境：

```bash
./setup_env.sh --recreate
```

---

## 4. 配置环境变量（含 AI Key）

项目启动脚本会优先读取：`env/wx_api.env`。  
请从模板复制并填写真实值：

```bash
cp env/wx_api.env.example env/wx_api.env
```

至少需要填写以下关键项：

- `AI_API_KEY`：你的真实 API Key（必填）
- `AI_BASE_URL`：兼容 OpenAI 的网关地址（如 DashScope）
- `AI_MODEL_TEXT_DEFAULT`：默认文本模型
- `AI_MODEL_STORY`、`AI_MODEL_READALONG_EVAL`、`AI_MODEL_VISION`：按业务配置

示例（请按你的账号实际替换）：

```env
AI_API_KEY=sk-xxxxxxxxxxxxxxxx
AI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
AI_MODEL_TEXT_DEFAULT="qwen-plus"
AI_MODEL_STORY="qwen-plus"
AI_MODEL_READALONG_EVAL="qwen-turbo"
AI_MODEL_VISION="qwen-vl-plus"
```

> 注意：`env/wx_api.env` 不要上传到 GitHub。

---

## 5. 一键安装 Release 大资源

你可以使用项目内置脚本自动下载并解压 Release 资源。

### 5.1 Windows（PowerShell）

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_from_release.ps1 -Repo "yihaoluo18-cmd/FVR-famliy_voice_readalong" -Tag "v1.0.0" -TargetRoot "." -AssetsAssetName "assets_release.zip"
```

默认会自动下载：

- `GPT_SoVITS_part01.zip` ~ `GPT_SoVITS_part04.zip`
- `assets_release.zip`

并解压到项目根目录：

- `./GPT_SoVITS`
- `./assets`

### 5.2 Linux/macOS

```bash
chmod +x ./scripts/bootstrap_from_release.sh
./scripts/bootstrap_from_release.sh yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 . assets_release.zip
```

---

## 6. 启动服务

### 6.1 Windows（Git Bash）或 Linux/macOS

```bash
bash ./start_wx_api.sh
```

仅启动主服务：

```bash
bash ./start_wx_api.sh --wx-only
```

---

## 7. 验证部署结果

启动后检查接口：

```bash
curl -sS http://127.0.0.1:9880/
curl -sS http://127.0.0.1:9881/readalong/health
```

常用端口：

- 主服务：`9880`
- 跟读服务：`9881`

日志目录：

- `train/runtime/`

---

## 8. GitHub Release 上传说明（给维护者）

如果你是维护者，需要发布新版资源：

1. 进入仓库 `Releases` -> `Draft a new release`
2. 填写 Tag（建议语义化，例如 `v1.0.1`）
3. 上传以下文件：
   - `GPT_SoVITS_part01.zip`
   - `GPT_SoVITS_part02.zip`
   - `GPT_SoVITS_part03.zip`
   - `GPT_SoVITS_part04.zip`
   - `assets_release.zip`
4. Publish release
5. 通知部署方把脚本里的 `-Tag` / `<tag>` 改成新版本

---

## 9. 常见问题

### 9.1 提示找不到 Release 资源

- 检查 Tag 是否正确（如 `v1.0.0`）。
- 检查 Release 附件文件名是否和脚本一致。

### 9.2 启动时报 AI 配置错误

- 确认 `env/wx_api.env` 已存在且 `AI_API_KEY` 非空。
- 确认 `AI_BASE_URL` 与模型名可用。

### 9.3 端口被占用

- 脚本会尝试自动释放端口。
- 若仍冲突，可先手动关闭占用进程再重启。

### 9.4 Windows 无法执行 `bash`

- 安装 Git for Windows，使用 Git Bash 执行 `start_wx_api.sh`。

---

## 10. 最小上线清单

- [ ] 代码已拉取到本地
- [ ] Python 依赖已安装成功（`setup_env.cmd` / `setup_env.sh`）
- [ ] `env/wx_api.env` 已配置真实 AI Key
- [ ] Release 资源已通过脚本下载并解压
- [ ] `start_wx_api.sh` 启动成功
- [ ] `9880` 与 `9881` 健康检查通过

完成以上步骤即可完成一套可复用部署流程。
