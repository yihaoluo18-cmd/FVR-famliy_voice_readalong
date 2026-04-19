# FVR 部署指南（从 GitHub 到一键启动）

本文档用于从零部署项目，覆盖：

- 从 GitHub 网页下载或命令行克隆代码
- 从 GitHub Release 下载大资源（`GPT_SoVITS` + `assets` + 尝试 `fvr_deploy_output.zip`，见第 5 节）
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
- `assets_release.zip`（由本地 **`仓库/assets`** 打包，根目录下为 `images/`、`paint_basement_generated/` 等，解压到项目根目录应对齐为 `./assets/...`）
- `fvr_deploy_output.zip`（**推荐**：默认运行时 `output/` 快照；一键脚本会**尝试自动下载**并解压到 `./output/`。若 Release 未上传该文件则跳过。含伴宠/涂色等数据，部署前请确认是否覆盖本地 `output/`）

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
- **尝试** `fvr_deploy_output.zip`（若该 Tag 的 Release 未附带此附件，则打印警告并跳过，其余资源照常安装）

并解压到项目根目录：

- `./GPT_SoVITS`
- `./assets`
- `./output`（仅当成功下载到 `fvr_deploy_output.zip` 时；脚本会先删除已有 `output/` 再解压，**等同于覆盖**）

**不想覆盖本地 `output/`：** 增加 `-SkipDeployOutput`。

### 5.2 Linux/macOS

```bash
chmod +x ./scripts/bootstrap_from_release.sh
./scripts/bootstrap_from_release.sh yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 . assets_release.zip
```

与 5.1 相同：会尝试拉取 `fvr_deploy_output.zip`。不想覆盖本地 `output/` 时：

```bash
FVR_SKIP_OUTPUT=1 ./scripts/bootstrap_from_release.sh yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 . assets_release.zip
# 或第五个参数传 skip：
# ./scripts/bootstrap_from_release.sh yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 . assets_release.zip skip
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
# 注意：根路径 "/" 可能返回 400（业务行为），不代表服务异常
curl -sS http://127.0.0.1:9880/coloring/health
curl -sS http://127.0.0.1:9881/readalong/health
```

常用端口：

- 主服务：`9880`
- 跟读服务：`9881`

日志目录：

- `train/runtime/`

### 7.1 伴宠 3D 视角参数：小程序接入与配置落盘

与本地 `@仓库/微信小程序final` 对齐的约定如下（主仓 `FVR_github` 已统一实现）。

**小程序侧（读哪些字段、写哪个 scope）**

| 页面 | 读后端 `companion/state` 的字段 | 保存调参 `set_view_tuning` 的 `view_scope` |
|------|----------------------------------|--------------------------------------------|
| 宠详情 `pages/pet-detail/pet-detail` | `form_view_tuning` | `pet_detail`（默认） |
| 首页 `pages/home/home` | `form_view_tuning_home`，缺省再读 `form_view_tuning` | `home` |
| 伴读 `pages/companion/companion` | 合并 `form_view_tuning` → `form_view_tuning_home` → `form_view_tuning_companion`（后者优先）；逻辑集中在 `微信小程序final/utils/companion-view-tuning.js` | `companion` |

HTTP 封装在 `微信小程序final/utils/pet-growth.js`：`requestCompanionState`、`postCompanionSetViewTuning(..., viewScope)`。

**后端与磁盘（从 GitHub 拉下来后能否读到）**

- 运行时主存储：`output/ar_companion_pet_companion_store.json`（相对项目根目录）。首次启动服务后由后端创建/写入；克隆代码后只要启动过 `wx_api` 且该路径可写，即可持久化。
- 三套全局调参键名与上述 `view_scope` 对应：`global_form_view_tuning`、`global_form_view_tuning_home`、`global_form_view_tuning_companion`；形态键为 `egg`、`tier1`、`tier2`、`tier3`。
- 仓库内随代码提供的**历史模板**（可选）：`modules/ar_companion_backend/data/ar_companion_tuning_store.json`、`ar_companion_scene_tuning_store.json`。服务启动时 `pet_companion` 会将其中与伴读相关的记录迁移进 `global_form_view_tuning_companion`，避免旧环境调好的镜头丢失。
- Release 里的 `assets` / `GPT_SoVITS` 只影响**模型与贴图 URL 是否 404**，不改变上述 JSON 的读写路径；小程序 `app.getApiBaseUrl()` 必须指向已启动的 `9880` 服务。

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
   - （可选）`fvr_deploy_output.zip`：部署用默认 `output/` 数据包
