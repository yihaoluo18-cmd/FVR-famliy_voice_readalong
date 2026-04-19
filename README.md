# FVR 项目（GitHub 上传精简版）

本仓库用于保存业务代码与脚本，已剔除大模型、运行时环境和静态大资源，便于上传到 GitHub 进行版本管理。

## 目录说明

- `modules/`：后端核心业务模块（训练、推理、接口等）
- `微信小程序final/`：小程序前端代码
- `env/`：环境安装脚本与示例配置
- `tools/`：项目工具脚本

## 已排除内容（不在当前上传包中）

- `GPT_SoVITS/`（大模型与训练框架目录）
- `venv/`（本地虚拟环境）
- `assets/`（静态大资源）
- 根目录大权重文件（`.pth`）
- 本地敏感配置（例如 `*.env`、`env/wx_api.env`）

## 安全注意（必须）

1. **不要提交任何真实密钥**（API Key、Token、Secret）。
2. 项目运行请使用 `env/wx_api.env.example` 复制生成本地 `env/wx_api.env`：
   - `cp env/wx_api.env.example env/wx_api.env`
3. `env/wx_api.env` 仅本地使用，已通过 `.gitignore` 忽略。

## 本地运行（简版）

1. 安装依赖：使用 `setup_env.cmd` 或 `setup_env.sh`
2. 填写本地环境变量：`env/wx_api.env`
3. 启动服务：`start_wx_api.sh`

## 上传建议

- 推荐将本目录解压后直接 `git init` / `git add .` / `git commit` / `git push`
- 首次上传后，后续仅提交代码变更，不要把模型、资源和本地环境再传上去。

## GitHub Release 大资源清单

**随 Release 可一并上传（维护者）：**

- `GPT_SoVITS_part01.zip`
- `GPT_SoVITS_part02.zip`
- `GPT_SoVITS_part03.zip`
- `GPT_SoVITS_part04.zip`
- `assets_release.zip`
- `fvr_deploy_output.zip`（**推荐上传**：`./output/` 默认数据快照；**一键脚本会尝试下载**；若该 Tag 的 Release 未附带此文件则跳过并提示，不影响 GPT/assets 安装）

**一键脚本默认会下载：** 四个 `GPT_SoVITS_part*.zip` + `assets_release.zip`，并**尝试**下载 `fvr_deploy_output.zip` 解压到 `./output`（会替换已有 `output/` 目录）。若你不想覆盖本地 `output/`，请使用下方「跳过 output」参数。

### 跳过 `./output`（保留本地数据）

- Windows：在命令末尾加 `-SkipDeployOutput`
- Linux/macOS：`FVR_SKIP_OUTPUT=1 ./scripts/bootstrap_from_release.sh ...` 或第 5 个参数传 `skip`（见脚本 `--help` 式说明）

### Release 页面可复制英文备注（给维护者）

```
FVR deployment assets for one-click bootstrap.

Included assets:
- GPT_SoVITS_part01.zip
- GPT_SoVITS_part02.zip
- GPT_SoVITS_part03.zip
- GPT_SoVITS_part04.zip
- assets_release.zip
- fvr_deploy_output.zip (recommended: ./output snapshot; bootstrap downloads it when attached to the release; use -SkipDeployOutput / FVR_SKIP_OUTPUT=1 to skip.)

Usage:
- Run scripts/bootstrap_from_release.ps1 (Windows)
- or scripts/bootstrap_from_release.sh (Linux/macOS)

Bootstrap downloads GPT-SoVITS parts, assets_release.zip, and attempts fvr_deploy_output.zip (skipped automatically if not published on this release).
```

## 一键拉取 Release 并部署

仓库已提供脚本：

- Windows: `scripts/bootstrap_from_release.ps1`
- Linux/macOS: `scripts/bootstrap_from_release.sh`

### Windows 一键执行

在项目根目录 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_from_release.ps1 -Repo "yihaoluo18-cmd/FVR-famliy_voice_readalong" -Tag "v1.0.0" -TargetRoot "." -AssetsAssetName "assets_release.zip"
# 不覆盖本地 output/：再加 -SkipDeployOutput
```

随后启动：

```bash
bash ./start_wx_api.sh
```

### Linux/macOS 一键执行

```bash
chmod +x ./scripts/bootstrap_from_release.sh
./scripts/bootstrap_from_release.sh yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 . assets_release.zip
# 不覆盖本地 output/：FVR_SKIP_OUTPUT=1 ./scripts/bootstrap_from_release.sh yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 . assets_release.zip
bash ./start_wx_api.sh
```
