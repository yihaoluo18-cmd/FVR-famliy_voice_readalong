#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 中文字体优先（如果系统没该字体会回退到英文）
mpl.rcParams["font.sans-serif"] = [
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Serif CJK SC",
]
mpl.rcParams["axes.unicode_minus"] = False

MODEL_LABELS = {
    "deepfilternet2": "NET2",
    "deepfilternet3": "NET3",
    "frcrn_baseline": "Baseline",
    "dpdfnet": "DPDFNet",
}
MODEL_COLORS = {
    "deepfilternet2": "#1f4e79",
    "deepfilternet3": "#b04a4a",
    "frcrn_baseline": "#7b7b7b",
    "dpdfnet": "#7a60a8",
}
MODEL_ORDER = ["deepfilternet2", "deepfilternet3", "frcrn_baseline", "dpdfnet"]
NOISE_CLASSES = ["low_noise", "mid_noise", "heavy_noise"]
NOISE_LABELS = {"low_noise": "低噪声", "mid_noise": "中噪声", "heavy_noise": "高噪声"}


def _minmax_norm(vals: Dict[str, float]) -> Dict[str, float]:
    ks = list(vals.keys())
    vs = np.array([float(vals[k]) for k in ks], dtype=float)
    lo = float(np.min(vs))
    hi = float(np.max(vs))
    if hi <= lo:
        return {k: 50.0 for k in ks}
    out: Dict[str, float] = {}
    for k in ks:
        out[k] = (float(vals[k]) - lo) / (hi - lo) * 100.0
    return out


