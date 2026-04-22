#!/usr/bin/env python3
"""
在 anti-noise/comparison 下生成四模型横向对比包：
- 每模型每噪声等级选 2 条典型样本（按 SNR 代理分数接近中位数）
- 导出 before/after 音频与频谱图
- 导出对比表（含 SNR、DNSMOS 字段、人工评分模板与加权规则）
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf


MODEL_DIRS = {
    "frcrn_baseline": "anti-noise/baseline_v1",
    "deepfilternet2": "anti-noise/df2_v1",
    "deepfilternet3": "anti-noise/df3_v1",
    "dpdfnet": "anti-noise/dpdfnet_v1",
}
NOISE_CLASSES = ["heavy_noise", "mid_noise", "low_noise"]


@dataclass
class Row:
    model: str
    noise_class: str
    file_name: str
    before_path: Path
    after_path: Path
    snr_proxy_db: float
    dnsmos_before: Optional[float]
    dnsmos_after: Optional[float]
    selected_rank: int = 0


def load_mono(path: Path, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    if sr != target_sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return y, sr


def snr_proxy(before: np.ndarray, after: np.ndarray) -> float:
    n = min(len(before), len(after))
    b = before[:n]
    a = after[:n]
    noise = b - a
    denom = float(np.mean(noise**2)) + 1e-9
    numer = float(np.mean(a**2)) + 1e-9
    return 10.0 * math.log10(numer / denom)


def save_spec(y: np.ndarray, sr: int, out_png: Path) -> None:
    spec = librosa.amplitude_to_db(
        np.abs(librosa.stft(y, n_fft=1024, hop_length=256)) + 1e-8, ref=np.max
    )
    plt.figure(figsize=(8, 3))
    librosa.display.specshow(spec, sr=sr, hop_length=256, x_axis="time", y_axis="hz")
    plt.colorbar(format="%+2.0f dB")
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(out_png), dpi=120)
    plt.close()


def pick_typical(rows: List[Row], k: int = 2) -> List[Row]:
    if not rows:
        return []
    vals = sorted(r.snr_proxy_db for r in rows)
    median = vals[len(vals) // 2]
    picked = sorted(rows, key=lambda r: abs(r.snr_proxy_db - median))[:k]
    return picked


def build_rows(dataset_root: Path, model_root: Path, model_name: str) -> List[Row]:
    out: List[Row] = []
    for cls in NOISE_CLASSES:
        before_dir = dataset_root / cls
        after_dir = model_root / cls
        for before in sorted(before_dir.glob("*.wav")):
            after = after_dir / before.name
            if not after.exists():
                continue
            yb, _ = load_mono(before)
            ya, _ = load_mono(after)
            out.append(
                Row(
                    model=model_name,
                    noise_class=cls,
                    file_name=before.name,
                    before_path=before,
                    after_path=after,
                    snr_proxy_db=snr_proxy(yb, ya),
                    dnsmos_before=None,
                    dnsmos_after=None,
                )
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_root", default="anti-noise/dataset_reindexed")
    ap.add_argument("--out_dir", default="anti-noise/comparison")
    ap.add_argument("--samples_per_class", type=int, default=2)
    ap.add_argument("--manual_weight", type=float, default=0.6)
    ap.add_argument("--dnsmos_weight", type=float, default=0.3)
    ap.add_argument("--snr_weight", type=float, default=0.1)
    args = ap.parse_args()

    dataset_root = Path(args.dataset_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_dir = out_dir / "samples"
    if sample_dir.exists():
        shutil.rmtree(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[Row] = []
    for model_name, model_path in MODEL_DIRS.items():
        rows = build_rows(dataset_root, Path(model_path).resolve(), model_name)
        for cls in NOISE_CLASSES:
            cls_rows = [r for r in rows if r.noise_class == cls]
            picked = pick_typical(cls_rows, k=args.samples_per_class)
            for i, r in enumerate(picked, 1):
                r.selected_rank = i
                all_rows.append(r)

    # 导出样本与频谱
    export_rows: List[Dict[str, str]] = []
    for r in all_rows:
        tag = f"{r.model}__{r.noise_class}__r{r.selected_rank:02d}__{r.file_name}"
        before_wav = sample_dir / f"{tag}__before.wav"
        after_wav = sample_dir / f"{tag}__after.wav"
        shutil.copy2(r.before_path, before_wav)
        shutil.copy2(r.after_path, after_wav)
        yb, sr = load_mono(before_wav)
        ya, _ = load_mono(after_wav, target_sr=sr)
        before_png = sample_dir / f"{tag}__before_spec.png"
        after_png = sample_dir / f"{tag}__after_spec.png"
        save_spec(yb, sr, before_png)
        save_spec(ya, sr, after_png)
        export_rows.append(
            {
                "model": r.model,
                "noise_class": r.noise_class,
                "file_name": r.file_name,
                "selected_rank": str(r.selected_rank),
                "snr_proxy_db": f"{r.snr_proxy_db:.6f}",
                "dnsmos_before": "",
                "dnsmos_after": "",
                "manual_score_0_10": "",
                "weighted_total": "",
                "before_wav": str(before_wav.relative_to(out_dir)),
                "after_wav": str(after_wav.relative_to(out_dir)),
                "before_spec": str(before_png.relative_to(out_dir)),
                "after_spec": str(after_png.relative_to(out_dir)),
            }
        )

    csv_path = out_dir / "comparison_table.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "model",
                "noise_class",
                "file_name",
                "selected_rank",
                "snr_proxy_db",
                "dnsmos_before",
                "dnsmos_after",
                "manual_score_0_10",
                "weighted_total",
                "before_wav",
                "after_wav",
                "before_spec",
                "after_spec",
            ],
        )
        writer.writeheader()
        writer.writerows(export_rows)

    config = {
        "weights": {
            "manual_score_weight": args.manual_weight,
            "dnsmos_weight": args.dnsmos_weight,
            "snr_weight": args.snr_weight,
        },
        "formula_note": (
            "推荐先将 manual_score(0~10)、dnsmos_after(0~5)、snr_proxy_db(按当前样本 min-max 归一化到 0~10) "
            "统一映射到 0~10，再按权重相加。权重要求：人工打分 > DNSMOS > SNR。"
        ),
        "selected_samples_count": len(export_rows),
    }
    (out_dir / "scoring_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# 四模型人声提纯典型样本对比",
        "",
        "- 目标：每模型在 low/mid/heavy 三类中各选 2 条典型样本，共 24 条。",
        "- 已包含：before/after 音频、before/after 频谱图、SNR 代理分数、DNSMOS 字段（待填）。",
        "- 人工评分：请在 `comparison_table.csv` 的 `manual_score_0_10` 列填写 0~10 分。",
        "- 加权建议：manual=0.6, dnsmos=0.3, snr=0.1（满足 人工 > DNSMOS > SNR）。",
        "",
        "## 文件",
        "- `comparison_table.csv`：样本清单与评分表",
        "- `samples/`：全部样本音频与频谱图",
        "- `scoring_config.json`：权重与公式说明",
    ]
    (out_dir / "README.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"done: {out_dir}")


if __name__ == "__main__":
    main()
