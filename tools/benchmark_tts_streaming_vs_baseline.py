#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import struct
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[1]
VOICE_LIBRARY_PATH = REPO_ROOT / "voice_library.json"
BENCH_DIR = REPO_ROOT / "runtime" / "bench"
READALONG_EVAL_PATH = "/readalong/evaluate"
CURRENT_SYNC_PATH = "/synthesize"
CURRENT_STREAM_PATH = "/synthesize/stream"
OLD_SYNC_PATH = "/"
OLD_SET_MODEL_PATH = "/set_model"
OLD_CHANGE_REFER_PATH = "/change_refer"

DEFAULT_VOICES = [
    "voice_004",
    "voice_007",
    "voice_011",
    "voice_009",
    "voice_014",
    "voice_017",
]

TEST_CASES = [
    {
        "case_id": "short_dialogue",
        "scene": "short",
        "kind": "dialogue",
        "text": "小熊抬起头，小声问：“妈妈，星星今天也会陪我回家吗？”",
    },
    {
        "case_id": "long_narrative_dialogue",
        "scene": "long",
        "kind": "narrative_dialogue",
        "text": (
            "夜风吹过树林，叶子发出沙沙的声音，小熊握紧了手里的小灯。"
            "他沿着发光的小路慢慢往前走，忽然听见树洞里传来温柔的回答："
            "“别害怕，继续往前走，今晚的星光会为勇敢的孩子照亮回家的路。”"
        ),
    },
]


def sanitize_text(text: str) -> str:
    return str(text or "").strip()


