from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .models import (
    AvatarConfigResponse,
    AvatarSceneConfigResponse,
    AvatarSceneTuningSaveRequest,
    AvatarSceneTuningSaveResponse,
    AvatarTuningSaveRequest,
    AvatarTuningSaveResponse,
    ChatResponse,
    ChatTurn,
    SessionCreateRequest,
    SessionCreateResponse,
    TextChatRequest,
    PetEggClaimRequest,
    PetCompanionActionRequest,
    PetCompanionReadXpRequest,
    PetCompanionSetDisplayFormRequest,
    PetCompanionSetViewTuningRequest,
    PetCompanionStateResponse,
    PetEggStateResponse,
    PetEggSlotItem,
    PetHatchClaimRequest,
    PetProgressReportRequest,
    PetStateResponse,
    VoiceChatRequest,
    WakeupRequest,
    WakeupResponse,
)
from .pet_companion import PetCompanionService
from .pet_egg import PetEggService
from .pet_growth import PetGrowthService
from .services import CompanionEngine

router = APIRouter(prefix="/ar_companion", tags=["ar_companion"])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
engine = CompanionEngine()
pet_growth_service = PetGrowthService(store_path=PROJECT_ROOT / "output" / "ar_companion_pet_growth_store.json")
pet_egg_service = PetEggService(store_path=PROJECT_ROOT / "output" / "ar_companion_pet_egg_store.json")
pet_companion_service = PetCompanionService(
    store_path=PROJECT_ROOT / "output" / "ar_companion_pet_companion_store.json",
    egg_service=pet_egg_service,
)
UPLOAD_DIR = PROJECT_ROOT / "output" / "ar_companion_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _classify_provider_account_issue(err_text: str) -> str:
    lower = str(err_text or "").lower()
    if not lower:
        return ""
    if any(k in lower for k in ["provider_arrearage", "arrearage", "insufficient_balance", "quota", "欠费", "余额不足"]):
        return "provider_arrearage"
    if any(
        k in lower
        for k in [
            "provider_auth_error",
            "invalid api key",
            "api key",
            "apikey",
            "unauthorized",
            "authentication",
            "forbidden",
            "鉴权",
            "密钥",
            "accesskey",
        ]
    ):
        return "provider_auth_error"
    return ""


def _build_companion_chat_error(exc: Exception):
    raw = str(exc or "").strip()
    lower = raw.lower()
    reason = ""
    if "provider_arrearage" in lower:
        reason = "provider_arrearage"
    elif "provider_auth_error" in lower:
        reason = "provider_auth_error"
    else:
        reason = _classify_provider_account_issue(raw)

    if reason == "provider_arrearage":
        return 503, {
            "reason": "provider_arrearage",
            "message": "当前 AI 服务账号欠费，伴宠暂时无法回复，请充值后重试。",
            "detail": raw[:320],
        }
    if reason == "provider_auth_error":
        return 503, {
            "reason": "provider_auth_error",
            "message": "当前 AI 服务密钥或鉴权异常，伴宠暂时无法回复，请检查配置。",
            "detail": raw[:320],
        }

    return 503, {
        "reason": "companion_llm_unavailable",
        "message": "伴宠 AI 暂时不可用，请稍后重试。",
        "detail": raw[:320] or "unknown",
    }


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "module": "ar_companion", "status": "healthy"}


@router.post("/session/create", response_model=SessionCreateResponse)
async def create_session(body: SessionCreateRequest) -> SessionCreateResponse:
    memory = engine.create_session(user_id=body.user_id, persona_id=body.persona_id)
    return SessionCreateResponse(
        session_id=memory.session_id,
        user_id=memory.user_id,
        persona_id=memory.persona_id,
        state=memory.state,
    )


@router.post("/session/wakeup", response_model=WakeupResponse)
async def wakeup_session(body: WakeupRequest) -> WakeupResponse:
    try:
        memory = engine.wakeup(session_id=body.session_id, wake_word=body.wake_word)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WakeupResponse(session_id=memory.session_id, state=memory.state)


