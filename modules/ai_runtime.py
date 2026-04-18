from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clean_api_key(raw: str) -> str:
    key = str(raw or "").strip()
    if not key:
        return ""
    lower = key.lower()
    if any(x in lower for x in ["替换", "留空", "your", "example", "placeholder", "xxx", "sk-xxx"]):
        return ""
    try:
        key.encode("ascii")
    except Exception:
        return ""
    return key


def _coerce_qwen_model(raw: str, fallback: str) -> str:
    model = str(raw or "").strip()
    if not model:
        return fallback
    if not model.lower().startswith("qwen"):
        return fallback
    return model


@dataclass(frozen=True)
class AIRuntimeConfig:
    enabled: bool
    base_url: str
    api_key: str
    timeout_sec: float
    fail_closed: bool
    max_chars: int
    cache_ttl_sec: float
    cache_max: int
    text_default_model: str
    models: Dict[str, str]

    def model_for(self, task: str) -> str:
        return self.models.get(task, self.text_default_model)


def load_ai_runtime_config() -> AIRuntimeConfig:
    base_url = (
        os.environ.get("AI_BASE_URL")
        or os.environ.get("SAFETY_AI_BASE_URL")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ).strip().rstrip("/")

    api_key = _clean_api_key(
        os.environ.get("AI_API_KEY")
        or os.environ.get("SAFETY_AI_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or ""
    )

    text_default = _coerce_qwen_model(
        os.environ.get("AI_MODEL_TEXT_DEFAULT") or os.environ.get("SAFETY_AI_MODEL") or "qwen-plus",
        "qwen-plus",
    )

    vision_default = _coerce_qwen_model(
        os.environ.get("AI_MODEL_VISION")
        or os.environ.get("STORY_VISION_MODEL")
        or os.environ.get("SAFETY_AI_VISION_MODEL")
        or "qwen-vl-plus",
        "qwen-vl-plus",
    )

    audio_default = _coerce_qwen_model(
        os.environ.get("AI_MODEL_AUDIO_DEFAULT") or "qwen-omni-turbo",
        "qwen-omni-turbo",
    )

    models = {
        "safety": _coerce_qwen_model(os.environ.get("AI_MODEL_SAFETY"), text_default),
        "story": _coerce_qwen_model(os.environ.get("AI_MODEL_STORY"), text_default),
        "readalong_eval": _coerce_qwen_model(os.environ.get("AI_MODEL_READALONG_EVAL"), text_default),
        "vision_caption": vision_default,
        "image_gen": _coerce_qwen_model(os.environ.get("AI_MODEL_IMAGE_GEN"), "qwen-image"),
        "readalong_asr": _coerce_qwen_model(
            os.environ.get("AI_MODEL_READALONG_ASR") or os.environ.get("AI_MODEL_ASR"),
            audio_default,
        ),
        "readalong_tts": _coerce_qwen_model(
            os.environ.get("AI_MODEL_READALONG_TTS") or os.environ.get("AI_MODEL_TTS"),
            audio_default,
        ),
    }

    return AIRuntimeConfig(
        enabled=_to_bool(os.environ.get("SAFETY_AI_ENABLED"), default=False),
        base_url=base_url,
        api_key=api_key,
        timeout_sec=float(os.environ.get("AI_TIMEOUT_SEC") or os.environ.get("SAFETY_AI_TIMEOUT_SEC") or "10"),
        fail_closed=_to_bool(os.environ.get("SAFETY_AI_FAIL_CLOSED"), default=False),
        max_chars=int(os.environ.get("SAFETY_AI_MAX_CHARS") or "5000"),
        cache_ttl_sec=float(os.environ.get("SAFETY_AI_CACHE_TTL_SEC") or "120"),
        cache_max=int(os.environ.get("SAFETY_AI_CACHE_MAX") or "1024"),
        text_default_model=text_default,
        models=models,
    )