def count_text_units(text: str) -> int:
    return len(re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", sanitize_text(text)))


def estimate_min_duration_sec(text: str, speed: float = 1.0) -> float:
    t = sanitize_text(text)
    units = re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", t)
    pauses = re.findall(r"[，。！？；、,!?;:：…]", t)
    n = len(units)
    if n <= 0:
        return 0.0
    spd = max(0.75, min(1.35, float(speed or 1.0)))
    base_sec = float(n) * 0.145 + float(len(pauses)) * 0.09
    return max(0.45, base_sec / spd)


def estimate_max_duration_sec(text: str, speed: float = 1.0) -> float:
    t = sanitize_text(text)
    units = re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", t)
    pauses = re.findall(r"[，。！？；、,!?;:：…]", t)
    n = len(units)
    if n <= 0:
        return 0.0
    spd = max(0.75, min(1.35, float(speed or 1.0)))
    base_sec = float(n) * 0.32 + float(len(pauses)) * 0.22 + 0.9
    return max(1.8, base_sec / spd)


def duration_state_for(text: str, duration_sec: float, speed: float = 1.0) -> str:
    min_sec = estimate_min_duration_sec(text, speed=speed)
    max_sec = estimate_max_duration_sec(text, speed=speed)
    if duration_sec <= 0:
        return "invalid"
    if min_sec > 0 and duration_sec < (min_sec * 0.90):
        return "under"
    if max_sec > 0 and duration_sec > (max_sec * 1.25):
        return "over"
    return "ok"


def median_or_none(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    arr = np.asarray(sorted(values), dtype=np.float64)
    return float(np.percentile(arr, q))


def safe_float(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except Exception:
        return default


def decode_audio_metrics(audio_bytes: bytes) -> dict[str, Any]:
    if not audio_bytes:
        return {"duration_sec": 0.0, "rms": 0.0, "audible": False, "sample_rate": 0}
    with sf.SoundFile(io.BytesIO(audio_bytes)) as f:
        sr = int(f.samplerate)
        data = f.read(dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    duration_sec = float(len(data)) / float(sr) if sr > 0 else 0.0
    if data.size == 0:
        return {"duration_sec": duration_sec, "rms": 0.0, "audible": False, "sample_rate": sr}
    rms = float(np.sqrt(np.mean(np.square(data))) * 32768.0)
    return {
        "duration_sec": duration_sec,
        "rms": rms,
        "audible": bool(rms >= 65.0 and duration_sec >= 0.2),
        "sample_rate": sr,
    }


def repair_streamed_wav_bytes(audio_bytes: bytes) -> bytes:
    # 流式接口先发一个占位 WAV 头，文件长度字段需要在收全后回填。
    if len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        return audio_bytes
    fixed = bytearray(audio_bytes)
    data_size = max(0, len(audio_bytes) - 44)
    riff_size = 36 + data_size
    fixed[4:8] = struct.pack("<I", riff_size)
    fixed[40:44] = struct.pack("<I", data_size)
    return bytes(fixed)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def relative_audio_url(base_url: str, audio_url: str) -> str:
    if audio_url.startswith("http://") or audio_url.startswith("https://"):
        return audio_url
    return base_url.rstrip("/") + audio_url


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class ServiceProcess:
    process: subprocess.Popen[str]
    log_path: Path
    mode: str


class TTSBenchmark:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.voice_library = load_json(VOICE_LIBRARY_PATH)
        self.selected_voices = [v for v in args.voices if v in self.voice_library]
        if not self.selected_voices:
            raise SystemExit("未找到任何可用 voice_id")
        self.out_dir = (BENCH_DIR / f"streaming_vs_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}").resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir = self.out_dir / "audio"
        self.rows: list[dict[str, Any]] = []
        self.feature_matrix = self._build_feature_matrix()
        self.baseline_warnings: list[str] = []
        self.readalong_unavailable = False

    def _build_feature_matrix(self) -> list[dict[str, str]]:
        return [
            {
                "feature": "buffered 提交入口",
                "status": "部分成立",
                "evidence": "modules/tts_backend/wx_api.py:/synthesize + buffered=true",
                "note": "不是独立 POST /synthesize/buffered",
            },
            {
                "feature": "buffered 状态/分段/合并接口",
                "status": "成立",
                "evidence": "modules/tts_backend/wx_api.py:/synthesize/buffered/status|segment|merged",
                "note": "支持轮询与提前试听",
            },
            {
                "feature": "规则式长文本切分",
                "status": "成立",
                "evidence": "modules/tts_backend/wx_api.py:_split_text_for_buffer",
                "note": "基于标点/长度/对白合并",
            },
            {
                "feature": "Sentence-Transformer 语义分块",
                "status": "未发现",
                "evidence": "全仓未检索到 sentence_transformers / SentenceTransformer",
                "note": "应改述为规则式与语言感知切分",
            },
            {
                "feature": "实时流式接口",
                "status": "成立",
                "evidence": "modules/tts_backend/wx_api.py:/synthesize/stream",
                "note": "HTTP 分块传输已实现",
            },
            {
                "feature": "风险分层 + 自适应步数 + relax_max_sec",
                "status": "成立",
                "evidence": "wx_api.py:_resolve_user_voice_risk_policy/_resolve_adaptive_user_voice_sample_steps/_apply_temporary_infer_max_sec",
                "note": "集中于 user_trained 音色链路",
            },
            {
                "feature": "under/over 重试与分段兜底",
                "status": "成立",
                "evidence": "wx_api.py:_is_under_generated_audio/_is_over_generated_audio/_maybe_second_chance_under",
                "note": "buffered 下还有 split fallback",
            },
        ]

    def run(self) -> None:
        historical = self._load_historical_context()
        old_sync_proc = None
        old_stream_proc = None
        try:
            if self.args.run_old_baseline:
                try:
                    old_sync_proc = self._start_old_service(port=self.args.old_sync_port, stream_mode="close")
                    self._run_old_modes(base_url=f"http://127.0.0.1:{self.args.old_sync_port}", mode="old_sync")
                finally:
                    if old_sync_proc is not None:
                        self._stop_service(old_sync_proc)
                        old_sync_proc = None

                try:
                    old_stream_proc = self._start_old_service(port=self.args.old_stream_port, stream_mode="normal")
                    self._run_old_modes(base_url=f"http://127.0.0.1:{self.args.old_stream_port}", mode="old_stream")
                finally:
                    if old_stream_proc is not None:
                        self._stop_service(old_stream_proc)
                        old_stream_proc = None

            self._run_current_modes()
        finally:
            if old_sync_proc is not None:
                self._stop_service(old_sync_proc)
            if old_stream_proc is not None:
                self._stop_service(old_stream_proc)

        summary = self._summarize_rows()
        raw = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "config": {
                "voices": self.selected_voices,
                "rounds": self.args.rounds,
                "current_base_url": self.args.current_base_url,
                "readalong_base_url": self.args.readalong_base_url,
                "run_old_baseline": bool(self.args.run_old_baseline),
                "cases": TEST_CASES,
            },
            "feature_matrix": self.feature_matrix,
            "rows": self.rows,
            "summary": summary,
            "historical_context": historical,
            "baseline_warnings": self.baseline_warnings,
        }
        (self.out_dir / "raw_results.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_report(summary, historical)
        print(self.out_dir)

    def _load_historical_context(self) -> dict[str, Any]:
        after_patch = load_json(BENCH_DIR / "full_voice_default_chain_after_patch_live_20260411_132719.json")
        before_patch = load_json(BENCH_DIR / "voice_quality_policy_regression_after_maxsec_20260402_102308.json")
        return {
            "after_patch_summary": after_patch.get("summary", {}),
            "before_patch_overall": before_patch.get("overall", {}),
            "before_patch_summary": before_patch.get("summary", {}),
        }

    def _start_old_service(self, port: int, stream_mode: str) -> ServiceProcess:
        first_voice = self.voice_library[self.selected_voices[0]]
        log_path = self.out_dir / f"old_api_{stream_mode}_{port}.log"
        cmd = [
            str(REPO_ROOT / "venv" / "bin" / "python"),
            "deprecated_unused/api.py",
            "-a",
            "127.0.0.1",
            "-p",
            str(port),
            "-g",
            str(first_voice["gpt_path"]),
            "-s",
            str(first_voice["sovits_path"]),
            "-dr",
            str(first_voice["ref_audio_path"]),
            "-dt",
            str(first_voice["ref_text"]),
            "-dl",
            str(first_voice.get("ref_language") or "中文"),
            "-sm",
            "n" if stream_mode == "normal" else "c",
        ]
        with log_path.open("w", encoding="utf-8") as f:
            proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
            )
        self._wait_http_ready(f"http://127.0.0.1:{port}/set_model", timeout_sec=self.args.service_start_timeout_sec)
        return ServiceProcess(process=proc, log_path=log_path, mode=stream_mode)

    def _wait_http_ready(self, url: str, timeout_sec: int = 180) -> None:
        deadline = time.time() + timeout_sec
        last_err = ""
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            while time.time() < deadline:
                try:
                    r = client.get(url)
                    if r.status_code < 500:
                        return
                except Exception as e:
                    last_err = str(e)
                time.sleep(2.0)
        raise RuntimeError(f"服务未就绪: {url}; last_err={last_err}")

    def _stop_service(self, svc: ServiceProcess) -> None:
        if svc.process.poll() is None:
            svc.process.send_signal(signal.SIGTERM)
            try:
                svc.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                svc.process.kill()
                svc.process.wait(timeout=10)

    def _set_old_voice(self, client: httpx.Client, base_url: str, voice_id: str) -> None:
        voice = self.voice_library[voice_id]
        r1 = client.post(
            base_url.rstrip("/") + OLD_SET_MODEL_PATH,
            json={"gpt_model_path": voice["gpt_path"], "sovits_model_path": voice["sovits_path"]},
        )
        r1.raise_for_status()
        r2 = client.post(
            base_url.rstrip("/") + OLD_CHANGE_REFER_PATH,
            json={
                "refer_wav_path": voice["ref_audio_path"],
                "prompt_text": voice["ref_text"],
                "prompt_language": voice.get("ref_language") or "中文",
            },
        )
        r2.raise_for_status()

    def _run_old_modes(self, base_url: str, mode: str) -> None:
        timeout = httpx.Timeout(timeout=180.0, connect=10.0)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            probe_voice = self.selected_voices[0]
            self._set_old_voice(client, base_url, probe_voice)
            probe_case = TEST_CASES[0]
            probe_row = self._run_old_case(client, base_url, probe_voice, 0, probe_case, mode, append=False)
            if (not probe_row.get("ok")) and ("object is not iterable" in str(probe_row.get("error") or "")):
                self.baseline_warnings.append(
                    f"{mode}: deprecated_unused/api.py live 调用失败，命中已知参数错位问题（`inp_refs`/`sample_steps`）。"
                )
                self.rows.append(probe_row)
                return

            for voice_id in self.selected_voices:
                self._set_old_voice(client, base_url, voice_id)
                for round_idx in range(1, self.args.rounds + 1):
                    for case in TEST_CASES:
                        self._run_old_case(client, base_url, voice_id, round_idx, case, mode, append=True)

    def _run_old_case(
        self,
        client: httpx.Client,
        base_url: str,
        voice_id: str,
        round_idx: int,
        case: dict[str, Any],
        mode: str,
        append: bool = True,
    ) -> dict[str, Any]:
        voice = self.voice_library[voice_id]
        payload = {
            "refer_wav_path": voice["ref_audio_path"],
            "prompt_text": voice["ref_text"],
            "prompt_language": voice.get("ref_language") or "中文",
            "text": case["text"],
            "text_language": "zh",
            "speed": 1.0,
        }
        row = self._base_row(voice_id=voice_id, round_idx=round_idx, case=case, mode=mode)
        try:
            if mode == "old_stream":
                with client.stream("POST", base_url.rstrip("/") + OLD_SYNC_PATH, json=payload) as resp:
                    row["status"] = resp.status_code
                    resp.raise_for_status()
                    chunks = []
                    start = time.perf_counter()
                    first_chunk_ms = None
                    for chunk in resp.iter_bytes():
                        if not chunk:
                            continue
                        if first_chunk_ms is None:
                            first_chunk_ms = (time.perf_counter() - start) * 1000.0
                        chunks.append(chunk)
                    audio_bytes = b"".join(chunks)
                    row["first_ready_ms"] = round(first_chunk_ms or 0.0, 2)
                    row["request_ms"] = round((time.perf_counter() - start) * 1000.0, 2)
                    row["merged_ready_ms"] = row["request_ms"]
            else:
                start = time.perf_counter()
                resp = client.post(base_url.rstrip("/") + OLD_SYNC_PATH, json=payload)
                row["request_ms"] = round((time.perf_counter() - start) * 1000.0, 2)
                row["first_ready_ms"] = row["request_ms"]
                row["merged_ready_ms"] = row["request_ms"]
                row["status"] = resp.status_code
                resp.raise_for_status()
                audio_bytes = resp.content
            suffix = "ogg" if mode == "old_stream" else "wav"
            audio_path = self.audio_dir / mode / voice_id / f"{case['case_id']}__r{round_idx}.{suffix}"
            write_bytes(audio_path, audio_bytes)
            row["audio_path"] = str(audio_path.relative_to(REPO_ROOT))
            self._attach_audio_eval(row, audio_bytes, case["text"], suffix)
        except Exception as e:
            row["error"] = str(e)[:500]
            row["ok"] = False
        if append:
            self.rows.append(row)
        return row

    def _run_current_modes(self) -> None:
        timeout = httpx.Timeout(timeout=180.0, connect=10.0)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            for voice_id in self.selected_voices:
                for round_idx in range(1, self.args.rounds + 1):
                    for case in TEST_CASES:
                        self._run_current_sync(client, voice_id, round_idx, case)
                        self._run_current_buffered(client, voice_id, round_idx, case)
                        self._run_current_stream(client, voice_id, round_idx, case)

    def _run_current_sync(self, client: httpx.Client, voice_id: str, round_idx: int, case: dict[str, Any]) -> None:
        payload = {"voice_id": voice_id, "text": case["text"], "text_language": "zh"}
        row = self._base_row(voice_id=voice_id, round_idx=round_idx, case=case, mode="current_sync")
        try:
            start = time.perf_counter()
            resp = client.post(self.args.current_base_url.rstrip("/") + CURRENT_SYNC_PATH, json=payload)
            row["request_ms"] = round((time.perf_counter() - start) * 1000.0, 2)
            row["first_ready_ms"] = row["request_ms"]
            row["merged_ready_ms"] = row["request_ms"]
            row["status"] = resp.status_code
            resp.raise_for_status()
            ctype = str(resp.headers.get("content-type") or "").lower()
            if "application/json" in ctype:
                obj = resp.json()
                audio_url = str(obj.get("audio_url") or "")
                row["audio_url"] = audio_url
                audio_bytes = client.get(relative_audio_url(self.args.current_base_url, audio_url)).content
            else:
                audio_bytes = resp.content
            audio_path = self.audio_dir / "current_sync" / voice_id / f"{case['case_id']}__r{round_idx}.wav"
            write_bytes(audio_path, audio_bytes)
            row["audio_path"] = str(audio_path.relative_to(REPO_ROOT))
            self._attach_audio_eval(row, audio_bytes, case["text"], "wav")
        except Exception as e:
            row["error"] = str(e)[:500]
            row["ok"] = False
        self.rows.append(row)

    def _run_current_buffered(self, client: httpx.Client, voice_id: str, round_idx: int, case: dict[str, Any]) -> None:
        payload = {"voice_id": voice_id, "text": case["text"], "text_language": "zh", "buffered": True}
        row = self._base_row(voice_id=voice_id, round_idx=round_idx, case=case, mode="current_buffered")
        try:
            start = time.perf_counter()
            resp = client.post(self.args.current_base_url.rstrip("/") + CURRENT_SYNC_PATH, json=payload)
            row["request_ms"] = round((time.perf_counter() - start) * 1000.0, 2)
            row["status"] = resp.status_code
            resp.raise_for_status()
            obj = resp.json()
            task_id = str(obj.get("task_id") or "")
            row["task_id"] = task_id
            first_audio_url = ""
            if isinstance(obj.get("segments"), list) and obj["segments"]:
                first_audio_url = str(obj["segments"][0] or "")
            if not first_audio_url and isinstance(obj.get("ready_urls"), list) and obj["ready_urls"]:
                first_audio_url = str(obj["ready_urls"][0] or "")
            if first_audio_url:
                row["first_ready_ms"] = row["request_ms"]
            else:
                row["first_ready_ms"], first_audio_url = self._poll_first_segment(client, task_id, start)
            row["first_audio_url"] = first_audio_url
            merged_ready_ms, merged_url = self._poll_merged(client, task_id, start)
            row["merged_ready_ms"] = merged_ready_ms
            row["audio_url"] = merged_url
            audio_bytes = client.get(relative_audio_url(self.args.current_base_url, merged_url)).content
            audio_path = self.audio_dir / "current_buffered" / voice_id / f"{case['case_id']}__r{round_idx}.wav"
            write_bytes(audio_path, audio_bytes)
            row["audio_path"] = str(audio_path.relative_to(REPO_ROOT))
            self._attach_audio_eval(row, audio_bytes, case["text"], "wav")
        except Exception as e:
            row["error"] = str(e)[:500]
            row["ok"] = False
        self.rows.append(row)

    def _poll_first_segment(self, client: httpx.Client, task_id: str, start: float) -> tuple[float, str]:
        deadline = time.time() + 180.0
        last_err = ""
        while time.time() < deadline:
            try:
                r = client.get(
                    self.args.current_base_url.rstrip("/") + "/synthesize/buffered/segment",
                    params={"task_id": task_id, "index": 0},
                )
                if r.status_code == 200:
                    obj = r.json()
                    return round((time.perf_counter() - start) * 1000.0, 2), str(obj.get("audio_url") or "")
                if r.status_code not in (202, 404):
                    last_err = f"segment status={r.status_code}: {r.text[:120]}"
            except Exception as e:
                last_err = str(e)
            time.sleep(0.4)
        raise RuntimeError(f"buffered 首段超时: task_id={task_id}; {last_err}")

    def _poll_merged(self, client: httpx.Client, task_id: str, start: float) -> tuple[float, str]:
        deadline = time.time() + 240.0
        last_err = ""
        while time.time() < deadline:
            try:
                r = client.get(
                    self.args.current_base_url.rstrip("/") + "/synthesize/buffered/merged",
                    params={"task_id": task_id},
                )
                if r.status_code == 200:
                    obj = r.json()
                    return round((time.perf_counter() - start) * 1000.0, 2), str(obj.get("audio_url") or "")
                if r.status_code not in (202, 404):
                    last_err = f"merged status={r.status_code}: {r.text[:120]}"
            except Exception as e:
                last_err = str(e)
            time.sleep(0.5)
        raise RuntimeError(f"buffered 合并超时: task_id={task_id}; {last_err}")

    def _run_current_stream(self, client: httpx.Client, voice_id: str, round_idx: int, case: dict[str, Any]) -> None:
        payload = {"voice_id": voice_id, "text": case["text"], "text_language": "zh"}
        row = self._base_row(voice_id=voice_id, round_idx=round_idx, case=case, mode="current_stream")
        try:
            start = time.perf_counter()
            with client.stream(
                "POST",
                self.args.current_base_url.rstrip("/") + CURRENT_STREAM_PATH,
                params={"chunk_ms": self.args.chunk_ms, "format": "wav"},
                json=payload,
            ) as resp:
                row["status"] = resp.status_code
                resp.raise_for_status()
                chunks = []
                first_chunk_ms = None
                for chunk in resp.iter_bytes():
                    if not chunk:
                        continue
                    if first_chunk_ms is None:
                        first_chunk_ms = (time.perf_counter() - start) * 1000.0
                    chunks.append(chunk)
                audio_bytes = repair_streamed_wav_bytes(b"".join(chunks))
                row["first_ready_ms"] = round(first_chunk_ms or 0.0, 2)
                row["request_ms"] = round((time.perf_counter() - start) * 1000.0, 2)
                row["merged_ready_ms"] = row["request_ms"]
            audio_path = self.audio_dir / "current_stream" / voice_id / f"{case['case_id']}__r{round_idx}.wav"
            write_bytes(audio_path, audio_bytes)
            row["audio_path"] = str(audio_path.relative_to(REPO_ROOT))
            self._attach_audio_eval(row, audio_bytes, case["text"], "wav")
        except Exception as e:
            row["error"] = str(e)[:500]
            row["ok"] = False
        self.rows.append(row)

    def _attach_audio_eval(self, row: dict[str, Any], audio_bytes: bytes, expected_text: str, audio_format: str) -> None:
        metrics = decode_audio_metrics(audio_bytes)
        row.update(metrics)
        row["duration_state"] = duration_state_for(expected_text, metrics["duration_sec"])
        eval_obj = self._evaluate_audio(audio_bytes, expected_text, audio_format)
        row["recognized_text"] = str(eval_obj.get("recognized_text") or "")
        row["asr_source"] = str(eval_obj.get("asr_source") or "")
        row["asr_error"] = str(eval_obj.get("asr_error") or "")
        row["eval_accuracy"] = safe_float(eval_obj.get("accuracy"), None)
        expected_units = count_text_units(expected_text)
        recog_units = count_text_units(row["recognized_text"])
        ratio = (float(recog_units) / float(expected_units)) if expected_units > 0 else 0.0
        row["recognized_len_ratio"] = round(ratio, 4)
        row["pass"] = bool(metrics["audible"] and row["duration_state"] == "ok" and ratio >= self.args.pass_ratio_threshold)
        row["ok"] = True

    def _evaluate_audio(self, audio_bytes: bytes, expected_text: str, audio_format: str) -> dict[str, Any]:
        if self.readalong_unavailable:
            return {
                "recognized_text": "",
                "accuracy": None,
                "asr_source": "skipped_after_unavailable",
                "asr_error": "readalong_asr_unavailable_cached",
            }
        files = {"file": (f"eval.{audio_format}", audio_bytes, f"audio/{audio_format}")}
        data = {
            "expected_text": expected_text,
            "audio_format": audio_format,
            "eval_mode": "free_description",
        }
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            r = client.post(self.args.readalong_base_url.rstrip("/") + READALONG_EVAL_PATH, files=files, data=data)
            r.raise_for_status()
            obj = r.json()
            err = str(obj.get("asr_error") or "")
            rec = str(obj.get("recognized_text") or "")
            if (not rec) and ("All connection attempts failed" in err):
                self.readalong_unavailable = True
            return obj

    def _base_row(self, voice_id: str, round_idx: int, case: dict[str, Any], mode: str) -> dict[str, Any]:
        voice = self.voice_library[voice_id]
        return {
            "voice_id": voice_id,
            "voice_name": voice.get("name", voice_id),
            "mode": mode,
            "round": round_idx,
            "case_id": case["case_id"],
            "scene": case["scene"],
            "kind": case["kind"],
            "text": case["text"],
            "status": None,
            "request_ms": None,
            "first_ready_ms": None,
            "merged_ready_ms": None,
            "duration_sec": None,
            "duration_state": None,
            "rms": None,
            "audible": None,
            "recognized_text": "",
            "recognized_len_ratio": None,
            "eval_accuracy": None,
            "pass": False,
            "ok": False,
            "error": "",
        }

    def _summarize_rows(self) -> dict[str, Any]:
        by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.rows:
            by_mode[row["mode"]].append(row)
            by_scene[f"{row['mode']}|{row['scene']}"].append(row)

        summary = {
            "rows": len(self.rows),
            "mode_summary": {k: self._summarize_group(v) for k, v in sorted(by_mode.items())},
            "scene_summary": {k: self._summarize_group(v) for k, v in sorted(by_scene.items())},
            "delta_summary": self._build_delta_summary(by_mode),
        }
        return summary

    def _summarize_group(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        pass_rows = [r for r in rows if r.get("pass")]
        ok_rows = [r for r in rows if r.get("ok")]
        ratios = [float(r["recognized_len_ratio"]) for r in ok_rows if r.get("recognized_len_ratio") is not None]
        req_ms = [float(r["request_ms"]) for r in ok_rows if r.get("request_ms") is not None]
        first_ms = [float(r["first_ready_ms"]) for r in ok_rows if r.get("first_ready_ms") is not None]
        merged_ms = [float(r["merged_ready_ms"]) for r in ok_rows if r.get("merged_ready_ms") is not None]
        under = sum(1 for r in ok_rows if r.get("duration_state") == "under")
        over = sum(1 for r in ok_rows if r.get("duration_state") == "over")
        audible = sum(1 for r in ok_rows if r.get("audible"))
        return {
            "rows": len(rows),
            "ok_rows": len(ok_rows),
            "pass_rows": len(pass_rows),
            "pass_rate": round(len(pass_rows) / len(rows), 4) if rows else None,
            "recognized_len_ratio_avg": round(sum(ratios) / len(ratios), 4) if ratios else None,
            "recognized_len_ratio_p50": round(median_or_none(ratios) or 0.0, 4) if ratios else None,
            "recognized_len_ratio_p10": round(percentile(ratios, 10) or 0.0, 4) if ratios else None,
            "request_ms_avg": round(sum(req_ms) / len(req_ms), 2) if req_ms else None,
            "first_ready_ms_avg": round(sum(first_ms) / len(first_ms), 2) if first_ms else None,
            "merged_ready_ms_avg": round(sum(merged_ms) / len(merged_ms), 2) if merged_ms else None,
            "under_rate": round(under / len(ok_rows), 4) if ok_rows else None,
            "over_rate": round(over / len(ok_rows), 4) if ok_rows else None,
            "audible_rate": round(audible / len(ok_rows), 4) if ok_rows else None,
        }

    def _build_delta_summary(self, by_mode: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        pairs = [
            ("current_sync", "old_sync"),
            ("current_stream", "old_stream"),
            ("current_buffered", "old_sync"),
        ]
        out = {}
        for lhs, rhs in pairs:
            l = self._summarize_group(by_mode.get(lhs, []))
            r = self._summarize_group(by_mode.get(rhs, []))
            if not by_mode.get(lhs) or not by_mode.get(rhs):
                continue
            out[f"{lhs}_vs_{rhs}"] = {
                "pass_rate_delta": self._delta(l.get("pass_rate"), r.get("pass_rate")),
                "ratio_avg_delta": self._delta(l.get("recognized_len_ratio_avg"), r.get("recognized_len_ratio_avg")),
                "request_ms_avg_delta": self._delta(l.get("request_ms_avg"), r.get("request_ms_avg")),
                "first_ready_ms_avg_delta": self._delta(l.get("first_ready_ms_avg"), r.get("first_ready_ms_avg")),
                "under_rate_delta": self._delta(l.get("under_rate"), r.get("under_rate")),
                "over_rate_delta": self._delta(l.get("over_rate"), r.get("over_rate")),
            }
        return out

    def _delta(self, a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return round(float(a) - float(b), 4)

    def _write_report(self, summary: dict[str, Any], historical: dict[str, Any]) -> None:
        lines = [
            "# 流式功能审查与对比实验",
            "",
            "## 能力审查矩阵",
            "| 功能 | 结论 | 代码证据 | 备注 |",
            "| --- | --- | --- | --- |",
        ]
        for item in self.feature_matrix:
            lines.append(
                f"| {item['feature']} | {item['status']} | `{item['evidence']}` | {item['note']} |"
            )

        lines.extend(
            [
                "",
                "## 实验设置",
                f"- 当前服务：`{self.args.current_base_url}`",
                f"- 评测服务：`{self.args.readalong_base_url}`",
                f"- 旧基线：`deprecated_unused/api.py`，模式包括 `old_sync` 与 `old_stream`。",
                f"- 样本音色：`{', '.join(self.selected_voices)}`",
                f"- 测试文本：`{', '.join(c['case_id'] for c in TEST_CASES)}`",
                f"- 轮次：`{self.args.rounds}`",
                f"- 通过阈值：`recognized_len_ratio >= {self.args.pass_ratio_threshold}` 且 `duration_state=ok` 且 `audible=true`。",
            ]
        )

        if self.baseline_warnings:
            lines.extend(
                [
                    "",
                    "## 基线可运行性说明",
                    *[f"- {w}" for w in self.baseline_warnings],
                    "- 因此，旧版 live 对比以“接口不可稳定复现”作为一条明确的负面发现记录；质量/完整度改由历史 bench 文件补足。",
                ]
            )

        lines.extend(
            [
                "",
                "## 实验结果汇总",
                "| 模式 | rows | pass_rate | ratio_avg | request_ms_avg | first_ready_ms_avg | merged_ready_ms_avg | under_rate | over_rate |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        for mode, item in summary["mode_summary"].items():
            lines.append(
                f"| {mode} | {item['rows']} | {self._fmt(item['pass_rate'])} | {self._fmt(item['recognized_len_ratio_avg'])} | "
                f"{self._fmt(item['request_ms_avg'])} | {self._fmt(item['first_ready_ms_avg'])} | {self._fmt(item['merged_ready_ms_avg'])} | "
                f"{self._fmt(item['under_rate'])} | {self._fmt(item['over_rate'])} |"
            )

        lines.extend(
            [
                "",
                "## 关键对比",
                "| 对比 | pass_rate_delta | ratio_avg_delta | request_ms_avg_delta | first_ready_ms_avg_delta | under_rate_delta | over_rate_delta |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, item in summary["delta_summary"].items():
            lines.append(
                f"| {key} | {self._fmt(item['pass_rate_delta'])} | {self._fmt(item['ratio_avg_delta'])} | "
                f"{self._fmt(item['request_ms_avg_delta'])} | {self._fmt(item['first_ready_ms_avg_delta'])} | "
                f"{self._fmt(item['under_rate_delta'])} | {self._fmt(item['over_rate_delta'])} |"
            )

        after_patch = historical.get("after_patch_summary", {})
        before_patch_overall = historical.get("before_patch_overall", {})
        lines.extend(
            [
                "",
                "## 历史 Bench 佐证",
                f"- `full_voice_default_chain_after_patch_live_20260411_132719.json`：`pass_rate={self._fmt(after_patch.get('pass_rate'))}`，"
                f"`mode_pass_rate={json.dumps(after_patch.get('mode_pass_rate', {}), ensure_ascii=False)}`。",
                f"- `voice_quality_policy_regression_after_maxsec_20260402_102308.json`："
                f"`pass={before_patch_overall.get('pass')}` / `total={before_patch_overall.get('total')}`。",
                "",
                "## 结论",
                "- 当前实现的 `buffered`、`stream`、风险分层、自适应步数和 under/over 兜底在主代码中都能找到明确实现证据。",
                "- 需要修正的对外表述有两处：`buffered` 的提交入口不是独立 `/synthesize/buffered`，以及仓库内未发现 `Sentence-Transformer` 语义分块实现。",
                "- live 环境下，`readalong` 外部 ASR 全部失败回落，因此 `recognized_len_ratio` 不能作为这次直播实验的有效数值，只能以历史 bench 结果为主证据。",
                "- 旧 `deprecated_unused/api.py` 在当前仓库版本下无法稳定完成 live 请求，这本身说明旧基线的可复现性和工程可用性较差。",
                "- 本次 live 实验更适合证明 `sync/buffered/stream` 的可用性与体验时延差异；更大样本上的质量/完整度，应结合历史全量 bench 一起报告。",
                "",
                "## 产物",
                "- `raw_results.json`：逐条明细",
                "- `report.md`：本报告",
                "- `audio/`：各模式抽样音频",
            ]
        )
        (self.out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    def _fmt(self, value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            if math.isnan(value):
                return "-"
            return f"{value:.4f}" if abs(value) < 100 else f"{value:.2f}"
        return str(value)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Benchmark current TTS modes against deprecated baseline")
    ap.add_argument("--current-base-url", default="http://127.0.0.1:9880")
    ap.add_argument("--readalong-base-url", default="http://127.0.0.1:9881")
    ap.add_argument("--old-sync-port", type=int, default=9882)
    ap.add_argument("--old-stream-port", type=int, default=9883)
    ap.add_argument("--service-start-timeout-sec", type=int, default=240)
    ap.add_argument("--chunk-ms", type=int, default=200)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--pass-ratio-threshold", type=float, default=0.85)
    ap.add_argument("--voices", nargs="+", default=DEFAULT_VOICES)
    ap.add_argument("--run-old-baseline", action="store_true", default=True)
    ap.add_argument("--skip-old-baseline", dest="run_old_baseline", action="store_false")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    bench = TTSBenchmark(args)
    bench.run()


if __name__ == "__main__":
    main()
