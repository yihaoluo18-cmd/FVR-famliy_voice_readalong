#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

BASE_URL = os.environ.get("QA_BASE_URL", "http://127.0.0.1:9880").rstrip("/")
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VOICE_LIBRARY_PATH = os.path.join(ROOT_DIR, "modules", "tts_backend", "data", "voice_library.json")
REPORT_DIR = os.path.join(ROOT_DIR, "train", "runtime", "qa_reports")
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Tuple[int, Dict[str, str], bytes]:
    url = f"{BASE_URL}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            return resp.getcode(), dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        body = e.read() if hasattr(e, "read") else b""
        return e.code, dict(e.headers.items()) if e.headers else {}, body


def _json_from_bytes(raw: bytes) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def _add_result(results, name: str, ok: bool, detail: Dict[str, Any]):
    results.append({"name": name, "ok": bool(ok), "detail": detail})


def _assert_http_json(
    results,
    name: str,
    method: str,
    path: str,
    expected_status: int,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
):
    status, headers, body = _request(method, path, payload=payload, timeout=timeout)
    body_json = _json_from_bytes(body)
    ok = status == expected_status
    _add_result(
        results,
        name,
        ok,
        {
            "status": status,
            "expected_status": expected_status,
            "path": path,
            "body": body_json or body.decode("utf-8", errors="replace")[:600],
            "content_type": headers.get("Content-Type") or headers.get("content-type", ""),
        },
    )
    return status, headers, body, body_json


def _assert_audio_url_served(results, name: str, audio_url: str, min_bytes: int = 8000):
    status, headers, body = _request("GET", audio_url, payload=None, timeout=40)
    ctype = (headers.get("Content-Type") or headers.get("content-type", "")).lower()
    ok = status == 200 and len(body) >= min_bytes and ("audio" in ctype or audio_url.endswith(".wav"))
    _add_result(
        results,
        name,
        ok,
        {
            "status": status,
            "audio_url": audio_url,
            "bytes": len(body),
            "content_type": ctype,
            "min_bytes": min_bytes,
        },
    )
    return ok


def _pick_user_voice(voices):
    for v in voices:
        if str(v.get("model_type") or "").strip().lower() == "user_trained":
            if v.get("gpt_path") and v.get("sovits_path"):
                return v
    return None


