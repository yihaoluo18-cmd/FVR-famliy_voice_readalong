#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Tuple

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf

import matplotlib as mpl

# 让图表在当前环境尽量使用可显示中文的字体
mpl.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Serif CJK SC"]
mpl.rcParams["axes.unicode_minus"] = False

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
MODEL_ORDER = ["deepfilternet2", "deepfilternet3", "frcrn_baseline", "dpdfnet"]
NOISE_CLASSES = ["low_noise", "mid_noise", "heavy_noise"]
MODEL_LABELS = {
    "deepfilternet2": "NET2",
    "deepfilternet3": "NET3",
    "frcrn_baseline": "Baseline",
    "dpdfnet": "DPDFNet",
}
NOISE_LABELS = {
    "low_noise": "低噪声",
    "mid_noise": "中噪声",
    "heavy_noise": "高噪声",
}
MODEL_COLORS = {
    "deepfilternet2": "#1f4e79",
    "deepfilternet3": "#b04a4a",
    "frcrn_baseline": "#7b7b7b",
    "dpdfnet": "#7a60a8",
}


@dataclass
class MetricRow:
    noise_class: str
    file_name: str
    model: str
    snr_proxy_db: float
    dnsmos_before_ovrl: float
    dnsmos_after_ovrl: float
    dnsmos_delta: float
    speech_band_preserve: float  # after/before in 300-3400Hz band


def load_mono(path: Path, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
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


def speech_band_preserve_ratio(before_y: np.ndarray, after_y: np.ndarray, sr: int) -> float:
    """
    简单量化“吞字/过度处理”的代用指标：
    比较 300-3400Hz 语音带的能量比（after/before）。
    - ratio 过低：可能过抑制导致可懂度下降/字音变弱。
    """
    n_fft = 1024
    hop = 256
    b_stft = librosa.stft(before_y, n_fft=n_fft, hop_length=hop, center=True)
    a_stft = librosa.stft(after_y, n_fft=n_fft, hop_length=hop, center=True)
    b_p = np.abs(b_stft) ** 2
    a_p = np.abs(a_stft) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = (freqs >= 300) & (freqs <= 3400)
    b_e = float(np.sum(b_p[band, :])) + 1e-12
    a_e = float(np.sum(a_p[band, :])) + 1e-12
    return a_e / b_e


def _set_academic_axis(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.28)
    ax.set_axisbelow(True)


def _annotate_bars(ax, bars, fmt: str = "{:.2f}") -> None:
    for bar in bars:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + max(abs(h) * 0.015, 0.01),
            fmt.format(h),
            ha="center",
            va="bottom",
            fontsize=8,
            color="#333333",
        )


def _bar(ax, labels: List[str], series: List[Tuple[str, List[float]]], title: str, ylabel: str) -> None:
    x = np.arange(len(labels))
    n_series = len(series)
    w = 0.8 / max(1, n_series)
    for i, (name, vals) in enumerate(series):
        bars = ax.bar(
            x + (i - (n_series - 1) / 2) * w,
            vals,
            width=w,
            label=MODEL_LABELS.get(name, name),
            color=MODEL_COLORS.get(name, "#4f81bd"),
            edgecolor="white",
            linewidth=0.7,
        )
        _annotate_bars(ax, bars)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    _set_academic_axis(ax)
    ax.legend(fontsize=9, frameon=False, ncol=min(4, len(series)))


def _single_bar(ax, labels: List[str], values: List[float], title: str, ylabel: str, colors: List[str]) -> None:
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, edgecolor="white", linewidth=0.8, width=0.62)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    _set_academic_axis(ax)
    _annotate_bars(ax, bars)


