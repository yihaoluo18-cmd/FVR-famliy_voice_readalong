import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import librosa
import librosa.display
import numpy as np
import soundfile as sf


def _pair_files(before_dir: Path, after_dir: Path) -> List[Tuple[Path, Path]]:
    after_map = {p.name: p for p in after_dir.glob("*.wav")}
    pairs: List[Tuple[Path, Path]] = []
    for before in sorted(before_dir.glob("*.wav")):
        target = after_map.get(before.name)
        if target is not None:
            pairs.append((before, target))
    return pairs


def _load_mono(path: Path, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    if sr != target_sr:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return audio, sr


def _snr_proxy(before: np.ndarray, after: np.ndarray) -> Optional[float]:
    min_len = min(len(before), len(after))
    if min_len <= 0:
        return None
    b = before[:min_len]
    a = after[:min_len]
    noise = b - a
    denom = float(np.mean(noise**2)) + 1e-9
    numer = float(np.mean(a**2)) + 1e-9
    return 10.0 * math.log10(numer / denom)


def _try_dnsmos_local(script_path: Optional[Path], wav_path: Path) -> Optional[Dict[str, float]]:
    # 优先：离线包 tools/dnsmos_offline（tools/dnsmos_scorer.py）
    try:
        from tools.dnsmos_scorer import score_wav_file  # type: ignore

        d = score_wav_file(wav_path)
        return {
            "ovrl": float(d["OVRL"]),
            "sig": float(d["SIG"]),
            "bak": float(d["BAK"]),
        }
    except Exception:
        pass
    if script_path is None or not script_path.exists():
        return None
    return None


def _save_spectrogram_png(wav: np.ndarray, sr: int, out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return
    spec = librosa.amplitude_to_db(np.abs(librosa.stft(wav, n_fft=1024, hop_length=256)) + 1e-8, ref=np.max)
    plt.figure(figsize=(8, 3))
    librosa.display.specshow(spec, sr=sr, hop_length=256, x_axis="time", y_axis="hz")
    plt.colorbar(format="%+2.0f dB")
    plt.tight_layout()
    plt.savefig(str(out_path), dpi=120)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B 音频清洗效果报告（支持 DNSMOS 扩展位）")
    parser.add_argument("--before_dir", type=str, required=True)
    parser.add_argument("--after_dir", type=str, required=True)
    parser.add_argument("--out_dir", type=str, required=True)
    parser.add_argument("--sample_limit", type=int, default=20)
    parser.add_argument(
        "--dnsmos_script",
        type=str,
        default="",
        help="已弃用保留位；DNSMOS 默认从 tools/dnsmos_offline 加载。",
    )
    args = parser.parse_args()

    before_dir = Path(args.before_dir)
    after_dir = Path(args.after_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = out_dir / "samples"
    samples_dir.mkdir(exist_ok=True)

    dnsmos_script = Path(args.dnsmos_script) if args.dnsmos_script else None
    pairs = _pair_files(before_dir, after_dir)[: args.sample_limit]
    report_path = out_dir / "report.jsonl"
    summary_path = out_dir / "summary.md"

    snr_values: List[float] = []
    dnsmos_before: List[float] = []
    dnsmos_after: List[float] = []

    with report_path.open("w", encoding="utf-8") as fw:
        for before_path, after_path in pairs:
            before_wav, sr = _load_mono(before_path)
            after_wav, _ = _load_mono(after_path, target_sr=sr)
            snr = _snr_proxy(before_wav, after_wav)
            if snr is not None:
                snr_values.append(snr)

            sample_name = before_path.stem
            _save_spectrogram_png(before_wav, sr, samples_dir / f"{sample_name}_before_spec.png")
            _save_spectrogram_png(after_wav, sr, samples_dir / f"{sample_name}_after_spec.png")

            db_before = _try_dnsmos_local(dnsmos_script, before_path)
            db_after = _try_dnsmos_local(dnsmos_script, after_path)
            if db_before and "ovrl" in db_before:
                dnsmos_before.append(float(db_before["ovrl"]))
            if db_after and "ovrl" in db_after:
                dnsmos_after.append(float(db_after["ovrl"]))

            rec = {
                "file": before_path.name,
                "before": str(before_path),
                "after": str(after_path),
                "snr_proxy_db": snr,
                "dnsmos_before": db_before,
                "dnsmos_after": db_after,
            }
            fw.write(json.dumps(rec, ensure_ascii=False) + "\n")

    avg_snr = float(np.mean(snr_values)) if snr_values else None
    avg_dnsmos_before = float(np.mean(dnsmos_before)) if dnsmos_before else None
    avg_dnsmos_after = float(np.mean(dnsmos_after)) if dnsmos_after else None
    delta_dnsmos = None
    if avg_dnsmos_before is not None and avg_dnsmos_after is not None:
        delta_dnsmos = avg_dnsmos_after - avg_dnsmos_before

    summary = [
        "# 音频清洗 A/B 对比报告",
        "",
        f"- 对比样本数: {len(pairs)}",
        f"- 平均 SNR 代理分数(dB): {avg_snr}",
        f"- DNSMOS before(OVRL): {avg_dnsmos_before}",
        f"- DNSMOS after(OVRL): {avg_dnsmos_after}",
        f"- DNSMOS 改善值(OVRL): {delta_dnsmos}",
        "",
        "## 产物",
        f"- 明细: `{report_path}`",
        f"- 频谱图样例目录: `{samples_dir}`",
        "",
        "## 说明",
        "- 若 DNSMOS 为空，表示未接入本地 dnsmos 推理脚本或权重。",
        "- SNR 代理分数用于快速排查，不等价于带干净参考的侵入式指标。",
    ]
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    print(f"[audio_ab_report] done, summary={summary_path}")


if __name__ == "__main__":
    main()
