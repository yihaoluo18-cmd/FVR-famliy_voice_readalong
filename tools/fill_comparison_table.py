#!/usr/bin/env python3
"""
读取 anti-noise/comparison/comparison_table.csv，批量填入 dnsmos_before / dnsmos_after，
并按 scoring_config.json 权重计算 weighted_total（需人工分已填时才算总分），
输出 comparison_table_filled.csv 与 final_ranking.md。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.dnsmos_scorer import score_wav_file  # noqa: E402


def _dnsmos_ovrl_to_0_10(ovrl: float) -> float:
    """将 OVRL（约 1~5）线性映射到 0~10。"""
    v = (float(ovrl) - 1.0) / 4.0 * 10.0
    return max(0.0, min(10.0, v))


def _snr_minmax_to_10(val: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 5.0
    return max(0.0, min(10.0, (float(val) - lo) / (hi - lo) * 10.0))


def _parse_manual(cell: str) -> Tuple[bool, float]:
    s = (cell or "").strip()
    if s == "":
        return False, 0.0
    try:
        return True, float(s)
    except ValueError:
        return False, 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparison_dir", default="anti-noise/comparison")
    ap.add_argument(
        "--skip_dnsmos",
        action="store_true",
        help="仅根据已有 CSV 重算加权与排名（需已含 dnsmos 列）",
    )
    args = ap.parse_args()

    comp = (Path(args.comparison_dir)).resolve()
    inp = comp / "comparison_table.csv"
    cfg_path = comp / "scoring_config.json"
    out_csv = comp / "comparison_table_filled.csv"
    out_md = comp / "final_ranking.md"

    rows: List[Dict[str, Any]] = []
    with inp.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            rows.append(dict(row))

    snrs = [float(r["snr_proxy_db"]) for r in rows]
    smin, smax = min(snrs), max(snrs)

    w_manual = 0.6
    w_dns = 0.3
    w_snr = 0.1
    if cfg_path.is_file():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        w = cfg.get("weights") or {}
        w_manual = float(w.get("manual_score_weight", w_manual))
        w_dns = float(w.get("dnsmos_weight", w_dns))
        w_snr = float(w.get("snr_weight", w_snr))

    if not args.skip_dnsmos:
        for i, r in enumerate(rows):
            before = comp / r["before_wav"]
            after = comp / r["after_wav"]
            db = score_wav_file(before)
            da = score_wav_file(after)
            r["dnsmos_before"] = f"{float(db['OVRL']):.6f}"
            r["dnsmos_after"] = f"{float(da['OVRL']):.6f}"
            print(f"[{i+1}/{len(rows)}] {r.get('model')} {r.get('noise_class')} OK")

    for r in rows:
        has_m, manual_v = _parse_manual(str(r.get("manual_score_0_10", "")))
        snr_v = float(r["snr_proxy_db"])
        snr10 = _snr_minmax_to_10(snr_v, smin, smax)
        da_ovrl = float(r["dnsmos_after"]) if str(r.get("dnsmos_after", "")).strip() else None
        if has_m and da_ovrl is not None:
            d10 = _dnsmos_ovrl_to_0_10(da_ovrl)
            total = w_manual * manual_v + w_dns * d10 + w_snr * snr10
            r["weighted_total"] = f"{total:.6f}"
        else:
            r["weighted_total"] = r.get("weighted_total") or ""

    fn = list(rows[0].keys()) if rows else []
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        w.writerows(rows)

    # 按模型聚合：平均 dnsmos_after、平均 snr、有 manual 时的平均 weighted
    from collections import defaultdict

    agg: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        agg[str(r["model"])].append(r)

    lines = [
        "# 四模型人声提纯对比 — 排名摘要",
        "",
        f"- 数据来源：`comparison_table_filled.csv`（DNSMOS 已本地推理）",
        f"- SNR 归一化：对本表 {len(rows)} 条样本的 `snr_proxy_db` 做 min-max 映射到 0~10。",
        f"- DNSMOS 映射：`dnsmos_after`（OVRL，约 1~5）→ 0~10：`(OVRL-1)/4*10`。",
        f"- 加权：`weighted_total = {w_manual}*manual + {w_dns}*dnsmos_0_10 + {w_snr}*snr_0_10`（人工未填则留空）。",
        "",
        "## 按模型汇总（均值）",
        "",
        "| 模型 | 平均 dnsmos_after(OVRL) | 平均 SNR 代理(dB) | 平均 weighted_total（仅已填人工分） |",
        "| --- | --- | --- | --- |",
    ]

    ranking: List[Tuple[float, str, Dict[str, float]]] = []
    for model, ms in sorted(agg.items()):
        dns_vals = [float(x["dnsmos_after"]) for x in ms if str(x.get("dnsmos_after", "")).strip()]
        snr_vals = [float(x["snr_proxy_db"]) for x in ms]
        wts: List[float] = []
        for x in ms:
            ok, mv = _parse_manual(str(x.get("manual_score_0_10", "")))
            if ok and str(x.get("weighted_total", "")).strip():
                wts.append(float(x["weighted_total"]))
        avg_dns = sum(dns_vals) / len(dns_vals) if dns_vals else float("nan")
        avg_snr = sum(snr_vals) / len(snr_vals) if snr_vals else float("nan")
        avg_w = sum(wts) / len(wts) if wts else float("nan")
        ranking.append((avg_dns, model, {"dns": avg_dns, "snr": avg_snr, "wt": avg_w}))
        wt_cell = f"{avg_w:.4f}" if wts else "—"
        lines.append(
            f"| {model} | {avg_dns:.4f} | {avg_snr:.4f} | {wt_cell} |"
        )

    lines.extend(["", "## 按平均 dnsmos_after 排序（主参考）", ""])
    ranking.sort(key=lambda t: t[0], reverse=True)
    for i, (_d, model, d) in enumerate(ranking, 1):
        lines.append(f"{i}. **{model}** — 平均 OVRL={d['dns']:.4f}，平均 SNR 代理={d['snr']:.4f} dB")

    lines.extend(["", "---", "*人工打分填齐后，以 `weighted_total` 行为主排序更可反映主观质量。*"])
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_csv} and {out_md}")


if __name__ == "__main__":
    main()
