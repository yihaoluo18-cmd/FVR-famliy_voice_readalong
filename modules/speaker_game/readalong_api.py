#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
import wave
import io
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
import numpy as np
from PIL import Image
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from modules.ai_runtime import load_ai_runtime_config

app = FastAPI()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
READALONG_LIBRARY_DIR = PROJECT_ROOT / "modules" / "books_library" / "readalong_library"
BOOKS_DIR = READALONG_LIBRARY_DIR / "books"

AI_RUNTIME = load_ai_runtime_config()
SAFETY_AI_API_KEY = AI_RUNTIME.api_key
SAFETY_AI_BASE_URL = AI_RUNTIME.base_url
SAFETY_AI_MODEL = AI_RUNTIME.model_for("readalong_eval")
SAFETY_AI_VISION_MODEL = AI_RUNTIME.model_for("vision_caption")
SAFETY_AI_ASR_MODEL = AI_RUNTIME.model_for("readalong_asr")
SAFETY_AI_TTS_MODEL = AI_RUNTIME.model_for("readalong_tts")
SAFETY_AI_TTS_VOICE = os.environ.get("AI_TTS_VOICE", "Cherry").strip() or "Cherry"
SAFETY_AI_TIMEOUT_SEC = AI_RUNTIME.timeout_sec

_AUDIO_CACHE: Dict[str, Dict[str, Any]] = {}
_AUDIO_CACHE_MAX = 128
_AUDIO_CACHE_TTL_SEC = 30 * 60

_STOP_CHARS = set("的是了在我你他她它和与及并呢啊吗吧就也都很再又还把被给向到对跟着")
_UNCIVIL_TERMS = [
    "傻逼", "煞笔", "脑残", "滚", "去死", "废物", "蠢货", "混蛋", "王八蛋", "妈的", "操", "草泥马", "你妈", "白痴", "笨蛋",
]

_COLORING_EVAL_SYSTEM_PROMPT = (
    "你是一个严格但鼓励的儿童美术老师，擅长评价儿童涂色作品。"
    "你必须输出严格 JSON（不要输出多余文字），并确保分数稳定、可解释。"
)

_COLORING_EVAL_USER_PROMPT = """
请评价这张儿童涂色作品，并按以下维度打分（总分 0-100 的整数）：
1) 颜色搭配是否协调漂亮（0-40）
2) 是否涂出线条外（0-25）
3) 涂色是否饱满均匀（0-20）
4) 是否有明显遗漏区域（0-15）

输出必须是严格 JSON，字段如下：
{
  "ok": true,
  "accuracy": <0-100 number>,        // 总分
  "stars": <1-5 int>,                // 1-5 星，按总分映射：0-59=1星，60-69=2星，70-79=3星，80-89=4星，90-100=5星
  "feedback": "<给孩子的鼓励+建议，中文，1句鼓励 + 2-4条可执行建议>",
  "source": "coloring_llm"
}

要求：
- 语言要孩子能懂，语气温暖鼓励，避免批评。
- 建议要具体可执行（例如“把边边再慢慢涂满一点点”），不要空泛。
- 如果图片看不清或无法判断，也要给出合理的保守分数与建议，不要返回空。
""".strip()


def _extract_first_json_object(text: str) -> Dict[str, Any] | None:
    s = str(text or "").strip()
    if not s:
        return None
    # 尝试直接解析
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # 尝试提取第一个 {...}
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _score_to_stars(score_0_100: float) -> int:
    s = float(score_0_100)
    if s >= 90:
        return 5
    if s >= 80:
        return 4
    if s >= 70:
        return 3
    if s >= 60:
        return 2
    return 1


