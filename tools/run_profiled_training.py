#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单次训练 + 分阶段耗时 JSONL（由 train_api 写入 *_phases.jsonl）。

用法（项目根目录）:
  TRAIN_SKIP_VOICE_REGISTRATION=1 ./venv/bin/python tools/run_profiled_training.py

可选:
  TRAIN_PROFILE_FAST=1   # TrainParams.fast_mode，缩短 S1/S2 轮数（仍跑全链路）
  TRAIN_PROFILE_USER=dev_local_phone_13318752322
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "modules" / "tts_backend"))
    os.environ.setdefault("TRAIN_SKIP_VOICE_REGISTRATION", "1")

    from train_api import TrainParams, run_training, train_tasks  # noqa: E402

    user_id = os.environ.get("TRAIN_PROFILE_USER", "dev_local_phone_13318752322").strip()
    dataset_path = ROOT / "user_datasets" / user_id / "v2Pro"
    if not dataset_path.is_dir():
        print(f"数据集目录不存在: {dataset_path}")
        return 2

    task_id = str(uuid.uuid4())
    short = task_id[:8]
    output_path = ROOT / "user_models" / user_id / f"profile_timing_{short}"
    output_path.mkdir(parents=True, exist_ok=True)
    log_path = output_path / "train.log"
    phases_path = output_path / "train_phases.jsonl"

    ref_wav = dataset_path / "sentence_0.wav"
    ref_txt_p = dataset_path / "sentence_0.txt"
    ref_text = ref_txt_p.read_text(encoding="utf-8").strip()[:500] if ref_txt_p.exists() else ""

    train_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "message": "",
        "version": "v2Pro",
        "model_name": f"profile_{short}",
        "ref_audio_path": str(ref_wav) if ref_wav.exists() else "",
        "ref_text": ref_text,
        "ref_language": "中文",
    }

    fast = os.environ.get("TRAIN_PROFILE_FAST", "0").strip() == "1"
    params = TrainParams(
        user_id=user_id,
        model_version="v2Pro",
        fast_mode=fast,
    )

    print(f"dataset_path={dataset_path}")
    print(f"output_path={output_path}")
    print(f"log_path={log_path}")
    print(f"fast_mode={fast} (设置 TRAIN_PROFILE_FAST=1 可缩短 S1/S2)")
    wall0 = time.perf_counter()
    run_training(task_id, str(dataset_path), str(output_path), str(log_path), params)
    wall1 = time.perf_counter()
    total_sec = wall1 - wall0

    print(f"\n=== 总 wall 时间（含 Python 开销）: {total_sec:.2f}s ({total_sec/60:.2f} min) ===")
    print(f"任务状态: {train_tasks.get(task_id, {}).get('status')}")
    print(f"分阶段 JSONL: {phases_path}")

    if phases_path.exists():
        summarize_phases(phases_path, total_sec)
    return 0 if train_tasks.get(task_id, {}).get("status") == "completed" else 1


def summarize_phases(jsonl_path: Path, total_wall: float) -> None:
    rows = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    by_phase = defaultdict(float)
    subprocess_rows = []
    for r in rows:
        ph = r.get("phase", "")
        if ph == "subprocess_wall":
            subprocess_rows.append(r)
            by_phase[r.get("description", "subprocess")] += float(r.get("duration_sec", 0) or 0)
        else:
            by_phase[ph] += float(r.get("duration_sec", 0) or 0)

    print("\n--- 按 phase 汇总 duration_sec（同类多行会相加）---")
    for k in sorted(by_phase.keys(), key=lambda x: -by_phase[x]):
        print(f"  {k}: {by_phase[k]:.2f}s")

    print("\n--- 子进程（subprocess_wall）明细 ---")
    for r in subprocess_rows:
        print(
            f"  {r.get('duration_sec', 0):.2f}s  rc={r.get('return_code')}  "
            f"cuda={r.get('cuda_visible_devices')}  {r.get('description', '')[:80]}"
        )

    run_end = next((r for r in rows if r.get("phase") == "run_finished_wall"), None)
    if run_end:
        print(f"\nrun_finished_wall 记录总耗时: {run_end.get('duration_sec')}s, status={run_end.get('final_task_status')}")
    print(f"\n对照: 脚本测得总 wall: {total_wall:.2f}s")


if __name__ == "__main__":
    raise SystemExit(main())
