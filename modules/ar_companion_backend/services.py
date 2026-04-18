from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib import error as urllib_error
from urllib import request

from .models import CompanionState


def _post_json(
    url: str,
    payload: dict,
    timeout: float = 20.0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(
        url=url,
        data=data,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    if not raw:
        return {}
    return json.loads(raw)


@dataclass
class SessionMemory:
    session_id: str
    user_id: str
    persona_id: str
    state: CompanionState = CompanionState.idle
    history: List[dict] = field(default_factory=list)


class CompanionEngine:
    """
    轻量后端引擎：
    - 维护会话状态机
    - 提供 ASR/LLM/TTS 占位调用
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionMemory] = {}
        self._project_root = Path(__file__).resolve().parents[2]
        # 兼容两种存储位置：
        # 1) 根目录（你现在手动贴入的文件）
        # 2) output/（历史版本默认位置）
        data_dir = self._project_root / "modules" / "ar_companion_backend" / "data"
        data_scene_tuning = data_dir / "ar_companion_scene_tuning_store.json"
        data_tuning = data_dir / "ar_companion_tuning_store.json"

        legacy_scene_candidates = [
            self._project_root / "ar_companion_scene_tuning_store.json",
            self._project_root / "output" / "ar_companion_scene_tuning_store.json",
        ]
        legacy_tuning_candidates = [
            self._project_root / "ar_companion_tuning_store.json",
            self._project_root / "output" / "ar_companion_tuning_store.json",
        ]

        # 目标：两份 tuning 都集中放到 modules/ar_companion_backend/data/
        self._scene_tuning_store_path = data_scene_tuning
        self._tuning_store_path = data_tuning

        # 若 data/ 下缺文件，则从旧位置迁移一份（只迁移一次，不覆盖现有）
        if not self._scene_tuning_store_path.exists():
            for legacy_path in legacy_scene_candidates:
                if legacy_path.exists():
                    try:
                        self._scene_tuning_store_path.parent.mkdir(parents=True, exist_ok=True)
                        self._scene_tuning_store_path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
                    except Exception:
                        pass
                    break

        if not self._tuning_store_path.exists():
            for legacy_path in legacy_tuning_candidates:
                if legacy_path.exists():
                    try:
                        self._tuning_store_path.parent.mkdir(parents=True, exist_ok=True)
                        self._tuning_store_path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
                    except Exception:
                        pass
                    break
        self._user_tuning_store: Dict[str, Dict[str, float]] = self._load_tuning_store()
        self._user_scene_tuning_store: Dict[str, Dict[str, float]] = self._load_scene_tuning_store()
        self._persona_catalog = {
            "default": {
                "display_name": "柴柴小星",
                # dog 三档形态最高级：用于伴读页默认加载（含有动作/行走动画的 glb）
                "model_url": "/ar_companion/assets/shiba/shiba%20level%203.glb",
                "camera_preset": {"camDistMul": 1.2, "targetSize": 2.4, "fov": 42, "lookAtHeightMul": 0.12},
            },
            "cute_chick": {
                "display_name": "嘎嘎小黄",
                "model_url": "/ar_companion/assets/chick/scene.gltf",
                "camera_preset": {"camDistMul": 1.0, "targetSize": 2.8, "fov": 42, "lookAtHeightMul": 0.14},
            },
            "cute_dino": {
                "display_name": "恐龙小绿",
                "model_url": "/ar_companion/assets/chick/scene.gltf",
                "camera_preset": {"camDistMul": 1.0, "targetSize": 2.8, "fov": 42, "lookAtHeightMul": 0.14},
            },
            "cute_fox": {
                "display_name": "狐狸小橙",
                "model_url": "/ar_companion/assets/fox/fox%20level%203.glb",
                "camera_preset": {"camDistMul": 1.05, "targetSize": 2.8, "fov": 42, "lookAtHeightMul": 0.14},
            },
            "cute_cat": {
                "display_name": "小猫咪咪",
                "model_url": "/ar_companion/assets/cat/scene.gltf",
                "camera_preset": {"camDistMul": 1.0, "targetSize": 2.9, "fov": 42, "lookAtHeightMul": 0.14},
            },
            "cute_bunny": {
                "display_name": "兔兔小白",
                "model_url": "/ar_companion/assets/bunny/scene.gltf",
                "camera_preset": {"camDistMul": 0.85, "targetSize": 5.5, "fov": 38, "lookAtHeightMul": 0.18, "liftMul": 0.12},
            },
            "cute_squirrel": {
                "display_name": "松鼠栗栗",
                "model_url": "/ar_companion/assets/squirrel/scene.gltf",
                "camera_preset": {"camDistMul": 0.95, "targetSize": 3.0, "fov": 40, "lookAtHeightMul": 0.15},
            },
            "cute_panda": {
                "display_name": "熊猫萌萌",
                "model_url": "/ar_companion/assets/cat/scene.gltf",
                "camera_preset": {"camDistMul": 1.0, "targetSize": 2.9, "fov": 42, "lookAtHeightMul": 0.14},
            },
            "cute_koala": {
                "display_name": "考拉困困",
                "model_url": "/ar_companion/assets/cat/scene.gltf",
                "camera_preset": {"camDistMul": 1.0, "targetSize": 2.9, "fov": 42, "lookAtHeightMul": 0.14},
            },
            "cute_penguin": {
                "display_name": "企鹅摇摇",
                "model_url": "/ar_companion/assets/chick/scene.gltf",
                "camera_preset": {"camDistMul": 1.0, "targetSize": 2.8, "fov": 42, "lookAtHeightMul": 0.14},
            },
            "warm_big_sister": {
                "display_name": "暖暖姐姐",
                "model_url": "/assets/avatar/warm_big_sister.glb",
            },
        }
    def create_session(self, user_id: str, persona_id: str) -> SessionMemory:
        sid = f"ar_{uuid.uuid4().hex[:12]}"
        if persona_id not in self._persona_catalog:
            persona_id = "default"
        memory = SessionMemory(session_id=sid, user_id=user_id, persona_id=persona_id)
        self._sessions[sid] = memory
        return memory

    def get_session(self, session_id: str) -> Optional[SessionMemory]:
        return self._sessions.get(session_id)

    def wakeup(self, session_id: str, wake_word: str) -> SessionMemory:
        memory = self._must_get(session_id)
        # 目前先采用按钮/短语触发，后续可替换热词引擎
        if wake_word.strip():
            memory.state = CompanionState.listening
        return memory

    def chat_by_text(self, session_id: str, text: str, use_tts: bool = True) -> dict:
        memory = self._must_get(session_id)
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("text is empty")

        memory.state = CompanionState.thinking
        assistant_text = self._llm_chat(memory, clean_text)

        tts_audio_url = None
        if use_tts:
            memory.state = CompanionState.speaking
            tts_audio_url = self._tts_synthesize(memory, assistant_text)
        else:
            memory.state = CompanionState.idle

        memory.history.append({"role": "user", "content": clean_text})
        memory.history.append({"role": "assistant", "content": assistant_text})
        memory.history = memory.history[-20:]
        memory.state = CompanionState.idle

        return {
            "user_text": clean_text,
            "assistant_text": assistant_text,
            "tts_audio_url": tts_audio_url,
            "state": memory.state,
            "history": memory.history,
        }

    def chat_by_voice_url(self, session_id: str, audio_url: str, audio_format: str, use_tts: bool = True) -> dict:
        memory = self._must_get(session_id)
        memory.state = CompanionState.listening
        user_text = self._asr_transcribe(memory, audio_url=audio_url, audio_format=audio_format)
        return self.chat_by_text(session_id=session_id, text=user_text, use_tts=use_tts)

    def avatar_config(self, persona_id: str, user_id: Optional[str] = None) -> dict:
        item = self._persona_catalog.get(persona_id) or self._persona_catalog["default"]
        pid = persona_id if persona_id in self._persona_catalog else "default"
        default_camera = item.get("camera_preset") or {}
        user_camera = self.get_user_tuning(user_id=user_id or "", persona_id=pid) if user_id else None
        final_camera = {**default_camera, **(user_camera or {})} if (default_camera or user_camera) else None
        return {
            "persona_id": pid,
            "display_name": item["display_name"],
            "model_url": item["model_url"],
            "camera_preset": final_camera,
            "tuning_source": "user" if user_camera else ("preset" if default_camera else None),
            "idle_animation": "idle",
            "talk_animation": "talk",
            "react_animation": "react",
        }

    def avatar_scene_config(self, persona_id: str, user_id: Optional[str] = None, scene_key: str = "companion") -> dict:
        item = self._persona_catalog.get(persona_id) or self._persona_catalog["default"]
        pid = persona_id if persona_id in self._persona_catalog else "default"
        skey = (scene_key or "companion").strip() or "companion"
        default_camera = item.get("camera_preset") or {}
        user_camera = None
        if user_id:
            # 优先场景参数，其次回落到旧版非分场景参数，保证兼容。
            user_camera = self.get_user_scene_tuning(user_id=user_id or "", persona_id=pid, scene_key=skey)
            if not user_camera:
                user_camera = self.get_user_tuning(user_id=user_id or "", persona_id=pid)
        final_camera = {**default_camera, **(user_camera or {})} if (default_camera or user_camera) else None
        source = None
        if user_camera:
            source = "user_scene"
        elif default_camera:
            source = "preset"
        return {
            "persona_id": pid,
            "scene_key": skey,
            "display_name": item["display_name"],
            "model_url": item["model_url"],
            "camera_preset": final_camera,
            "tuning_source": source,
            "idle_animation": "idle",
            "talk_animation": "talk",
            "react_animation": "react",
        }

    def _tuning_key(self, user_id: str, persona_id: str) -> str:
        return f"{user_id.strip()}::{persona_id.strip()}"

    def _candidate_user_ids(self, user_id: str) -> List[str]:
        """
        兼容动态 uid：
        - 精确匹配：wx_child_user_1775xxx
        - 前缀回退：wx_child_user
        """
        uid = str(user_id or "").strip()
        if not uid:
            return [""]
        out = [uid]
        if uid.startswith("wx_child_user_"):
            out.append("wx_child_user")
        return out

    def _load_tuning_store(self) -> Dict[str, Dict[str, float]]:
        try:
            if not self._tuning_store_path.exists():
                return {}
            raw = json.loads(self._tuning_store_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out: Dict[str, Dict[str, float]] = {}
                for k, v in raw.items():
                    if isinstance(k, str) and isinstance(v, dict):
                        out[k] = {str(kk): float(vv) for kk, vv in v.items() if isinstance(vv, (int, float))}
                return out
        except Exception:
            pass
        return {}

    def _save_tuning_store(self) -> None:
        self._tuning_store_path.parent.mkdir(parents=True, exist_ok=True)
        self._tuning_store_path.write_text(
            json.dumps(self._user_tuning_store, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _scene_tuning_key(self, user_id: str, persona_id: str, scene_key: str) -> str:
        return f"{user_id.strip()}::{persona_id.strip()}::{scene_key.strip()}"

    def _load_scene_tuning_store(self) -> Dict[str, Dict[str, float]]:
        try:
            if not self._scene_tuning_store_path.exists():
                return {}
            raw = json.loads(self._scene_tuning_store_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out: Dict[str, Dict[str, float]] = {}
                for k, v in raw.items():
                    if isinstance(k, str) and isinstance(v, dict):
                        out[k] = {str(kk): float(vv) for kk, vv in v.items() if isinstance(vv, (int, float))}
                return out
        except Exception:
            pass
        return {}

    def _save_scene_tuning_store(self) -> None:
        self._scene_tuning_store_path.parent.mkdir(parents=True, exist_ok=True)
        self._scene_tuning_store_path.write_text(
            json.dumps(self._user_scene_tuning_store, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_user_tuning(self, user_id: str, persona_id: str, tuning: Dict[str, float]) -> None:
        key = self._tuning_key(user_id=user_id, persona_id=persona_id)
        cleaned = {str(k): float(v) for k, v in (tuning or {}).items() if isinstance(v, (int, float))}
        self._user_tuning_store[key] = cleaned
        self._save_tuning_store()

    def get_user_tuning(self, user_id: str, persona_id: str) -> Optional[Dict[str, float]]:
        for uid in self._candidate_user_ids(user_id):
            key = self._tuning_key(user_id=uid, persona_id=persona_id)
            got = self._user_tuning_store.get(key)
            if got:
                return got
        return None

    def save_user_scene_tuning(self, user_id: str, persona_id: str, scene_key: str, tuning: Dict[str, float]) -> None:
        key = self._scene_tuning_key(user_id=user_id, persona_id=persona_id, scene_key=scene_key)
        cleaned = {str(k): float(v) for k, v in (tuning or {}).items() if isinstance(v, (int, float))}
        self._user_scene_tuning_store[key] = cleaned
        self._save_scene_tuning_store()

    def get_user_scene_tuning(self, user_id: str, persona_id: str, scene_key: str) -> Optional[Dict[str, float]]:
        for uid in self._candidate_user_ids(user_id):
            key = self._scene_tuning_key(user_id=uid, persona_id=persona_id, scene_key=scene_key)
            got = self._user_scene_tuning_store.get(key)
            if got:
                return got
        return None

    def _must_get(self, session_id: str) -> SessionMemory:
        memory = self.get_session(session_id)
        if not memory:
            raise KeyError(f"session not found: {session_id}")
        return memory

    def _persona_display_name(self, persona_id: str) -> str:
        row = self._persona_catalog.get(persona_id) or self._persona_catalog["default"]
        return str(row.get("display_name") or "小伙伴").strip() or "小伙伴"

    def _build_companion_system_prompt(self, memory: SessionMemory) -> str:
        """伴读宠第一人称与儿童对话；环境变量 AR_COMPANION_SYSTEM_PROMPT 可作追加规则。"""

        name = self._persona_display_name(memory.persona_id)
        extra = os.getenv("AR_COMPANION_SYSTEM_PROMPT", "").strip()
        core = (
            f"你是陪读小伙伴「{name}」，用自己的口吻和小朋友说话（用“我/你”，不要说自己是助手、AI 或模型）。\n"
            "语气温暖、简短、口语化，像温柔的好朋友；每回复尽量控制在两三句以内。\n"
            "可以偶尔用合适的语气词，但不要幼稚堆砌。\n"
            "内容要正向、安全：不恐吓、不严厉训斥；涉及危险、辱骂、隐私、医疗诊断等要委婉拒绝并建议问家长或老师。\n"
            "小朋友问学习或习惯时，多鼓励并给一个小步骤，避免长篇大论。"
        )
        if extra:
            return core + "\n\n【额外规则】\n" + extra
        return core

    def _llm_infer_openai_compatible(self, *, system_prompt: str, history: List[dict], user_text: str) -> str:
        """OpenAI-compatible 网关（与主项目一致，如 DashScope Qwen）。"""
        base_url = (os.getenv("AI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip().rstrip("/")
        api_key = (os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "").strip()
        model = (
            os.getenv("AR_COMPANION_QWEN_MODEL")
            or os.getenv("AI_MODEL_TEXT_DEFAULT")
            or os.getenv("SAFETY_AI_MODEL")
            or "qwen-plus"
        ).strip()
        try:
            timeout = float(os.getenv("AI_TIMEOUT_SEC", "45"))
        except Exception:
            timeout = 45.0
        if not base_url or not api_key:
            return ""

        url = f"{base_url}/chat/completions"
        msgs: List[dict] = [{"role": "system", "content": system_prompt}]
        for turn in history[-16:]:
            role = str(turn.get("role") or "")
            content = str(turn.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": user_text})

        payload = {
            "model": model,
            "temperature": 0.65,
            "max_tokens": 512,
            "messages": msgs,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        opener = request.build_opener(request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except urllib_error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            raise RuntimeError(f"LLM HTTP {e.code}: {body[:500]}")

        if not raw:
            return ""
        obj = json.loads(raw)
        text = (((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not text:
            return ""
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text).strip()
        text = re.sub(r"\s*```$", "", text).strip()
        return text

    def _asr_transcribe(self, memory: SessionMemory, audio_url: str, audio_format: str) -> str:
        asr_url = os.getenv("AR_COMPANION_ASR_URL", "").strip()
        if asr_url:
            payload = {
                "session_id": memory.session_id,
                "user_id": memory.user_id,
                "audio_url": audio_url,
                "audio_format": audio_format,
            }
            resp = _post_json(asr_url, payload)
            text = str(resp.get("text", "")).strip()
            if text:
                return text
        return "你好，我想和你聊聊天。"

    def _llm_chat(self, memory: SessionMemory, user_text: str) -> str:
        system_prompt = self._build_companion_system_prompt(memory)
        llm_url = os.getenv("AR_COMPANION_LLM_URL", "").strip()
        if llm_url:
            payload = {
                "session_id": memory.session_id,
                "user_id": memory.user_id,
                "persona_id": memory.persona_id,
                "display_name": self._persona_display_name(memory.persona_id),
                "system_prompt": system_prompt,
                "messages": memory.history + [{"role": "user", "content": user_text}],
            }
            resp = _post_json(llm_url, payload)
            text = str(resp.get("text", "")).strip()
            if text:
                return text

        use_builtin = os.getenv("AR_COMPANION_USE_BUILTIN_QWEN", "").strip().lower() in {"1", "true", "yes"}
        if not use_builtin and not llm_url:
            has_cfg = bool(
                (os.getenv("AI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()
                and (os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "").strip()
            )
            use_builtin = has_cfg

        if use_builtin:
            try:
                out = self._llm_infer_openai_compatible(
                    system_prompt=system_prompt,
                    history=memory.history,
                    user_text=user_text,
                )
                if out:
                    return out
            except Exception:
                pass

        return f"我在呢，我们可以继续聊「{user_text[:12]}」哦。"

    def _tts_synthesize(self, memory: SessionMemory, text: str) -> Optional[str]:
        tts_url = os.getenv("AR_COMPANION_TTS_URL", "").strip()
        if tts_url:
            payload = {
                "session_id": memory.session_id,
                "user_id": memory.user_id,
                "text": text,
                "voice_id": os.getenv("AR_COMPANION_VOICE_ID", "default"),
            }
            resp = _post_json(tts_url, payload)
            url = str(resp.get("audio_url", "")).strip()
            if url:
                return url
        return ""

