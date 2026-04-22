# -*- coding: utf-8 -*-
"""训练分阶段耗时记录：写入 JSONL，供 profile 与优化分析。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

_CURRENT: Optional["TrainPhaseRecorder"] = None


class TrainPhaseRecorder:
    def __init__(self, jsonl_path: Path):
        self.path = Path(jsonl_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._t0 = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self._t0

    def emit(self, phase: str, duration_sec: float = 0.0, **extra: Any) -> None:
        row: dict[str, Any] = {
            "phase": str(phase),
            "duration_sec": round(float(duration_sec), 4),
            "elapsed_since_run_start_sec": round(self.elapsed(), 4),
        }
        for k, v in extra.items():
            if isinstance(v, Path):
                row[k] = str(v)
            else:
                row[k] = v
        with open(self.path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def set_current(rec: Optional[TrainPhaseRecorder]) -> None:
    global _CURRENT
    _CURRENT = rec


def get_current() -> Optional[TrainPhaseRecorder]:
    return _CURRENT


def emit_subprocess_wall(
    description: str,
    command: list,
    env_cuda_visible: Optional[str],
    return_code: Optional[int],
    wall_sec: float,
    oom_cpu_fallback: bool = False,
) -> None:
    rec = get_current()
    if rec is None:
        return
    script = ""
    if command:
        try:
            script = str(Path(command[0]).name)
        except Exception:
            script = str(command[0])[:120]
    rec.emit(
        "subprocess_wall",
        wall_sec,
        description=description,
        script=script,
        return_code=return_code,
        cuda_visible_devices=env_cuda_visible,
        oom_cpu_fallback=oom_cpu_fallback,
    )
