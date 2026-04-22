from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from . import companion_admin, db
from .schemas import (
    AdminUserPatch,
    PasswordLoginRequest,
    PasswordRegisterRequest,
    PasswordResetRequest,
    UserListResponse,
    UserProfileUpdate,
    WechatBindPhoneLoginRequest,
    WechatLoginRequest,
)


router = APIRouter(tags=["user_mgmt"])
db.init_db()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
db.migrate_from_voice_library_json(str(PROJECT_ROOT / "voice_library.json"))

# 微信 access_token 内存缓存（用于手机号快速验证组件）
_wx_stable_token: Dict[str, Any] = {"token": "", "exp": 0.0}

# 外呼微信 HTTPS：Windows/部分环境默认 SSL 校验易失败，优先用 certifi 根证书
_WX_HTTP_TIMEOUT_SEC = 15


def _wx_https_opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), https_handler)


def _dev_password_reset_skip_wx_verify() -> bool:
    """仅本地联调：与 DEV_LOGIN_ENABLED 同时开启时跳过手机号 code 换号（极不安全，禁止用于公网）。"""
    return _safe_str(os.environ.get("DEV_LOGIN_ENABLED")) == "1" and _safe_str(
        os.environ.get("PASSWORD_RESET_SKIP_WX_VERIFY")
    ).lower() in ("1", "true", "yes")


def _safe_str(v) -> str:
    return str(v or "").strip()


def _valid_cn_mobile(s: str) -> bool:
    return bool(re.fullmatch(r"1[3-9]\d{9}", _safe_str(s)))


def _valid_email(s: str) -> bool:
    t = _safe_str(s)
    if not t or len(t) > 120 or "@" not in t:
        return False
    return bool(
        re.match(
            r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$",
            t,
        )
    )


def _valid_password_policy(p: str) -> bool:
    if len(_safe_str(p)) < 8:
        return False
    return bool(re.search(r"[A-Za-z]", p)) and bool(re.search(r"\d", p))


def _token_secret() -> str:
    s = _safe_str(os.environ.get("USER_TOKEN_SECRET"))
    return s or "dev_user_token_secret_change_me"


def _admin_api_key() -> str:
    return _safe_str(os.environ.get("ADMIN_API_KEY"))


def _wechat_appid() -> str:
    return _safe_str(os.environ.get("WECHAT_APPID"))


def _wechat_secret() -> str:
    return _safe_str(os.environ.get("WECHAT_SECRET"))