4. Publish release
5. 通知部署方把脚本里的 `-Tag` / `<tag>` 改成新版本

**维护者本地打包（与本次生成方式一致）**

在开发机已准备好目录时，可用 Python 一键生成上述两个 zip（单文件不超过 GitHub Release 2GB 限制即可）：

```powershell
cd <项目根目录>
python scripts/package_release_assets.py
```

默认会读取环境变量或脚本内路径：将 **`仓库/assets`** 打成 `release_packages/assets_release.zip`，将 **`test/FVR_deploy_run/output`** 打成 `release_packages/fvr_deploy_output.zip`。生成后请在浏览器打开 GitHub 仓库 → **Releases** → 编辑对应 Tag → **Attach binaries** 上传。

若已安装 [GitHub CLI](https://cli.github.com/) 且已 `gh auth login`，可在生成 zip 后执行（将 `TAG` 换成实际标签）：

```bash
gh release upload TAG release_packages/assets_release.zip release_packages/fvr_deploy_output.zip --repo yihaoluo18-cmd/FVR-famliy_voice_readalong --clobber
```

（`GPT_SoVITS_part*.zip` 需自行上传；单文件若超过 2GB 须分卷，与现有 `bootstrap` 脚本约定一致。）

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
- 若 PowerShell 提示 `bash` 找不到，但 Git 已安装，可显式调用：

```powershell
& "C:\Program Files\Git\bin\bash.exe" -lc "cd /d/部署测试/test/FVR_deploy_run && ./start_wx_api.sh"
```

### 9.5 Release 下载卡住 / 中断 / 文件被占用

现象：

- `bootstrap_from_release.ps1` 长时间停在 `Downloading ...`
- 报错：`OutFile ... is being used by another process`

处理建议：

1. 先结束残留下载进程，再清理 `.release_tmp` 后重试。
2. 确认代理可用（尤其是 `127.0.0.1:7890` 是否监听）。
3. 若网络不稳定，使用本地同批 Release 包离线安装（与线上解压结果等价）。

离线安装示例（Windows）：

```powershell
# 假设已在 d:\部署测试\release_packages 下准备好分卷包
python -c "import zipfile,shutil;from pathlib import Path;root=Path(r'd:\部署测试\test\FVR_deploy_run');rel=Path(r'd:\部署测试\release_packages');g=root/'GPT_SoVITS';a=root/'assets';shutil.rmtree(g,ignore_errors=True);shutil.rmtree(a,ignore_errors=True);g.mkdir(parents=True,exist_ok=True);a.mkdir(parents=True,exist_ok=True);[zipfile.ZipFile(rel/n).extractall(g) for n in ['GPT_SoVITS_part01.zip','GPT_SoVITS_part02.zip','GPT_SoVITS_part03.zip','GPT_SoVITS_part04.zip']];zipfile.ZipFile(rel/'assets_release.zip').extractall(a);print('ok')"
```

### 9.6 代理已开但 GitHub 仍偶发连接重置

- 先检查代理端口是否监听：

```powershell
Test-NetConnection 127.0.0.1 -Port 7890
```

- 建议在执行下载脚本前显式设置代理环境变量：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
$env:ALL_PROXY="http://127.0.0.1:7890"
```

- 若仍失败，优先走上面的“离线安装”兜底方案，再启动服务。

### 9.7 小程序静态图 `404`（`/static/miniprogram_assets/images/...`）

现象（日志）：

- `GET /static/miniprogram_assets/images/... 404 Not Found`

原因：

- 部署目录缺少 `static/miniprogram_assets` 映射所需文件，或资源未按后端约定路径放置。

处理：

1. 确认 `assets` 已正确解压（包含小程序图片资源）。
2. 检查后端静态路由对应目录是否存在这些图片文件。
3. 若使用自定义资源目录，需同步修改前端 `asset-url` 配置与后端静态映射路径。
4. 修复后重启 `start_wx_api.sh` 并重新请求对应图片 URL。

---

## 10. 最小上线清单

- [ ] 代码已拉取到本地
- [ ] Python 依赖已安装成功（`setup_env.cmd` / `setup_env.sh`）
- [ ] `env/wx_api.env` 已配置真实 AI Key
- [ ] Release 资源已通过脚本下载并解压
- [ ] `start_wx_api.sh` 启动成功
- [ ] `9880` 与 `9881` 健康检查通过

完成以上步骤即可完成一套可复用部署流程。