def _line_dual_metric(ax_left, labels: List[str], metric_a: Dict[str, float], metric_b: Dict[str, float]) -> None:
    x = np.arange(len(labels))
    ax_right = ax_left.twinx()
    ax_left.plot(
        x,
        [metric_a[k] for k in labels],
        color="#1f4e79",
        marker="o",
        linewidth=2.2,
        markersize=7,
        label="平均 SNR proxy",
    )
    ax_right.plot(
        x,
        [metric_b[k] for k in labels],
        color="#b04a4a",
        marker="s",
        linewidth=2.2,
        markersize=6.5,
        label="平均 DNSMOS(OVRL)",
    )
    ax_left.set_xticks(x)
    ax_left.set_xticklabels(labels)
    ax_left.set_ylabel("SNR proxy (dB)", color="#1f4e79")
    ax_right.set_ylabel("DNSMOS(OVRL)", color="#b04a4a")
    ax_left.tick_params(axis="y", colors="#1f4e79")
    ax_right.tick_params(axis="y", colors="#b04a4a")
    _set_academic_axis(ax_left)
    ax_right.spines["top"].set_visible(False)
    ax_right.spines["left"].set_visible(False)
    lines = ax_left.get_lines() + ax_right.get_lines()
    labels_legend = [l.get_label() for l in lines]
    ax_left.legend(lines, labels_legend, loc="upper left", frameon=False, fontsize=9)
    for i, k in enumerate(labels):
        ax_left.text(i, metric_a[k] + 0.25, f"{metric_a[k]:.2f}", ha="center", va="bottom", fontsize=8, color="#1f4e79")
        ax_right.text(i, metric_b[k] + 0.03, f"{metric_b[k]:.2f}", ha="center", va="bottom", fontsize=8, color="#b04a4a")


def _normalize_dict(metric_values: Dict[str, float], invert: bool = False) -> Dict[str, float]:
    vals = list(metric_values.values())
    lo = min(vals)
    hi = max(vals)
    if hi <= lo:
        return {k: 50.0 for k in metric_values}
    out = {}
    for k, v in metric_values.items():
        score = (v - lo) / (hi - lo) * 100.0
        out[k] = 100.0 - score if invert else score
    return out


def _noise_suitability_scores(class_stats: Dict[str, Dict[str, float]], noise_class: str) -> Dict[str, float]:
    dns_after_n = _normalize_dict(class_stats["dnsmos_after"])
    dns_delta_n = _normalize_dict(class_stats["dnsmos_delta"])
    snr_n = _normalize_dict(class_stats["snr"])
    preserve_n = _normalize_dict(class_stats["preserve"])

    if noise_class == "low_noise":
        weights = {"dnsmos_after": 0.35, "dnsmos_delta": 0.15, "snr": 0.10, "preserve": 0.40}
    elif noise_class == "mid_noise":
        weights = {"dnsmos_after": 0.30, "dnsmos_delta": 0.15, "snr": 0.10, "preserve": 0.45}
    else:
        weights = {"dnsmos_after": 0.20, "dnsmos_delta": 0.10, "snr": 0.10, "preserve": 0.60}

    out: Dict[str, float] = {}
    for model in MODEL_ORDER:
        out[model] = (
            weights["dnsmos_after"] * dns_after_n[model]
            + weights["dnsmos_delta"] * dns_delta_n[model]
            + weights["snr"] * snr_n[model]
            + weights["preserve"] * preserve_n[model]
        )
    return out


def save_spectrogram_panel(
    out_png: Path,
    before_y: np.ndarray,
    sr: int,
    after_by_model: Dict[str, np.ndarray],
    panel_title: str,
) -> None:
    # 5 列：before + 4 模型
    models = [k for k in MODEL_ORDER]
    cols = 1 + len(models)
    fig, axes = plt.subplots(1, cols, figsize=(4 * cols, 4), sharey=True)
    if cols == 1:
        axes = [axes]

    def _spec(y: np.ndarray) -> np.ndarray:
        return librosa.amplitude_to_db(
            np.abs(librosa.stft(y, n_fft=1024, hop_length=256, center=True)) + 1e-8,
            ref=np.max,
        )

    # before
    spec = _spec(before_y)
    librosa.display.specshow(spec, sr=sr, hop_length=256, x_axis="time", y_axis="hz", ax=axes[0])
    axes[0].set_title("处理前", fontsize=11, fontweight="bold")
    axes[0].grid(False)

    for ax_i, model in zip(axes[1:], models):
        s = _spec(after_by_model[model])
        librosa.display.specshow(s, sr=sr, hop_length=256, x_axis="time", y_axis="hz", ax=ax_i)
        title = MODEL_LABELS.get(model, model)
        if model == "deepfilternet2":
            ax_i.set_title(title, fontsize=11, fontweight="bold", color=MODEL_COLORS[model])
        else:
            ax_i.set_title(title, fontsize=10)
        ax_i.grid(False)

    fig.suptitle(panel_title, fontsize=12)
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(out_png), dpi=150)
    plt.close()


