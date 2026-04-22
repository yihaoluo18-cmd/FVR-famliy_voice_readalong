# 环境配置目录说明

本目录统一存放项目环境与部署相关文件，避免散落在仓库根目录。

## 文件用途

- `wx_api.env`：实际运行时环境变量（包含 AI Key/微信密钥等敏感配置，**不要提交 git**）
- `wx_api.env.example`：环境变量模板（不含真实密钥）
- `requirements.txt`：Python 依赖冻结（由可运行环境 `pip freeze` 生成，用于复现）
- `setup_env.cmd`：Windows 环境初始化脚本（创建 `venv` + 安装依赖）
- `setup_env.sh`：Linux/macOS/WSL2 环境初始化脚本
- `setuptools-81.0.0-py3-none-any.whl`：离线安装辅助包（可选）
- `DEPLOY.md`：部署文档

## 一键初始化（在 test1/ 根目录执行）

```bash
chmod +x env/setup_env.sh
env/setup_env.sh
```

Windows 直接运行 `env\\setup_env.cmd` 即可。

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

`start_wx_api.sh` 会依次尝试加载：

1. `wx_api.env`
2. `env/wx_api.env`
3. `wx_api.env.example`
4. `env/wx_api.env.example`

建议只维护 `env/wx_api.env`（不提交）与 `env/wx_api.env.example`（提交）。
