#!/usr/bin/env python3
"""
将目录内所有 wav 的响度与参考文件对齐（默认：整体 RMS 电平 dBFS 一致）。
未安装 pyloudnorm 时使用 RMS，与「统一分贝」的工程含义一致。

可选：将误命名为 *.wav.wav 的文件重命名为 *.wav
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def load_mono_float(path: Path) -> tuple[np.ndarray, int]:
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    return y, sr


def rms_dbfs(x: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(np.square(x)) + 1e-20))
    return 20.0 * np.log10(r + 1e-20)


def apply_gain_db(x: np.ndarray, gain_db: float) -> np.ndarray:
    g = 10.0 ** (gain_db / 20.0)
    return (x * g).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--reference",
        type=str,
        required=True,
        help="参考音频路径（以此文件的 RMS/dBFS 为目标）",
    )
    ap.add_argument(
        "--root",
        type=str,
        default="anti-noise/dataset",
        help="递归处理该目录下所有 .wav",
    )
    ap.add_argument(
        "--fix_double_wav",
        action="store_true",
        help="将 *.wav.wav 重命名为 *.wav（处理完响度后）",
    )
    ap.add_argument(
        "--peak_ceiling",
        type=float,
        default=0.99,
        help="防削波：若增益后峰值超过该值则整体再衰减（可能略偏离目标 RMS）",
    )
    args = ap.parse_args()

    ref_path = Path(args.reference).resolve()
    root = Path(args.root).resolve()
    y_ref, sr_ref = load_mono_float(ref_path)
    target_db = rms_dbfs(y_ref)
    print(f"参考: {ref_path}")
    print(f"参考 RMS: {target_db:.3f} dBFS (近似响度对齐目标)")

    paths = sorted(root.rglob("*.wav"))
    n = 0
    for p in paths:
        try:
            y, sr = load_mono_float(p)
        except Exception as e:
            print(f"SKIP load {p}: {e}")
            continue
        if sr != sr_ref:
            y = librosa.resample(y, orig_sr=sr, target_sr=sr_ref)
            sr = sr_ref
        cur_db = rms_dbfs(y)
        delta_db = float(target_db - cur_db)
        y2 = apply_gain_db(y, delta_db)
        peak = float(np.max(np.abs(y2)))
        if peak > args.peak_ceiling:
            y2 = (y2 * (args.peak_ceiling / peak)).astype(np.float32)
        out_path = p
        if args.fix_double_wav and p.name.endswith(".wav.wav"):
            out_path = p.with_name(p.name[: -len(".wav")])  # strip one .wav
            if out_path == p:
                out_path = Path(str(p) + ".fixed.wav")

        fd, tmp = tempfile.mkstemp(suffix=".wav", dir=str(out_path.parent))
        import os

        os.close(fd)
        try:
            sf.write(tmp, y2, sr_ref, subtype="PCM_16")
            os.replace(tmp, str(out_path))
            if out_path != p and p.exists():
                p.unlink()
        except Exception:
            if Path(tmp).exists():
                Path(tmp).unlink()
            raise
        n += 1
        if n % 20 == 0:
            print(f"  ... {n} files")
    print(f"完成: 已处理 {n} 个文件（含参考文件自身会再写一遍，结果不变）")


if __name__ == "__main__":
    main()