def _load_voice_library():
    if not os.path.exists(VOICE_LIBRARY_PATH):
        return {}
    try:
        with open(VOICE_LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main() -> int:
    started = time.time()
    results = []
    meta: Dict[str, Any] = {
        "base_url": BASE_URL,
        "started_at_epoch": started,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
    }

    # 1) voices list and builtin metadata
    _, _, _, data = _assert_http_json(results, "voices_list_200", "GET", "/voices", 200, timeout=20)
    voices = data.get("voices", []) if isinstance(data, dict) else []
    by_id = {str(v.get("voice_id")): v for v in voices if isinstance(v, dict)}

    for vid, gender in (("voice_001", "female"), ("voice_002", "male")):
        v = by_id.get(vid) or {}
        ok = (
            bool(v)
            and v.get("provider") == "qwen_tts"
            and v.get("is_builtin") is True
            and v.get("can_delete") is False
            and v.get("can_rename") is False
            and str(v.get("gender") or "").lower() == gender
        )
        _add_result(
            results,
            f"builtin_meta_{vid}",
            ok,
            {
                "voice_found": bool(v),
                "voice": v,
                "expected": {
                    "provider": "qwen_tts",
                    "is_builtin": True,
                    "can_delete": False,
                    "can_rename": False,
                    "gender": gender,
                },
            },
        )

    # 2) protected rename/delete
    _assert_http_json(
        results,
        "protect_rename_voice_001",
        "POST",
        "/voices/rename",
        400,
        payload={"voice_id": "voice_001", "name": "qa_try_rename"},
        timeout=20,
    )
    _assert_http_json(
        results,
        "protect_delete_voice_001",
        "DELETE",
        "/voices/voice_001",
        400,
        timeout=20,
    )

    # 3) base voice one-shot
    _, _, _, synth_data = _assert_http_json(
        results,
        "base_female_synthesize_oneshot",
        "POST",
        "/synthesize",
        200,
        payload={
            "voice_id": "voice_001",
            "text": "小熊在森林里找到了会发光的星星。",
            "text_language": "zh",
            "return_url": True,
        },
        timeout=220,
    )
    base_one_audio_url = str((synth_data or {}).get("audio_url") or "")
    if base_one_audio_url:
        _assert_audio_url_served(results, "base_female_oneshot_audio_served", base_one_audio_url)
    else:
        _add_result(
            results,
            "base_female_oneshot_audio_served",
            False,
            {"reason": "missing audio_url", "response": synth_data},
        )

    # 4) base voice buffered + merged
    _, _, _, buf_data = _assert_http_json(
        results,
        "base_male_synthesize_buffered",
        "POST",
        "/synthesize",
        200,
        payload={
            "voice_id": "voice_002",
            "text": "夜晚的风轻轻吹过草地，爸爸低声讲起了勇敢的小船长。",
            "text_language": "zh",
            "buffered": True,
        },
        timeout=260,
    )

    task_id = str((buf_data or {}).get("task_id") or "")
    merged_url = str((buf_data or {}).get("merged_url") or "")

    if task_id:
        _assert_http_json(
            results,
            "base_buffered_status",
            "GET",
            f"/synthesize/buffered/status?task_id={urllib.parse.quote(task_id)}",
            200,
            timeout=30,
        )

    if not merged_url and task_id:
        for _ in range(20):
            st, _, _, merged_data = _assert_http_json(
                results,
                "base_buffered_merged_poll",
                "GET",
                f"/synthesize/buffered/merged?task_id={urllib.parse.quote(task_id)}",
                200,
                timeout=40,
            )
            if st == 200 and isinstance(merged_data, dict) and merged_data.get("audio_url"):
                merged_url = str(merged_data.get("audio_url"))
                break
            time.sleep(0.4)

    if merged_url:
        _assert_audio_url_served(results, "base_buffered_merged_audio_served", merged_url)
    else:
        _add_result(
            results,
            "base_buffered_merged_audio_served",
            False,
            {"reason": "missing merged_url", "response": buf_data},
        )

    # 5) base voice stream route
    stream_status, stream_headers, stream_body = _request(
        "POST",
        "/synthesize/stream",
        payload={
            "voice_id": "voice_001",
            "text": "月亮升起来了，大家围着篝火听故事。",
            "text_language": "zh",
            "chunk_ms": 120,
        },
        timeout=260,
    )
    h_lower = {str(k).lower(): str(v) for k, v in (stream_headers or {}).items()}
    ctype = h_lower.get("content-type", "")
    ok_stream = (
        stream_status == 200
        and "audio/wav" in ctype.lower()
        and len(stream_body) >= 8000
        and bool(h_lower.get("x-qwen-voice"))
        and bool(h_lower.get("x-qwen-source"))
    )
    _add_result(
        results,
        "base_stream_audio",
        ok_stream,
        {
            "status": stream_status,
            "bytes": len(stream_body),
            "content_type": ctype,
            "x_qwen_voice": h_lower.get("x-qwen-voice", ""),
            "x_qwen_source": h_lower.get("x-qwen-source", ""),
        },
    )

    # 6) legacy stream alias
    legacy_status, legacy_headers, legacy_body = _request(
        "POST",
        "/synthesize_stream",
        payload={
            "voice_id": "voice_001",
            "text": "这是一段兼容路由验证。",
            "text_language": "zh",
            "chunk_ms": 120,
        },
        timeout=260,
    )
    legacy_ctype = (legacy_headers.get("Content-Type") or legacy_headers.get("content-type") or "").lower()
    _add_result(
        results,
        "legacy_stream_alias",
        legacy_status == 200 and "audio" in legacy_ctype and len(legacy_body) >= 6000,
        {
            "status": legacy_status,
            "bytes": len(legacy_body),
            "content_type": legacy_ctype,
        },
    )

    # 7) regression: user-trained voice one-shot + stream
    user_voice = _pick_user_voice(voices)
    if user_voice:
        uv_id = str(user_voice.get("voice_id"))
        meta["regression_user_voice_id"] = uv_id

        _, _, _, uv_synth = _assert_http_json(
            results,
            "user_voice_synthesize_oneshot",
            "POST",
            "/synthesize",
            200,
            payload={
                "voice_id": uv_id,
                "text": "这是对已有训练音色的回归验证。",
                "text_language": "zh",
                "return_url": True,
            },
            timeout=320,
        )
        uv_audio_url = str((uv_synth or {}).get("audio_url") or "")
        if uv_audio_url:
            _assert_audio_url_served(results, "user_voice_oneshot_audio_served", uv_audio_url)
        else:
            _add_result(
                results,
                "user_voice_oneshot_audio_served",
                False,
                {"reason": "missing audio_url", "response": uv_synth, "voice_id": uv_id},
            )

        uv_stream_status, uv_stream_headers, uv_stream_body = _request(
            "POST",
            "/synthesize/stream",
            payload={
                "voice_id": uv_id,
                "text": "这是已有训练音色流式回归验证。",
                "text_language": "zh",
                "chunk_ms": 120,
            },
            timeout=320,
        )
        uv_stream_ctype = (
            uv_stream_headers.get("Content-Type") or uv_stream_headers.get("content-type") or ""
        ).lower()
        _add_result(
            results,
            "user_voice_stream_audio",
            uv_stream_status == 200 and "audio" in uv_stream_ctype and len(uv_stream_body) >= 6000,
            {
                "voice_id": uv_id,
                "status": uv_stream_status,
                "bytes": len(uv_stream_body),
                "content_type": uv_stream_ctype,
            },
        )
    else:
        _add_result(
            results,
            "user_voice_regression_present",
            False,
            {"reason": "no eligible user_trained voice found in /voices"},
        )

    # 8) optional direct ref mode regression (if user voice has refs in voice_library.json)
    voice_library = _load_voice_library()
    direct_ref_done = False
    if user_voice:
        uv_id = str(user_voice.get("voice_id"))
        info = voice_library.get(uv_id) if isinstance(voice_library, dict) else None
        if isinstance(info, dict):
            ref_audio = str(info.get("ref_audio_path") or "").strip()
            prompt_text = str(info.get("ref_text") or "").strip()
            gpt_path = str(info.get("gpt_path") or "").strip()
            sovits_path = str(info.get("sovits_path") or "").strip()
            if ref_audio and prompt_text and gpt_path and sovits_path:
                direct_ref_done = True
                _, _, _, direct_data = _assert_http_json(
                    results,
                    "direct_ref_mode_synthesize",
                    "POST",
                    "/synthesize",
                    200,
                    payload={
                        "refer_wav_path": ref_audio,
                        "prompt_text": prompt_text[:24],
                        "prompt_language": "中文",
                        "gpt_path": gpt_path,
                        "sovits_path": sovits_path,
                        "text": "这是参考音频直传模式回归测试。",
                        "text_language": "zh",
                        "return_url": True,
                    },
                    timeout=320,
                )
                direct_url = str((direct_data or {}).get("audio_url") or "")
                if direct_url:
                    _assert_audio_url_served(results, "direct_ref_mode_audio_served", direct_url)
                else:
                    _add_result(
                        results,
                        "direct_ref_mode_audio_served",
                        False,
                        {"reason": "missing audio_url", "response": direct_data},
                    )

    if not direct_ref_done:
        _add_result(
            results,
            "direct_ref_mode_skipped",
            True,
            {"reason": "no complete ref/gpt/sovits metadata available for selected user voice"},
        )

    # summary
    total = len(results)
    passed = sum(1 for r in results if r.get("ok"))
    failed = total - passed
    elapsed = round(time.time() - started, 3)

    summary = {
        "meta": meta,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "elapsed_sec": elapsed,
            "quality_gate": "PASS" if failed == 0 else "FAIL",
        },
        "results": results,
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    report_path = os.path.join(REPORT_DIR, f"full_flow_qa_{ts}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary["summary"], ensure_ascii=False))
    print(f"report_path={report_path}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
