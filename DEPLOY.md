# test1 独立部署（可上传 GitHub）

目标：让 `test1/` 在新机器上做到 **拉代码 → 一键建环境 → 一键启动**，并且**不依赖仓库外的任何路径**。

---

## 0. 前置条件

- **Python**：建议 `3.10.x` 或 `3.11.x`
- **ffmpeg**：必须（训练/上传转码会用到）
- **可选 GPU**：Linux + NVIDIA 驱动（需要 CUDA 推理/训练时）

目录约定（必须存在）：

- `test1/GPT_SoVITS/`（上游推理/训练代码与资源）
- `test1/GPT_SoVITS/pretrained_models/`（BERT、Hubert、SoVITS 预训练等）
- `test1/assets/`（小程序静态资源：题库、伴宠资源、涂色资源等）
- `test1/GPT_weights_v2Pro/`、`test1/SoVITS_weights_v2Pro/`（可选：你们的全局权重池）

---

## 1. 一键创建 Python 虚拟环境

### 1.1 Linux / macOS / WSL2

在 `test1/` 根目录执行：

```bash
chmod +x env/setup_env.sh
env/setup_env.sh
```

若你在 Linux 上有 NVIDIA GPU 且希望安装 CUDA 版 PyTorch（cu124）：

```bash
CUDA_PIP=1 env/setup_env.sh
```

需要重建环境（删除旧 venv）：

```bash
env/setup_env.sh --recreate
```

### 1.2 Windows

在 `test1/` 目录中双击：

- `env\\setup_env.cmd`

需要重建环境：

- `env\\setup_env.cmd --recreate`

说明：Windows 下建议用 **Git Bash** 启动 `start_wx_api.sh`；若只做部署运行更推荐 WSL2 或 Linux。

---

## 2. 配置环境变量（不要提交密钥）

后端会按优先级加载（见 `start_wx_api.sh`）：

1. `test1/wx_api.env`
2. `test1/env/wx_api.env`
3. `test1/wx_api.env.example`
4. `test1/env/wx_api.env.example`

推荐做法：

```bash
cp env/wx_api.env.example env/wx_api.env
# 然后编辑 env/wx_api.env，填入 AI_API_KEY / WECHAT_* 等真实配置
```

安全要求：

- **不要把** `env/wx_api.env` 提交到 GitHub（里面是密钥）
- 只提交 `env/wx_api.env.example`

---

## 3. 一键启动后端（9880/9881）

在 `test1/` 根目录：

```bash
./start_wx_api.sh
```

只启动主服务（仍会确保 readalong 依赖就绪）：

```bash
./start_wx_api.sh --wx-only
```

健康检查：

```bash
./start_wx_api.sh --health
```

日志默认在：

- `test1/runtime/wx_api_9880.log`
- `test1/runtime/readalong_9881.log`

---

## 4. GitHub 上传前自检（强烈建议）

- **不要提交**：`test1/venv/`、`test1/runtime/`、`test1/train_logs/`、`test1/user_models/`、`test1/env/wx_api.env`
- `test1/voice_library.json` 内的模型路径应为**相对路径**（本仓库已改为相对路径）
- 如需保留示例音色，请把对应 `user_models/...` 一并纳入仓库；否则建议只保留预置音色（qwen_tts）

