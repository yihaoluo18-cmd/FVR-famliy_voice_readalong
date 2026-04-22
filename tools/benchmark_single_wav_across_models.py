#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.dnsmos_scorer import score_wav_file  # noqa: E402

MODEL_DIRS = {
    "frcrn_baseline": "anti-noise/baseline_v1",
    "deepfilternet2": "anti-noise/df2_v1",
    "deepfilternet3": "anti-noise/df3_v1",
    "dpdfnet": "anti-noise/dpdfnet_v1",
}


def load_mono(path: Path, target_sr: int) -> Tuple[np.ndarray, int]:
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


def save_spec_panel(before_wav: Path, after_by_model: Dict[str, Path], out_png: Path) -> None:
    # 使用 before 的采样率作为对齐基准
    b, sr = load_mono(before_wav, target_sr=16000)
    panels: List[Tuple[str, np.ndarray]] = [("before", b)]
    for model, p in after_by_model.items():
        y, _ = load_mono(p, target_sr=sr)
        panels.append((model, y))

    # 5 列：before + 4 个模型
    cols = 1 + len(after_by_model)
    fig, axes = plt.subplots(1, cols, figsize=(4 * cols, 4), sharey=True)
    if cols == 1:
        axes = [axes]

    for ax, (title, wav) in zip(axes, panels):
        spec = librosa.amplitude_to_db(
            np.abs(librosa.stft(wav, n_fft=1024, hop_length=256)) + 1e-8,
            ref=np.max,
        )
        librosa.display.specshow(spec, sr=sr, hop_length=256, x_axis="time", y_axis="hz", ax=ax)
        ax.set_title(title)
        ax.grid(False)

    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(out_png), dpi=150)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Single wav benchmark across four models")
    ap.add_argument("--before_wav", type=str, required=True)
    ap.add_argument("--noise_class", type=str, required=True, help="heavy_noise/mid_noise/low_noise")
    ap.add_argument("--out_dir", type=str, default="anti-noise/benchmark_single")
    args = ap.parse_args()

    before_wav = Path(args.before_wav).resolve()
    noise_class = args.noise_class.strip()
    out_dir = Path(args.out_dir).resolve()
    stem = before_wav.stem

    out = out_dir / f"{noise_class}__{stem}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    after_by_model: Dict[str, Path] = {}
    for model, root in MODEL_DIRS.items():
        p = (REPO_ROOT / root / noise_class / before_wav.name).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"missing model output: {p}")
        after_by_model[model] = p

    # copy audio artifacts for convenience
    shutil.copy2(before_wav, out / "before.wav")
    for model, p in after_by_model.items():
        shutil.copy2(p, out / f"after__{model}.wav")

    # metric compute
    # DNSMOS 在本项目使用统一 16k 内部采样率，不要求你事先 resample
    dnsmos_before = float(score_wav_file(before_wav)["OVRL"])
    rows: List[Dict[str, str]] = []
    snr_all: List[float] = []

    # SNR proxy 以 16k 对齐（before 的目标 sr）
    before_y, before_sr = load_mono(before_wav, target_sr=16000)

    for model, after_path in after_by_model.items():
        after_y, _ = load_mono(after_path, target_sr=before_sr)
        snr = snr_proxy(before_y, after_y)
        snr_all.append(snr)
        dnsmos_after = float(score_wav_file(after_path)["OVRL"])
        dnsmos_delta = dnsmos_after - dnsmos_before
        rows.append(
            {
                "noise_class": noise_class,
                "file_name": before_wav.name,
                "model": model,
                "snr_proxy_db": f"{snr:.6f}",
                "dnsmos_before_ovrl": f"{dnsmos_before:.6f}",
                "dnsmos_after_ovrl": f"{dnsmos_after:.6f}",
                "dnsmos_delta": f"{dnsmos_delta:.6f}",
            }
        )

    # spectrogram visualization
    save_spec_panel(out / "before.wav", {m: p for m, p in after_by_model.items()}, out / "spectrogram_panel.png")

    # csv + md report
    csv_path = out / "benchmark_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )
        w.writeheader()
        w.writerows(rows)

    # simple ranking by dnsmos_after
    sorted_rows = sorted(rows, key=lambda r: float(r["dnsmos_after_ovrl"]), reverse=True)
    md_lines = [
        f"# 单样本基准测试：{noise_class}/{before_wav.name}",
        "",
        "## 指标定义",
        "- `SNR proxy`：`10*log10(after_power / (before-after residual power))` 的无参考近似。",
        "- `DNSMOS(OVRL)`：本地 ONNX 离线 DNSMOS 推理结果。",
        "",
        "## 结果（按 DNSMOS after 排序）",
        "| 模型 | SNR proxy(dB) | DNSMOS OVRL(before) | DNSMOS OVRL(after) | delta |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in sorted_rows:
        md_lines.append(
            f"| {r['model']} | {r['snr_proxy_db']} | {r['dnsmos_before_ovrl']} | {r['dnsmos_after_ovrl']} | {r['dnsmos_delta']} |"
        )

    md_lines.extend(
        [
            "",
            "## 产物",
            "- `before.wav`：原始输入样本",
            "- `after__<model>.wav`：四模型处理结果",
            "- `spectrogram_panel.png`：before 与四模型并排频谱图",
            f"- `benchmark_metrics.csv`：指标明细",
        ]
    )
    (out / "benchmark.md").write_text("\n".join(md_lines), encoding="utf-8")

    print(f"done: {out}")


if __name__ == "__main__":
    main()

