from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 仅游客（wx_child_user*）下可选：自动补全未写入的「狐狸小橙」；正式登录用户不走此逻辑。
_DEV_UNLOCK_FOX_MASCOT = False
# ---------------------------------------------------------------------------

def is_guest_companion_user_id(user_id: str) -> bool:
    """未注册/未登录联调：设备级 id，前缀与小程序 pet-growth.getUserId 一致。"""
    uid = str(user_id or "").strip()
    return uid == "wx_child_user" or uid.startswith("wx_child_user_")


# UI 状态：与前端展示一致
UI_LOCKED = "locked"
UI_INCUBATING = "incubating"
UI_READY = "ready"
UI_CLAIMED = "claimed"


@dataclass(frozen=True)
class _SlotDef:
    index: int
    mascot_id: str
    label: str
    emoji: str
    rule: str  # starter | checkin_month | read_count | combo
    checkin_need: int = 0
    read_need: int = 0


# 10 个伙伴槽位：签到档 3/7/15/30 + 阅读阶梯 + 复合门槛；槽 0 为初始小狗
EGG_SLOT_DEFS: List[_SlotDef] = [
    _SlotDef(0, "cute-dog", "柴柴小星", "🐶", "starter"),
    _SlotDef(1, "cute-fox", "狐狸小橙", "🦊", "checkin_month", checkin_need=3),
    _SlotDef(2, "cute-dino", "恐龙小绿", "🦕", "checkin_month", checkin_need=7),
    _SlotDef(3, "cute-cat", "小猫咪咪", "🐱", "checkin_month", checkin_need=15),
    _SlotDef(4, "cute-bunny", "兔兔小白", "🐰", "checkin_month", checkin_need=30),
    _SlotDef(5, "cute-squirrel", "松鼠栗栗", "🐿️", "read_count", read_need=4),
    _SlotDef(6, "cute-chick", "嘎嘎小黄", "🐥", "read_count", read_need=7),
    _SlotDef(7, "cute-panda", "熊猫萌萌", "🐼", "read_count", read_need=10),
    _SlotDef(8, "cute-koala", "考拉困困", "🐨", "checkin_month", checkin_need=20),
    _SlotDef(9, "cute-penguin", "企鹅摇摇", "🐧", "combo", checkin_need=25, read_need=15),
]

ALL_MASCOT_IDS: List[str] = [d.mascot_id for d in EGG_SLOT_DEFS]