def suitability_by_noise_class(class_df: pd.DataFrame, noise_class: str) -> Dict[str, float]:
    # class_df：仅该 noise_class 的数据
    agg = class_df.groupby("model").agg(
        dnsmos_after=("dnsmos_after_ovrl", "mean"),
        dnsmos_delta=("dnsmos_delta", "mean"),
        snr=("snr_proxy_db", "mean"),
        preserve=("speech_band_preserve_ratio", "mean"),
    )
    # 强制补齐四模型（防御性处理）
    for m in MODEL_ORDER:
        if m not in agg.index:
            agg.loc[m] = [0.0, 0.0, 0.0, 0.0]
    agg = agg.loc[MODEL_ORDER]

    dns_after_n = _minmax_norm({m: float(agg.loc[m, "dnsmos_after"]) for m in MODEL_ORDER})
    dns_delta_n = _minmax_norm({m: float(agg.loc[m, "dnsmos_delta"]) for m in MODEL_ORDER})
    snr_n = _minmax_norm({m: float(agg.loc[m, "snr"]) for m in MODEL_ORDER})
    preserve_n = _minmax_norm({m: float(agg.loc[m, "preserve"]) for m in MODEL_ORDER})

    if noise_class == "low_noise":
        w = {"dnsmos_after": 0.35, "dnsmos_delta": 0.15, "snr": 0.10, "preserve": 0.40}
    elif noise_class == "mid_noise":
        w = {"dnsmos_after": 0.30, "dnsmos_delta": 0.15, "snr": 0.10, "preserve": 0.45}
    else:
        w = {"dnsmos_after": 0.20, "dnsmos_delta": 0.10, "snr": 0.10, "preserve": 0.60}

    out: Dict[str, float] = {}
    for m in MODEL_ORDER:
        out[m] = (
            w["dnsmos_after"] * dns_after_n[m]
            + w["dnsmos_delta"] * dns_delta_n[m]
            + w["snr"] * snr_n[m]
            + w["preserve"] * preserve_n[m]
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail_csv", default="anti-noise/net2_final_comparison/net2_choice_metrics_detail.csv")
    ap.add_argument("--out_dir", default="anti-noise/net2_final_comparison/charts")
    args = ap.parse_args()

    detail_csv = (REPO_ROOT / args.detail_csv).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(detail_csv)

    # 统一列名（兼容性）
    if "dnsmos_delta" not in df.columns:
        # 发生过列名差异时的兜底
        raise RuntimeError(f"CSV 缺少 dnsmos_delta 列: {detail_csv}")

    # ===== 图1：SNR + DNSMOS（总体均值，等权噪声类）=====
    # 等权噪声类：先按 noise_class 计算每模型的均值，再对 class 取平均
    overall = (
        df.groupby(["model", "noise_class"])
        .agg(snr=("snr_proxy_db", "mean"), dnsmos_after=("dnsmos_after_ovrl", "mean"))
        .reset_index()
        .groupby("model")[["snr", "dnsmos_after"]]
        .mean()
    )

    x = np.arange(len(MODEL_ORDER))
    y_snr = [float(overall.loc[m, "snr"]) for m in MODEL_ORDER]
    y_dnsmos = [float(overall.loc[m, "dnsmos_after"]) for m in MODEL_ORDER]

    # PPT 友好参数：整体尺寸更小，但字体更大以保证可读性
    FIG1_SIZE = (8.4, 4.0)
    FIG2_SIZE = (14.0, 4.2)

    fig, ax = plt.subplots(figsize=FIG1_SIZE, facecolor="#fbfbfd")
    ax.plot(x, y_snr, color="#1f4e79", marker="o", linewidth=2.6, markersize=7.2)
    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER])
    ax.set_ylabel("SNR proxy (dB)", color="#1f4e79", fontsize=13)
    ax.tick_params(axis="y", colors="#1f4e79")
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.28)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax2 = ax.twinx()
    ax2.plot(x, y_dnsmos, color="#b04a4a", marker="s", linewidth=2.4, markersize=6.8)
    ax2.set_ylabel("DNSMOS(OVRL)", color="#b04a4a", fontsize=13)
    ax2.tick_params(axis="y", colors="#b04a4a")
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)

    # 只标注点值（不在柱体上方堆字，避免遮挡）
    for i in range(len(MODEL_ORDER)):
        ax.text(i, y_snr[i] + 0.15, f"{y_snr[i]:.2f}", ha="center", va="bottom", fontsize=10, color="#1f4e79")
        ax2.text(i, y_dnsmos[i] + 0.03, f"{y_dnsmos[i]:.2f}", ha="center", va="bottom", fontsize=10, color="#b04a4a")

    # 用轴内标题替代 suptitle，避免 bbox 计算导致大面积空白
    ax.set_title("图1：SNR proxy 与 DNSMOS(OVRL)（总体均值，等权噪声类）", fontsize=16, fontweight="bold", pad=10)

    out1 = out_dir / "figure1_snr_dnsmos.png"
    fig.tight_layout(pad=0.08)
    fig.savefig(str(out1), dpi=220, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    # ===== 图2：各噪声环境下的训练适配度 =====
    fig, axes = plt.subplots(1, 3, figsize=FIG2_SIZE, facecolor="#fbfbfd")
    for ax, cls in zip(axes, NOISE_CLASSES):
        scores = suitability_by_noise_class(df[df["noise_class"] == cls], cls)
        vals = [scores[m] for m in MODEL_ORDER]
        cols = [MODEL_COLORS[m] for m in MODEL_ORDER]

        ax.bar(x, vals, color=cols, edgecolor="white", linewidth=0.9, width=0.64)
        ax.set_xticks(x)
        ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER])
        ax.set_ylim(0, 100)
        ax.set_title(f"{NOISE_LABELS[cls]}：训练适配度(0-100)", fontsize=14, fontweight="bold")
        ax.set_ylabel("训练适配度", fontsize=13)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.28)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # 只给最高的两个模型标一次，避免遮挡
        sorted_idx = sorted(range(len(MODEL_ORDER)), key=lambda i: vals[i], reverse=True)[:2]
        for i in sorted_idx:
            ax.text(i, vals[i] + 2.0, f"{vals[i]:.0f}", ha="center", va="bottom", fontsize=11, color="#222222")

    fig.suptitle("图2：不同噪声环境下的训练适配度对比（相对归一化综合分）", fontsize=16, fontweight="bold")
    fig.tight_layout()
    out2 = out_dir / "figure2_training_suitability_by_noise.png"
    fig.savefig(str(out2), dpi=220, bbox_inches="tight")
    plt.close(fig)

    print(f"Wrote:\n  {out1}\n  {out2}")


if __name__ == "__main__":
    main()

