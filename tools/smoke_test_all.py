#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CaseResult:
    name: str
    ok: bool
    method: str
    url: str
    status: int
    elapsed_ms: int
    note: str = ""
    response_sample: Optional[Dict[str, Any]] = None


def _http_request(
    method: str,
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_sec: float = 6.0,
) -> Tuple[int, Dict[str, str], bytes]:
    headers = {"User-Agent": "smoke-test/1.0"}
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method.upper())
    try:
        # 不走系统代理（否则本地 127.0.0.1 可能被转发导致 Connection refused）
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout_sec) as resp:
            status = int(getattr(resp, "status", 200))
            resp_headers = {k.lower(): v for k, v in (resp.headers.items() if resp.headers else [])}
            body = resp.read() or b""
            return status, resp_headers, body
    except urllib.error.HTTPError as e:
        status = int(getattr(e, "code", 0) or 0)
        resp_headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        body = e.read() if hasattr(e, "read") else b""
        return status, resp_headers, body


def _json_sample(body: bytes, limit: int = 2800) -> Optional[Dict[str, Any]]:
    if not body:
        return None
    raw = body[:limit].decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        return {"_type": type(obj).__name__, "_value": obj}
    except Exception:
        return {"_raw": raw}


def _json_load_full(body: bytes, max_bytes: int = 2_000_000) -> Any:
    """
    用于“必须解析”的接口（如索引列表），避免 sample 截断导致 JSON 解析失败。
    """
    bb = body or b""
    if not bb:
        return None
    if len(bb) > max_bytes:
        return None
    try:
        return json.loads(bb.decode("utf-8", errors="strict"))
    except Exception:
        try:
            return json.loads(bb.decode("utf-8", errors="replace"))
        except Exception:
            return None


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _now_ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def run(base_wx: str, base_readalong: str, timeout_sec: float) -> Dict[str, Any]:
    started_at = time.time()
    results: List[CaseResult] = []

    def record(name: str, method: str, url: str, status: int, elapsed_ms: int, ok: bool, note: str = "", sample=None):
        results.append(
            CaseResult(
                name=name,
                ok=bool(ok),
                method=method.upper(),
                url=url,
                status=int(status),
                elapsed_ms=int(elapsed_ms),
                note=str(note or ""),
                response_sample=sample,
            )
        )

    # --- 0) 基础健康检查
    for name, url in [
        ("wx_root", _join(base_wx, "/")),
        ("wx_admin", _join(base_wx, "/admin")),
        ("wx_voices", _join(base_wx, "/voices")),
        ("wx_coloring_health", _join(base_wx, "/coloring/health")),
        ("wx_coloring_get_sketches", _join(base_wx, "/coloring/get_sketches?limit=1")),
        ("wx_magic_books_index", _join(base_wx, "/magic_books/index")),
        ("wx_practice_speaker_questions", _join(base_wx, "/practice/speaker/questions")),
        ("readalong_health", _join(base_readalong, "/readalong/health")),
        ("readalong_books", _join(base_readalong, "/readalong/books")),
    ]:
        t0 = time.time()
        status, headers, body = _http_request("GET", url, timeout_sec=timeout_sec)
        elapsed_ms = int((time.time() - t0) * 1000)
        sample = _json_sample(body)

        # / 可能返回 400（FastAPI 根路由可能仅接收 POST 或返回 Bad Request），只要服务在响应就算“活着”
        ok = status in (200, 400, 405)
        if name == "wx_root" and status == 400:
            note = "root 返回 400 视为正常（服务在线）"
        elif status >= 500:
            note = "服务端错误"
        else:
            note = ""
        record(name, "GET", url, status, elapsed_ms, ok=ok, note=note, sample=sample)

    # --- 0b) readalong books/{id}
    # 先拿一个 id
    t0 = time.time()
    url_rl_books = _join(base_readalong, "/readalong/books")
    st0, hh0, bb0 = _http_request("GET", url_rl_books, timeout_sec=timeout_sec)
    elapsed_ms0 = int((time.time() - t0) * 1000)
    rl_obj = _json_load_full(bb0)
    book_id = None
    if isinstance(rl_obj, dict):
        books = rl_obj.get("books")
        if isinstance(books, list) and books and isinstance(books[0], dict):
            book_id = books[0].get("id")
    record("readalong_books_parse", "GET", url_rl_books, st0, elapsed_ms0, ok=(st0 == 200 and bool(book_id)), note=f"book_id={book_id!r}")
    if book_id:
        url_one = _join(base_readalong, f"/readalong/books/{urllib.parse.quote(str(book_id))}")
        t0 = time.time()
        st1, hh1, bb1 = _http_request("GET", url_one, timeout_sec=timeout_sec)
        elapsed_ms1 = int((time.time() - t0) * 1000)
        obj1 = _json_sample(bb1)
        ok1 = (st1 == 200) and isinstance(obj1, dict) and bool(obj1.get("ok")) and isinstance(obj1.get("book"), dict)
        record("readalong_book_detail", "GET", url_one, st1, elapsed_ms1, ok=ok1, sample=obj1)

    # --- 1) 绘本：拿到一个 title 后访问 book
    # 读取 /magic_books/index 的 items，挑一个 title
    t0 = time.time()
    url_index = _join(base_wx, "/magic_books/index")
    status, headers, body = _http_request("GET", url_index, timeout_sec=timeout_sec)
    index_full = _json_load_full(body)
    index_obj = index_full if isinstance(index_full, dict) else (_json_sample(body) or {})
    items = (index_full or {}).get("items") if isinstance(index_full, dict) else (index_obj.get("items") if isinstance(index_obj, dict) else None)
    title = None
    if isinstance(items, list) and items:
        first = items[0] if isinstance(items[0], dict) else {}
        title = first.get("title") or first.get("id")
    elapsed_ms = int((time.time() - t0) * 1000)
    record(
        "magic_books_index_parse",
        "GET",
        url_index,
        status,
        elapsed_ms,
        ok=(status == 200 and bool(title)),
        note=f"title={title!r}",
        sample=index_obj if isinstance(index_obj, dict) else None,
    )

    if title:
        q = urllib.parse.urlencode({"title": str(title)})
        url_book = _join(base_wx, f"/magic_books/book?{q}")
        t0 = time.time()
        st, hh, bb = _http_request("GET", url_book, timeout_sec=timeout_sec)
        elapsed_ms = int((time.time() - t0) * 1000)
        obj = _json_sample(bb)
        ok = (st == 200) and isinstance(obj, dict) and ("paras" in obj)
        record("magic_books_book", "GET", url_book, st, elapsed_ms, ok=ok, sample=obj)

    # --- 1b) 伴宠（ar_companion）基础状态接口（只测接口可用，不依赖真实登录态）
    dummy_uid = "smoke_user_001"
    for name, path in [
        ("ar_egg_state", f"/ar_companion/pet/egg/state?{urllib.parse.urlencode({'user_id': dummy_uid})}"),
        ("ar_companion_state", f"/ar_companion/pet/companion/state?{urllib.parse.urlencode({'user_id': dummy_uid, 'mascot_id': 'cute-fox'})}"),
    ]:
        url = _join(base_wx, path)
        t0 = time.time()
        st, hh, bb = _http_request("GET", url, timeout_sec=timeout_sec)
        elapsed_ms = int((time.time() - t0) * 1000)
        obj = _json_sample(bb)
        ok = st in (200, 400, 404)  # 允许参数校验类 400（接口仍可用），但不应 5xx
        record(name, "GET", url, st, elapsed_ms, ok=ok, sample=obj)

    # --- 2) 内容安全：/safety/check（不消耗 TTS 推理资源）
    url_safety = _join(base_wx, "/safety/check")
    t0 = time.time()
    st, hh, bb = _http_request("POST", url_safety, json_body={"text": "小熊宝宝吃饭了。"}, timeout_sec=timeout_sec)
    elapsed_ms = int((time.time() - t0) * 1000)
    obj = _json_sample(bb)
    ok = (st == 200) and isinstance(obj, dict) and ("ok" in obj)
    record("safety_check", "POST", url_safety, st, elapsed_ms, ok=ok, sample=obj)

    # --- 2b) 训练历史模型列表（只读接口）
    url_hist = _join(base_wx, "/train/history_models")
    t0 = time.time()
    st, hh, bb = _http_request("GET", url_hist, timeout_sec=timeout_sec)
    elapsed_ms = int((time.time() - t0) * 1000)
    full = _json_load_full(bb)
    obj = full if isinstance(full, dict) else _json_sample(bb)
    ok = (st == 200) and isinstance(obj, dict) and any(k in obj for k in ("items", "models", "data", "code"))
    record("train_history_models", "GET", url_hist, st, elapsed_ms, ok=ok, sample=(obj if isinstance(obj, dict) else _json_sample(bb)))

    # --- 3) TTS 合成（最小化）：优先用 voice_001（Qwen 预置音色），返回 URL 避免大 payload
    url_syn = _join(base_wx, "/synthesize")
    t0 = time.time()
    st, hh, bb = _http_request(
        "POST",
        url_syn,
        json_body={
            "voice_id": "voice_001",
            "text": "你好，我是紫宝故事园。",
            "text_language": "中文",
            "return_url": True,
        },
        timeout_sec=max(timeout_sec, 10.0),
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    ct = (hh.get("content-type") or "").lower()
    if ct.startswith("audio/"):
        record("synthesize_voice_001_audio", "POST", url_syn, st, elapsed_ms, ok=(st == 200), note=f"content-type={ct}")
    else:
        obj = _json_sample(bb)
        # 兼容两类返回：直接 bytes 或返回 {audio_url/merged_url/task_id/...}
        ok = (st in (200,)) and isinstance(obj, dict) and any(
            k in obj for k in ("audio_url", "url", "task_id", "merged_url", "code", "segments")
        )
        record("synthesize_voice_001_json", "POST", url_syn, st, elapsed_ms, ok=ok, note=f"content-type={ct}", sample=obj)

    # --- 4) Buffered 合成队列（如果支持）
    t0 = time.time()
    st, hh, bb = _http_request(
        "POST",
        url_syn,
        json_body={
            "voice_id": "voice_001",
            "text": "这是一段较长的文本，用来测试分段合成与合并。",
            "text_language": "中文",
            "buffered": True,
            "return_url": True,
        },
        timeout_sec=max(timeout_sec, 12.0),
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    obj = _json_sample(bb)
    task_id = obj.get("task_id") if isinstance(obj, dict) else None
    ok = (st == 200) and bool(task_id)
    record("synthesize_buffered_create", "POST", url_syn, st, elapsed_ms, ok=ok, note=f"task_id={task_id}", sample=obj)

    if task_id:
        # status
        url_status = _join(base_wx, f"/synthesize/buffered/status?{urllib.parse.urlencode({'task_id': task_id})}")
        t0 = time.time()
        st2, hh2, bb2 = _http_request("GET", url_status, timeout_sec=timeout_sec)
        elapsed_ms2 = int((time.time() - t0) * 1000)
        obj2 = _json_sample(bb2)
        ok2 = (st2 == 200) and isinstance(obj2, dict) and ("done" in obj2 or "total" in obj2 or "segments" in obj2)
        record("synthesize_buffered_status", "GET", url_status, st2, elapsed_ms2, ok=ok2, sample=obj2)

        # merged
        url_merged = _join(base_wx, f"/synthesize/buffered/merged?{urllib.parse.urlencode({'task_id': task_id})}")
        t0 = time.time()
        st3, hh3, bb3 = _http_request("GET", url_merged, timeout_sec=timeout_sec)
        elapsed_ms3 = int((time.time() - t0) * 1000)
        ct3 = (hh3.get("content-type") or "").lower()
        if ct3.startswith("audio/"):
            record("synthesize_buffered_merged_audio", "GET", url_merged, st3, elapsed_ms3, ok=(st3 == 200), note=f"content-type={ct3}")
        else:
            obj3 = _json_sample(bb3)
            ok3 = (st3 in (200, 404))  # 允许未生成 merged 的场景（仍算接口可用）
            record("synthesize_buffered_merged_json", "GET", url_merged, st3, elapsed_ms3, ok=ok3, note=f"content-type={ct3}", sample=obj3)

    # --- 汇总
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed
    elapsed_ms = int((time.time() - started_at) * 1000)
    return {
        "ok": failed == 0,
        "summary": {"total": total, "passed": passed, "failed": failed, "elapsed_ms": elapsed_ms},
        "bases": {"wx": base_wx, "readalong": base_readalong},
        "results": [r.__dict__ for r in results],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="模块化功能冒烟测试（HTTP）")
    ap.add_argument("--wx", default=os.environ.get("WX_BASE", "http://127.0.0.1:9880"), help="主服务 base url")
    ap.add_argument(
        "--readalong",
        default=os.environ.get("READALONG_BASE", "http://127.0.0.1:9881"),
        help="跟读评测服务 base url",
    )
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("SMOKE_TIMEOUT", "6")), help="单请求超时秒数")
    ap.add_argument("--out", default="", help="输出目录（默认 train/runtime/smoke_reports）")
    args = ap.parse_args()

    report = run(args.wx, args.readalong, args.timeout)

    out_dir = args.out.strip() or os.path.join(os.getcwd(), "train", "runtime", "smoke_reports")
    os.makedirs(out_dir, exist_ok=True)
    ts = _now_ts()
    out_json = os.path.join(out_dir, f"smoke-report-{ts}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # stdout 简报（便于 CI/复制）
    s = report.get("summary") or {}
    print(f"[smoke] ok={report.get('ok')} total={s.get('total')} passed={s.get('passed')} failed={s.get('failed')} elapsed_ms={s.get('elapsed_ms')}")
    print(f"[smoke] report_json={out_json}")
    if not report.get("ok"):
        for r in report.get("results", []):
            if not r.get("ok"):
                print(f"[FAIL] {r.get('name')} {r.get('method')} {r.get('url')} status={r.get('status')} note={r.get('note')}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

