from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 三档成长：仅 tier1 / tier2 / tier3（已撤销原四档 baby/growth/mature/star）
TIER2_XP = 120
TIER3_XP = 300

STAGE_THRESHOLDS = [
    ("tier1", 0),
    ("tier2", TIER2_XP),
    ("tier3", TIER3_XP),
]

# 与小程序调参对齐（用于服务端校验/裁剪）
# - liftMul：pet-detail 滑条 UI 仍限制在约 0.35；home / 伴读 companion 用「位置 Y」映射为 0.1 + posY/100，需允许到 2.0（对应 posY≈190）
_VIEW_TUNING_LIMITS: Dict[str, tuple[float, float, float]] = {
    "fov": (20.0, 90.0, 45.0),
    "camDistMul": (0.2, 8.0, 1.2),
    "camHeightMul": (0.0, 1.2, 0.18),
    "lookAtHeightMul": (0.0, 0.35, 0.12),
    "liftMul": (-100.0, 2.0, 0.1),
    "targetSize": (0.1, 200.0, 3.0),
    "baseRotYDeg": (-180.0, 180.0, 0.0),
    # 首页调参：额外支持平移（前端单位与 slider 保持一致）
    "position_x": (-200.0, 200.0, 0.0),
    "position_z": (-499.0, 200.0, 0.0),
}

_FORM_VIEW_KEYS = frozenset({"egg", "tier1", "tier2", "tier3"})


