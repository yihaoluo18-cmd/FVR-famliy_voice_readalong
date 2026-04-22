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


DF2_DIR = "anti-noise/df2_v1"
DF3_DIR = "anti-noise/df3_v1"
BEFORE_ROOT = "anti-noise/dataset_reindexed/heavy_noise"


def load_mono(path: Path, target_sr: int) -> Tuple[np.ndarray, int]:
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    if sr != target_sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return y, sr


def snr_proxy(before_y: np.ndarray, after_y: np.ndarray) -> float:
    n = min(len(before_y), len(after_y))
    b = before_y[:n]
    a = after_y[:n]
    noise = b - a
    denom = float(np.mean(noise**2)) + 1e-9
    numer = float(np.mean(a**2)) + 1e-9
    return 10.0 * math.log10(numer / denom)


def save_panel(before_wav: Path, df2_wav: Path, df3_wav: Path, out_png: Path) -> None:
    # 频谱以 16k 对齐，确保横向可比较
    target_sr = 16000
    before_y, sr = load_mono(before_wav, target_sr)
    df2_y, _ = load_mono(df2_wav, target_sr)
    df3_y, _ = load_mono(df3_wav, target_sr)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    titles = ["before", "deepfilternet2 (net2)", "deepfilternet3 (net3)"]
    waves = [before_y, df2_y, df3_y]
    for ax, title, y in zip(axes, titles, waves):
        spec = librosa.amplitude_to_db(
            np.abs(librosa.stft(y, n_fft=1024, hop_length=256)) + 1e-8,
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
    ap = argparse.ArgumentParser(description="Compare DeepFilterNet2 vs 3 on heavy_noise set")
    ap.add_argument(
        "--files",
        nargs="+",
        default=["heavy_noise_0005.wav", "heavy_noise_0009.wav", "heavy_noise_0023.wav", "heavy_noise_0028.wav"],
        help="List of wav basenames under anti-noise/dataset_reindexed/heavy_noise/",
    )
    ap.add_argument("--out_dir", default="anti-noise/benchmark_df2_vs_df3_heavy")
    ap.add_argument("--skip_copy_audio", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    before_root = (REPO_ROOT / BEFORE_ROOT).resolve()
    df2_root = (REPO_ROOT / DF2_DIR).resolve()
    df3_root = (REPO_ROOT / DF3_DIR).resolve()

    rows: List[Dict[str, str]] = []
    for i, fname in enumerate(args.files, 1):
        before_wav = before_root / fname
        df2_wav = df2_root / "heavy_noise" / fname
        df3_wav = df3_root / "heavy_noise" / fname
        if not before_wav.is_file():
            raise FileNotFoundError(f"before wav missing: {before_wav}")
        if not df2_wav.is_file():
            raise FileNotFoundError(f"df2 wav missing: {df2_wav}")
        if not df3_wav.is_file():
            raise FileNotFoundError(f"df3 wav missing: {df3_wav}")

        target_sr = 16000
        before_y, _ = load_mono(before_wav, target_sr)
        df2_y, _ = load_mono(df2_wav, target_sr)
        df3_y, _ = load_mono(df3_wav, target_sr)

        snr2 = snr_proxy(before_y, df2_y)
        snr3 = snr_proxy(before_y, df3_y)

        dnsmos_before = float(score_wav_file(before_wav)["OVRL"])
        dnsmos2 = float(score_wav_file(df2_wav)["OVRL"])
        dnsmos3 = float(score_wav_file(df3_wav)["OVRL"])

        delta2 = dnsmos2 - dnsmos_before
        delta3 = dnsmos3 - dnsmos_before

        sample_out = out_dir / fname.replace(".wav", "")
        sample_out.mkdir(parents=True, exist_ok=True)
        if not args.skip_copy_audio:
            shutil.copy2(before_wav, sample_out / "before.wav")
            shutil.copy2(df2_wav, sample_out / "after__net2.wav")
            shutil.copy2(df3_wav, sample_out / "after__net3.wav")

        save_panel(
            sample_out / "before.wav" if not args.skip_copy_audio else before_wav,
            sample_out / "after__net2.wav" if not args.skip_copy_audio else df2_wav,
            sample_out / "after__net3.wav" if not args.skip_copy_audio else df3_wav,
            sample_out / "spectrogram_panel.png",
        )

        winner = "net2" if (dnsmos2 > dnsmos3) else ("net3" if (dnsmos3 > dnsmos2) else "tie")
        rows.append(
            {
                "file_name": fname,
                "dnsmos_before_ovrl": f"{dnsmos_before:.6f}",
                "net2_dnsmos_after_ovrl": f"{dnsmos2:.6f}",
                "net2_dnsmos_delta": f"{delta2:.6f}",
                "net3_dnsmos_after_ovrl": f"{dnsmos3:.6f}",
                "net3_dnsmos_delta": f"{delta3:.6f}",
                "net2_snr_proxy_db": f"{snr2:.6f}",
                "net3_snr_proxy_db": f"{snr3:.6f}",
                "dns_winner_by_after": winner,
            }
        )
        print(f"[{i}/{len(args.files)}] {fname} ok")

    csv_path = out_dir / "df2_vs_df3_heavy_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 汇总报告（给科研说明用）
    def avg(key: str) -> float:
        return sum(float(r[key]) for r in rows) / max(1, len(rows))

    avg2 = avg("net2_dnsmos_after_ovrl")
    avg3 = avg("net3_dnsmos_after_ovrl")
    avg_delta2 = avg("net2_dnsmos_delta")
    avg_delta3 = avg("net3_dnsmos_delta")
    avg_snr2 = avg("net2_snr_proxy_db")
    avg_snr3 = avg("net3_snr_proxy_db")

    net2_wins = sum(1 for r in rows if r["dns_winner_by_after"] == "net2")
    net3_wins = sum(1 for r in rows if r["dns_winner_by_after"] == "net3")
    ties = len(rows) - net2_wins - net3_wins

    best = "net2" if avg2 > avg3 else ("net3" if avg3 > avg2 else "tie")

    md = out_dir / "final_report.md"
    md.write_text(
        "\n".join(
            [
                "# heavy_noise 场景：DeepFilterNet2(net2) vs DeepFilterNet3(net3) 对比",
                "",
                "## 实验设置",
                "- 输入：同一条 `heavy_noise` 音频分别送入 net2 与 net3。",
                "- 指标：SNR proxy、DNSMOS(OVRL) before/after 与 delta。",
                "",
                "## 逐样本结果",
                "| 文件 | net2 DNSMOS after | net2 delta | net3 DNSMOS after | net3 delta | SNR proxy(net2) | SNR proxy(net3) | winner |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
                *[
                    f"| {r['file_name']} | {r['net2_dnsmos_after_ovrl']} | {r['net2_dnsmos_delta']} | {r['net3_dnsmos_after_ovrl']} | {r['net3_dnsmos_delta']} | {r['net2_snr_proxy_db']} | {r['net3_snr_proxy_db']} | {r['dns_winner_by_after']} |"
                    for r in rows
                ],
                "",
                "## 汇总（均值）",
                f"- DNSMOS after：net2={avg2:.4f}，net3={avg3:.4f}",
                f"- DNSMOS delta：net2={avg_delta2:.4f}，net3={avg_delta3:.4f}",
                f"- SNR proxy(dB)：net2={avg_snr2:.4f}，net3={avg_snr3:.4f}",
                f"- 逐样本胜出次数：net2={net2_wins}，net3={net3_wins}，tie={ties}",
                "",
                "## 结论建议（科研表述）",
                f"- 在当前选取的 heavy_noise 样本上，按 DNSMOS(OVRL) after 的均值，推荐选择：**{best}**。",
                "- 你可以在论文中强调：net2 与 net3 使用同一输入集合，对比结果更具公平性；并配合每条样本的 `spectrogram_panel.png` 作为定性证据。",
                "",
                "## 产物",
                "- `df2_vs_df3_heavy_metrics.csv`：逐样本指标明细",
                "- 每个样本目录：`spectrogram_panel.png` 与（可选）before/after 音频",
            ]
        ),
        encoding="utf-8",
    )

    print(f"done: {out_dir}")


if __name__ == "__main__":
    main()

