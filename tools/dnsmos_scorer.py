"""
本地 DNSMOS（ONNX）封装：使用 tools/dnsmos_offline 下的权重与官方 dnsmos_local.ComputeScore。
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

_DNSMOS_ROOT = Path(__file__).resolve().parent / "dnsmos_offline"
_SRC = _DNSMOS_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@lru_cache(maxsize=1)
def _load_compute_score():
    from dnsmos_local import ComputeScore  # type: ignore

    models = _DNSMOS_ROOT / "models"
    primary = models / "sig_bak_ovr.onnx"
    p808 = models / "model_v8.onnx"
    if not primary.is_file() or not p808.is_file():
        raise FileNotFoundError(f"DNSMOS ONNX 缺失: {primary} / {p808}")
    return ComputeScore(str(primary), str(p808))


def score_wav_file(path: Path, personalized_mos: bool = False) -> Dict[str, Any]:
    """
    对单个 wav 计算 DNSMOS。返回含 OVRL/SIG/BAK 等字段的字典（见 dnsmos_local.ComputeScore.__call__）。
    """
    cs = _load_compute_score()
    return cs(str(path.resolve()), 16000, personalized_mos)


def score_wav_ovrl(path: Path, personalized_mos: bool = False) -> Optional[float]:
    d = score_wav_file(path, personalized_mos=personalized_mos)
    v = d.get("OVRL")
    return float(v) if v is not None else None
