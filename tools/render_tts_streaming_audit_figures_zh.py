#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = REPO_ROOT / "runtime" / "bench" / "tts_streaming_audit_20260416.json"
OUT_DIR = REPO_ROOT / "runtime" / "bench" / "tts_streaming_audit_20260416_assets_zh"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def setup_zh_academic_style() -> str:
    """
    在常见 Linux 发行版上优先使用文泉驿微米黑（对简体中文覆盖较好）。
    返回 matplotlib 识别的字体 family 名称（用于后续 FontProperties 也可）。
    """
    candidates = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    chosen: str | None = None
    for p in candidates:
        fp = Path(p)
        if not fp.exists():
            continue
        try:
            font_manager.fontManager.addfont(str(fp))
            chosen = str(fp)
            break
        except Exception:
            continue

    # 从 fontManager 里反查该文件对应的 font.name（TTC 可能是 JP/SC 集合）
    font_name = "DejaVu Sans"
    if chosen:
        hits = [f for f in font_manager.fontManager.ttflist if getattr(f, "fname", None) == chosen]
        if hits:
            font_name = hits[0].name

    mpl.rcParams.update(
        {
            "font.sans-serif": [font_name, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "figure.dpi": 140,
            "savefig.dpi": 220,
            "axes.titlesize": 13,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 10.5,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "grid.linestyle": "--",
            "axes.axisbelow": True,
            "axes.linewidth": 0.9,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
        }
    )
    return font_name


def _style_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def save_csv(path: Path, headers: List[str], rows: List[Dict[str, Any]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def plot_grouped_bars_zh(
    fig_no: str,
    title: str,
    x_labels: List[str],
    series: Dict[str, List[float]],
    y_label: str,
    legend_labels: Dict[str, str],
    out_png: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 4.9))
    x = list(range(len(x_labels)))
    width = 0.24
    k_list = list(series.keys())
    offsets = [(i - (len(k_list) - 1) / 2) * width for i in range(len(k_list))]

    for off, (key, vals) in zip(offsets, series.items()):
        bars = ax.bar([v + off for v in x], vals, width=width, label=legend_labels.get(key, key))
        for b in bars:
            h = float(b.get_height())
            ax.text(b.get_x() + b.get_width() / 2, h, f"{h:.0f}", ha="center", va="bottom", fontsize=9.5)

    ax.set_xticks(x, x_labels)
    ax.set_ylabel(y_label)
    ax.set_title(f"{fig_no}  {title}")
    ax.legend(frameon=False, ncol=min(3, len(k_list)))
    _style_axes(ax)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def plot_pass_rate_compare_zh(audit: Dict[str, Any], out_png: Path) -> None:
    hist = audit["historical_benchmarks"]
    after = float(hist["after_patch_full_chain"]["pass_rate"])
    older = float(hist["older_quality_regression"]["pass_rate"])
    labels = ["旧阶段回归（2026-04-02）", "新链路全量（2026-04-11）"]
    vals = [older, after]

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    bars = ax.bar(labels, vals, width=0.55)
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("通过率（pass_rate）")
    ax.set_title("图2  历史基准：端到端通过率对比")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", va="bottom", fontsize=11)
    _style_axes(ax)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def plot_buffered_stability_zh(audit: Dict[str, Any], out_png: Path) -> None:
    buf = audit["historical_benchmarks"]["buffered_hotvoice_stability"]
    total = float(buf["total"])
    ok = float(buf["ok"]) / total if total else 0.0
    audible = float(buf["audible"]) / total if total else 0.0

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    bars = ax.bar(["请求成功占比（ok）", "可听占比（audible）"], [ok, audible], width=0.55)
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("比例")
    ax.set_title("图3  buffered 热音色稳定性专项（20 次请求）")
    for b, v in zip(bars, [ok, audible]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", va="bottom", fontsize=11)
    _style_axes(ax)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def main() -> None:
    _font_name = setup_zh_academic_style()
    ensure_dir(OUT_DIR)
    audit = load_json(AUDIT_JSON)

    # 1) 导出能力矩阵 CSV（中文文件名）
    feature_rows = []
    for k, v in audit["feature_audit"].items():
        feature_rows.append({"key": k, "status": v.get("status"), "detail": v.get("detail")})
    save_csv(OUT_DIR / "feature_audit_zh.csv", headers=["key", "status", "detail"], rows=feature_rows)

    # 2) 导出 live mode_summary CSV
    ms = audit["live_sanity_current_modes"]["mode_summary"]
    mode_rows = []
    for mode, item in ms.items():
        mode_rows.append(
            {
                "mode": mode,
                "rows": item.get("rows"),
                "request_ms_avg": item.get("request_ms_avg"),
                "first_ready_ms_avg": item.get("first_ready_ms_avg"),
                "merged_ready_ms_avg": item.get("merged_ready_ms_avg"),
                "under_rate": item.get("under_rate"),
                "over_rate": item.get("over_rate"),
                "audible_rate": item.get("audible_rate"),
            }
        )
    save_csv(
        OUT_DIR / "live_mode_summary_zh.csv",
        headers=[
            "mode",
            "rows",
            "request_ms_avg",
            "first_ready_ms_avg",
            "merged_ready_ms_avg",
            "under_rate",
            "over_rate",
            "audible_rate",
        ],
        rows=mode_rows,
    )

    # 3) 图：三模式时延（request/first/merged）
    order = ["current_sync", "current_buffered", "current_stream"]
    x_labels = ["同步（sync）", "分段缓冲（buffered）", "流式（stream）"]
    request = [float(ms[m]["request_ms_avg"]) for m in order]
    first = [float(ms[m]["first_ready_ms_avg"]) for m in order]
    merged = [float(ms[m]["merged_ready_ms_avg"]) for m in order]

    plot_grouped_bars_zh(
        fig_no="图1",
        title="在线小样本稳健性检查：三模式时延对比（毫秒）",
        x_labels=x_labels,
        series={
            "request_ms_avg": request,
            "first_ready_ms_avg": first,
            "merged_ready_ms_avg": merged,
        },
        y_label="时延（ms）",
        legend_labels={
            "request_ms_avg": "请求耗时（均值）",
            "first_ready_ms_avg": "首次可消费耗时（均值）",
            "merged_ready_ms_avg": "全量合并就绪耗时（均值）",
        },
        out_png=OUT_DIR / "live_latency_ms_zh.png",
    )

    plot_pass_rate_compare_zh(audit, OUT_DIR / "historical_pass_rate_zh.png")
    plot_buffered_stability_zh(audit, OUT_DIR / "buffered_stability_rates_zh.png")

    print(str(OUT_DIR))


if __name__ == "__main__":
    main()