@router.post("/chat/text", response_model=ChatResponse)
async def chat_text(body: TextChatRequest) -> ChatResponse:
    try:
        result = engine.chat_by_text(
            session_id=body.session_id,
            text=body.text,
            use_tts=body.use_tts,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        status, detail = _build_companion_chat_error(exc)
        raise HTTPException(status_code=status, detail=detail) from exc
    return ChatResponse(
        session_id=body.session_id,
        state=result["state"],
        user_text=result["user_text"],
        assistant_text=result["assistant_text"],
        tts_audio_url=result["tts_audio_url"],
        expression="talk",
        animation="talk",
        history=[ChatTurn(**x) for x in result["history"]],
    )


@router.post("/chat/voice_url", response_model=ChatResponse)
async def chat_voice_url(body: VoiceChatRequest) -> ChatResponse:
    try:
        result = engine.chat_by_voice_url(
            session_id=body.session_id,
            audio_url=body.audio_url,
            audio_format=body.audio_format,
            use_tts=body.use_tts,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        status, detail = _build_companion_chat_error(exc)
        raise HTTPException(status_code=status, detail=detail) from exc
    return ChatResponse(
        session_id=body.session_id,
        state=result["state"],
        user_text=result["user_text"],
        assistant_text=result["assistant_text"],
        tts_audio_url=result["tts_audio_url"],
        expression="talk",
        animation="talk",
        history=[ChatTurn(**x) for x in result["history"]],
    )


@router.get("/avatar/config", response_model=AvatarConfigResponse)
async def avatar_config(persona_id: str = "default", user_id: str = "") -> AvatarConfigResponse:
    data = engine.avatar_config(persona_id=persona_id, user_id=user_id or None)
    return AvatarConfigResponse(**data)


@router.get("/avatar/scene_config", response_model=AvatarSceneConfigResponse)
async def avatar_scene_config(persona_id: str = "default", user_id: str = "", scene_key: str = "companion") -> AvatarSceneConfigResponse:
    data = engine.avatar_scene_config(persona_id=persona_id, user_id=user_id or None, scene_key=scene_key)
    return AvatarSceneConfigResponse(**data)


@router.post("/avatar/tuning/save", response_model=AvatarTuningSaveResponse)
async def avatar_tuning_save(body: AvatarTuningSaveRequest) -> AvatarTuningSaveResponse:
    try:
        engine.save_user_tuning(user_id=body.user_id, persona_id=body.persona_id, tuning=body.tuning)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"save tuning failed: {exc}") from exc
    return AvatarTuningSaveResponse(user_id=body.user_id, persona_id=body.persona_id)


@router.post("/avatar/scene_tuning/save", response_model=AvatarSceneTuningSaveResponse)
async def avatar_scene_tuning_save(body: AvatarSceneTuningSaveRequest) -> AvatarSceneTuningSaveResponse:
    try:
        engine.save_user_scene_tuning(
            user_id=body.user_id,
            persona_id=body.persona_id,
            scene_key=body.scene_key or "companion",
            tuning=body.tuning,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"save scene tuning failed: {exc}") from exc
    return AvatarSceneTuningSaveResponse(
        user_id=body.user_id,
        persona_id=body.persona_id,
        scene_key=body.scene_key or "companion",
    )


@router.get("/pet/state", response_model=PetStateResponse)
async def pet_state(user_id: str) -> PetStateResponse:
    try:
        data = pet_growth_service.get_state(user_id=user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"get pet state failed: {exc}") from exc
    return PetStateResponse(**data)


@router.post("/pet/progress/report", response_model=PetStateResponse)
async def pet_progress_report(body: PetProgressReportRequest) -> PetStateResponse:
    try:
        data = pet_growth_service.report_progress(
            user_id=body.user_id,
            event_type=body.event_type,
            payload=body.payload or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"report pet progress failed: {exc}") from exc
    return PetStateResponse(**data)


@router.post("/pet/hatch/claim", response_model=PetStateResponse)
async def pet_hatch_claim(body: PetHatchClaimRequest) -> PetStateResponse:
    try:
        data = pet_growth_service.claim_hatch(user_id=body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"claim pet hatch failed: {exc}") from exc
    return PetStateResponse(**data)


def _enrich_egg_slots_with_companion(data: dict) -> dict:
    """已领取槽位附带伴宠成长状态，供乐园页区分静态蛋 / 已孵化形态模型。"""
    uid = str(data.get("user_id") or "").strip()
    if not uid:
        return data
    slots = data.get("slots")
    if not isinstance(slots, list):
        return data
    for s in slots:
        if not isinstance(s, dict) or s.get("ui_state") != "claimed":
            continue
        mid = str(s.get("mascot_id") or "").strip()
        if not mid:
            continue
        try:
            cs = pet_companion_service.get_state(user_id=uid, mascot_id=mid)
            s["egg_model_active"] = bool(cs.get("egg_model_active"))
            s["display_form_tier"] = int(cs.get("display_form_tier") or 1)
        except Exception:
            s["egg_model_active"] = False
            s["display_form_tier"] = 1
    return data


def _egg_state_response(data: dict) -> PetEggStateResponse:
    slots = [PetEggSlotItem(**x) for x in (data.get("slots") or [])]
    return PetEggStateResponse(
        user_id=str(data.get("user_id") or ""),
        slots=slots,
        unlocked_mascot_ids=list(data.get("unlocked_mascot_ids") or []),
        has_ready_to_claim=bool(data.get("has_ready_to_claim")),
        read_lifetime=int(data.get("read_lifetime") or 0),
        checkin_month_total=int(data.get("checkin_month_total") or 0),
        checkin_month_key=str(data.get("checkin_month_key") or ""),
        consecutive_checkin=int(data.get("consecutive_checkin") or 0),
        updated_at=str(data.get("updated_at") or ""),
    )


@router.get("/pet/egg/state", response_model=PetEggStateResponse)
async def pet_egg_state(user_id: str) -> PetEggStateResponse:
    try:
        data = pet_egg_service.get_state(user_id=user_id)
        _enrich_egg_slots_with_companion(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"get pet egg state failed: {exc}") from exc
    return _egg_state_response(data)


@router.post("/pet/egg/progress/report", response_model=PetEggStateResponse)
async def pet_egg_progress_report(body: PetProgressReportRequest) -> PetEggStateResponse:
    try:
        data = pet_egg_service.report_progress(
            user_id=body.user_id,
            event_type=body.event_type,
            payload=body.payload or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pet egg report failed: {exc}") from exc
    _enrich_egg_slots_with_companion(data)
    return _egg_state_response(data)


@router.post("/pet/egg/claim", response_model=PetEggStateResponse)
async def pet_egg_claim(body: PetEggClaimRequest) -> PetEggStateResponse:
    try:
        data = pet_egg_service.claim_slot(user_id=body.user_id, slot_index=body.slot_index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pet egg claim failed: {exc}") from exc
    _enrich_egg_slots_with_companion(data)
    return _egg_state_response(data)


@router.get("/pet/companion/state", response_model=PetCompanionStateResponse)
async def pet_companion_state(user_id: str, mascot_id: str) -> PetCompanionStateResponse:
    try:
        data = pet_companion_service.get_state(user_id=user_id, mascot_id=mascot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pet companion state failed: {exc}") from exc
    return PetCompanionStateResponse(**data)


@router.post("/pet/companion/action", response_model=PetCompanionStateResponse)
async def pet_companion_action(body: PetCompanionActionRequest) -> PetCompanionStateResponse:
    try:
        data = pet_companion_service.apply_action(
            user_id=body.user_id,
            mascot_id=body.mascot_id,
            action_type=body.action_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pet companion action failed: {exc}") from exc
    return PetCompanionStateResponse(**data)


@router.post("/pet/companion/read_xp", response_model=PetCompanionStateResponse)
async def pet_companion_read_xp(body: PetCompanionReadXpRequest) -> PetCompanionStateResponse:
    try:
        data = pet_companion_service.report_read_progress(
            user_id=body.user_id,
            mascot_id=body.mascot_id,
            payload=body.payload or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pet companion read_xp failed: {exc}") from exc
    return PetCompanionStateResponse(**data)


@router.post("/pet/companion/set_display_form", response_model=PetCompanionStateResponse)
async def pet_companion_set_display_form(body: PetCompanionSetDisplayFormRequest) -> PetCompanionStateResponse:
    try:
        data = pet_companion_service.set_display_form(
            user_id=body.user_id,
            mascot_id=body.mascot_id,
            form_tier=body.form_tier,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pet companion set_display_form failed: {exc}") from exc
    return PetCompanionStateResponse(**data)


@router.post("/pet/companion/set_view_tuning", response_model=PetCompanionStateResponse)
async def pet_companion_set_view_tuning(body: PetCompanionSetViewTuningRequest) -> PetCompanionStateResponse:
    try:
        data = pet_companion_service.set_view_tuning(
            user_id=body.user_id,
            mascot_id=body.mascot_id,
            form_key=body.form_key,
            view_scope=body.view_scope,
            tuning=body.tuning,
            camera=body.camera,
            clear_manual_camera=bool(body.clear_manual_camera),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pet companion set_view_tuning failed: {exc}") from exc
    return PetCompanionStateResponse(**data)


@router.get("/assets/{asset_path:path}")
async def companion_assets(asset_path: str):
    safe_path = Path(asset_path)
    if safe_path.is_absolute() or ".." in safe_path.parts:
        raise HTTPException(status_code=400, detail="invalid asset path")

    asset_root = PROJECT_ROOT / "animal"
    file_path = (asset_root / safe_path).resolve()
    if not str(file_path).startswith(str(asset_root.resolve())):
        raise HTTPException(status_code=400, detail="invalid asset path")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="asset missing")

    ext = file_path.suffix.lower()
    if ext == ".glb":
        media_type = "model/gltf-binary"
    elif ext == ".gltf":
        media_type = "model/gltf+json"
    elif ext == ".bin":
        media_type = "application/octet-stream"
    elif ext in {".png"}:
        media_type = "image/png"
    elif ext in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif ext in {".webp"}:
        media_type = "image/webp"
    else:
        media_type = "application/octet-stream"
    return FileResponse(path=str(file_path), media_type=media_type, filename=file_path.name)


@router.post("/chat/voice_upload", response_model=ChatResponse)
async def chat_voice_upload(
    session_id: str = Form(...),
    use_tts: bool = Form(True),
    audio_format: str = Form("mp3"),
    audio_file: UploadFile = File(...),
) -> ChatResponse:
    try:
        suffix = Path(audio_file.filename or "").suffix.lower() or f".{audio_format.strip().lower() or 'mp3'}"
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        fname = f"{uuid.uuid4().hex}{suffix}"
        save_path = UPLOAD_DIR / fname
        with open(save_path, "wb") as fw:
            fw.write(await audio_file.read())

        result = engine.chat_by_voice_url(
            session_id=session_id,
            audio_url=str(save_path),
            audio_format=suffix.lstrip("."),
            use_tts=bool(use_tts),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        status, detail = _build_companion_chat_error(exc)
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"voice upload failed: {exc}") from exc

    return ChatResponse(
        session_id=session_id,
        state=result["state"],
        user_text=result["user_text"],
        assistant_text=result["assistant_text"],
        tts_audio_url=result["tts_audio_url"],
        expression="talk",
        animation="talk",
        history=[ChatTurn(**x) for x in result["history"]],
    )