class PetEggService:
    """首页宠物蛋：10 槽进度、领取后写入 unlocked_mascot_ids（伴读等只读此列表）。"""

    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path
        self._store = self._load_store()

    def is_guest_user(self, user_id: str) -> bool:
        return is_guest_companion_user_id(user_id)

    def get_state(self, user_id: str) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        user = self._ensure_user(uid)
        return self._build_full_state(uid, user)

    def report_progress(self, user_id: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        user = self._ensure_user(uid)
        event_payload = payload or {}
        event_type = str(event_type or "").strip()

        if event_type == "checkin_month_sync":
            self._apply_checkin_month_snapshot(user, event_payload)
        elif event_type == "checkin_completed":
            self._apply_checkin_month_snapshot(user, event_payload)
            last_day = str(user.setdefault("events", {}).get("last_checkin_day", "")).strip()
            today = self._today_str()
            if last_day != today:
                user["events"]["last_checkin_day"] = today
                streak = int(event_payload.get("consecutive_days") or 0)
                if streak > 0:
                    user["consecutive_checkin"] = streak
                else:
                    user["consecutive_checkin"] = max(1, int(user.get("consecutive_checkin", 0)) + 1)
        elif event_type == "read_task_completed":
            book_id = str(event_payload.get("book_id") or "unknown")
            dedup_key = f"{self._today_str()}:{book_id}"
            read_keys = user.setdefault("events", {}).setdefault("read_task_keys", [])
            if dedup_key not in read_keys:
                read_keys.append(dedup_key)
                user["read_lifetime"] = int(user.get("read_lifetime", 0)) + 1
                if len(read_keys) > 500:
                    user["events"]["read_task_keys"] = read_keys[-500:]
        else:
            raise ValueError(f"unsupported event_type: {event_type}")

        user["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_full_state(uid, user)

    def claim_slot(self, user_id: str, slot_index: int) -> Dict[str, Any]:
        uid = self._safe_user_id(user_id)
        user = self._ensure_user(uid)
        if slot_index < 0 or slot_index >= len(EGG_SLOT_DEFS):
            raise ValueError("invalid slot_index")

        slot_meta = self._slot_view(user, EGG_SLOT_DEFS[slot_index])
        if slot_meta["ui_state"] != UI_READY:
            raise ValueError("egg not ready to claim")

        defs = EGG_SLOT_DEFS[slot_index]
        unlocked = user.setdefault("unlocked_mascot_ids", [])
        if defs.mascot_id not in unlocked:
            unlocked.append(defs.mascot_id)

        user["updated_at"] = self._now_iso()
        self._save_store()
        return self._build_full_state(uid, user)

    def _apply_checkin_month_snapshot(self, user: Dict[str, Any], payload: Dict[str, Any]) -> None:
        ym = str(payload.get("year_month") or "").strip()
        if not ym:
            dt = datetime.now()
            ym = f"{dt.year}-{dt.month:02d}"
        total = int(payload.get("total_check_ins_this_month") or 0)
        key = str(user.get("checkin_month_key") or "")
        if key != ym:
            user["checkin_month_key"] = ym
            user["checkin_month_total"] = max(0, total)
        else:
            user["checkin_month_total"] = max(int(user.get("checkin_month_total", 0)), total)

    def _ensure_user(self, user_id: str) -> Dict[str, Any]:
        users = self._store.setdefault("users", {})
        guest = is_guest_companion_user_id(user_id)
        if user_id not in users or not isinstance(users.get(user_id), dict):
            init_unlocked = list(ALL_MASCOT_IDS) if guest else ["cute-dog"]
            users[user_id] = {
                "unlocked_mascot_ids": init_unlocked,
                "read_lifetime": 0,
                "checkin_month_key": "",
                "checkin_month_total": 0,
                "consecutive_checkin": 0,
                "events": {"last_checkin_day": "", "read_task_keys": []},
                "created_at": self._now_iso(),
                "updated_at": self._now_iso(),
            }
        u = users[user_id]
        if "unlocked_mascot_ids" not in u or not isinstance(u.get("unlocked_mascot_ids"), list):
            u["unlocked_mascot_ids"] = list(ALL_MASCOT_IDS) if guest else ["cute-dog"]
        ul: List[str] = u["unlocked_mascot_ids"]
        if guest:
            changed = False
            for mid in ALL_MASCOT_IDS:
                if mid not in ul:
                    ul.append(mid)
                    changed = True
            if _DEV_UNLOCK_FOX_MASCOT and "cute-fox" not in ul:
                ul.append("cute-fox")
                changed = True
            if changed:
                self._save_store()
        else:
            if "cute-dog" not in ul:
                ul.insert(0, "cute-dog")
                self._save_store()
        return u

    def _requirements_met(self, user: Dict[str, Any], defs: _SlotDef) -> bool:
        if defs.rule == "starter":
            return True
        month_total = int(user.get("checkin_month_total", 0))
        read_n = int(user.get("read_lifetime", 0))
        if defs.rule == "checkin_month":
            return month_total >= defs.checkin_need
        if defs.rule == "read_count":
            return read_n >= defs.read_need
        if defs.rule == "combo":
            return month_total >= defs.checkin_need and read_n >= defs.read_need
        return False

    def _slot_view(self, user: Dict[str, Any], defs: _SlotDef) -> Dict[str, Any]:
        unlocked = set(user.get("unlocked_mascot_ids") or [])
        mascot_id = defs.mascot_id
        month_total = int(user.get("checkin_month_total", 0))
        read_n = int(user.get("read_lifetime", 0))
        hint = _hint_for(defs, user)

        if defs.rule == "starter" or mascot_id in unlocked:
            return {
                "slot_index": defs.index,
                "mascot_id": mascot_id,
                "label": defs.label,
                "emoji": defs.emoji,
                "rule": defs.rule,
                "ui_state": UI_CLAIMED,
                "progress_percent": 100,
                "progress_current": month_total,
                "progress_need": 0,
                "hint": hint,
            }

        if self._requirements_met(user, defs):
            pc, pn = self._display_current_need(user, defs)
            return {
                "slot_index": defs.index,
                "mascot_id": mascot_id,
                "label": defs.label,
                "emoji": defs.emoji,
                "rule": defs.rule,
                "ui_state": UI_READY,
                "progress_percent": 100,
                "progress_current": pc,
                "progress_need": pn,
                "hint": hint,
            }

        if defs.rule == "combo":
            pct = min(
                _safe_percent(month_total, defs.checkin_need),
                _safe_percent(read_n, defs.read_need),
            )
            ui_state = UI_INCUBATING if pct > 0 else UI_LOCKED
            return {
                "slot_index": defs.index,
                "mascot_id": mascot_id,
                "label": defs.label,
                "emoji": defs.emoji,
                "rule": defs.rule,
                "ui_state": ui_state,
                "progress_percent": pct,
                "progress_current": pct,
                "progress_need": 100,
                "hint": hint,
            }

        if defs.rule == "checkin_month":
            cur, nd = month_total, defs.checkin_need
        else:
            cur, nd = read_n, defs.read_need
        pct = _safe_percent(cur, nd)
        ui_state = UI_INCUBATING if cur > 0 else UI_LOCKED
        return {
            "slot_index": defs.index,
            "mascot_id": mascot_id,
            "label": defs.label,
            "emoji": defs.emoji,
            "rule": defs.rule,
            "ui_state": ui_state,
            "progress_percent": pct,
            "progress_current": cur,
            "progress_need": nd,
            "hint": hint,
        }

    def _display_current_need(self, user: Dict[str, Any], defs: _SlotDef) -> tuple[int, int]:
        month_total = int(user.get("checkin_month_total", 0))
        read_n = int(user.get("read_lifetime", 0))
        if defs.rule == "checkin_month":
            return month_total, defs.checkin_need
        if defs.rule == "read_count":
            return read_n, defs.read_need
        if defs.rule == "combo":
            return month_total + read_n, defs.checkin_need + defs.read_need
        return 1, 1

    def _build_full_state(self, user_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        slots = [self._slot_view(user, d) for d in EGG_SLOT_DEFS]
        # 与 unlocked_mascot_ids 强制对齐：已解锁的蛋一律视为 claimed（避免存档/旧逻辑导致仍显示未解锁）
        unlocked = set(user.get("unlocked_mascot_ids") or [])
        month_total = int(user.get("checkin_month_total", 0))
        for s in slots:
            mid = str(s.get("mascot_id") or "").strip()
            if mid in unlocked and s.get("ui_state") != UI_CLAIMED:
                defs = next((d for d in EGG_SLOT_DEFS if d.mascot_id == mid), None)
                s["ui_state"] = UI_CLAIMED
                s["progress_percent"] = 100
                s["progress_need"] = 0
                s["progress_current"] = month_total
                s["hint"] = _hint_for(defs, user) if defs else str(s.get("hint") or "")
        has_ready = any(s["ui_state"] == UI_READY for s in slots)
        return {
            "user_id": user_id,
            "slots": slots,
            "unlocked_mascot_ids": list(user.get("unlocked_mascot_ids") or []),
            "has_ready_to_claim": has_ready,
            "read_lifetime": int(user.get("read_lifetime", 0)),
            "checkin_month_total": int(user.get("checkin_month_total", 0)),
            "checkin_month_key": str(user.get("checkin_month_key") or ""),
            "consecutive_checkin": int(user.get("consecutive_checkin", 0)),
            "updated_at": str(user.get("updated_at") or ""),
        }

    def _safe_user_id(self, user_id: str) -> str:
        uid = str(user_id or "").strip()
        return uid or "guest_user"

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


def _hint_for(defs: _SlotDef, user: Dict[str, Any]) -> str:
    m = int(user.get("checkin_month_total", 0))
    r = int(user.get("read_lifetime", 0))
    if defs.rule == "starter":
        return "一开始就陪伴你的小伙伴"
    if defs.rule == "checkin_month":
        return f"本月签到 {m}/{defs.checkin_need} 天"
    if defs.rule == "read_count":
        return f"完成阅读 {r}/{defs.read_need} 次"
    if defs.rule == "combo":
        return f"签到{m}/{defs.checkin_need} · 阅读{r}/{defs.read_need}"
    return ""


def _safe_percent(cur: int, need: int) -> int:
    if need <= 0:
        return 0
    return max(0, min(99, int((cur / need) * 100)))
