from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "output" / "user_mgmt.sqlite3"


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _dict_factory(cursor, row):
    data = {}
    for idx, col in enumerate(cursor.description):
        data[col[0]] = row[idx]
    return data


def get_db_path() -> str:
    env_path = str(os.environ.get("USER_MGMT_DB_PATH") or "").strip()
    return env_path or str(DEFAULT_DB_PATH)


def get_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = _dict_factory
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                openid TEXT NOT NULL UNIQUE,
                unionid TEXT DEFAULT '',
                parent_name TEXT DEFAULT '',
                baby_name TEXT DEFAULT '',
                baby_age TEXT DEFAULT '',
                avatar TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                nickname TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_models (
                voice_id TEXT PRIMARY KEY,
                owner_user_id TEXT DEFAULT '',
                display_name TEXT DEFAULT '',
                gpt_path TEXT DEFAULT '',
                sovits_path TEXT DEFAULT '',
                scene TEXT DEFAULT '',
                emotion TEXT DEFAULT '',
                trained_at TEXT DEFAULT '',
                model_type TEXT DEFAULT '',
                owner_inferred INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_voice_owner_trained ON voice_models(owner_user_id, trained_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_voice_display_name ON voice_models(display_name)")
        try:
            cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        for _col, _ddl in (
            ("blacklisted", "INTEGER NOT NULL DEFAULT 0"),
            ("ban_reason", "TEXT DEFAULT ''"),
            ("reader_stars", "INTEGER NOT NULL DEFAULT 0"),
            ("reader_level", "INTEGER NOT NULL DEFAULT 1"),
            ("admin_note", "TEXT DEFAULT ''"),
        ):
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {_col} {_ddl}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()


def upsert_user_from_wechat(
    *,
    user_id: str,
    openid: str,
    unionid: str = "",
) -> Dict:
    now = utc_now_iso()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (
                user_id, openid, unionid, created_at, updated_at, last_login_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                openid=excluded.openid,
                unionid=excluded.unionid,
                updated_at=excluded.updated_at,
                last_login_at=excluded.last_login_at
            """,
            (user_id, openid, unionid, now, now, now),
        )
        conn.commit()
        return get_user_by_id(user_id) or {}
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> Optional[Dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ? LIMIT 1", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def _normalize_phone(phone: str) -> str:
    d = "".join(c for c in str(phone or "") if c.isdigit())
    return d if len(d) == 11 else ""


def normalize_login_phone(phone: str) -> str:
    """对外：将输入规范为大陆 11 位手机号，非法则空串。"""
    return _normalize_phone(phone)


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def get_user_by_phone(phone: str) -> Optional[Dict]:
    p = _normalize_phone(phone)
    if not p:
        return None
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE phone = ? ORDER BY updated_at DESC LIMIT 1",
            (p,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_openid(openid: str) -> Optional[Dict]:
    o = str(openid or "").strip()
    if not o:
        return None
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE openid = ? LIMIT 1", (o,))
        return cur.fetchone()
    finally:
        conn.close()


def update_user_openid_unionid(user_id: str, openid: str, unionid: str) -> Optional[Dict]:
    """将微信 openid/unionid 写入指定用户（用于手机号账号绑定微信）。"""
    uid = str(user_id or "").strip()
    o = str(openid or "").strip()
    u = str(unionid or "").strip()
    if not uid or not o:
        return None
    now = utc_now_iso()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET openid = ?, unionid = ?, updated_at = ? WHERE user_id = ?",
            (o, u, now, uid),
        )
        conn.commit()
        return get_user_by_id(uid)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict]:
    e = _normalize_email(email)
    if not e or "@" not in e:
        return None
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE lower(trim(COALESCE(email, ''))) = ? ORDER BY updated_at DESC LIMIT 1",
            (e,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    rounds = 310000
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("ascii"), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    if not plain or not stored:
        return False
    parts = str(stored).split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        rounds = int(parts[1])
        salt = parts[2]
        hexdigest = parts[3]
    except (TypeError, ValueError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("ascii"), rounds)
    return hmac.compare_digest(dk.hex(), hexdigest)


def set_user_password_hash(user_id: str, password_hash: str) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    now = utc_now_iso()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
            (str(password_hash or ""), now, uid),
        )
        conn.commit()
    finally:
        conn.close()


def user_public_dict(row: Optional[Dict]) -> Dict:
    if not row or not isinstance(row, dict):
        return {}
    out = dict(row)
    out.pop("password_hash", None)
    out.pop("admin_note", None)
    return out


def admin_user_view(row: Optional[Dict]) -> Dict:
    """管理后台列表/详情：脱敏密码，保留运营备注。"""
    if not row or not isinstance(row, dict):
        return {}
    out = dict(row)
    out.pop("password_hash", None)
    return out


def register_password_user(
    *,
    phone: str,
    email: str,
    password_plain: str,
    baby_name: str = "",
    nickname: str = "",
) -> Dict:
    p = _normalize_phone(phone)
    e = _normalize_email(email)
    if not p and not e:
        raise ValueError("missing_phone_or_email")
    pwd_h = hash_password(password_plain)
    existing: Optional[Dict] = None
    if p:
        existing = get_user_by_phone(p)
        if existing is None:
            legacy_uid = f"dev_local_phone_{p}"
            existing = get_user_by_id(legacy_uid)
    if existing is None and e:
        existing = get_user_by_email(e)
        if existing is None:
            slug = "".join(c if c.isalnum() else "_" for c in e)[:72].strip("_") or "user"
            existing = get_user_by_id(f"dev_local_email_{slug}")
    if existing:
        uid = str(existing.get("user_id") or "").strip()
        if not uid:
            raise ValueError("bad_existing_user")
        if str(existing.get("password_hash") or "").strip():
            raise ValueError("already_registered")
        set_user_password_hash(uid, pwd_h)
        prof: Dict = {}
        if baby_name:
            prof["baby_name"] = str(baby_name).strip()
        if nickname:
            prof["nickname"] = str(nickname).strip()
        elif baby_name:
            prof["nickname"] = str(baby_name).strip()
        if p:
            prof["phone"] = p
        if e:
            prof["email"] = e
        if prof:
            update_user_profile(uid, prof)
        touch_user_last_login(uid)
        return user_public_dict(get_user_by_id(uid)) or {}

    if p:
        uid = f"dev_local_phone_{p}"
    else:
        slug = "".join(c if c.isalnum() else "_" for c in e)[:72].strip("_") or "user"
        uid = f"dev_local_email_{slug}"
    openid = uid
    upsert_user_from_wechat(user_id=uid, openid=openid, unionid="")
    set_user_password_hash(uid, pwd_h)
    prof2: Dict = {
        "baby_name": str(baby_name or "").strip(),
        "nickname": (str(nickname).strip() or str(baby_name or "").strip()),
        "phone": p,
        "email": e,
    }
    prof2 = {k: v for k, v in prof2.items() if v}
    if prof2:
        update_user_profile(uid, prof2)
    touch_user_last_login(uid)
    return user_public_dict(get_user_by_id(uid)) or {}


def login_password_user(*, account: str, password_plain: str) -> Optional[Dict]:
    acc = str(account or "").strip()
    if not acc or not password_plain:
        return None
    user: Optional[Dict] = None
    if re.match(r"^1[3-9]\d{9}$", acc):
        user = get_user_by_phone(acc)
    elif "@" in acc:
        user = get_user_by_email(acc)
    else:
        p2 = _normalize_phone(acc)
        if p2:
            user = get_user_by_phone(p2)
        else:
            user = get_user_by_email(acc)
    if not user:
        return None
    if not verify_password(password_plain, str(user.get("password_hash") or "")):
        return None
    uid = str(user.get("user_id") or "").strip()
    if uid:
        touch_user_last_login(uid)
    return user_public_dict(get_user_by_id(uid) if uid else user)


def touch_user_last_login(user_id: str) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    now = utc_now_iso()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE user_id = ?",
            (now, now, uid),
        )
        conn.commit()
    finally:
        conn.close()


def update_user_profile(user_id: str, profile_fields: Dict) -> Optional[Dict]:
    allowed = {"parent_name", "baby_name", "baby_age", "avatar", "phone", "email", "nickname"}
    updates = {k: v for k, v in (profile_fields or {}).items() if k in allowed and v is not None}
    # 手机/邮箱：空字符串视为未提交，避免只改一项却把另一项清空
    drop_empty = []
    for key in ("phone", "email", "avatar"):
        if key not in updates:
            continue
        val = updates[key]
        if isinstance(val, str) and not val.strip():
            drop_empty.append(key)
    for key in drop_empty:
        updates.pop(key, None)
    if not updates:
        return get_user_by_id(user_id)

    sets = []
    values: List = []
    for key, val in updates.items():
        sets.append(f"{key} = ?")
        values.append(str(val))
    sets.append("updated_at = ?")
    values.append(utc_now_iso())
    values.append(user_id)

    sql = f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?"
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(values))
        conn.commit()
        return get_user_by_id(user_id)
    finally:
        conn.close()


def upsert_voice_model(
    *,
    voice_id: str,
    owner_user_id: str = "",
    display_name: str = "",
    gpt_path: str = "",
    sovits_path: str = "",
    scene: str = "",
    emotion: str = "",
    trained_at: str = "",
    model_type: str = "",
    owner_inferred: int = 0,
) -> None:
    now = utc_now_iso()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO voice_models (
                voice_id, owner_user_id, display_name, gpt_path, sovits_path, scene, emotion,
                trained_at, model_type, owner_inferred, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(voice_id) DO UPDATE SET
                owner_user_id=excluded.owner_user_id,
                display_name=excluded.display_name,
                gpt_path=excluded.gpt_path,
                sovits_path=excluded.sovits_path,
                scene=excluded.scene,
                emotion=excluded.emotion,
                trained_at=excluded.trained_at,
                model_type=excluded.model_type,
                owner_inferred=excluded.owner_inferred,
                updated_at=excluded.updated_at
            """,
            (
                voice_id,
                owner_user_id,
                display_name,
                gpt_path,
                sovits_path,
                scene,
                emotion,
                trained_at,
                model_type,
                int(owner_inferred or 0),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def rename_voice_model(voice_id: str, new_name: str) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE voice_models SET display_name = ?, updated_at = ? WHERE voice_id = ?",
            (new_name, utc_now_iso(), voice_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_voice_model(voice_id: str) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM voice_models WHERE voice_id = ?", (voice_id,))
        conn.commit()
    finally:
        conn.close()


def list_user_voices(user_id: str) -> List[Dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM voice_models
            WHERE owner_user_id = ?
            ORDER BY trained_at DESC, created_at DESC
            """,
            (user_id,),
        )
        return cur.fetchall() or []
    finally:
        conn.close()


def list_voice_ids_for_owner(owner_user_id: str) -> List[str]:
    uid = str(owner_user_id or "").strip()
    if not uid:
        return []
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT voice_id FROM voice_models WHERE owner_user_id = ?",
            (uid,),
        )
        rows = cur.fetchall() or []
        return [str(r.get("voice_id") or "").strip() for r in rows if str(r.get("voice_id") or "").strip()]
    finally:
        conn.close()


def update_user_admin_fields(
    user_id: str,
    *,
    is_active: Optional[int] = None,
    blacklisted: Optional[int] = None,
    ban_reason: Optional[str] = None,
    reader_stars: Optional[int] = None,
    reader_level: Optional[int] = None,
    admin_note: Optional[str] = None,
) -> Optional[Dict]:
    uid = str(user_id or "").strip()
    if not uid:
        return None
    sets: List[str] = []
    vals: List = []
    if is_active is not None:
        sets.append("is_active = ?")
        vals.append(1 if int(is_active) else 0)
    if blacklisted is not None:
        sets.append("blacklisted = ?")
        vals.append(1 if int(blacklisted) else 0)
    if ban_reason is not None:
        sets.append("ban_reason = ?")
        vals.append(str(ban_reason))
    if reader_stars is not None:
        sets.append("reader_stars = ?")
        vals.append(max(0, int(reader_stars)))
    if reader_level is not None:
        sets.append("reader_level = ?")
        vals.append(max(1, min(99, int(reader_level))))
    if admin_note is not None:
        sets.append("admin_note = ?")
        vals.append(str(admin_note))
    if not sets:
        return get_user_by_id(uid)
    sets.append("updated_at = ?")
    vals.append(utc_now_iso())
    vals.append(uid)
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?",
            tuple(vals),
        )
        conn.commit()
        return get_user_by_id(uid)
    finally:
        conn.close()


def delete_user_account(user_id: str) -> bool:
    uid = str(user_id or "").strip()
    if not uid:
        return False
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM voice_models WHERE owner_user_id = ?", (uid,))
        cur.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        deleted = cur.rowcount
        conn.commit()
        return deleted > 0
    finally:
        conn.close()


def admin_stats_summary() -> Dict:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1) AS c FROM users")
        total_users = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("SELECT COUNT(1) AS c FROM users WHERE COALESCE(blacklisted, 0) = 1")
        blacklisted = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("SELECT COUNT(1) AS c FROM users WHERE is_active = 0 AND COALESCE(blacklisted, 0) = 0")
        disabled = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("SELECT COUNT(1) AS c FROM voice_models")
        total_voices = int((cur.fetchone() or {}).get("c") or 0)
        return {
            "total_users": total_users,
            "blacklisted_users": blacklisted,
            "disabled_users": disabled,
            "total_voice_models": total_voices,
        }
    finally:
        conn.close()


def list_users(
    *,
    keyword: str = "",
    is_active: Optional[int] = None,
    blacklisted: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[int, List[Dict]]:
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 20)))
    where_parts: List[str] = []
    values: List = []

    if keyword:
        q = f"%{keyword.strip()}%"
        where_parts.append(
            "(user_id LIKE ? OR openid LIKE ? OR phone LIKE ? OR nickname LIKE ? OR parent_name LIKE ? OR baby_name LIKE ? OR email LIKE ?)"
        )
        values.extend([q, q, q, q, q, q, q])
    if is_active in (0, 1):
        where_parts.append("is_active = ?")
        values.append(int(is_active))
    if blacklisted in (0, 1):
        where_parts.append("COALESCE(blacklisted, 0) = ?")
        values.append(int(blacklisted))

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    offset = (page - 1) * page_size

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(1) AS c FROM users {where_sql}", tuple(values))
        total = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute(
            f"""
            SELECT u.*,
                   COALESCE(v.voice_count, 0) AS voice_count
            FROM users u
            LEFT JOIN (
                SELECT owner_user_id, COUNT(1) AS voice_count
                FROM voice_models
                GROUP BY owner_user_id
            ) v ON v.owner_user_id = u.user_id
            {where_sql}
            ORDER BY u.updated_at DESC, u.created_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(values + [page_size, offset]),
        )
        return total, (cur.fetchall() or [])
    finally:
        conn.close()


def _infer_owner_user_id(model_name: str) -> str:
    name = str(model_name or "").strip()
    if not name:
        return ""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id FROM users
            WHERE user_id = ? OR openid = ? OR unionid = ?
            LIMIT 1
            """,
            (name, name, name),
        )
        row = cur.fetchone() or {}
        return str(row.get("user_id") or "").strip()
    finally:
        conn.close()


def migrate_from_voice_library_json(path: str) -> int:
    p = str(path or "").strip()
    if not p or not os.path.isfile(p):
        return 0
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0

    count = 0
    for voice_id, info in data.items():
        if not isinstance(info, dict):
            continue
        owner_user_id = str(info.get("owner_user_id") or "").strip()
        owner_inferred = 0
        if not owner_user_id:
            owner_user_id = _infer_owner_user_id(info.get("name"))
            owner_inferred = 1 if owner_user_id else 0
        upsert_voice_model(
            voice_id=str(voice_id or "").strip(),
            owner_user_id=owner_user_id,
            display_name=str(info.get("name") or voice_id),
            gpt_path=str(info.get("gpt_path") or ""),
            sovits_path=str(info.get("sovits_path") or ""),
            scene=str(info.get("scene") or ""),
            emotion=str(info.get("emotion") or ""),
            trained_at=str(info.get("trained_at") or ""),
            model_type=str(info.get("model_type") or ""),
            owner_inferred=owner_inferred,
        )
        count += 1
    return count