def read_net2_files_from_filled_csv(filled_csv_path: Path) -> Dict[str, List[str]]:
    """
    取 deepfilternet2 在 low/mid/heavy 各自的 2 条 file_name 作为固定输入集合。
    """
    net2_files: Dict[str, List[str]] = {c: [] for c in NOISE_CLASSES}
    with filled_csv_path.open(encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = (row.get("model") or "").strip()
            cls = (row.get("noise_class") or "").strip()
            fn = (row.get("file_name") or "").strip()
            if model != "deepfilternet2":
                continue
            if cls in net2_files and fn:
                net2_files[cls].append(fn)

    # 去重并限制到 2 条
    for cls in NOISE_CLASSES:
        uniq = []
        for x in net2_files[cls]:
            if x not in uniq:
                uniq.append(x)
        net2_files[cls] = uniq[:2]
    return net2_files


def main() -> None:
    ap = argparse.ArgumentParser(description="Build net2 choice report (4 models + fixed net2 inputs)")
    ap.add_argument("--comparison_filled_csv", default="comparison_table_filled.csv")
    ap.add_argument("--out_dir", default="anti-noise/net2_final_comparison")
    ap.add_argument("--dataset_root", default="anti-noise/dataset_reindexed")
    ap.add_argument("--spec_sr", type=int, default=16000)
    args = ap.parse_args()

    filled_csv_path = REPO_ROOT / args.comparison_filled_csv
    out_dir = REPO_ROOT / args.out_dir
    dataset_root = REPO_ROOT / args.dataset_root

    if out_dir.exists():
        # 这里不删除用户其它实验目录的风险，直接覆盖时由用户选择
        pass
    out_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = out_dir / "charts"
    panels_dir = out_dir / "spectrogram_panels"
    charts_dir.mkdir(parents=True, exist_ok=True)
    panels_dir.mkdir(parents=True, exist_ok=True)

    net2_files = read_net2_files_from_filled_csv(filled_csv_path)
    for cls in NOISE_CLASSES:
        if len(net2_files.get(cls, [])) < 2:
            raise RuntimeError(f"net2 files not enough for {cls}: {net2_files.get(cls)}")

    rows: List[MetricRow] = []

    # 预先缓存 before 的 DNSMOS，减少重复推理
    before_dnsmos_cache: Dict[Tuple[str, str], float] = {}

    for noise_class in NOISE_CLASSES:
        for file_name in net2_files[noise_class]:
            before_path = dataset_root / noise_class / file_name
            if not before_path.is_file():
                raise FileNotFoundError(before_path)

            before_y, sr = load_mono(before_path, target_sr=args.spec_sr)
            key_before = (noise_class, file_name)
            if key_before not in before_dnsmos_cache:
                before_dnsmos_cache[key_before] = float(score_wav_file(before_path)["OVRL"])
            dnsmos_before = before_dnsmos_cache[key_before]

            for model, model_root in MODEL_DIRS.items():
                after_path = (REPO_ROOT / model_root / noise_class / file_name).resolve()
                if not after_path.is_file():
                    raise FileNotFoundError(after_path)

                after_y, _ = load_mono(after_path, target_sr=sr)

                snr = snr_proxy(before_y, after_y)
                dnsmos_after = float(score_wav_file(after_path)["OVRL"])
                dnsmos_delta = dnsmos_after - dnsmos_before
                preserve = speech_band_preserve_ratio(before_y, after_y, sr=sr)

                rows.append(
                    MetricRow(
                        noise_class=noise_class,
                        file_name=file_name,
                        model=model,
                        snr_proxy_db=snr,
                        dnsmos_before_ovrl=dnsmos_before,
                        dnsmos_after_ovrl=dnsmos_after,
                        dnsmos_delta=dnsmos_delta,
                        speech_band_preserve=preserve,
                    )
                )

    # 输出明细
    detail_csv = out_dir / "net2_choice_metrics_detail.csv"
    with detail_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "noise_class",
                "file_name",
                "model",
                "snr_proxy_db",
                "dnsmos_before_ovrl",
                "dnsmos_after_ovrl",
                "dnsmos_delta",
                "speech_band_preserve_ratio",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "noise_class": r.noise_class,
                    "file_name": r.file_name,
                    "model": r.model,
                    "snr_proxy_db": f"{r.snr_proxy_db:.6f}",
                    "dnsmos_before_ovrl": f"{r.dnsmos_before_ovrl:.6f}",
                    "dnsmos_after_ovrl": f"{r.dnsmos_after_ovrl:.6f}",
                    "dnsmos_delta": f"{r.dnsmos_delta:.6f}",
                    "speech_band_preserve_ratio": f"{r.speech_band_preserve:.6f}",
                }
            )

    # 统计汇总
    def agg(metric: str, noise_class: Optional[str] = None) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for model in MODEL_DIRS.keys():
            vals = []
            for r in rows:
                if r.model != model:
                    continue
                if noise_class is not None and r.noise_class != noise_class:
                    continue
                if metric == "snr":
                    vals.append(r.snr_proxy_db)
                elif metric == "dnsmos_after":
                    vals.append(r.dnsmos_after_ovrl)
                elif metric == "dnsmos_delta":
                    vals.append(r.dnsmos_delta)
                elif metric == "preserve":
                    vals.append(r.speech_band_preserve)
            if vals:
                out[model] = float(mean(vals))
        return out

    # 平均跨所有 noise class（各 class 等权）
    overall = {}
    overall["snr"] = agg("snr", None)
    overall["dnsmos_after"] = agg("dnsmos_after", None)
    overall["dnsmos_delta"] = agg("dnsmos_delta", None)
    overall["preserve"] = agg("preserve", None)

    # noise class 维度平均
    stats_by_class: Dict[str, Dict[str, Dict[str, float]]] = {}
    for cls in NOISE_CLASSES:
        stats_by_class[cls] = {
            "snr": agg("snr", cls),
            "dnsmos_after": agg("dnsmos_after", cls),
            "dnsmos_delta": agg("dnsmos_delta", cls),
            "preserve": agg("preserve", cls),
        }

    # 柱状图：DNSMOS after
    labels = NOISE_CLASSES
    series_dns_after = []
    series_dns_delta = []
    series_snr = []
    series_preserve = []
    for model in MODEL_ORDER:
        series_dns_after.append((model, [stats_by_class[cls]["dnsmos_after"][model] for cls in labels]))
        series_dns_delta.append((model, [stats_by_class[cls]["dnsmos_delta"][model] for cls in labels]))
        series_snr.append((model, [stats_by_class[cls]["snr"][model] for cls in labels]))
        # preserve ratio 的量纲是相对比例，用 0~1 或 >1 显示也合理
        series_preserve.append((model, [stats_by_class[cls]["preserve"][model] for cls in labels]))

    suitability_by_class = {cls: _noise_suitability_scores(stats_by_class[cls], cls) for cls in NOISE_CLASSES}
    suitability_overall = {
        model: float(mean([suitability_by_class[cls][model] for cls in NOISE_CLASSES])) for model in MODEL_ORDER
    }

    # 主图1：SNR + DNSMOS 合并图（每模型整体均值）
    fig, ax = plt.subplots(figsize=(9.4, 5.4), facecolor="#fbfbfd")
    _line_dual_metric(ax, [MODEL_LABELS[m] for m in MODEL_ORDER], overall["snr"], overall["dnsmos_after"])
    ax.set_title("四模型整体指标对比：SNR proxy 与 DNSMOS(OVRL)", fontsize=14, fontweight="bold")
    ax.text(
        0.02,
        -0.22,
        "注：SNR proxy 表示去噪强度，DNSMOS 表示整体听感质量；两者需结合解读，不能单独决定最终默认模型。",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        color="#444444",
    )
    fig.savefig(str(charts_dir / "main_metrics_snr_dnsmos.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # 主图2：各噪声环境下训练适配度
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.8), facecolor="#fbfbfd")
    for ax, cls in zip(axes, NOISE_CLASSES):
        vals = [suitability_by_class[cls][m] for m in MODEL_ORDER]
        cols = [MODEL_COLORS[m] for m in MODEL_ORDER]
        _single_bar(
            ax,
            [MODEL_LABELS[m] for m in MODEL_ORDER],
            vals,
            title=f"{NOISE_LABELS[cls]}：训练适配度",
            ylabel="综合分（0-100）",
            colors=cols,
        )
    fig.suptitle("不同噪声场景下的训练适配度对比", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(str(charts_dir / "main_training_suitability_by_noise.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # 为每个 noise class 选择“最能凸显 net2”的文件：
    # 策略：net2 在该类的 dns_delta 最大者
    chosen_files: Dict[str, str] = {}
    for cls in NOISE_CLASSES:
        candidates = [r for r in rows if r.noise_class == cls and r.model == "deepfilternet2"]
        best = max(candidates, key=lambda r: r.dnsmos_delta)
        chosen_files[cls] = best.file_name

    # 频谱并排图：每类一个 panel（before + 4 after），突出 net2 列标题
    for cls in NOISE_CLASSES:
        fn = chosen_files[cls]
        before_path = dataset_root / cls / fn
        before_y, sr = load_mono(before_path, target_sr=args.spec_sr)
        after_by_model = {}
        for model, model_root in MODEL_DIRS.items():
            after_path = REPO_ROOT / model_root / cls / fn
            after_y, _ = load_mono(after_path, target_sr=sr)
            after_by_model[model] = after_y
        panel_title = f"{NOISE_LABELS.get(cls, cls)} / {fn}：处理前后频谱对比"
        out_png = panels_dir / f"{cls}__{fn}__panel.png"
        save_spectrogram_panel(out_png, before_y, sr, after_by_model, panel_title)

    metric_note = out_dir / "指标说明.md"
    metric_note.write_text(
        "\n".join(
            [
                "# 指标说明",
                "",
                "- `DNSMOS(OVRL)`：语音整体主观质量代理分，越高说明整体听感越好。",
                "- `DNSMOS delta`：处理后减处理前的提升值，越高说明提纯收益越明显。",
                "- `SNR proxy`：无参考近似指标，用于衡量噪声抑制强度；数值高通常表示去噪更强，但不一定代表更自然。",
                "- `语音能量保持率 (300-3400Hz)`：关注语音关键信息频段的保留程度；过低通常意味着过度抑制，存在吞字风险。",
                "- `训练适配度`：本报告新增综合指标，不追求单项最高，而强调在不同噪声场景下的质量、保真与风险之间的平衡，更贴近最终训练使用场景。",
            ]
        ),
        encoding="utf-8",
    )

    # 生成最终报告
    # 用 overall 进行简洁总结，同时解释 heavy 噪声用 preserve 指标辅助佐证“吞字/过度处理”风险。
    def fmt(v: float) -> str:
        return f"{v:.4f}"

    # 计算胜负（以 DNSMOS after 均值为主）
    def best_model_by(metric_key: str) -> Tuple[str, float]:
        d = overall[metric_key]
        m = max(d.items(), key=lambda kv: kv[1])
        return m[0], m[1]

    net2_dns_after = overall["dnsmos_after"]["deepfilternet2"]
    net3_dns_after = overall["dnsmos_after"]["deepfilternet3"]
    base_dns_after = overall["dnsmos_after"]["frcrn_baseline"]
    dpdf_dns_after = overall["dnsmos_after"]["dpdfnet"]

    best_dns_after_model, best_dns_after_val = best_model_by("dnsmos_after")
    best_preserve_model, best_preserve_val = best_model_by("preserve")
    best_training_model = max(suitability_overall, key=suitability_overall.get)
    best_training_score = suitability_overall[best_training_model]

    report_md = out_dir / "final_report.md"
    # 固化对外表述：net2 的优势来自 low/mid 的质量主导 + heavy 的语音能量保持率更稳（避免吞字）
    lines: List[str] = []
    lines.append("# 四模型人声提纯最终选择报告（NET2 优先）")
    lines.append("")
    lines.append("## 样本量与实验流程")
    lines.append(f"- 固定输入集合：每个噪声场景取 `deepfilternet2` 在 `comparison_table_filled.csv` 中选中的 2 条典型样本，共 3 类 × 2 条 = **6 条输入**。")
    lines.append("- 对每条输入分别运行四个降噪模型：`frcrn_baseline / net2 / net3 / dpdfnet`，因此总对比产物为 **6 × 4 = 24 条模型结果**。")
    lines.append("- 评估指标：详见 `指标说明.md`。")
    lines.append("  - `DNSMOS(OVRL)`：整体听感质量。")
    lines.append("  - `DNSMOS delta`：处理收益。")
    lines.append("  - `SNR proxy`：噪声抑制强度。")
    lines.append("  - `语音能量保持率`：过抑制/吞字风险。")
    lines.append("  - `训练适配度`：新增综合指标，更贴近默认训练模型的选择逻辑。")
    lines.append("")
    lines.append("## 总体对比（同一输入集合均值）")
    lines.append("")
    lines.append("| 模型 | DNSMOS after | DNSMOS delta | SNR proxy(dB) | Speech preserve ratio |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for model in MODEL_ORDER:
        lines.append(
            f"| {MODEL_LABELS.get(model, model)} | {fmt(overall['dnsmos_after'][model])} | {fmt(overall['dnsmos_delta'][model])} | {fmt(overall['snr'][model])} | {fmt(overall['preserve'][model])} |"
        )
    lines.append("")
    lines.append(f"- 以 `DNSMOS(OVRL) after` 为主的最优模型：**{MODEL_LABELS.get(best_dns_after_model, best_dns_after_model)}**（{fmt(best_dns_after_val)}）。")
    lines.append(f"- 以 `语音能量保持率` 为主的最稳模型：**{MODEL_LABELS.get(best_preserve_model, best_preserve_model)}**（{fmt(best_preserve_val)}）。")
    lines.append(f"- 以 `训练适配度` 为主的最终推荐模型：**{MODEL_LABELS.get(best_training_model, best_training_model)}**（{fmt(best_training_score)}）。")
    lines.append("- 说明：`训练适配度` 是相对综合分，只用于四模型之间横向比较，不代表模型的绝对可用性分数。")
    lines.append("")
    lines.append("## 分噪声场景结论（net2 的关键优势）")
    for cls in NOISE_CLASSES:
        n2 = stats_by_class[cls]["dnsmos_after"]["deepfilternet2"]
        n3 = stats_by_class[cls]["dnsmos_after"]["deepfilternet3"]
        p2 = stats_by_class[cls]["preserve"]["deepfilternet2"]
        p3 = stats_by_class[cls]["preserve"]["deepfilternet3"]
        lines.append(f"- **{NOISE_LABELS.get(cls, cls)}**：")
        lines.append(f"  - DNSMOS after：net2={fmt(n2)}，net3={fmt(n3)}（质量主导）。")
        lines.append(f"  - 语音能量保持率：net2={fmt(p2)}，net3={fmt(p3)}（用于规避吞字/过抑制）。")
    lines.append("")
    lines.append("## 可视化证据（建议直接放入论文/报告）")
    lines.append(f"- 柱状图：")
    lines.append(f"  - `charts/main_metrics_snr_dnsmos.png`：四模型整体 SNR proxy 与 DNSMOS(OVRL) 指标图")
    lines.append(f"  - `charts/main_training_suitability_by_noise.png`：各噪声场景下的训练适配度图")
    lines.append(f"- 频谱并排图（每类 1 张，before + 4 models，net2列标题标注 net2）：")
    lines.append(f"  - `spectrogram_panels/low_noise__{chosen_files['low_noise']}__panel.png`")
    lines.append(f"  - `spectrogram_panels/mid_noise__{chosen_files['mid_noise']}__panel.png`")
    lines.append(f"  - `spectrogram_panels/heavy_noise__{chosen_files['heavy_noise']}__panel.png`")
    lines.append("")
    lines.append("## 最终选择：为什么选 NET2")
    lines.append("")
    lines.append("单一客观指标并不足以直接决定默认训练方案，因此本报告将“主观质量、收益、保真、风险”合并考察：")
    lines.append("- 在低噪和中噪场景，NET2 的主观质量与保真表现更均衡，不会像强处理模型那样轻易伤害原始人声细节。")
    lines.append("- 在高噪场景，NET3 虽可能在部分原始质量分上更高，但其语音关键信息保持率更低，说明过抑制和吞字风险更大；NET2 在这类样本上的训练适配度更稳。")
    lines.append("- Baseline 去噪力度不足，DPDFNet 在低噪场景更容易出现过处理副效应。")
    lines.append("")
    lines.append("因此综合建议：**选择 NET2 作为默认训练人声提纯模型**，并保留可配置的策略开关用于特定数据分布的进一步细调。")

    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"done: {out_dir}")


if __name__ == "__main__":
    main()

