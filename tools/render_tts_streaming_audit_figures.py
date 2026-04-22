#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = REPO_ROOT / "runtime" / "bench" / "tts_streaming_audit_20260416.json"
OUT_DIR = REPO_ROOT / "runtime" / "bench" / "tts_streaming_audit_20260416_assets"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def save_csv(path: Path, headers: List[str], rows: List[Dict[str, Any]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def plot_bar(
    title: str,
    x_labels: List[str],
    series: Dict[str, List[float]],
    y_label: str,
    out_png: Path,
) -> None:
    plt.figure(figsize=(9.5, 4.8))
    x = range(len(x_labels))
    width = 0.22
    offsets = []
    k_list = list(series.keys())
    for i, _k in enumerate(k_list):
        offsets.append((i - (len(k_list) - 1) / 2) * width)

    for off, (name, vals) in zip(offsets, series.items()):
        plt.bar([v + off for v in x], vals, width=width, label=name)

    plt.xticks(list(x), x_labels, rotation=0)
    plt.ylabel(y_label)
    plt.title(title)
    plt.grid(axis="y", alpha=0.25)
    plt.legend()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_png, dpi=160)
    plt.close()


def plot_pass_rate_compare(audit: Dict[str, Any], out_png: Path) -> None:
    hist = audit["historical_benchmarks"]
    after = float(hist["after_patch_full_chain"]["pass_rate"])
    older = float(hist["older_quality_regression"]["pass_rate"])
    labels = ["old_stage(20260402)", "new_chain(20260411)"]
    vals = [older, after]

    plt.figure(figsize=(7.2, 4.2))
    plt.bar(labels, vals)
    plt.ylim(0.0, 1.05)
    plt.ylabel("pass_rate")
    plt.title("historical bench: pass_rate comparison")
    plt.grid(axis="y", alpha=0.25)
    for i, v in enumerate(vals):
        plt.text(i, v + 0.03, f"{v:.2f}", ha="center", va="bottom", fontsize=11)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_png, dpi=160)
    plt.close()


def main() -> None:
    ensure_dir(OUT_DIR)
    audit = load_json(AUDIT_JSON)

    # 1) 导出能力矩阵 CSV
    feature_rows = []
    for k, v in audit["feature_audit"].items():
        feature_rows.append({"key": k, "status": v.get("status"), "detail": v.get("detail")})
    save_csv(OUT_DIR / "feature_audit.csv", headers=["key", "status", "detail"], rows=feature_rows)

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
        OUT_DIR / "live_mode_summary.csv",
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
    x_labels = ["sync", "buffered", "stream"]
    request = [float(ms[m]["request_ms_avg"]) for m in order]
    first = [float(ms[m]["first_ready_ms_avg"]) for m in order]
    merged = [float(ms[m]["merged_ready_ms_avg"]) for m in order]

    plot_bar(
        title="live sanity: latency comparison (ms)",
        x_labels=x_labels,
        series={"request_ms_avg": request, "first_ready_ms_avg": first, "merged_ready_ms_avg": merged},
        y_label="ms",
        out_png=OUT_DIR / "live_latency_ms.png",
    )

    # 4) 图：历史 pass_rate 对比
    plot_pass_rate_compare(audit, OUT_DIR / "historical_pass_rate.png")

    # 5) 图：buffered 稳定性专项（ok/audible）
    buf = audit["historical_benchmarks"]["buffered_hotvoice_stability"]
    total = float(buf["total"])
    ok = float(buf["ok"]) / total if total else 0.0
    audible = float(buf["audible"]) / total if total else 0.0
    plt.figure(figsize=(7.2, 4.2))
    plt.bar(["ok_rate", "audible_rate"], [ok, audible])
    plt.ylim(0.0, 1.05)
    plt.title("buffered stability: ok/audible rates")
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "buffered_stability_rates.png", dpi=160)
    plt.close()

    print(str(OUT_DIR))


if __name__ == "__main__":
    main()

