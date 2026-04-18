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

## GitHub Release 上传大资源

把以下两个大目录单独压缩后上传到 Release 附件：

- `GPT_SoVITS_part01.zip`
- `GPT_SoVITS_part02.zip`
- `GPT_SoVITS_part03.zip`
- `GPT_SoVITS_part04.zip`
- `assets_release.zip`

### 1) 本地打包（已生成）

- `d:\部署测试\release_packages\GPT_SoVITS_part01.zip`
- `d:\部署测试\release_packages\GPT_SoVITS_part02.zip`
- `d:\部署测试\release_packages\GPT_SoVITS_part03.zip`
- `d:\部署测试\release_packages\GPT_SoVITS_part04.zip`
- `d:\部署测试\release_packages\assets_release.zip`

### 2) 上传到 GitHub Release

1. 打开仓库页面 -> `Releases` -> `Draft a new release`
2. 填写 Tag（例如 `v1.0.0`）
3. 在 Attach binaries 区域上传上面两个 zip
4. Publish release

## 一键拉取 Release 并部署

仓库已提供脚本：

- Windows: `scripts/bootstrap_from_release.ps1`
- Linux/macOS: `scripts/bootstrap_from_release.sh`

### Windows 一键执行

在项目根目录 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_from_release.ps1 -Repo "yihaoluo18-cmd/FVR-famliy_voice_readalong" -Tag "v1.0.0" -TargetRoot "." -AssetsAssetName "assets_release.zip"
```

随后启动：

```bash
bash ./start_wx_api.sh
```

### Linux/macOS 一键执行

```bash
chmod +x ./scripts/bootstrap_from_release.sh
./scripts/bootstrap_from_release.sh yihaoluo18-cmd/FVR-famliy_voice_readalong v1.0.0 . assets_release.zip
bash ./start_wx_api.sh
```