def _heuristic_coloring_evaluate(image_bytes: bytes) -> Dict[str, Any]:
    """
    本地离线兜底打分（不依赖外部模型/密钥），输出与前端兼容的 {accuracy, stars, feedback}。
    目标：稳定可用，而不是“视觉理解最强”。
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")  # type: ignore[name-defined]
    except Exception:
        # 兜底：无法解析图像
        score = 70.0
        stars = _score_to_stars(score)
        fb = "我看到你很认真！如果图片有点看不清也没关系，继续慢慢涂，把每个小区域都涂满会更漂亮。"
        return {"accuracy": score, "stars": stars, "feedback": fb, "source": "coloring_local_heuristic"}

    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    if h < 8 or w < 8:
        score = 70.0
        stars = _score_to_stars(score)
        fb = "你画得很努力！可以把颜色再涂得更满一点点，边边也慢慢补齐，就更棒啦。"
        return {"accuracy": score, "stars": stars, "feedback": fb, "source": "coloring_local_heuristic"}

    # 1) “涂色覆盖度”估计：非白像素比例（排除近白背景）
    near_white = (arr[..., 0] > 245) & (arr[..., 1] > 245) & (arr[..., 2] > 245)
    non_white_ratio = float(1.0 - near_white.mean())

    # 2) “颜色丰富度”估计：下采样后聚类到 64 桶的颜色占用数
    small = arr[:: max(1, h // 160), :: max(1, w // 160), :].reshape(-1, 3)
    q = (small // 32).astype(np.int32)  # 0..7
    codes = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    uniq = int(len(np.unique(codes)))
    uniq_norm = min(1.0, max(0.0, (uniq - 6) / 20.0))  # 6~26 映射到 0~1

    # 3) “涂色均匀度”估计：色彩饱和度的稳定性
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = (mx - mn) / (mx + 1e-6)
    sat_mean = float(np.clip(sat.mean(), 0.0, 1.0))
    sat_std = float(np.clip(sat.std(), 0.0, 1.0))

    # 4) “线外涂色”难以精确判定：用边缘附近颜色变化作为弱指标（越剧烈越可能涂到线外/抖动）
    # 用简单的梯度近似，不依赖 cv2
    gx = np.abs(arr[:, 1:, :] - arr[:, :-1, :]).mean()
    gy = np.abs(arr[1:, :, :] - arr[:-1, :, :]).mean()
    edge_activity = float(np.clip((gx + gy) / 60.0, 0.0, 1.0))  # 经验归一化

    # 分项评分（稳定、可解释）
    color_score = 40.0 * (0.35 * sat_mean + 0.65 * uniq_norm)  # 颜色搭配：饱和+色域
    overflow_score = 25.0 * (1.0 - 0.55 * edge_activity)       # 线外：边缘活动越高扣分
    uniform_score = 20.0 * (1.0 - min(1.0, sat_std * 1.8))     # 均匀：std 越大越扣分
    complete_score = 15.0 * np.clip((non_white_ratio - 0.06) / 0.40, 0.0, 1.0)  # 覆盖：>=~46% 接近满分

    score = float(np.clip(color_score + overflow_score + uniform_score + complete_score, 0.0, 100.0))
    score_i = float(int(round(score)))
    stars = _score_to_stars(score_i)

    # 生成建议（温暖+可执行）
    praise = "你画得真棒！" if score_i >= 85 else ("你画得很认真！" if score_i >= 70 else "你很勇敢地在涂色！")
    tips = []
    if complete_score < 9:
        tips.append("把小空白再补一补，慢慢把每个区域都涂满。")
    if uniform_score < 12:
        tips.append("同一块区域尽量用一个颜色慢慢涂匀，会更整齐。")
    if overflow_score < 15:
        tips.append("沿着黑线慢慢涂，快到边边时放慢一点点，就不容易涂出去。")
    if color_score < 24:
        tips.append("可以试试 2-3 种颜色搭配：主色 + 辅色 + 小点缀，会更漂亮。")
    if not tips:
        tips = ["继续保持！你可以尝试给不同部位选更有趣的颜色，让作品更有个性。"]
    tips = tips[:4]

    fb = praise + " " + " ".join([f"{i+1}){t}" for i, t in enumerate(tips)])
    return {"accuracy": score_i, "stars": stars, "feedback": fb, "source": "coloring_local_heuristic"}


async def _ai_coloring_evaluate_image(image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    data_url = "data:%s;base64,%s" % (mime_type, base64.b64encode(image_bytes).decode("utf-8"))
    url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if str(SAFETY_AI_API_KEY or "").strip():
        headers["Authorization"] = f"Bearer {str(SAFETY_AI_API_KEY).strip()}"
    payload = {
        "model": SAFETY_AI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _COLORING_EVAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _COLORING_EVAL_USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    async with httpx.AsyncClient(timeout=SAFETY_AI_TIMEOUT_SEC, trust_env=False) as client:
        try:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        except Exception:
            # 没有可用的视觉大模型/密钥时，用本地启发式打分保证可用
            h = _heuristic_coloring_evaluate(image_bytes)
            return {
                "ok": True,
                "accuracy": float(h["accuracy"]),
                "stars": int(h["stars"]),
                "feedback": str(h["feedback"]),
                "feedback_text": str(h["feedback"]),
                "transcript": "",
                "recognized_text": "",
                "feedback_audio_url": "",
                "source": str(h.get("source") or "coloring_local_heuristic"),
            }
    text = _extract_chat_content_text(data)
    obj = _extract_first_json_object(text)
    if not obj:
        # 兜底：给一个保守但不空的结果
        return {
            "ok": True,
            "accuracy": 75.0,
            "stars": 3,
            "feedback": "你的作品很可爱！可以再慢慢把边边涂满一点点，颜色再多试试两三种搭配，会更漂亮。",
            "source": "coloring_fallback",
        }
    # 规范化
    raw_score = obj.get("accuracy", obj.get("score", obj.get("total", 0)))
    try:
        score = float(raw_score)
    except Exception:
        score = 0.0
    score = max(0.0, min(100.0, score))
    stars = obj.get("stars")
    try:
        stars_i = int(stars)
    except Exception:
        stars_i = _score_to_stars(score)
    stars_i = max(1, min(5, stars_i))
    feedback = str(obj.get("feedback") or obj.get("comment") or "").strip()
    if not feedback:
        feedback = "你画得很认真！可以把小空白再补一补，沿着线条慢慢涂，会更整齐更漂亮。"
    return {
        "ok": True,
        "accuracy": float(round(score, 2)),
        "stars": int(stars_i),
        "feedback": feedback,
        "feedback_text": feedback,
        "transcript": "",
        "recognized_text": "",
        "feedback_audio_url": "",
        "source": str(obj.get("source") or "coloring_llm"),
        "raw": obj,
    }


def _safe_load_json(fp: Path) -> Dict[str, Any] | None:
    try:
        with fp.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _list_books() -> List[Dict[str, str]]:
    if not BOOKS_DIR.is_dir():
        return []

    out: List[Dict[str, str]] = []
    for fp in sorted(BOOKS_DIR.glob("*.json")):
        obj = _safe_load_json(fp)
        if not obj:
            continue
        book_id = str(obj.get("id") or fp.stem)
        title = str(obj.get("title") or book_id)
        out.append({"id": book_id, "title": title})
    return out


def _get_book(book_id: str) -> Dict[str, Any] | None:
    if not BOOKS_DIR.is_dir():
        return None
    book_id = str(book_id or "").strip()
    if not book_id:
        return None

    fp = BOOKS_DIR / f"{book_id}.json"
    if fp.exists():
        obj = _safe_load_json(fp)
        if obj:
            return obj

    for candidate in BOOKS_DIR.glob("*.json"):
        obj = _safe_load_json(candidate)
        if not obj:
            continue
        cid = str(obj.get("id") or candidate.stem).strip()
        if cid == book_id:
            return obj
    return None


def _accuracy_to_stars(accuracy: float) -> int:
    a = float(accuracy)
    if a >= 90:
        return 5
    if a >= 80:
        return 4
    if a >= 70:
        return 3
    if a >= 60:
        return 2
    return 1


def _normalize_text(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[，。！？；：、,.!?;:\"'“”‘’（）()\[\]{}<>《》-]", "", s)
    return s


def _sequence_ratio(expected_text: str, actual_text: str) -> float:
    exp = _normalize_text(expected_text)
    act = _normalize_text(actual_text)
    if not exp or not act:
        return 0.0
    return max(0.0, min(100.0, SequenceMatcher(None, exp, act).ratio() * 100.0))


def _lcs_ratio(expected_text: str, actual_text: str) -> float:
    exp = _normalize_text(expected_text)
    act = _normalize_text(actual_text)
    if not exp or not act:
        return 0.0
    n, m = len(exp), len(act)
    dp = [0] * (m + 1)
    for i in range(1, n + 1):
        prev = 0
        for j in range(1, m + 1):
            cur = dp[j]
            if exp[i - 1] == act[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = cur
    return (dp[m] / max(1, n)) * 100.0


def _extract_keywords(expected_text: str) -> List[str]:
    exp = _normalize_text(expected_text)
    if not exp:
        return []

    keys: List[str] = []
    chunks = [x for x in re.split(r"[，。！？；：、,.!?;\s]+", str(expected_text or "")) if x]
    if not chunks:
        chunks = [exp]

    for c in chunks:
        cc = _normalize_text(c)
        if len(cc) >= 2:
            keys.append(cc)
        for n in (2, 3):
            for i in range(0, max(0, len(cc) - n + 1)):
                gram = cc[i : i + n]
                if len(gram) == n and not all(ch in _STOP_CHARS for ch in gram):
                    keys.append(gram)

    dedup: List[str] = []
    seen = set()
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            dedup.append(k)
    return dedup[:18]


def _keyword_hit_ratio(expected_text: str, actual_text: str) -> Tuple[float, List[str], List[str]]:
    act = _normalize_text(actual_text)
    kws = _extract_keywords(expected_text)
    if not kws or not act:
        return 0.0, kws, []

    hit = [k for k in kws if k in act]
    ratio = (len(hit) / max(1, len(kws))) * 100.0
    return ratio, kws, hit


def _strict_scoring(expected_text: str, actual_text: str) -> Dict[str, Any]:
    seq = _sequence_ratio(expected_text, actual_text)
    order_ratio = _lcs_ratio(expected_text, actual_text)
    kw_ratio, kws, kw_hit = _keyword_hit_ratio(expected_text, actual_text)

    accuracy = 0.45 * order_ratio + 0.35 * kw_ratio + 0.20 * seq

    # 严格门槛：关键词和语序不足时，不允许高分。
    if kw_ratio < 20 and order_ratio < 20:
        accuracy = min(accuracy, 39.0)
    elif kw_ratio < 35 or order_ratio < 30:
        accuracy = min(accuracy, 59.0)
    elif kw_ratio < 55 or order_ratio < 45:
        accuracy = min(accuracy, 74.0)

    accuracy = max(0.0, min(100.0, accuracy))
    return {
        "accuracy": float(round(accuracy, 2)),
        "sequence_ratio": float(round(seq, 2)),
        "order_ratio": float(round(order_ratio, 2)),
        "keyword_ratio": float(round(kw_ratio, 2)),
        "keywords": kws,
        "keyword_hits": kw_hit,
    }


async def _ai_semantic_score(expected_text: str, transcript: str) -> Dict[str, Any]:
    exp = str(expected_text or "").strip()
    rec = str(transcript or "").strip()
    if not SAFETY_AI_API_KEY or not exp or not rec:
        return {"ok": False, "accuracy": 0.0, "reason": "disabled_or_empty"}

    prompt = (
        "你是儿童口语评测助手。请比较参考描述和孩子转写，只做语义一致性评分。"
        "输出严格JSON：{\"accuracy\":0-100数字,\"reason\":\"一句中文原因\"}，不要输出其他内容。"
    )
    user = (
        f"参考描述：{exp}\n"
        f"孩子转写：{rec}\n"
        "评分标准：语义高度一致接近100；说到部分信息给中分；明显偏题给低分。"
    )
    url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": SAFETY_AI_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }

    try:
        timeout_sec = max(10.0, float(SAFETY_AI_TIMEOUT_SEC) * 1.5)
        async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}

        text = _extract_chat_content_text(data if isinstance(data, dict) else {})
        obj = _extract_first_json_object(text) if text else None
        if not isinstance(obj, dict):
            return {"ok": False, "accuracy": 0.0, "reason": "bad_semantic_json"}

        acc = max(0.0, min(100.0, float(obj.get("accuracy", 0.0))))
        reason = str(obj.get("reason") or "").strip()
        return {"ok": True, "accuracy": acc, "reason": reason}
    except Exception as e:
        return {"ok": False, "accuracy": 0.0, "reason": f"semantic_error:{str(e)[:120]}"}


async def _ai_positive_score(transcript: str) -> Dict[str, Any]:
    rec = str(transcript or "").strip()
    if not SAFETY_AI_API_KEY or not rec:
        return {"ok": False, "positive": 60.0, "reason": "disabled_or_empty"}

    prompt = (
        "你是儿童口语鼓励评测助手。请只根据孩子话语的积极程度评分。"
        "输出严格JSON：{\"positive\":0-100数字,\"reason\":\"一句鼓励性中文点评\"}，不要输出其他内容。"
    )
    user = (
        f"孩子转写：{rec}\n"
        "评分标准：积极、友善、礼貌、乐观得分更高；中性表达中等；消极或攻击性降低。"
    )
    url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": SAFETY_AI_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }

    try:
        timeout_sec = max(10.0, float(SAFETY_AI_TIMEOUT_SEC) * 1.5)
        async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}

        text = _extract_chat_content_text(data if isinstance(data, dict) else {})
        obj = _extract_first_json_object(text) if text else None
        if not isinstance(obj, dict):
            return {"ok": False, "positive": 65.0, "reason": "bad_positive_json"}

        pos = max(0.0, min(100.0, float(obj.get("positive", 65.0))))
        reason = str(obj.get("reason") or "").strip()
        return {"ok": True, "positive": pos, "reason": reason}
    except Exception as e:
        return {"ok": False, "positive": 65.0, "reason": f"positive_error:{str(e)[:120]}"}


def _build_grounded_feedback(
    expected_text: str,
    transcript: str,
    score: Dict[str, Any],
    asr_error: str = "",
    positive_reason: str = "",
    uncivil_term: str = "",
) -> str:
    rec = str(transcript or "").strip()
    if not rec:
        err = str(asr_error or "").lower()
        if any(x in err for x in ["invalid_api_key", "401", "404", "asr_disabled"]):
            return "当前语音识别服务暂时不可用，这次先不计分。你已经很棒了，稍后再试一次。"
        return "我这次没有听清你说的内容。你已经很努力啦，放慢一点、靠近麦克风再说一次就更好了。"

    acc = float(score.get("accuracy", 0.0))
    pos_hint = f" {positive_reason}" if positive_reason else ""

    if uncivil_term:
        return (
            f"我听到你说：{rec}。这句话里有不文明表达（{uncivil_term}）。"
            "我们可以用更礼貌、更尊重别人的方式表达情绪。"
            "请把这句话换成文明说法再试一次，我相信你可以做到。"
        )

    if acc >= 96:
        return f"我听到你说：{rec}。你的表达很积极、很温暖，特别棒。{pos_hint}"
    if acc >= 90:
        return f"我听到你说：{rec}。你今天的表达很不错，继续保持这份自信。{pos_hint}"
    return f"我听到你说：{rec}。你已经说得很好啦，只要再更放松一点就会更出色。{pos_hint}"

def _detect_uncivil_term(text: str) -> str:
    t = _normalize_text(str(text or ""))
    if not t:
        return ""
    for w in _UNCIVIL_TERMS:
        ww = _normalize_text(w)
        if ww and ww in t:
            return w
    return ""


def _looks_like_invalid_asr_text(text: str) -> bool:
    t = str(text or "").strip().lower()
    if not t:
        return True
    # These patterns usually indicate model fallback chatter, not real ASR transcript.
    bad_markers = [
        "请提供",
        "请上传",
        "需要转写",
        "语音内容",
        "无法转写",
        "无法识别",
        "无法处理",
        "i need",
        "please provide",
        "audio content",
        "transcribe",
    ]
    return any(m in t for m in bad_markers)


def _cleanup_audio_cache() -> None:
    now = time.time()
    expired = [k for k, v in _AUDIO_CACHE.items() if now - float(v.get("ts", 0)) > _AUDIO_CACHE_TTL_SEC]
    for k in expired:
        _AUDIO_CACHE.pop(k, None)
    if len(_AUDIO_CACHE) > _AUDIO_CACHE_MAX:
        keys = sorted(_AUDIO_CACHE.keys(), key=lambda x: float(_AUDIO_CACHE[x].get("ts", 0)))
        for k in keys[: max(0, len(keys) - _AUDIO_CACHE_MAX)]:
            _AUDIO_CACHE.pop(k, None)


def _cache_audio_bytes(audio_bytes: bytes, mime_type: str = "audio/mpeg") -> str:
    _cleanup_audio_cache()
    audio_id = uuid.uuid4().hex
    _AUDIO_CACHE[audio_id] = {
        "bytes": bytes(audio_bytes or b""),
        "mime": str(mime_type or "audio/mpeg"),
        "ts": time.time(),
    }
    return f"/readalong/audio/{audio_id}"


def _collect_text_chunks(node: Any, out: List[str]) -> None:
    if isinstance(node, str):
        t = node.strip()
        if t:
            out.append(t)
        return

    if isinstance(node, list):
        for item in node:
            _collect_text_chunks(item, out)
        return

    if not isinstance(node, dict):
        return

    # 常见文本字段
    for k in ("text", "transcript", "output_text", "result", "caption"):
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())

    # OpenAI/兼容网关里音频识别有时在 message.audio.transcript
    audio = node.get("audio")
    if isinstance(audio, dict):
        for k in ("transcript", "text"):
            v = audio.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())

    # 仅递归可能包含正文的结构字段，避免把错误信息当转写结果
    for k in ("content", "message", "messages", "output", "outputs", "choices", "data", "response"):
        if k in node:
            _collect_text_chunks(node.get(k), out)


def _join_unique_chunks(chunks: List[str]) -> str:
    uniq: List[str] = []
    seen = set()
    for c in chunks:
        t = str(c or "").strip()
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return " ".join(uniq).strip()


def _extract_chat_content_text(payload: Dict[str, Any]) -> str:
    content = ((((payload or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    out.append(item.get("text"))
                elif item.get("type") == "output_text" and isinstance(item.get("text"), str):
                    out.append(item.get("text"))
        text = " ".join(x.strip() for x in out if x and x.strip()).strip()
        if text:
            return text

    # 兜底：兼容不同网关返回 schema
    chunks: List[str] = []
    _collect_text_chunks(payload or {}, chunks)
    return _join_unique_chunks(chunks)


def _extract_dashscope_text(payload: Dict[str, Any]) -> str:
    try:
        choices = (((payload or {}).get("output") or {}).get("choices") or [])
        if not choices:
            return ""
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content") or []
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    t = item.get("text", "").strip()
                    if t:
                        chunks.append(t)
            text = " ".join(chunks).strip()
            if text:
                return text
        if isinstance(content, str):
            return content.strip()
    except Exception:
        pass
    chunks: List[str] = []
    _collect_text_chunks(payload or {}, chunks)
    return _join_unique_chunks(chunks)


def _dashscope_native_base_url() -> str:
    base = str(SAFETY_AI_BASE_URL or "").strip().rstrip("/")
    if not base:
        return ""
    if "/compatible-mode/" in base:
        return base.split("/compatible-mode/", 1)[0]
    if base.endswith("/compatible-mode"):
        return base[: -len("/compatible-mode")]
    return base

async def _ai_transcribe_audio(audio_bytes: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
    if not SAFETY_AI_API_KEY or not audio_bytes:
        return {"ok": False, "transcript": "", "source": "fallback", "error": "asr_disabled"}

    errs: List[str] = []
    timeout_sec = max(12.0, float(SAFETY_AI_TIMEOUT_SEC) * 2)

    # Path A: OpenAI-style transcription endpoint (some gateways may not support).
    try:
        headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}"}
        files = {"file": (filename or "speech.wav", audio_bytes, mime_type or "audio/wav")}
        data = {"model": SAFETY_AI_ASR_MODEL, "language": "zh", "temperature": "0"}
        url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/audio/transcriptions"
        async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            payload = resp.json() if resp.content else {}
        text = str((payload or {}).get("text") or (payload or {}).get("transcript") or (payload or {}).get("result") or "").strip()
        if not text:
            text = _extract_chat_content_text(payload if isinstance(payload, dict) else {})
        text = re.sub(r"\s+", " ", text)
        if text:
            return {"ok": True, "transcript": text, "source": "qwen_asr_transcriptions"}
    except Exception as e:
        errs.append(f"transcriptions:{str(e)[:180]}")

    # Path B: multimodal chat completion with inline audio (non-stream).
    try:
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        payload_variants = [
            {
                "model": SAFETY_AI_ASR_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请把这段中文语音逐字转写为简体中文，只输出转写文本，不要解释。"},
                            {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
                        ],
                    }
                ],
                "temperature": 0,
            },
            {
                "model": SAFETY_AI_ASR_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请把这段中文语音逐字转写为简体中文，只输出转写文本，不要解释。"},
                            {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{b64}"}},
                        ],
                    }
                ],
                "temperature": 0,
            },
        ]
        headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}", "Content-Type": "application/json"}
        url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
            for idx, payload in enumerate(payload_variants):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json() if resp.content else {}
                    text = _extract_chat_content_text(data)
                    text = re.sub(r"\s+", " ", text)
                    if text:
                        source = "qwen_asr_chat_audio" if idx == 0 else "qwen_asr_chat_audio_url"
                        return {"ok": True, "transcript": text, "source": source}
                except Exception as inner_e:
                    errs.append(f"chat_audio_v{idx + 1}:{str(inner_e)[:180]}")
    except Exception as e:
        errs.append(f"chat_audio:{str(e)[:180]}")

    # Path C: DashScope native multimodal generation (verified fallback for qwen-omni).
    try:
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        native_base = _dashscope_native_base_url()
        if native_base:
            url = f"{native_base}/api/v1/services/aigc/multimodal-generation/generation"
            payload = {
                "model": SAFETY_AI_ASR_MODEL,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"text": "请把这段中文语音逐字转写为简体中文，只输出转写文本，不要解释。"},
                                {"audio": f"data:audio/wav;base64,{b64}"},
                            ],
                        }
                    ]
                },
                "parameters": {"temperature": 0},
            }
            headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
            text = _extract_dashscope_text(data)
            text = re.sub(r"\s+", " ", text)
            if text:
                return {"ok": True, "transcript": text, "source": "dashscope_multimodal_asr"}
    except Exception as e:
        errs.append(f"dashscope_mm:{str(e)[:180]}")

    return {"ok": False, "transcript": "", "source": "fallback", "error": " | ".join(errs)[:360]}


def _decode_tts_bytes(content_type: str, body: bytes) -> bytes:
    ct = str(content_type or "").lower()
    if ct.startswith("audio/"):
        return bytes(body or b"")
    try:
        obj = json.loads((body or b"{}").decode("utf-8", errors="ignore"))
    except Exception:
        return b""

    candidates = [
        (obj or {}).get("audio"),
        ((obj or {}).get("data") or {}).get("audio"),
        (obj or {}).get("output"),
    ]
    for c in candidates:
        if isinstance(c, dict):
            b64 = c.get("data") or c.get("b64") or c.get("audio")
            if isinstance(b64, str) and b64.strip():
                try:
                    return base64.b64decode(b64)
                except Exception:
                    continue
        if isinstance(c, str) and c.strip():
            try:
                return base64.b64decode(c)
            except Exception:
                continue
    return b""


def _extract_audio_b64_deep(obj: Any) -> bytes:
    # DashScope/Omni 返回结构可能有嵌套，这里做递归提取。
    if isinstance(obj, str):
        ss = obj.strip()
        if len(ss) > 64:
            try:
                return base64.b64decode(ss)
            except Exception:
                return b""
        return b""
    if isinstance(obj, dict):
        for k in ("audio", "data", "b64", "audio_data"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                try:
                    return base64.b64decode(v)
                except Exception:
                    pass
            if isinstance(v, dict):
                got = _extract_audio_b64_deep(v)
                if got:
                    return got
        for v in obj.values():
            got = _extract_audio_b64_deep(v)
            if got:
                return got
    if isinstance(obj, list):
        for it in obj:
            got = _extract_audio_b64_deep(it)
            if got:
                return got
    return b""

def _pcm16_to_wav_bytes(raw_pcm: bytes, sample_rate: int = 24000) -> bytes:
    pcm = bytes(raw_pcm or b"")
    if not pcm:
        return b""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm)
    return buf.getvalue()


async def _ai_synthesize_feedback_audio(feedback_text: str) -> Dict[str, Any]:
    text = str(feedback_text or "").strip()
    if not SAFETY_AI_API_KEY or not text:
        return {"ok": False, "audio_url": "", "source": "fallback", "error": "tts_disabled"}

    timeout_sec = max(12.0, float(SAFETY_AI_TIMEOUT_SEC) * 2)
    errs: List[str] = []

    # 方案A：OpenAI 兼容 TTS
    try:
        url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/audio/speech"
        headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": SAFETY_AI_TTS_MODEL, "voice": SAFETY_AI_TTS_VOICE, "input": text, "format": "mp3"}
        async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            audio_bytes = _decode_tts_bytes(resp.headers.get("content-type", ""), resp.content or b"")
        if audio_bytes:
            audio_url = _cache_audio_bytes(audio_bytes, "audio/mpeg")
            return {"ok": True, "audio_url": audio_url, "source": "qwen_tts_openai_compat"}
        errs.append("openai_tts:empty_audio")
    except Exception as e:
        errs.append(f"openai_tts:{str(e)[:160]}")

    # 方案B：chat/completions 流式音频（Qwen Omni）
    try:
        url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": SAFETY_AI_TTS_MODEL,
            "messages": [{"role": "user", "content": f"请自然、亲切地朗读：{text}"}],
            "modalities": ["text", "audio"],
            "audio": {"voice": SAFETY_AI_TTS_VOICE, "format": "pcm16"},
            "stream": True,
            "temperature": 0.3,
        }

        raw_pcm = bytearray()
        async with httpx.AsyncClient(timeout=timeout_sec, trust_env=False) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        obj = json.loads(body)
                    except Exception:
                        continue
                    delta = ((obj.get("choices") or [{}])[0].get("delta") or {})
                    audio = delta.get("audio")
                    if isinstance(audio, dict):
                        seg = audio.get("data")
                        if isinstance(seg, str) and seg.strip():
                            try:
                                raw_pcm.extend(base64.b64decode(seg))
                            except Exception:
                                continue

        wav_bytes = _pcm16_to_wav_bytes(bytes(raw_pcm), sample_rate=24000)
        if wav_bytes:
            audio_url = _cache_audio_bytes(wav_bytes, "audio/wav")
            return {"ok": True, "audio_url": audio_url, "source": "qwen_tts_chat_stream"}
        errs.append("chat_stream_tts:empty_audio")
    except Exception as e:
        errs.append(f"chat_stream_tts:{str(e)[:160]}")

    return {"ok": False, "audio_url": "", "source": "fallback", "error": " | ".join(errs)[:360]}

async def _ai_image_caption(file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    if not SAFETY_AI_API_KEY or not file_bytes:
        return {
            "ok": True,
            "caption": "这是一张图片，请你先说说看到了什么（当前为兜底描述）。",
            "source": "fallback",
        }

    b64 = base64.b64encode(file_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"
    prompt = "请用一句适合3-6岁儿童复述的中文，描述图片里最主要的角色和动作。要求不超过35字。"
    payload = {
        "model": SAFETY_AI_VISION_MODEL,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]}],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {SAFETY_AI_API_KEY}", "Content-Type": "application/json"}
    url = f"{SAFETY_AI_BASE_URL.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=max(12.0, SAFETY_AI_TIMEOUT_SEC), trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        caption = _extract_chat_content_text(data)
        if not caption:
            raise RuntimeError("empty caption")
        caption = re.sub(r"\s+", " ", caption)
        return {"ok": True, "caption": caption[:80], "source": "safety_ai"}
    except Exception as e:
        return {"ok": True, "caption": "我看到一张很有趣的图片，你可以说说里面发生了什么。", "source": "fallback", "error": str(e)[:200]}


@app.get("/readalong/health")
async def health():
    return {
        "ok": True,
        "module": "readalong",
        "status": "healthy",
        "ai_configured": bool(SAFETY_AI_API_KEY),
        "ai_model": SAFETY_AI_MODEL,
        "vision_model": SAFETY_AI_VISION_MODEL,
        "asr_model": SAFETY_AI_ASR_MODEL,
        "tts_model": SAFETY_AI_TTS_MODEL,
        "tts_voice": SAFETY_AI_TTS_VOICE,
        "note": "encouraging scoring; uncivil speech gets educational correction; asr includes chat-audio fallback.",
    }


@app.get("/readalong/books")
async def readalong_books():
    return {"ok": True, "books": _list_books()}


@app.get("/readalong/books/{book_id}")
async def readalong_book(book_id: str):
    obj = _get_book(book_id)
    if not obj:
        return {"ok": False, "message": "book not found", "book": None}

    title = str(obj.get("title") or obj.get("id") or book_id)
    sentences = obj.get("sentences") or []
    if not isinstance(sentences, list):
        sentences = []
    normalized = dict(obj)
    normalized["id"] = str(obj.get("id") or book_id)
    normalized["title"] = title
    normalized["sentences"] = [str(x) for x in sentences]
    return {"ok": True, "book": normalized}


@app.post("/readalong/image_caption")
async def image_caption(file: UploadFile = File(...)):
    data = await file.read()
    mime = file.content_type or "image/jpeg"
    return await _ai_image_caption(data, mime)


@app.post("/readalong/evaluate")
async def evaluate(
    file: UploadFile = File(...),
    expected_text: str = Form(""),
    book_id: str = Form(""),
    sentence_index: str = Form("0"),
    audio_format: str = Form("wav"),
    eval_mode: str = Form("free_description"),
):
    _ = (book_id, sentence_index, eval_mode)

    data_bytes = await file.read()
    if not data_bytes:
        feedback_text = "没有收到有效文件，请重试。"
        return {
            "ok": True,
            "accuracy": 0.0,
            "stars": 1,
            "feedback": feedback_text,
            "feedback_text": feedback_text,
            "transcript": "",
            "recognized_text": "",
            "feedback_audio_url": "",
            "source": "fallback",
        }

    content_type = str(file.content_type or "").strip().lower()
    fmt = str(audio_format or "").strip().lower()
    # 兼容：涂色评价会上传 PNG，并设置 eval_mode=coloring_evaluation
    is_image = content_type.startswith("image/") or fmt in ("png", "jpg", "jpeg", "webp") or str(eval_mode or "").strip() == "coloring_evaluation"
    if is_image:
        mime = content_type if content_type.startswith("image/") else (f"image/{fmt}" if fmt else "image/png")
        try:
            return await _ai_coloring_evaluate_image(data_bytes, mime)
        except Exception as e:
            # 兜底：仍返回可展示的结果，避免前端“无交互”
            fb = "我已经看到你的作品啦！可以再把边边涂得更满一点点，再试试两三种颜色搭配，会更漂亮。"
            return {
                "ok": True,
                "accuracy": 72.0,
                "stars": 3,
                "feedback": fb,
                "feedback_text": fb,
                "transcript": "",
                "recognized_text": "",
                "feedback_audio_url": "",
                "source": f"coloring_error_fallback:{str(e)[:80]}",
            }

    # 默认：语音跟读评测（ASR + 严格对齐评分 + TTS 反馈）
    mime_type = content_type or f"audio/{fmt or 'wav'}"
    asr = await _ai_transcribe_audio(audio_bytes=data_bytes, filename=str(file.filename or f"record.{fmt or 'wav'}"), mime_type=mime_type)
    transcript = str(asr.get("transcript") or "").strip()
    asr_error = str(asr.get("error") or "")
    asr_source = str(asr.get("source") or "fallback")

    if _looks_like_invalid_asr_text(transcript):
        transcript = ""
        asr_error = (asr_error + "|invalid_transcript").strip("|")

    if not transcript:
        print(
            f"[readalong][asr-empty] source={asr_source} file={str(file.filename or '')[:80]} "
            f"fmt={fmt or 'wav'} bytes={len(data_bytes)} err={asr_error[:200]}"
        )

    positive = await _ai_positive_score(transcript) if transcript else {"ok": False, "positive": 60.0, "reason": ""}
    pos_ok = bool(positive.get("ok"))
    pos_val = float(positive.get("positive", 60.0)) if pos_ok else 60.0
    uncivil_term = _detect_uncivil_term(transcript)

    score: Dict[str, Any] = {
        "score_mode": "positive_encouraging",
        "positive_score": float(round(pos_val, 2)),
        "positive_reason": str(positive.get("reason") or ""),
        "uncivil_term": uncivil_term,
    }

    if uncivil_term:
        final_acc = max(35.0, min(79.0, pos_val))
        score["score_mode"] = "uncivil_guardrail"
    else:
        # 按积极程度映射到鼓励区间 85-100
        final_acc = max(85.0, min(100.0, 85.0 + (pos_val / 100.0) * 15.0))

    score["accuracy"] = float(round(final_acc, 2))

    accuracy = float(score.get("accuracy", 0.0))
    stars = _accuracy_to_stars(accuracy)
    feedback_text = _build_grounded_feedback(
        expected_text,
        transcript,
        score,
        asr_error,
        str(positive.get("reason") or "") if pos_ok else "",
        uncivil_term,
    )

    tts = await _ai_synthesize_feedback_audio(feedback_text)
    return {
        "ok": True,
        "accuracy": accuracy,
        "stars": int(stars),
        "feedback": feedback_text,
        "feedback_text": feedback_text,
        "transcript": transcript,
        "recognized_text": transcript,
        "feedback_audio_url": str(tts.get("audio_url") or ""),
        "scoring": score,
        "source": f"{asr_source}+{tts.get('source', 'fallback')}",
        "asr_source": asr_source,
        "asr_error": asr_error,
        "tts_error": str(tts.get("error") or ""),
    }


@app.get("/readalong/tts")
async def readalong_tts(text: str = ""):
    t = str(text or "").strip()
    if not t:
        return {"ok": False, "audio_url": "", "source": "fallback", "error": "empty_text"}
    tts = await _ai_synthesize_feedback_audio(t)
    return {
        "ok": bool(tts.get("ok")),
        "audio_url": str(tts.get("audio_url") or ""),
        "source": str(tts.get("source") or "fallback"),
        "error": str(tts.get("error") or ""),
        "voice": SAFETY_AI_TTS_VOICE,
    }

@app.get("/readalong/audio/{audio_id}")
async def get_feedback_audio(audio_id: str):
    _cleanup_audio_cache()
    key = str(audio_id or "").strip()
    item = _AUDIO_CACHE.get(key)
    if not item:
        raise HTTPException(status_code=404, detail="audio not found")
    return Response(content=item.get("bytes") or b"", media_type=str(item.get("mime") or "audio/mpeg"))
