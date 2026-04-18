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
