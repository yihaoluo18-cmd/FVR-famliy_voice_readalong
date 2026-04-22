#!/usr/bin/env python3
"""
从 user_datasets 收集全部 wav，按「估计伪 SNR + 语音活跃度」粗分档，
复制到 anti-noise/dataset/{low_noise,mid_noise,heavy_noise,rejected_no_clear_speech}，
并写出 manifest.jsonl 供人工复核。

说明：分类为启发式，不等价于真实 SNR 或 DNSMOS；阈值可在命令行调整。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import minimum_filter

DEFAULT_USER_ROOT = "user_datasets"
DEFAULT_OUT = "anti-noise/dataset"


def _load_mono_16k(path: Path) -> Tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    if sr != 16000:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        sr = 16000
    return audio, sr


def estimate_pseudo_snr_db(y: np.ndarray, sr: int = 16000) -> float:
    """最小统计法：沿时间维对每频点做 min-filter 得噪声 PSD，再估帧级 SNR 取中位数。"""
    n_fft = 1024
    hop = 256
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop, center=True))
    power = np.maximum(S.astype(np.float64) ** 2, 1e-20)
    # 时间方向最小滤波（奇数核）
    noise_psd = minimum_filter(power, size=(1, 31), mode="nearest")
    sig_power = np.sum(power, axis=0)
    noise_power = np.sum(noise_psd, axis=0)
    snr_frames = sig_power / np.maximum(noise_power, 1e-20)
    snr_db = 10.0 * np.log10(np.maximum(snr_frames, 1e-10))
    return float(np.median(snr_db))


def speech_active_ratio(y: np.ndarray, sr: int = 16000) -> float:
    """300–3400 Hz 带内帧能量相对底噪的活跃比例，用于粗判是否有人声。"""
    n_fft = 400
    hop = 160
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop, center=True))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = (freqs >= 300) & (freqs <= 3400)
    frame_e = np.sum(S[band, :] ** 2, axis=0)
    if frame_e.size == 0:
        return 0.0
    floor = float(np.percentile(frame_e, 15))
    active = frame_e > max(floor * 4.0, 1e-12)
    return float(np.mean(active))


def safe_stem(rel: Path, max_len: int = 180) -> str:
    s = str(rel).replace("\\", "__").replace("/", "__")
    s = re.sub(r"[^0-9A-Za-z._\-]", "_", s)
    if len(s) > max_len:
        h = hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:10]
        s = s[: max_len - 11] + "_" + h
    return s


def classify(
    snr_db: float,
    low_th: float,
    mid_th: float,
) -> str:
    if snr_db >= low_th:
        return "low_noise"
    if snr_db >= mid_th:
        return "mid_noise"
    return "heavy_noise"


def hf_hiss_ratio(y: np.ndarray, sr: int = 16000) -> float:
    """4–8 kHz 能量占 80 Hz–8 kHz 的比例，偏高多偏嘈杂/嘶声（粗指标）。"""
    n_fft = 1024
    hop = 256
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop, center=True))
    power = S**2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    full = (freqs >= 80) & (freqs <= 8000)
    hf = (freqs >= 4000) & (freqs <= 8000)
    e_full = float(np.sum(power[full, :]))
    e_hf = float(np.sum(power[hf, :]))
    if e_full < 1e-20:
        return 0.0
    return e_hf / e_full


def combined_score(snr_db: float, hiss: float, hiss_weight: float = 25.0) -> float:
    """综合分：伪 SNR 降低、嘶声升高 → 分数更低 → 更噪。"""
    return snr_db - hiss_weight * hiss


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user_root", type=str, default=DEFAULT_USER_ROOT)
    ap.add_argument("--out_dir", type=str, default=DEFAULT_OUT)
    ap.add_argument(
        "--strategy",
        type=str,
        choices=["threshold", "quantile", "combined_threshold"],
        default="quantile",
        help="threshold: 固定 dB 阈值；quantile: 按综合分三分位；combined_threshold: 用伪SNR-加权嘶声后固定阈值",
    )
    ap.add_argument("--low_th", type=float, default=12.0, help="strategy=threshold 时 >= 判 low_noise")
    ap.add_argument("--mid_th", type=float, default=5.0, help="strategy=threshold 时 mid 区间下界")
    ap.add_argument("--combined_low_th", type=float, default=8.0, help="combined_threshold: >= 判 low")
    ap.add_argument("--combined_mid_th", type=float, default=2.0, help="combined_threshold: >= 判 mid")
    ap.add_argument("--hiss_weight", type=float, default=25.0, help="combined_* 中嘶声项权重")
    ap.add_argument("--min_duration_s", type=float, default=0.25)
    ap.add_argument("--min_speech_ratio", type=float, default=0.12, help="低于则 rejected")
    ap.add_argument("--min_peak", type=float, default=1e-5, help="峰值过低视为无效")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    user_root = Path(args.user_root).resolve()
    out_root = Path(args.out_dir).resolve()

    subdirs = ["low_noise", "mid_noise", "heavy_noise", "rejected_no_clear_speech", "_legacy_baseline_samples"]
    for d in subdirs:
        (out_root / d).mkdir(parents=True, exist_ok=True)

    # 旧版放在 dataset 根目录的 baseline 小样本移到 _legacy，避免与分类目录混淆
    legacy_dir = out_root / "_legacy_baseline_samples"
    for wav in list(out_root.glob("*.wav")):
        if not args.dry_run:
            shutil.move(str(wav), str(legacy_dir / wav.name))

    wavs: List[Path] = sorted(user_root.rglob("*.wav"))
    manifest_path = out_root / "manifest.jsonl"
    meta = {
        "version": 2,
        "strategy": args.strategy,
        "user_root": str(user_root),
        "low_th_db": args.low_th,
        "mid_th_db": args.mid_th,
        "combined_low_th": args.combined_low_th,
        "combined_mid_th": args.combined_mid_th,
        "hiss_weight": args.hiss_weight,
        "min_duration_s": args.min_duration_s,
        "min_speech_ratio": args.min_speech_ratio,
        "note": "quantile: 按 combined_score 三分位；threshold: 仅伪SNR；combined_threshold: 伪SNR-加权嘶声。仅供粗分，请人工复核",
    }
    (out_root / "classification_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for d in ("low_noise", "mid_noise", "heavy_noise", "rejected_no_clear_speech"):
        p = out_root / d
        if p.exists() and not args.dry_run:
            for child in p.iterdir():
                if child.is_file():
                    child.unlink()

    records: List[Dict] = []
    for src in wavs:
        rel = src.relative_to(user_root)
        # 避免路径里已含 .wav 时再拼一次变成 *.wav.wav
        rel_for_name = rel.with_suffix("") if rel.suffix.lower() == ".wav" else rel
        out_name = safe_stem(rel_for_name) + ".wav"
        row: Dict = {
            "source": str(src),
            "rel_path": str(rel),
            "out_name": out_name,
        }
        try:
            y, sr = _load_mono_16k(src)
        except Exception as e:
            row["error"] = f"load_failed:{e}"
            row["bucket"] = "rejected_no_clear_speech"
            records.append(row)
            continue

        dur = len(y) / float(sr)
        peak = float(np.max(np.abs(y)))
        snr_db = estimate_pseudo_snr_db(y, sr)
        sp_ratio = speech_active_ratio(y, sr)
        hiss = hf_hiss_ratio(y, sr)
        score = combined_score(snr_db, hiss, args.hiss_weight)

        row["duration_s"] = round(dur, 4)
        row["peak"] = peak
        row["pseudo_snr_median_db"] = round(snr_db, 3)
        row["speech_active_ratio"] = round(sp_ratio, 4)
        row["hf_hiss_ratio"] = round(hiss, 4)
        row["combined_score"] = round(score, 3)

        if dur < args.min_duration_s or peak < args.min_peak:
            row["bucket"] = "rejected_no_clear_speech"
            row["reject_reason"] = "too_short_or_silent"
        elif sp_ratio < args.min_speech_ratio:
            row["bucket"] = "rejected_no_clear_speech"
            row["reject_reason"] = "low_speech_activity"
        else:
            row["bucket"] = None  # 待分配
        records.append(row)

    # 对 bucket 仍为 None 的样本分档（低分 combined_score = 更噪 → heavy）
    accepted = [r for r in records if r.get("bucket") is None]

    def assign_combined_threshold() -> None:
        for r in records:
            if r.get("bucket") is not None:
                continue
            sc = float(r["combined_score"])
            if sc >= args.combined_low_th:
                r["bucket"] = "low_noise"
            elif sc >= args.combined_mid_th:
                r["bucket"] = "mid_noise"
            else:
                r["bucket"] = "heavy_noise"

    if args.strategy == "quantile" and len(accepted) >= 3:
        accepted_sorted = sorted(accepted, key=lambda r: float(r["combined_score"]))
        n = len(accepted_sorted)
        t1 = n // 3
        t2 = (2 * n) // 3
        for i, r in enumerate(accepted_sorted):
            if i < t1:
                r["bucket"] = "heavy_noise"
            elif i < t2:
                r["bucket"] = "mid_noise"
            else:
                r["bucket"] = "low_noise"
            r["quantile_rank"] = i + 1
            r["quantile_n"] = n
    elif args.strategy == "quantile" and len(accepted) < 3:
        for r in records:
            if r.get("bucket") is None:
                r["note"] = "quantile_fallback_lt3_samples"
        assign_combined_threshold()
    elif args.strategy == "threshold":
        for r in records:
            if r.get("bucket") is not None:
                continue
            r["bucket"] = classify(float(r["pseudo_snr_median_db"]), args.low_th, args.mid_th)
    elif args.strategy == "combined_threshold":
        assign_combined_threshold()

    counts: Dict[str, int] = {}
    for k in ("low_noise", "mid_noise", "heavy_noise", "rejected_no_clear_speech"):
        counts[k] = 0

    with manifest_path.open("w", encoding="utf-8") as mf:
        for row in records:
            if row.get("bucket") is None:
                row["bucket"] = "rejected_no_clear_speech"
                row["reject_reason"] = row.get("reject_reason", "unclassified")
            if not args.dry_run:
                src_path = Path(row["source"])
                dst = out_root / row["bucket"] / row["out_name"]
                try:
                    shutil.copy2(src_path, dst)
                except Exception as exc:
                    row["copy_error"] = str(exc)
            counts[row["bucket"]] = counts.get(row["bucket"], 0) + 1
            mf.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {**meta, "total_scanned": len(wavs), "counts": counts}
    (out_root / "classification_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
