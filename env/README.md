# 环境配置目录说明

本目录统一存放项目环境与部署相关文件，避免散落在仓库根目录。

## 文件用途

- `wx_api.env`：实际运行时环境变量（包含 AI Key 等敏感配置）
- `wx_api.env.example`：环境变量模板（不含真实密钥）
- `requirements.txt`：Python 依赖列表（无 `requirements-lock.txt` 时使用）
- `setup_env.cmd`：Windows 环境初始化脚本（创建 `venv` + 安装依赖）
- `setup_env.sh`：Linux / Git Bash 环境初始化脚本
- `setuptools-81.0.0-py3-none-any.whl`：离线安装辅助包（可选）
- `DEPLOY.md`：部署文档

## 一键初始化（从仓库根目录）

根目录保留了启动入口脚本：

- Windows：`setup_env.cmd`
- Linux / Git Bash：`./setup_env.sh`

它们会转发到本目录对应脚本执行。

## `wx_api.env` 配置说明（重点）

1. 先复制模板：

   - Windows: `copy env\\wx_api.env.example env\\wx_api.env`
   - Bash: `cp env/wx_api.env.example env/wx_api.env`

2. 打开 `env/wx_api.env`，至少填写以下关键项：

   - `AI_API_KEY`：主模型 API Key
   - `AI_BASE_URL`：模型服务地址（如网关地址）
   - `AI_MODEL_CHAT`：聊天模型名
   - `AI_MODEL_ASR`：语音识别模型名（如项目启用）
   - `AI_MODEL_TTS`：语音合成模型名（如项目启用）

3. 不要提交真实密钥到 git。

## 运行时加载规则

`start_wx_api.sh` 会按以下顺序加载：

1. `env/wx_api.env`
2. `env/wx_api.env.example`（仅当前者不存在时）

因此生产环境务必提供 `env/wx_api.env`。
