from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str
    openid: str
    unionid: str = ""
    parent_name: str = ""
    baby_name: str = ""
    baby_age: str = ""
    avatar: str = ""
    phone: str = ""
    email: str = ""
    nickname: str = ""
    is_active: int = 1
    created_at: str = ""
    updated_at: str = ""
    last_login_at: str = ""


class UserProfileUpdate(BaseModel):
    parent_name: Optional[str] = None
    baby_name: Optional[str] = None
    baby_age: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    nickname: Optional[str] = None


class VoiceModelRecord(BaseModel):
    voice_id: str
    owner_user_id: str = ""
    display_name: str = ""
    gpt_path: str = ""
    sovits_path: str = ""
    scene: str = ""
    emotion: str = ""
    trained_at: str = ""
    model_type: str = ""
    owner_inferred: int = 0
    created_at: str = ""
    updated_at: str = ""


class UserListItem(BaseModel):
    user_id: str
    openid: str
    unionid: str = ""
    parent_name: str = ""
    baby_name: str = ""
    phone: str = ""
    email: str = ""
    nickname: str = ""
    is_active: int = 1
    blacklisted: int = 0
    reader_stars: int = 0
    reader_level: int = 1
    ban_reason: str = ""
    created_at: str = ""
    updated_at: str = ""
    last_login_at: str = ""
    voice_count: int = 0

    class Config:
        extra = "ignore"


class UserListResponse(BaseModel):
    total: int
    page: int
    page_size: int = Field(ge=1, le=200)
    items: List[UserListItem]


class WechatLoginRequest(BaseModel):
    code: str


class WechatBindPhoneLoginRequest(BaseModel):
    """微信登录须配合手机号快速验证：wx.login 的 code + getPhoneNumber 的 code。"""

    wx_code: str = Field(default="", max_length=256)
    phone_code: str = Field(default="", max_length=512)
    # 仅当服务端开启 DEV_LOGIN_ENABLED + PASSWORD_RESET_SKIP_WX_VERIFY 时使用，便于无外网联调
    dev_phone: str = Field(default="", max_length=20)
    # 仅本地联调可选：无外网时可传固定 dev_openid，避免每次生成不同微信身份
    dev_openid: str = Field(default="", max_length=128)


class WechatLoginResponse(BaseModel):
    token: str
    user: UserProfile


class PasswordRegisterRequest(BaseModel):
    """账号为大陆 11 位手机号或标准邮箱；密码至少 8 位且同时含字母与数字。"""

    account: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    baby_name: str = Field(default="", max_length=64)
    nickname: str = Field(default="", max_length=64)


class PasswordLoginRequest(BaseModel):
    account: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    """通过微信 getPhoneNumber 返回的 code 换绑校验手机号后重置密码（仅支持大陆手机号账号）。"""

    account: str = Field(min_length=3, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    phone_code: str = Field(min_length=4, max_length=512)


class AdminUserPatch(BaseModel):
    is_active: Optional[int] = None
    blacklisted: Optional[int] = None
    ban_reason: Optional[str] = None
    reader_stars: Optional[int] = None
    reader_level: Optional[int] = None
    admin_note: Optional[str] = None

