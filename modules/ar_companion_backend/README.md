# AR Companion Backend

用于微信小程序 AR/3D 数字陪伴形象的后端模块（MVP）。

## 功能范围

- 会话创建与状态机（`idle -> listening -> thinking -> speaking`）
- 唤醒接口（可由前端按钮或唤醒词触发）
- 文本对话接口
- 语音 URL 对话接口（ASR 占位）
- 返回 TTS 音频地址（TTS 占位）
- 3D 形象配置接口（用于首页/AR 页加载模型）
- **内置伴宠口吻**：系统提示以「陪读小伙伴」第一人称与儿童对话（见 `services.py` 中 `_build_companion_system_prompt`）

## 目录

- `app.py`：独立 FastAPI 启动入口
- `api.py`：`/ar_companion/*` API 路由
- `services.py`：会话与 ASR/LLM/TTS 业务逻辑
- `models.py`：请求/响应数据模型

## 启动

在项目根目录执行：

```bash
python -m modules.ar_companion_backend.app -a 0.0.0.0 -p 9896
```

若需 **与主项目相同的 Qwen（DashScope OpenAI-compatible）**，请在**同一环境**中加载主站 `wx_api.env`（或手动导出变量），保证进程能读到 `AI_BASE_URL` 与 `AI_API_KEY`。未设 `AR_COMPANION_LLM_URL` 时，只要上述变量存在，会自动走内置 Qwen 文本补全。

## API

前缀：`/ar_companion`

- `GET /health`
- `POST /session/create`
- `POST /session/wakeup`
- `POST /chat/text`
- `POST /chat/voice_url`
- `GET /avatar/config?persona_id=default`

## LLM 接入说明

优先级如下：

1. **`AR_COMPANION_LLM_URL`**（可选）  
   自定义 HTTP JSON 服务，请求体含 `system_prompt`、`messages`（含历史）、`session_id` 等；响应 JSON 字段 **`text`** 为助手回复。

2. **内置 Qwen（与仓库 `wx_api.env` 一致）**  
   当未配置 `AR_COMPANION_LLM_URL`，且存在 **`AI_BASE_URL` + `AI_API_KEY`**（或 `OPENAI_API_KEY` / `DASHSCOPE_API_KEY`）时，自动请求 `{AI_BASE_URL}/chat/completions`。  
   - 模型： **`AR_COMPANION_QWEN_MODEL`** → `AI_MODEL_TEXT_DEFAULT` → `SAFETY_AI_MODEL` → 默认 `qwen-plus`  
   - 超时：`AI_TIMEOUT_SEC`（默认 45s）  
   - 显式关闭内置链：`AR_COMPANION_USE_BUILTIN_QWEN=0`

3. **占位回复**  
   以上都不可用时返回简短本地占位句，便于联调 UI。

## 伴宠提示词

- 核心人设由代码内 `_build_companion_system_prompt` 生成（含当前 `persona` 展示名）。  
- 环境变量 **`AR_COMPANION_SYSTEM_PROMPT`** 仅作为**追加规则**片段，不要求覆盖全文。

## 对接外部 ASR/TTS（可选）

- `AR_COMPANION_ASR_URL`
- `AR_COMPANION_TTS_URL`
- `AR_COMPANION_VOICE_ID`

若未配置，模块会使用内置占位 ASR 文本与空 TTS URL，方便先联调 UI 与状态机。
