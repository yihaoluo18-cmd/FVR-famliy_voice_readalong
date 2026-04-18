"""
伴宠 JSON 存档只读快照与按 user_id 清理（管理后台用）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EGG_STORE = PROJECT_ROOT / "output" / "ar_companion_pet_egg_store.json"
COMPANION_STORE = PROJECT_ROOT / "output" / "ar_companion_pet_companion_store.json"
GROWTH_STORE = PROJECT_ROOT / "output" / "ar_companion_pet_growth_store.json"


def _safe_uid(user_id: str) -> str:
    return str(user_id or "").strip()


def get_companion_snapshot(user_id: str) -> Dict[str, Any]:
    """聚合蛋槽、已解锁伙伴、主宠柴犬成长状态（只读）。"""
    uid = _safe_uid(user_id)
    out: Dict[str, Any] = {"user_id": uid, "egg": None, "mascots": {}, "errors": []}
    if not uid:
        out["errors"].append("empty user_id")
        return out

    try:
        from modules.ar_companion_backend.pet_egg import PetEggService
        from modules.ar_companion_backend.pet_companion import PetCompanionService

        egg_svc = PetEggService(store_path=EGG_STORE)
        egg_state = egg_svc.get_state(uid)
        out["egg"] = egg_state
        unlocked = list(egg_state.get("unlocked_mascot_ids") or [])
        out["unlocked_mascot_ids"] = unlocked
        out["slots_summary"] = _slots_progress_summary(egg_state.get("slots") or [])

        comp_svc = PetCompanionService(store_path=COMPANION_STORE, egg_service=egg_svc)
        mids = list(dict.fromkeys(["cute-dog"] + unlocked))[:12]
        for mid in mids:
            try:
                st = comp_svc.get_state(uid, mid)
                out["mascots"][mid] = _trim_companion_state(st)
            except Exception as e:
                out["mascots"][mid] = {"_error": str(e)}
    except Exception as e:
        out["errors"].append(str(e))
    return out


def _slots_progress_summary(slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    s: List[Dict[str, Any]] = []
    for x in slots:
        if not isinstance(x, dict):
            continue
        s.append(
            {
                "index": x.get("slot_index"),
                "mascot_id": x.get("mascot_id"),
                "label": x.get("label"),
                "ui_state": x.get("ui_state"),
                "progress_percent": x.get("progress_percent"),
                "hint": x.get("hint"),
            }
        )
    return s


def _trim_companion_state(st: Dict[str, Any]) -> Dict[str, Any]:
    """去掉超大 tuning 映射，保留成长与形态关键字段。"""
    if not isinstance(st, dict):
        return {}
    keys = (
        "mascot_id",
        "xp",
        "level",
        "stage",
        "growth_percent",
        "stats",
        "egg_model_active",
        "display_form_tier",
        "unlocked_form_tiers",
        "updated_at",
    )
    return {k: st.get(k) for k in keys if k in st}


def clear_user_companion_json_stores(user_id: str) -> Dict[str, bool]:
    """从伴宠相关 JSON 中删除该 user_id 条目（不影响全局调参表）。"""
    uid = _safe_uid(user_id)
    report: Dict[str, bool] = {}
    if not uid:
        return report
    for name, path in (
        ("pet_egg", EGG_STORE),
        ("pet_companion", COMPANION_STORE),
        ("pet_growth", GROWTH_STORE),
    ):
        report[name] = _pop_user_from_store(path, uid)
    return report


def _pop_user_from_store(path: Path, user_id: str) -> bool:
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(raw, dict):
        return False
    users = raw.get("users")
    if not isinstance(users, dict) or user_id not in users:
        return False
    del users[user_id]
    try:
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return False
    return True
