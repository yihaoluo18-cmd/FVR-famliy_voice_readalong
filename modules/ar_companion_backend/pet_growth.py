from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PET_STATE_NO_EGG = "no_egg"
PET_STATE_INCUBATING = "incubating"
PET_STATE_HATCH_READY = "hatch_ready"
PET_STATE_HATCHED = "hatched"


@dataclass
class PetGrowthConfig:
    read_threshold: int = 3
    streak_threshold: int = 3


class PetGrowthService:
    """
    宠物蛋养成模块：
    - 维护用户宠物状态与进度
    - 处理阅读/签到事件
    - 条件满足（其一）后进入可孵化状态
    """

    def __init__(self, store_path: Path, config: Optional[PetGrowthConfig] = None) -> None:
        self._store_path = store_path
        self._config = config or PetGrowthConfig()
        self._store = self._load_store()
        self._persona_pool: List[str] = ["cute_fox", "cute_cat", "cute_bunny", "cute_squirrel", "cute_dino", "cute_chick"]

    def get_state(self, user_id: str) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        user = self._ensure_user(uid)
        return self._build_state(uid, user)

    def report_progress(self, user_id: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        user = self._ensure_user(uid)
        event_payload = payload or {}
        today = self._today_str()
        event_type = str(event_type or "").strip()
        user.setdefault("events", {})

        if event_type == "checkin_completed":
            last_day = str(user["events"].get("last_checkin_day", "")).strip()
            if last_day != today:
                user["events"]["last_checkin_day"] = today
                streak = int(event_payload.get("consecutive_days") or 0)
                if streak > 0:
                    user["checkin_streak_days"] = streak
                else:
                    user["checkin_streak_days"] = max(1, int(user.get("checkin_streak_days", 0)) + 1)
        elif event_type == "read_task_completed":
            book_id = str(event_payload.get("book_id") or "unknown")
            dedup_key = f"{today}:{book_id}"
            read_keys = user["events"].setdefault("read_task_keys", [])
            if dedup_key not in read_keys:
                read_keys.append(dedup_key)
                user["read_task_count"] = int(user.get("read_task_count", 0)) + 1
                if len(read_keys) > 500:
                    user["events"]["read_task_keys"] = read_keys[-500:]
        else:
            raise ValueError(f"unsupported event_type: {event_type}")

        self._sync_pet_state(user)
        user["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_state(uid, user)

    def claim_hatch(self, user_id: str) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        user = self._ensure_user(uid)
        self._sync_pet_state(user)
        if user.get("pet_state") != PET_STATE_HATCH_READY:
            raise ValueError("pet not ready to hatch")

        hatched = user.setdefault("hatched_companions", [])
        next_persona = self._pick_next_persona(hatched)
        if next_persona not in hatched:
            hatched.append(next_persona)

        user["pet_state"] = PET_STATE_HATCHED
        user["last_hatched_persona"] = next_persona
        user["last_hatched_at"] = self._now_iso()
        user["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_state(uid, user)

    def _pick_next_persona(self, hatched: List[str]) -> str:
        for pid in self._persona_pool:
            if pid not in hatched:
                return pid
        return self._persona_pool[0]

    def _safe_user_id(self, user_id: str) -> str:
        uid = str(user_id or "").strip()
        return uid or "guest_user"

    def _ensure_user(self, user_id: str) -> Dict[str, Any]:
        users = self._store.setdefault("users", {})
        if user_id not in users or not isinstance(users.get(user_id), dict):
            users[user_id] = {
                "pet_state": PET_STATE_INCUBATING,
                "read_task_count": 0,
                "checkin_streak_days": 0,
                "hatched_companions": [],
                "last_hatched_persona": "",
                "last_hatched_at": "",
                "events": {
                    "last_checkin_day": "",
                    "read_task_keys": [],
                },
                "created_at": self._now_iso(),
                "updated_at": self._now_iso(),
            }
        return users[user_id]

    def _sync_pet_state(self, user: Dict[str, Any]) -> None:
        read_count = int(user.get("read_task_count", 0))
        streak_days = int(user.get("checkin_streak_days", 0))
        if read_count >= self._config.read_threshold or streak_days >= self._config.streak_threshold:
            if user.get("pet_state") != PET_STATE_HATCHED:
                user["pet_state"] = PET_STATE_HATCH_READY
        elif user.get("pet_state") != PET_STATE_HATCHED:
            user["pet_state"] = PET_STATE_INCUBATING

    def _build_state(self, user_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "pet_state": str(user.get("pet_state") or PET_STATE_INCUBATING),
            "read_task_count": int(user.get("read_task_count", 0)),
            "checkin_streak_days": int(user.get("checkin_streak_days", 0)),
            "read_threshold": self._config.read_threshold,
            "streak_threshold": self._config.streak_threshold,
            "is_hatch_ready": str(user.get("pet_state")) == PET_STATE_HATCH_READY,
            "hatched_companions": list(user.get("hatched_companions") or []),
            "last_hatched_persona": str(user.get("last_hatched_persona") or ""),
            "last_hatched_at": str(user.get("last_hatched_at") or ""),
            "updated_at": str(user.get("updated_at") or ""),
        }

    def _load_store(self) -> Dict[str, Any]:
        try:
            if self._store_path.exists():
                raw = json.loads(self._store_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
        except Exception:
            pass
        return {"users": {}}

    def _save_store(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._store_path.write_text(json.dumps(self._store, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")