class PetCompanionService:
    """每只宠物独立成长与互动状态（三档形态）。"""

    def __init__(self, store_path: Path, egg_service: Any) -> None:
        self._store_path = store_path
        self._egg_service = egg_service
        self._project_root = Path(__file__).resolve().parents[2]
        self._store = self._load_store()

        # 全局（所有 user 共享）3D 视角/调参：mascot_id -> form_key(egg/tier1-3) -> {tuning,camera}
        if not isinstance(self._store.get("global_form_view_tuning"), dict):
            self._store["global_form_view_tuning"] = {}
        # 首页专用（与 pet-detail 分开）：mascot_id -> form_key -> {tuning,camera}
        if not isinstance(self._store.get("global_form_view_tuning_home"), dict):
            self._store["global_form_view_tuning_home"] = {}
        # 伴读页（AI 陪伴对话）独立一套，避免与首页 global_form_view_tuning_home 互相覆盖
        if not isinstance(self._store.get("global_form_view_tuning_companion"), dict):
            self._store["global_form_view_tuning_companion"] = {}

        # 兼容旧存档：如果全局还没收集到某些 mascot/form_key 的调参，
        # 就从 users[*].mascot_states[*].form_view_tuning 里“迁移一次”补齐全局。
        # 这样你之前已经手动调好的位置参数，新的用户也能立刻复用。
        users = self._store.get("users")
        migrated = False
        if isinstance(users, dict):
            global_store = self._store.setdefault("global_form_view_tuning", {})
            for _, u in users.items():
                if not isinstance(u, dict):
                    continue
                mascot_states = u.get("mascot_states")
                if not isinstance(mascot_states, dict):
                    continue
                for mid, pet in mascot_states.items():
                    if not isinstance(pet, dict) or not mid:
                        continue
                    ft = pet.get("form_view_tuning")
                    if not isinstance(ft, dict):
                        continue
                    mid_store = global_store.setdefault(str(mid), {})
                    for fk in _FORM_VIEW_KEYS:
                        if fk in mid_store:
                            continue
                        entry = ft.get(fk)
                        if isinstance(entry, dict):
                            mid_store[fk] = entry
                            migrated = True
        if migrated:
            self._save_store()

        # 兼容历史「场景调参」存储：将 modules/ar_companion_backend/data/ar_companion_scene_tuning_store.json
        # 中的 companion 视角参数，迁移到当前 pet_companion 全局调参（按 mascot_id）。
        # 仅在目标 form_key 缺失时补齐，不覆盖现有新结构数据。
        self._seed_companion_tuning_from_legacy_scene_store()
        # 再从历史的非分场景参数补齐：ar_companion_tuning_store.json
        # 该文件通常按 persona 维度保存用户手工调好的镜头参数（你之前主要在这里调）。
        self._seed_companion_tuning_from_legacy_tuning_store()

    def _seed_companion_tuning_from_legacy_scene_store(self) -> None:
        legacy_path = self._project_root / "modules" / "ar_companion_backend" / "data" / "ar_companion_scene_tuning_store.json"
        if not legacy_path.exists():
            return
        try:
            raw = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return

        persona_to_mascot = {
            "default": "cute-dog",
            "cute_fox": "cute-fox",
            "cute_dino": "cute-dino",
            "cute_cat": "cute-cat",
            "cute_bunny": "cute-bunny",
            "cute_squirrel": "cute-squirrel",
            "cute_chick": "cute-chick",
            "cute_panda": "cute-panda",
            "cute_koala": "cute-koala",
            "cute_penguin": "cute-penguin",
        }
        target = self._store.setdefault("global_form_view_tuning_companion", {})
        changed = False

        for key, tuning in raw.items():
            if not isinstance(key, str) or not isinstance(tuning, dict):
                continue
            parts = key.split("::")
            if len(parts) != 3:
                continue
            uid, persona_id, scene_key = parts
            if scene_key != "companion":
                continue
            # 历史数据主要以 wx_child_user 为模板，动态 uid 会在读取时回退到模板。
            if uid not in {"wx_child_user", ""}:
                continue
            mascot_id = persona_to_mascot.get(persona_id)
            if not mascot_id:
                continue

            safe_tuning = self._sanitize_view_tuning(tuning)
            if not safe_tuning:
                continue

            mascot_store = target.setdefault(mascot_id, {})
            # 兼容蛋形态与三档模型，避免切换形态后参数丢失。
            for fk in ("egg", "tier1", "tier2", "tier3"):
                if isinstance(mascot_store.get(fk), dict):
                    continue
                mascot_store[fk] = {"tuning": dict(safe_tuning)}
                changed = True

        if changed:
            self._save_store()

    def _seed_companion_tuning_from_legacy_tuning_store(self) -> None:
        legacy_path = self._project_root / "modules" / "ar_companion_backend" / "data" / "ar_companion_tuning_store.json"
        if not legacy_path.exists():
            return
        try:
            raw = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return

        persona_to_mascot = {
            "default": "cute-dog",
            "cute_fox": "cute-fox",
            "cute_dino": "cute-dino",
            "cute_cat": "cute-cat",
            "cute_bunny": "cute-bunny",
            "cute_squirrel": "cute-squirrel",
            "cute_chick": "cute-chick",
            "cute_panda": "cute-panda",
            "cute_koala": "cute-koala",
            "cute_penguin": "cute-penguin",
        }

        target = self._store.setdefault("global_form_view_tuning_companion", {})
        changed = False

        for key, tuning in raw.items():
            if not isinstance(key, str) or not isinstance(tuning, dict):
                continue
            parts = key.split("::")
            if len(parts) != 2:
                continue
            uid, persona_id = parts
            if uid not in {"wx_child_user", ""}:
                continue
            mascot_id = persona_to_mascot.get(persona_id)
            if not mascot_id:
                continue
            safe_tuning = self._sanitize_view_tuning(tuning)
            if not safe_tuning:
                continue

            mascot_store = target.setdefault(mascot_id, {})
            # 对 legacy_tuning_store 采用“补齐覆盖”策略：
            # - 若该形态为空，直接写入
            # - 若已有值，仅保留已有键并补齐缺失键（避免破坏线上已二次微调）
            for fk in ("egg", "tier1", "tier2", "tier3"):
                existing = mascot_store.get(fk) if isinstance(mascot_store.get(fk), dict) else {}
                existing_tuning = existing.get("tuning") if isinstance(existing.get("tuning"), dict) else {}
                merged = dict(safe_tuning)
                merged.update(existing_tuning)
                if existing_tuning != merged:
                    mascot_store[fk] = {"tuning": merged}
                    changed = True

        if changed:
            self._save_store()

    def get_state(self, user_id: str, mascot_id: str) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        mid = self._safe_mascot_id(mascot_id)
        self._ensure_unlocked(uid, mid)
        user = self._ensure_user(uid)
        pet = self._ensure_pet_state(user, mid)
        self._apply_decay(pet)
        self._normalize_display_tier(uid, pet)
        pet["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_state(uid, mid, pet)

    def set_display_form(self, user_id: str, mascot_id: str, form_tier: int) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        mid = self._safe_mascot_id(mascot_id)
        ft = int(form_tier)
        if ft not in (1, 2, 3):
            raise ValueError("form_tier must be 1, 2, or 3")
        self._ensure_unlocked(uid, mid)
        user = self._ensure_user(uid)
        pet = self._ensure_pet_state(user, mid)
        self._apply_decay(pet)
        xp = int(pet.get("xp", 0))
        unlocked = self._unlocked_tiers_for_user_xp(uid, xp)
        if ft not in unlocked:
            raise ValueError("form tier not unlocked")
        pet["display_form_tier"] = ft
        pet["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_state(uid, mid, pet)

    def set_view_tuning(
        self,
        user_id: str,
        mascot_id: str,
        form_key: str,
        view_scope: str = "pet_detail",
        tuning: Optional[Dict[str, Any]] = None,
        camera: Any = None,
        clear_manual_camera: bool = False,
    ) -> Dict[str, Any]:
        """保存某形态下的 3D 展示调参（镜头滑条 + 可选手动相机）。"""
        uid = self._safe_user_id(user_id)
        mid = self._safe_mascot_id(mascot_id)
        fk = str(form_key or "").strip()
        if fk not in _FORM_VIEW_KEYS:
            raise ValueError("form_key must be egg, tier1, tier2, or tier3")
        self._ensure_unlocked(uid, mid)
        # 按你的需求：tuning 不按 user_id 存储，统一写入“后端全局标准”
        # 仍然保留解锁校验逻辑：避免恶意用户写入未解锁的 mascot_key。

        scope = str(view_scope or "pet_detail").strip().lower()
        if scope not in {"pet_detail", "home", "companion"}:
            scope = "pet_detail"

        raw_tuning = tuning if isinstance(tuning, dict) else {}
        safe_tuning = self._sanitize_view_tuning(raw_tuning)
        if scope == "home":
            global_key = "global_form_view_tuning_home"
        elif scope == "companion":
            global_key = "global_form_view_tuning_companion"
        else:
            global_key = "global_form_view_tuning"
        global_store = self._store.setdefault(global_key, {})
        mid_store = global_store.setdefault(mid, {})
        prev = mid_store.get(fk) if isinstance(mid_store.get(fk), dict) else {}
        entry: Dict[str, Any] = {"tuning": safe_tuning}
        if clear_manual_camera:
            pass
        else:
            cam_sanitized = self._sanitize_view_camera(camera)
            if cam_sanitized is not None:
                entry["camera"] = cam_sanitized
            elif isinstance(prev.get("camera"), dict):
                entry["camera"] = prev["camera"]

        mid_store[fk] = entry
        self._save_store()
        # set_view_tuning 的 response：返回当前用户的完整 state，但 form_view_tuning 将来自“全局标准”
        user = self._ensure_user(uid)
        pet = self._ensure_pet_state(user, mid)
        self._apply_decay(pet)
        self._normalize_display_tier(uid, pet)
        pet["updated_at"] = self._now_iso()
        return self._build_state(uid, mid, pet)

    def apply_action(self, user_id: str, mascot_id: str, action_type: str) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        mid = self._safe_mascot_id(mascot_id)
        act = str(action_type or "").strip()
        if act not in {"feed", "clean", "play"}:
            raise ValueError(f"unsupported action_type: {act}")
        self._ensure_unlocked(uid, mid)
        user = self._ensure_user(uid)
        pet = self._ensure_pet_state(user, mid)
        self._apply_decay(pet)

        if act == "feed":
            pet["stats"]["hunger"] = self._clamp100(int(pet["stats"].get("hunger", 0)) + 22)
            pet["stats"]["sleepy"] = self._clamp100(int(pet["stats"].get("sleepy", 0)) + 4)
            pet["xp"] = int(pet.get("xp", 0)) + 6
        elif act == "clean":
            pet["stats"]["clean"] = self._clamp100(int(pet["stats"].get("clean", 0)) + 25)
            pet["stats"]["mood"] = self._clamp100(int(pet["stats"].get("mood", 0)) + 5)
            pet["xp"] = int(pet.get("xp", 0)) + 5
        else:
            pet["stats"]["mood"] = self._clamp100(int(pet["stats"].get("mood", 0)) + 18)
            pet["stats"]["sleepy"] = self._clamp100(int(pet["stats"].get("sleepy", 0)) - 6)
            pet["xp"] = int(pet.get("xp", 0)) + 9

        # 孵化规则：只在「喂养」后才从 egg 切到 tier1/2/3
        if act == "feed" and int(pet.get("xp", 0) or 0) > 0:
            pet["egg_model_active"] = False

        pet.setdefault("last_actions", {})[act] = self._now_iso()
        self._normalize_display_tier(uid, pet)
        pet["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_state(uid, mid, pet)

    def report_read_progress(self, user_id: str, mascot_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        mid = self._safe_mascot_id(mascot_id)
        self._ensure_unlocked(uid, mid)
        user = self._ensure_user(uid)
        pet = self._ensure_pet_state(user, mid)
        self._apply_decay(pet)

        data = payload or {}
        pages = int(data.get("total_pages") or 0)
        xp_add = 10 + min(max(pages, 0), 20)
        pet["xp"] = int(pet.get("xp", 0)) + xp_add
        pet["stats"]["mood"] = self._clamp100(int(pet["stats"].get("mood", 0)) + 8)
        pet["stats"]["hunger"] = self._clamp100(int(pet["stats"].get("hunger", 0)) - 4)
        pet.setdefault("last_actions", {})["read"] = self._now_iso()

        # 阅读不触发孵化：仍保持 egg，直到喂养

        self._normalize_display_tier(uid, pet)
        pet["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_state(uid, mid, pet)

    def _guest_unlock_all_form_tiers(self, user_id: str) -> bool:
        try:
            fn = getattr(self._egg_service, "is_guest_user", None)
            if callable(fn):
                return bool(fn(user_id))
        except Exception:
            pass
        return False

    def _unlocked_tiers_for_user_xp(self, user_id: str, xp: int) -> List[int]:
        if self._guest_unlock_all_form_tiers(user_id):
            return [1, 2, 3]
        x = max(0, int(xp))
        out = [1]
        if x >= TIER2_XP:
            out.append(2)
        if x >= TIER3_XP:
            out.append(3)
        return out

    def _normalize_display_tier(self, user_id: str, pet: Dict[str, Any]) -> None:
        xp = int(pet.get("xp", 0))
        unlocked = self._unlocked_tiers_for_user_xp(user_id, xp)
        dft = int(pet.get("display_form_tier", 1) or 1)
        if dft not in unlocked:
            pet["display_form_tier"] = max(unlocked)

    def _ensure_unlocked(self, user_id: str, mascot_id: str) -> None:
        state = self._egg_service.get_state(user_id=user_id)
        unlocked = set(state.get("unlocked_mascot_ids") or [])
        if mascot_id not in unlocked:
            raise ValueError("mascot not unlocked")

    def _ensure_user(self, user_id: str) -> Dict[str, Any]:
        users = self._store.setdefault("users", {})
        if user_id not in users or not isinstance(users.get(user_id), dict):
            users[user_id] = {
                "mascot_states": {},
                "created_at": self._now_iso(),
                "updated_at": self._now_iso(),
            }
        return users[user_id]

    def _ensure_pet_state(self, user: Dict[str, Any], mascot_id: str) -> Dict[str, Any]:
        states = user.setdefault("mascot_states", {})
        if mascot_id not in states or not isinstance(states.get(mascot_id), dict):
            states[mascot_id] = {
                "xp": 0,
                "stats": {"hunger": 70, "mood": 68, "clean": 72, "sleepy": 40},
                "last_actions": {},
                "last_decay_at": self._now_iso(),
                "display_form_tier": 1,
                # 新孵化后的首次展示：egg 模型；当产生过 xp 后自动切回 tier1/2/3
                "egg_model_active": True,
                "updated_at": self._now_iso(),
            }
        pet = states[mascot_id]
        if "display_form_tier" not in pet:
            pet["display_form_tier"] = 1
        if "egg_model_active" not in pet:
            # 兼容旧存档：
            # egg 期的切换规则是“只有 feed 才会从 egg 切到 tier1/2/3”，
            # 但旧存档可能没有 egg_model_active 字段，若仅用 xp==0 推断，
            # 会把“阅读带来的 xp 增长”（不应触发孵化）误判为已破壳。
            last_actions = pet.get("last_actions") or {}
            had_feed = bool(last_actions.get("feed"))
            pet["egg_model_active"] = not had_feed
        else:
            # 进一步兜底：若存档里 egg_model_active=false，但 last_actions 里没有 feed，
            # 则说明该状态可能是旧版本推断错误（例如用 xp==0 推断）。
            last_actions = pet.get("last_actions") or {}
            had_feed = bool(last_actions.get("feed"))
            if not had_feed:
                pet["egg_model_active"] = True
        if "form_view_tuning" not in pet or not isinstance(pet.get("form_view_tuning"), dict):
            pet["form_view_tuning"] = {}
        return pet

    def _apply_decay(self, pet: Dict[str, Any]) -> None:
        last = str(pet.get("last_decay_at") or "").strip()
        if not last:
            pet["last_decay_at"] = self._now_iso()
            return
        try:
            last_dt = datetime.fromisoformat(last)
        except ValueError:
            pet["last_decay_at"] = self._now_iso()
            return
        now = datetime.now()
        elapsed_hours = max(0.0, (now - last_dt).total_seconds() / 3600.0)
        if elapsed_hours <= 0:
            return

        hunger_drop = int(elapsed_hours * 2.2)
        mood_drop = int(elapsed_hours * 1.3)
        clean_drop = int(elapsed_hours * 1.9)
        sleepy_raise = int(elapsed_hours * 1.7)
        pet["stats"]["hunger"] = self._clamp100(int(pet["stats"].get("hunger", 0)) - hunger_drop)
        pet["stats"]["mood"] = self._clamp100(int(pet["stats"].get("mood", 0)) - mood_drop)
        pet["stats"]["clean"] = self._clamp100(int(pet["stats"].get("clean", 0)) - clean_drop)
        pet["stats"]["sleepy"] = self._clamp100(int(pet["stats"].get("sleepy", 0)) + sleepy_raise)
        pet["last_decay_at"] = self._now_iso()

    def _growth_percent(self, xp: int) -> int:
        x = max(0, int(xp))
        if x >= TIER3_XP:
            return 100
        if x >= TIER2_XP:
            span = max(1, TIER3_XP - TIER2_XP)
            return min(99, 50 + int(((x - TIER2_XP) / span) * 50))
        span = max(1, TIER2_XP)
        return min(49, int((x / span) * 50))

    def _build_state(self, user_id: str, mascot_id: str, pet: Dict[str, Any]) -> Dict[str, Any]:
        xp = int(pet.get("xp", 0))
        stage = self._get_stage(xp)
        dft = int(pet.get("display_form_tier", 1) or 1)
        unlocked = self._unlocked_tiers_for_user_xp(user_id, xp)
        global_ft = self._get_global_form_view_tuning(mascot_id, scope="pet_detail")
        global_ft_home = self._get_global_form_view_tuning(mascot_id, scope="home")
        global_ft_companion = self._get_global_form_view_tuning(mascot_id, scope="companion")
        return {
            "user_id": user_id,
            "mascot_id": mascot_id,
            "xp": xp,
            "level": min(10, (xp // 60) + 1),
            "stage": stage,
            "next_stage_xp": self._next_stage_xp(xp),
            "growth_percent": self._growth_percent(xp),
            "stats": {
                "hunger": self._clamp100(int((pet.get("stats") or {}).get("hunger", 0))),
                "mood": self._clamp100(int((pet.get("stats") or {}).get("mood", 0))),
                "clean": self._clamp100(int((pet.get("stats") or {}).get("clean", 0))),
                "sleepy": self._clamp100(int((pet.get("stats") or {}).get("sleepy", 0))),
            },
            "last_actions": dict(pet.get("last_actions") or {}),
            "updated_at": str(pet.get("updated_at") or ""),
            "unlocked_form_tiers": unlocked,
            "display_form_tier": dft,
            "form_tier_thresholds": {"2": TIER2_XP, "3": TIER3_XP},
            "egg_model_active": bool(pet.get("egg_model_active", False)),
            # form_view_tuning：优先使用全局标准；若全局尚未设置，则回退到旧的用户存档结构。
            "form_view_tuning": global_ft or dict(pet.get("form_view_tuning") or {}),
            # 首页单独一套（不回退到旧用户存档，避免历史 pet-detail 影响首页）
            "form_view_tuning_home": global_ft_home or {},
            # 伴读页单独一套（与首页、宠详情互不影响）
            "form_view_tuning_companion": global_ft_companion or {},
        }

    def _get_global_form_view_tuning(self, mascot_id: str, scope: str = "pet_detail") -> Dict[str, Any]:
        s = str(scope or "").strip().lower()
        if s == "home":
            key = "global_form_view_tuning_home"
        elif s == "companion":
            key = "global_form_view_tuning_companion"
        else:
            key = "global_form_view_tuning"
        global_store = self._store.get(key)
        if not isinstance(global_store, dict):
            return {}
        mid_store = global_store.get(str(mascot_id or "").strip())
        if not isinstance(mid_store, dict):
            return {}
        # 只暴露合法 key，避免脏数据
        out: Dict[str, Any] = {}
        for fk in _FORM_VIEW_KEYS:
            v = mid_store.get(fk)
            if v is not None:
                out[fk] = v
        return out

    def _sanitize_view_tuning(self, raw: Dict[str, Any]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for key, (lo, hi, default) in _VIEW_TUNING_LIMITS.items():
            if key not in raw:
                out[key] = default
                continue
            try:
                v = float(raw[key])
            except (TypeError, ValueError):
                v = default
            out[key] = max(lo, min(hi, v))
        return out

    def _sanitize_view_camera(self, camera: Any) -> Optional[Dict[str, Any]]:
        """合法则返回 pos+lookAt；camera 为 None 表示调用方未提交，应保留旧值。"""
        if camera is None:
            return None
        if not isinstance(camera, dict):
            return None
        pos = camera.get("pos") or {}
        look_at = camera.get("lookAt") or camera.get("look_at") or {}
        try:
            px, py, pz = float(pos.get("x")), float(pos.get("y")), float(pos.get("z"))
            lx, ly, lz = float(look_at.get("x")), float(look_at.get("y")), float(look_at.get("z"))
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(v) for v in (px, py, pz, lx, ly, lz)):
            return None
        # 合理范围裁剪，避免恶意超大 JSON
        def _clip_coord(n: float) -> float:
            return max(-500.0, min(500.0, n))

        return {
            "pos": {"x": _clip_coord(px), "y": _clip_coord(py), "z": _clip_coord(pz)},
            "lookAt": {"x": _clip_coord(lx), "y": _clip_coord(ly), "z": _clip_coord(lz)},
        }

    def _next_stage_xp(self, xp: int) -> int:
        x = int(xp)
        for _, threshold in STAGE_THRESHOLDS:
            if x < threshold:
                return threshold
        return STAGE_THRESHOLDS[-1][1]

    def _get_stage(self, xp: int) -> str:
        current = "tier1"
        for name, threshold in STAGE_THRESHOLDS:
            if int(xp) >= threshold:
                current = name
            else:
                break
        return current

    def _safe_user_id(self, user_id: str) -> str:
        uid = str(user_id or "").strip()
        return uid or "guest_user"

    def _safe_mascot_id(self, mascot_id: str) -> str:
        mid = str(mascot_id or "").strip()
        if not mid:
            raise ValueError("mascot_id required")
        return mid

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

    def _clamp100(self, v: int) -> int:
        return max(0, min(100, int(v)))