def _b64_url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64_url(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def sign_user_token(user_id: str, ttl_sec: int = 30 * 24 * 3600) -> str:
    payload = {
        "uid": _safe_str(user_id),
        "exp": int(time.time()) + int(ttl_sec),
        "iat": int(time.time()),
    }
    payload_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64_url(payload_raw)
    sig = hmac.new(_token_secret().encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_user_token(token: str) -> Optional[Dict]:
    tok = _safe_str(token)
    if "." not in tok:
        return None
    payload_b64, sig = tok.rsplit(".", 1)
    expect = hmac.new(_token_secret().encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        payload = json.loads(_unb64_url(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    uid = _safe_str(payload.get("uid"))
    if not uid:
        return None
    return payload


def _extract_bearer(authorization: str) -> str:
    auth = _safe_str(authorization)
    if not auth.lower().startswith("bearer "):
        return ""
    return auth[7:].strip()


def require_user_id(authorization: str) -> str:
    token = _extract_bearer(authorization)
    payload = verify_user_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid token")
    user_id = _safe_str(payload.get("uid"))
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid user")
    return user_id


def _assert_user_may_login(user: Optional[Dict]) -> None:
    if not user:
        raise HTTPException(
            status_code=404,
            detail="账号不存在或登录已失效，请退出后重新登录",
        )
    if int(user.get("is_active") or 0) != 1:
        raise HTTPException(status_code=403, detail="account disabled")
    if int(user.get("blacklisted") or 0) == 1:
        reason = _safe_str(user.get("ban_reason"))
        raise HTTPException(
            status_code=403,
            detail=f"account blacklisted: {reason}" if reason else "account blacklisted",
        )


def require_admin(admin_api_key_header: str, authorization: str) -> None:
    key = _admin_api_key()
    if not key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY not configured")
    header_key = _safe_str(admin_api_key_header)
    bearer = _extract_bearer(authorization)
    if header_key == key or bearer == key:
        return
    raise HTTPException(status_code=401, detail="admin auth failed")


def call_wechat_code2session(code: str) -> Dict:
    appid = _wechat_appid()
    secret = _wechat_secret()
    if not appid or not secret:
        raise HTTPException(status_code=503, detail="WECHAT_APPID/WECHAT_SECRET not configured")
    q = urllib.parse.urlencode(
        {
            "appid": appid,
            "secret": secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
    )
    url = f"https://api.weixin.qq.com/sns/jscode2session?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "gpt-sovits-user-mgmt/1.0"})
    try:
        opener = _wx_https_opener()
        with opener.open(req, timeout=_WX_HTTP_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw or "{}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"无法连接微信服务器（登录 code 换 session），请检查网络与 SSL 证书：{e}",
        ) from e
    if data.get("errcode"):
        raise HTTPException(status_code=400, detail=f"wechat login failed: {data.get('errmsg') or data.get('errcode')}")
    return data


def _wechat_stable_access_token() -> str:
    """小程序服务端 API 用的 access_token（非用户网页授权）。"""
    appid = _wechat_appid()
    secret = _wechat_secret()
    if not appid or not secret:
        raise HTTPException(status_code=503, detail="WECHAT_APPID/WECHAT_SECRET not configured")
    now = time.time()
    if _wx_stable_token["token"] and float(_wx_stable_token["exp"] or 0) > now + 120:
        return str(_wx_stable_token["token"])
    q = urllib.parse.urlencode(
        {"grant_type": "client_credential", "appid": appid, "secret": secret}
    )
    url = f"https://api.weixin.qq.com/cgi-bin/token?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "gpt-sovits-user-mgmt/1.0"})
    try:
        opener = _wx_https_opener()
        with opener.open(req, timeout=_WX_HTTP_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw or "{}")
    except HTTPException:
        raise
    except Exception as e:
        hint = ""
        es = str(e).lower()
        if any(x in es for x in ("refused", "timed out", "timeout", "network is unreachable", "name or service not known")):
            hint = (
                " 本地开发若无法访问外网，可在环境变量中同时设置 DEV_LOGIN_ENABLED=1 与 "
                "PASSWORD_RESET_SKIP_WX_VERIFY=1 后重启 wx_api（仅调试，禁止用于生产）。"
            )
        raise HTTPException(
            status_code=503,
            detail=f"无法连接微信服务器（获取 access_token），请检查网络、防火墙或 Python SSL：{e}{hint}",
        ) from e
    if data.get("errcode"):
        raise HTTPException(
            status_code=400,
            detail=f"微信未签发 access_token，请核对 WECHAT_APPID/WECHAT_SECRET 与小程序后台是否一致：{data.get('errmsg') or data.get('errcode')}",
        )
    tok = _safe_str(data.get("access_token"))
    if not tok:
        raise HTTPException(status_code=400, detail="微信返回的 access_token 为空，请检查 AppSecret")
    exp_in = int(data.get("expires_in") or 7200)
    _wx_stable_token["token"] = tok
    _wx_stable_token["exp"] = now + float(exp_in)
    return tok


def _normalize_phone_from_wechat(phone_raw: str) -> str:
    """与库内 _normalize_phone 一致：大陆 11 位。"""
    d = "".join(c for c in str(phone_raw or "") if c.isdigit())
    if len(d) == 13 and d.startswith("86"):
        d = d[2:]
    if len(d) == 11 and d.startswith("1"):
        return d
    return ""


def call_wechat_get_user_phone_number(phone_code: str) -> str:
    """使用手机号快速验证组件返回的 code 换取用户手机号。"""
    code = _safe_str(phone_code)
    if not code:
        raise HTTPException(status_code=400, detail="missing phone_code")
    token = _wechat_stable_access_token()
    url = f"https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token={urllib.parse.quote(token)}"
    body = json.dumps({"code": code}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": "gpt-sovits-user-mgmt/1.0", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = _wx_https_opener()
        with opener.open(req, timeout=_WX_HTTP_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw or "{}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"无法连接微信服务器（换取手机号），请检查网络与 SSL：{e}",
        ) from e
    if int(data.get("errcode") or 0) != 0:
        raise HTTPException(
            status_code=400,
            detail=f"微信手机号 code 无效或已过期，请关闭弹窗重试一次：{data.get('errmsg') or data.get('errcode')}",
        )
    info = data.get("phone_info") or {}
    phone_number = _safe_str(info.get("purePhoneNumber") or info.get("phoneNumber"))
    norm = _normalize_phone_from_wechat(phone_number)
    if not norm:
        raise HTTPException(status_code=400, detail="微信返回的手机号格式异常，请重试授权")
    return norm


@router.post("/auth/wechat/login")
async def auth_wechat_login(body: WechatLoginRequest):
    code = _safe_str(body.code)
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    wx_data = call_wechat_code2session(code)
    openid = _safe_str(wx_data.get("openid"))
    unionid = _safe_str(wx_data.get("unionid"))
    if not openid:
        raise HTTPException(status_code=400, detail="missing openid from wechat")
    user_id = unionid or openid
    user = db.upsert_user_from_wechat(user_id=user_id, openid=openid, unionid=unionid)
    _assert_user_may_login(user)
    token = sign_user_token(user_id=user_id)
    return {"code": 0, "token": token, "user": db.user_public_dict(user)}


@router.post("/auth/wechat/login-bind-phone")
async def auth_wechat_login_bind_phone(body: WechatBindPhoneLoginRequest):
    """
    微信登录（强制手机号）：wx.login 的 code + 手机号快速验证组件的 phone_code。
    将微信 openid/unionid 绑定到「已用手机号注册」的同一用户；token 的 user_id 为手机号账号 id（如 dev_local_phone_*）。
    """
    skip_wx_verify = _dev_password_reset_skip_wx_verify()
    if skip_wx_verify:
        dp = _safe_str(body.dev_phone)
        if not _valid_cn_mobile(dp):
            raise HTTPException(
                status_code=400,
                detail="本地联调请传 dev_phone（11位手机号），或关闭 PASSWORD_RESET_SKIP_WX_VERIFY 后使用真机授权",
            )
        phone_norm = _normalize_phone_from_wechat(dp)
        dev_openid = _safe_str(getattr(body, "dev_openid", ""))
        # 本地联调允许完全离线：若无法访问微信 code2session，则回退到可复现的开发 openid
        wx_code = _safe_str(body.wx_code)
        openid = ""
        unionid = ""
        if wx_code:
            try:
                wx_data = call_wechat_code2session(wx_code)
                openid = _safe_str(wx_data.get("openid"))
                unionid = _safe_str(wx_data.get("unionid"))
            except HTTPException:
                openid = ""
        if not openid:
            openid = dev_openid or f"dev_wx_bind_{phone_norm}"
    else:
        wx_code = _safe_str(body.wx_code)
        if not wx_code:
            raise HTTPException(status_code=400, detail="missing wx_code")
        wx_data = call_wechat_code2session(wx_code)
        openid = _safe_str(wx_data.get("openid"))
        unionid = _safe_str(wx_data.get("unionid"))
        if not openid:
            raise HTTPException(status_code=400, detail="missing openid from wechat")
        phone_norm = call_wechat_get_user_phone_number(body.phone_code)
    if not phone_norm:
        raise HTTPException(status_code=400, detail="无法解析手机号")

    phone_user = db.get_user_by_phone(phone_norm)
    if not phone_user:
        raise HTTPException(
            status_code=404,
            detail="该手机号尚未注册，请先用「注册」创建账号后再授权手机号完成微信绑定登录",
        )
    aid = _safe_str(phone_user.get("user_id"))
    if not aid:
        raise HTTPException(status_code=500, detail="bad user row")

    wx_row = db.get_user_by_openid(openid)
    if wx_row:
        bid = _safe_str(wx_row.get("user_id"))
        if bid and bid != aid:
            b_phone_raw = str(wx_row.get("phone") or "").strip()
            b_phone = _normalize_phone_from_wechat(b_phone_raw) or db.normalize_login_phone(b_phone_raw)
            if b_phone:
                raise HTTPException(
                    status_code=409,
                    detail="该微信已绑定其他手机号，请使用原手机号或微信方式登录",
                )
            companion_admin.clear_user_companion_json_stores(bid)
            if not db.delete_user_account(bid):
                raise HTTPException(status_code=500, detail="合并账号时清理旧会话失败，请稍后重试")

    updated = db.update_user_openid_unionid(aid, openid, unionid)
    if not updated:
        raise HTTPException(status_code=500, detail="绑定微信身份失败")
    db.touch_user_last_login(aid)
    raw = db.get_user_by_id(aid)
    _assert_user_may_login(raw)
    token = sign_user_token(user_id=aid)
    return {"code": 0, "token": token, "user": db.user_public_dict(raw)}


@router.post("/auth/register/password")
async def auth_register_password(body: PasswordRegisterRequest):
    if not _valid_password_policy(body.password):
        raise HTTPException(
            status_code=400,
            detail="password must be at least 8 characters and include both letters and digits",
        )
    acc = _safe_str(body.account)
    phone = ""
    email = ""
    if _valid_cn_mobile(acc):
        phone = acc
    elif _valid_email(acc):
        email = acc.lower()
    else:
        raise HTTPException(status_code=400, detail="invalid phone or email format")
    baby = _safe_str(body.baby_name)
    if not baby:
        raise HTTPException(status_code=400, detail="baby_name is required for registration")
    nick = _safe_str(body.nickname)
    try:
        user = db.register_password_user(
            phone=phone,
            email=email,
            password_plain=body.password,
            baby_name=baby,
            nickname=nick or baby,
        )
    except ValueError as e:
        code = str(e)
        if code == "already_registered":
            detail = (
                "当前手机号已经注册，请直接登录"
                if phone
                else "该邮箱已注册，请直接登录"
            )
            raise HTTPException(status_code=409, detail=detail) from e
        raise HTTPException(status_code=400, detail="registration failed") from e
    uid = _safe_str(user.get("user_id"))
    if not uid:
        raise HTTPException(status_code=500, detail="registration incomplete")
    token = sign_user_token(user_id=uid)
    return {"code": 0, "token": token, "user": db.user_public_dict(user)}


@router.post("/auth/password/reset")
async def auth_password_reset(body: PasswordResetRequest):
    """
    忘记密码：仅支持「注册账号为大陆手机号」的场景。
    通过微信小程序手机号快速验证组件拿到的 phone_code 校验机号与账号一致后，写入新密码。
    邮箱注册账号请使用微信登录或联系管理员。
    """
    if not _valid_password_policy(body.new_password):
        raise HTTPException(
            status_code=400,
            detail="password must be at least 8 characters and include both letters and digits",
        )
    acc = _safe_str(body.account)
    if not _valid_cn_mobile(acc) and not _valid_email(acc):
        raise HTTPException(status_code=400, detail="invalid phone or email format")
    if _valid_email(acc):
        raise HTTPException(
            status_code=400,
            detail="邮箱注册账号暂不支持自助重置密码，请使用微信登录或联系客服",
        )
    phone_norm = _normalize_phone_from_wechat(acc)
    if not phone_norm:
        raise HTTPException(status_code=400, detail="请填写注册时使用的大陆手机号")

    if _dev_password_reset_skip_wx_verify():
        wx_phone = phone_norm
    else:
        wx_phone = call_wechat_get_user_phone_number(body.phone_code)
    if wx_phone != phone_norm:
        raise HTTPException(status_code=403, detail="微信授权手机号与填写账号不一致")

    user = db.get_user_by_phone(phone_norm)
    if not user:
        raise HTTPException(status_code=404, detail="该手机号尚未注册")
    uid = _safe_str(user.get("user_id"))
    if not uid:
        raise HTTPException(status_code=500, detail="bad user row")
    raw = db.get_user_by_id(uid)
    _assert_user_may_login(raw)
    pwd_h = db.hash_password(body.new_password)
    db.set_user_password_hash(uid, pwd_h)
    refreshed = db.get_user_by_id(uid)
    return {"code": 0, "message": "password updated", "user": db.user_public_dict(refreshed)}


@router.post("/auth/login/password")
async def auth_login_password(body: PasswordLoginRequest):
    acc = _safe_str(body.account)
    if not _valid_cn_mobile(acc) and not _valid_email(acc):
        raise HTTPException(status_code=400, detail="invalid phone or email format")
    user = db.login_password_user(account=acc, password_plain=body.password)
    if not user:
        raise HTTPException(status_code=401, detail="wrong account or password")
    uid = _safe_str(user.get("user_id"))
    raw = db.get_user_by_id(uid)
    _assert_user_may_login(raw)
    token = sign_user_token(user_id=uid)
    return {"code": 0, "token": token, "user": user}


@router.get("/users/me")
async def users_me(authorization: str = Header(default="", alias="Authorization")):
    user_id = require_user_id(authorization)
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="账号不存在或登录已失效，请退出后重新登录",
        )
    _assert_user_may_login(user)
    voices = db.list_user_voices(user_id)
    return {"code": 0, "user": db.user_public_dict(user), "voice_count": len(voices)}


@router.put("/users/me/profile")
async def users_me_profile_update(
    body: UserProfileUpdate,
    authorization: str = Header(default="", alias="Authorization"),
):
    user_id = require_user_id(authorization)
    user_row = db.get_user_by_id(user_id)
    _assert_user_may_login(user_row)
    updated = db.update_user_profile(user_id, body.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="账号不存在或登录已失效，请退出后重新登录",
        )
    return {"code": 0, "user": db.user_public_dict(updated)}


@router.get("/admin/stats")
async def admin_stats(
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    return {"code": 0, "stats": db.admin_stats_summary()}


@router.get("/admin/users")
async def admin_list_users(
    keyword: str = Query(default=""),
    is_active: int = Query(default=-1),
    blacklisted: int = Query(default=-1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    active = is_active if is_active in (0, 1) else None
    bl = blacklisted if blacklisted in (0, 1) else None
    total, items = db.list_users(
        keyword=keyword, is_active=active, blacklisted=bl, page=page, page_size=page_size
    )
    items = [db.admin_user_view(it) for it in items]
    _ = UserListResponse(total=total, page=page, page_size=page_size, items=items)
    return {"code": 0, "total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/admin/users/{user_id}")
async def admin_get_user(
    user_id: str,
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    uid = _safe_str(user_id)
    if not uid:
        raise HTTPException(status_code=400, detail="missing user_id")
    row = db.get_user_by_id(uid)
    if not row:
        raise HTTPException(status_code=404, detail="user not found")
    voices = db.list_user_voices(uid)
    return {
        "code": 0,
        "user": db.admin_user_view(row),
        "voice_count": len(voices),
    }


@router.patch("/admin/users/{user_id}")
async def admin_patch_user(
    user_id: str,
    body: AdminUserPatch,
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    uid = _safe_str(user_id)
    if not uid:
        raise HTTPException(status_code=400, detail="missing user_id")
    data = body.model_dump(exclude_none=True)
    updated = db.update_user_admin_fields(
        uid,
        is_active=data.get("is_active"),
        blacklisted=data.get("blacklisted"),
        ban_reason=data.get("ban_reason"),
        reader_stars=data.get("reader_stars"),
        reader_level=data.get("reader_level"),
        admin_note=data.get("admin_note"),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="user not found")
    return {"code": 0, "user": db.admin_user_view(updated)}


@router.get("/admin/users/{user_id}/companion")
async def admin_user_companion(
    user_id: str,
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    uid = _safe_str(user_id)
    if not uid:
        raise HTTPException(status_code=400, detail="missing user_id")
    snap: Dict[str, Any] = companion_admin.get_companion_snapshot(uid)
    return {"code": 0, "companion": snap}


@router.post("/admin/users/{user_id}/clear-companion-data")
async def admin_clear_companion_data(
    user_id: str,
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    uid = _safe_str(user_id)
    if not uid:
        raise HTTPException(status_code=400, detail="missing user_id")
    report = companion_admin.clear_user_companion_json_stores(uid)
    return {"code": 0, "cleared": report}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    uid = _safe_str(user_id)
    if not uid:
        raise HTTPException(status_code=400, detail="missing user_id")
    companion_admin.clear_user_companion_json_stores(uid)
    ok = db.delete_user_account(uid)
    if not ok:
        raise HTTPException(status_code=404, detail="user not found or already deleted")
    return {"code": 0, "deleted": True, "user_id": uid}


@router.get("/admin/users/{user_id}/voices")
async def admin_user_voices(
    user_id: str,
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    uid = _safe_str(user_id)
    if not uid:
        raise HTTPException(status_code=400, detail="missing user_id")
    voices = db.list_user_voices(uid)
    return {"code": 0, "user_id": uid, "voices": voices, "total": len(voices)}


@router.get("/admin/health")
async def admin_health(
    x_admin_api_key: str = Header(default="", alias="X-Admin-Api-Key"),
    authorization: str = Header(default="", alias="Authorization"),
):
    require_admin(x_admin_api_key, authorization)
    return {"ok": True, "module": "user_mgmt", "db_path": db.get_db_path()}


@router.post("/auth/dev/login")
async def auth_dev_login(request: Request):
    """
    Dev-only helper: by setting DEV_LOGIN_ENABLED=1, test without WeChat.
    同一手机号/邮箱多次登录应回到同一 user_id（与小程序端稳定 id + 库内按联系方式查找一致）。
    """
    if _safe_str(os.environ.get("DEV_LOGIN_ENABLED")) != "1":
        raise HTTPException(status_code=403, detail="dev login disabled")
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    phone = _safe_str(body.get("phone"))
    email = _safe_str(body.get("email"))
    user_id_req = _safe_str(body.get("user_id"))
    openid_req = _safe_str(body.get("openid"))
    unionid = _safe_str(body.get("unionid"))

    existing = None
    if phone:
        existing = db.get_user_by_phone(phone)
    if existing is None and email:
        existing = db.get_user_by_email(email)
    if existing is None and user_id_req:
        existing = db.get_user_by_id(user_id_req)

    if existing:
        uid = _safe_str(existing.get("user_id"))
        if uid:
            db.touch_user_last_login(uid)
            user = db.get_user_by_id(uid) or existing
            _assert_user_may_login(user if isinstance(user, dict) else existing)
            token = sign_user_token(user_id=uid)
            return {"code": 0, "token": token, "user": db.user_public_dict(user)}

    user_id = user_id_req or "dev_user"
    openid = openid_req or user_id
    user = db.upsert_user_from_wechat(user_id=user_id, openid=openid, unionid=unionid)
    _assert_user_may_login(user)
    token = sign_user_token(user_id=user_id)
    return {"code": 0, "token": token, "user": db.user_public_dict(user)}

