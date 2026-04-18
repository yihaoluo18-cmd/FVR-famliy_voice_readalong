from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CompanionState(str, Enum):
    idle = "idle"
    listening = "listening"
    thinking = "thinking"
    speaking = "speaking"


class SessionCreateRequest(BaseModel):
    user_id: str = Field(default="guest")
    persona_id: str = Field(default="default")


class SessionCreateResponse(BaseModel):
    ok: bool = True
    session_id: str
    user_id: str
    persona_id: str
    state: CompanionState = CompanionState.idle


class WakeupRequest(BaseModel):
    session_id: str
    wake_word: str = Field(default="你好小伴")


class WakeupResponse(BaseModel):
    ok: bool = True
    session_id: str
    accepted: bool = True
    state: CompanionState = CompanionState.listening
    hint: str = "已唤醒，请开始说话。"


class TextChatRequest(BaseModel):
    session_id: str
    text: str
    use_tts: bool = True
    metadata: Optional[Dict[str, Any]] = None


class VoiceChatRequest(BaseModel):
    session_id: str
    audio_url: str
    audio_format: str = "wav"
    use_tts: bool = True
    metadata: Optional[Dict[str, Any]] = None


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    ok: bool = True
    session_id: str
    state: CompanionState
    user_text: str
    assistant_text: str
    tts_audio_url: Optional[str] = None
    expression: str = "talk"
    animation: str = "talk"
    history: List[ChatTurn] = Field(default_factory=list)


class AvatarConfigResponse(BaseModel):
    ok: bool = True
    persona_id: str
    display_name: str
    model_url: str
    camera_preset: Optional[Dict[str, float]] = None
    tuning_source: Optional[str] = None
    idle_animation: str = "idle"
    talk_animation: str = "talk"
    react_animation: str = "react"


class AvatarTuningSaveRequest(BaseModel):
    user_id: str
    persona_id: str
    tuning: Dict[str, float]


class AvatarTuningSaveResponse(BaseModel):
    ok: bool = True
    user_id: str
    persona_id: str


class AvatarSceneConfigResponse(BaseModel):
    ok: bool = True
    persona_id: str
    scene_key: str
    display_name: str
    model_url: str
    camera_preset: Optional[Dict[str, float]] = None
    tuning_source: Optional[str] = None
    idle_animation: str = "idle"
    talk_animation: str = "talk"
    react_animation: str = "react"


class AvatarSceneTuningSaveRequest(BaseModel):
    user_id: str
    persona_id: str
    scene_key: str = Field(default="companion", description="home | companion | other scene id")
    tuning: Dict[str, float]


class AvatarSceneTuningSaveResponse(BaseModel):
    ok: bool = True
    user_id: str
    persona_id: str
    scene_key: str


class PetProgressReportRequest(BaseModel):
    user_id: str
    event_type: str
    payload: Optional[Dict[str, Any]] = None


class PetHatchClaimRequest(BaseModel):
    user_id: str


class PetStateResponse(BaseModel):
    ok: bool = True
    user_id: str
    pet_state: str
    read_task_count: int = 0
    checkin_streak_days: int = 0
    read_threshold: int = 0
    streak_threshold: int = 0
    is_hatch_ready: bool = False
    hatched_companions: List[str] = Field(default_factory=list)
    last_hatched_persona: str = ""
    last_hatched_at: str = ""
    updated_at: str = ""


class PetEggSlotItem(BaseModel):
    slot_index: int
    mascot_id: str
    label: str
    emoji: str
    rule: str
    ui_state: str
    progress_percent: int = 0
    progress_current: int = 0
    progress_need: int = 0
    hint: str = ""
    # 仅 ui_state=claimed 时由接口填充：是否仍为「幼儿蛋」；展示用当前形态档
    egg_model_active: Optional[bool] = None
    display_form_tier: Optional[int] = None


class PetEggStateResponse(BaseModel):
    ok: bool = True
    user_id: str
    slots: List[PetEggSlotItem]
    unlocked_mascot_ids: List[str] = Field(default_factory=list)
    has_ready_to_claim: bool = False
    read_lifetime: int = 0
    checkin_month_total: int = 0
    checkin_month_key: str = ""
    consecutive_checkin: int = 0
    updated_at: str = ""


class PetEggClaimRequest(BaseModel):
    user_id: str
    slot_index: int = Field(ge=0, le=9)


class PetCompanionActionRequest(BaseModel):
    user_id: str
    mascot_id: str
    action_type: str = Field(description="feed | clean | play")
    payload: Optional[Dict[str, Any]] = None


class PetCompanionReadXpRequest(BaseModel):
    user_id: str
    mascot_id: str
    payload: Optional[Dict[str, Any]] = None


class PetCompanionSetDisplayFormRequest(BaseModel):
    user_id: str
    mascot_id: str
    form_tier: int = Field(ge=1, le=3)


class PetCompanionSetViewTuningRequest(BaseModel):
    """伴宠详情页 3D：按形态（egg / tier1–3）保存镜头与缩放调参，便于换设备复用。"""

    user_id: str
    mascot_id: str
    form_key: str = Field(description="egg | tier1 | tier2 | tier3")
    # 视图作用域：用于区分 pet-detail 与首页等不同页面的调参，避免互相覆盖
    view_scope: str = Field(default="pet_detail", description="pet_detail | home | companion")
    tuning: Dict[str, Any] = Field(default_factory=dict)
    camera: Optional[Dict[str, Any]] = None
    # True：清除该形态下保存的手动相机（例如用户拖动滑条后 orbit 已失效）
    clear_manual_camera: bool = False


class PetCompanionStateResponse(BaseModel):
    ok: bool = True
    user_id: str
    mascot_id: str
    xp: int = 0
    level: int = 1
    stage: str = "tier1"
    next_stage_xp: int = 120
    growth_percent: int = 0
    stats: Dict[str, int] = Field(default_factory=dict)
    last_actions: Dict[str, str] = Field(default_factory=dict)
    updated_at: str = ""
    unlocked_form_tiers: List[int] = Field(default_factory=list)
    display_form_tier: int = 1
    form_tier_thresholds: Dict[str, int] = Field(default_factory=dict)
    # egg 幼儿孵化阶段：用于展示“孵化后第一个模型”（不计入三档成长 tier）
    egg_model_active: bool = False
    # 各形态 3D 展示调参（与小程序 pet-detail 存储后缀一致）
    form_view_tuning: Dict[str, Any] = Field(default_factory=dict)
    # 首页 3D 展示调参：与 pet-detail 分开存放，避免互相覆盖
    form_view_tuning_home: Dict[str, Any] = Field(default_factory=dict)
    # 伴读（AI 陪伴）页 3D 调参：与首页、宠详情分开存放
    form_view_tuning_companion: Dict[str, Any] = Field(default_factory=dict)

