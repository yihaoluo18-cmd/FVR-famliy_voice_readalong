import os
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Tuple

import librosa
import numpy as np
import soundfile as sf


def _to_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_float_env(name: str, default: float, min_v: float = None, max_v: float = None) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        value = float(raw) if raw else float(default)
    except Exception:
        value = float(default)
    if min_v is not None:
        value = max(float(min_v), value)
    if max_v is not None:
        value = min(float(max_v), value)
    return value


def _safe_int_env(name: str, default: int, min_v: int = None, max_v: int = None) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else int(default)
    except Exception:
        value = int(default)
    if min_v is not None:
        value = max(int(min_v), value)
    if max_v is not None:
        value = min(int(max_v), value)
    return value


def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 1.0:
        audio = audio / peak
    return np.clip(audio, -1.0, 1.0).astype(np.float32)


def _resolve_df_model_dir(default_dir_name: str) -> Path | None:
    override = os.environ.get("TRAIN_AUDIO_PURIFY_DF_MODEL_DIR", "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        return p if p.exists() else None
    local_model = Path(__file__).resolve().parents[1] / "tools" / "denoise-model" / default_dir_name
    return local_model if local_model.exists() else None


def _run_deepfilternet_cli(model_dir_name: str, engine_name: str, input_path: str, output_path: str) -> Dict[str, str]:
    cli = os.environ.get("TRAIN_AUDIO_PURIFY_DF_CLI", "").strip() or "/home/ubuntu/anaconda3/bin/deepFilter"
    cli_path = Path(cli)
    if not cli_path.exists():
        raise FileNotFoundError(cli)
    model_base_dir = _resolve_df_model_dir(model_dir_name)
    with tempfile.TemporaryDirectory(prefix="audio_purify_df_cli_") as tmpdir:
        tmpdir_p = Path(tmpdir)
        cmd = [
            str(cli_path),
            str(Path(input_path).resolve()),
            "-o",
            str(tmpdir_p),
            "--no-suffix",
            "--log-level",
            "error",
        ]
        if model_base_dir is not None:
            cmd.extend(["-m", str(model_base_dir)])
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        cli_out = tmpdir_p / Path(input_path).name
        if not cli_out.exists():
            raise FileNotFoundError(f"DeepFilter CLI output missing: {cli_out}")
        shutil.copyfile(str(cli_out), output_path)
    detail = f"deepFilter_cli:{cli_path}"
    if model_base_dir is not None:
        detail = f"{detail}:{model_base_dir}"
    return {"engine": engine_name, "detail": detail}


def _run_deepfilternet(model_dir_name: str, engine_name: str, input_path: str, output_path: str) -> Dict[str, str]:
    try:
        from df.enhance import enhance, init_df, load_audio, save_audio  # type: ignore

        model_base_dir = _resolve_df_model_dir(model_dir_name)
        model, df_state, _ = init_df(
            model_base_dir=None if model_base_dir is None else str(model_base_dir),
            post_filter=False,
        )
        audio, _ = load_audio(input_path, sr=df_state.sr())
        enhanced = enhance(model, df_state, audio)
        save_audio(output_path, enhanced, df_state.sr())
        detail = "df.enhance"
        if model_base_dir is not None:
            detail = f"{detail}:{model_base_dir}"
        return {"engine": engine_name, "detail": detail}
    except Exception:
        return _run_deepfilternet_cli(model_dir_name, engine_name, input_path, output_path)


def _run_deepfilternet2(input_path: str, output_path: str) -> Dict[str, str]:
    return _run_deepfilternet("DeepFilterNet2", "deepfilternet2", input_path, output_path)


def _run_deepfilternet3(input_path: str, output_path: str) -> Dict[str, str]:
    return _run_deepfilternet("DeepFilterNet3", "deepfilternet3", input_path, output_path)


def _run_frcrn_fallback(input_path: str, output_path: str) -> Dict[str, str]:
    from modelscope.pipelines import pipeline  # type: ignore
    from modelscope.utils.constant import Tasks  # type: ignore

    local_model = Path(__file__).resolve().parents[1] / "tools" / "denoise-model" / "speech_frcrn_ans_cirm_16k"
    model_ref = str(local_model) if local_model.exists() else "damo/speech_frcrn_ans_cirm_16k"
    ans = pipeline(Tasks.acoustic_noise_suppression, model=model_ref)
    result = ans(input=input_path)
    out = result["output_pcm"]
    if isinstance(out, (bytes, bytearray)):
        with open(output_path, "wb") as f:
            f.write(out)
    else:
        shutil.copyfile(str(out), output_path)
    return {"engine": "frcrn_fallback", "detail": str(model_ref)}


def _run_wpe_dereverb(input_path: str, output_path: str) -> Dict[str, str]:
    from nara_wpe.wpe import wpe  # type: ignore

    audio, sr = sf.read(input_path, dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    stft = librosa.stft(audio, n_fft=1024, hop_length=256, win_length=1024)
    spec = stft.T[np.newaxis, :, :]
    dereverb_spec = wpe(spec, taps=10, delay=3, iterations=3, statistics_mode="full")
    dereverb_stft = dereverb_spec[0].T
    out = librosa.istft(dereverb_stft, hop_length=256, win_length=1024, length=len(audio))
    sf.write(output_path, _normalize_audio(out), sr)
    return {"engine": "wpe", "detail": "nara_wpe.wpe"}


def _run_dpdfnet_onnx(input_path: str, output_path: str) -> Dict[str, str]:
    import onnxruntime as ort  # type: ignore

    model_path = os.environ.get("TRAIN_DPDFNET_MODEL", "").strip()
    if not model_path:
        raise RuntimeError("TRAIN_DPDFNET_MODEL is not set")
    if not os.path.exists(model_path):
        raise FileNotFoundError(model_path)

    audio, sr = sf.read(input_path, dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    if sr != 16000:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        sr = 16000
    audio = _normalize_audio(audio)
    feats = audio[np.newaxis, np.newaxis, :]

    sess = ort.InferenceSession(model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    output = sess.run(None, {input_name: feats.astype(np.float32)})[0]
    enhanced = np.squeeze(output)
    sf.write(output_path, _normalize_audio(enhanced), sr)
    return {"engine": "dpdfnet_onnx", "detail": model_path}


def _run_noisereduce_spectral_gate(audio: np.ndarray, sr: int) -> Tuple[np.ndarray, Dict[str, str]]:
    if audio.size <= 0:
        return audio, {"engine": "none", "detail": "empty_audio"}

    if not _to_bool(os.environ.get("TRAIN_AUDIO_PURIFY_ENABLE_SPECTRAL_GATE"), True):
        return audio, {"engine": "disabled", "detail": "TRAIN_AUDIO_PURIFY_ENABLE_SPECTRAL_GATE=false"}

    try:
        import noisereduce as nr  # type: ignore
    except Exception as exc:
        return audio, {"engine": "unavailable", "detail": f"noisereduce_import_failed:{exc.__class__.__name__}"}

    stationary = _to_bool(os.environ.get("TRAIN_AUDIO_PURIFY_SPECTRAL_GATE_STATIONARY"), False)
    prop_decrease = _safe_float_env("TRAIN_AUDIO_PURIFY_SPECTRAL_GATE_PROP_DECREASE", 0.88, 0.0, 1.0)
    time_constant_s = _safe_float_env("TRAIN_AUDIO_PURIFY_SPECTRAL_GATE_TIME_CONSTANT", 1.6, 0.05, 8.0)
    n_fft = _safe_int_env("TRAIN_AUDIO_PURIFY_SPECTRAL_GATE_NFFT", 512, 128, 4096)
    hop_length = _safe_int_env("TRAIN_AUDIO_PURIFY_SPECTRAL_GATE_HOP", max(64, n_fft // 4), 16, 2048)

    try:
        reduced = nr.reduce_noise(
            y=audio,
            sr=int(sr),
            stationary=bool(stationary),
            prop_decrease=float(prop_decrease),
            time_constant_s=float(time_constant_s),
            n_fft=int(n_fft),
            hop_length=int(hop_length),
        )
        reduced = _normalize_audio(np.asarray(reduced, dtype=np.float32))
        return reduced, {
            "engine": "noisereduce",
            "detail": (
                f"stationary={stationary},prop_decrease={prop_decrease:.2f},"
                f"time_constant_s={time_constant_s:.2f},n_fft={n_fft},hop={hop_length}"
            ),
        }
    except Exception as exc:
        return audio, {"engine": "failed", "detail": f"spectral_gate_failed:{exc.__class__.__name__}"}


def _trim_edge_silence(audio: np.ndarray, sr: int) -> Tuple[np.ndarray, Dict[str, object]]:
    if audio.size <= 0:
        return audio, {"applied": False, "reason": "empty_audio"}

    if not _to_bool(os.environ.get("TRAIN_AUDIO_PURIFY_ENABLE_EDGE_TRIM"), True):
        return audio, {"applied": False, "reason": "disabled"}

    top_db = _safe_float_env("TRAIN_AUDIO_PURIFY_TRIM_TOP_DB", 34.0, 6.0, 80.0)
    frame_length = _safe_int_env("TRAIN_AUDIO_PURIFY_TRIM_FRAME", 1024, 128, 8192)
    hop_length = _safe_int_env("TRAIN_AUDIO_PURIFY_TRIM_HOP", 256, 16, 4096)
    pad_ms = _safe_int_env("TRAIN_AUDIO_PURIFY_TRIM_PAD_MS", 140, 0, 3000)
    max_trim_ratio = _safe_float_env("TRAIN_AUDIO_PURIFY_TRIM_MAX_RATIO", 0.70, 0.0, 0.95)
    min_keep_sec = _safe_float_env("TRAIN_AUDIO_PURIFY_TRIM_MIN_KEEP_SEC", 2.0, 0.2, 60.0)

    try:
        intervals = librosa.effects.split(audio, top_db=top_db, frame_length=frame_length, hop_length=hop_length)
    except Exception as exc:
        return audio, {"applied": False, "reason": f"split_failed:{exc.__class__.__name__}"}

    if intervals is None or len(intervals) == 0:
        return audio, {"applied": False, "reason": "no_non_silent_interval"}

    total = int(audio.shape[0])
    start = int(intervals[0][0])
    end = int(intervals[-1][1])
    pad = int(float(sr) * (float(pad_ms) / 1000.0))
    start = max(0, start - pad)
    end = min(total, end + pad)

    keep = max(0, end - start)
    if keep <= 0:
        return audio, {"applied": False, "reason": "trim_to_empty"}

    min_keep_samples = int(float(sr) * float(min_keep_sec))
    if keep < min_keep_samples:
        return audio, {"applied": False, "reason": "too_short_after_trim", "keep_samples": keep}

    max_trim_samples = int(float(total) * float(max_trim_ratio))
    trimmed_samples = total - keep
    if trimmed_samples <= 0:
        return audio, {"applied": False, "reason": "already_compact"}
    if trimmed_samples > max_trim_samples:
        return audio, {
            "applied": False,
            "reason": "trim_exceeds_ratio_limit",
            "trimmed_samples": trimmed_samples,
            "max_trim_samples": max_trim_samples,
        }

    trimmed = np.asarray(audio[start:end], dtype=np.float32)
    return trimmed, {
        "applied": True,
        "reason": "edge_trimmed",
        "start_sample": start,
        "end_sample": end,
        "removed_head_sec": float(start) / float(sr),
        "removed_tail_sec": float(total - end) / float(sr),
        "src_sec": float(total) / float(sr),
        "dst_sec": float(keep) / float(sr),
    }


def purify_audio_file(
    input_path: str,
    output_path: str,
    enable_vocal_separation: bool = False,
    vocal_model: str = "HP5",
    enable_denoise: bool = True,
    enable_dereverb: bool = True,
    enable_deecho: bool = False,
    verbose: bool = False,
) -> Dict[str, str]:
    del enable_vocal_separation, vocal_model, enable_deecho
    input_path = str(Path(input_path))
    output_path = str(Path(output_path))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    work_dir = tempfile.mkdtemp(prefix="audio_purify_")
    denoise_out = os.path.join(work_dir, "denoise.wav")
    dereverb_out = os.path.join(work_dir, "dereverb.wav")
    report: Dict[str, str] = {
        "input": input_path,
        "output": output_path,
        "denoise_engine": "none",
        "dereverb_engine": "none",
        "spectral_gate_engine": "none",
        "silence_trim": "none",
    }

    current = input_path
    try:
        enable_denoise = enable_denoise and _to_bool(os.environ.get("TRAIN_AUDIO_PURIFY_ENABLE_DENOISE"), True)
        enable_dereverb = enable_dereverb and _to_bool(os.environ.get("TRAIN_AUDIO_PURIFY_ENABLE_DEREVERB"), True)
        strategy = os.environ.get("TRAIN_AUDIO_PURIFY_STRATEGY", "deepfilternet2_wpe").strip().lower()

        if strategy == "dpdfnet":
            denoise_meta = _run_dpdfnet_onnx(current, denoise_out)
            report["denoise_engine"] = denoise_meta["engine"]
            report["denoise_detail"] = denoise_meta["detail"]
            report["dereverb_engine"] = "included_in_dpdfnet"
            report["dereverb_detail"] = "included_in_dpdfnet"
            current = denoise_out
        else:
            if enable_denoise:
                try:
                    if strategy in {"deepfilternet2", "deepfilternet2_wpe", "df2", "net2"}:
                        denoise_meta = _run_deepfilternet2(current, denoise_out)
                    else:
                        denoise_meta = _run_deepfilternet3(current, denoise_out)
                except Exception:
                    denoise_meta = _run_frcrn_fallback(current, denoise_out)
                report["denoise_engine"] = denoise_meta["engine"]
                report["denoise_detail"] = denoise_meta["detail"]
                current = denoise_out

            if enable_dereverb:
                try:
                    dereverb_meta = _run_wpe_dereverb(current, dereverb_out)
                    report["dereverb_engine"] = dereverb_meta["engine"]
                    report["dereverb_detail"] = dereverb_meta["detail"]
                    current = dereverb_out
                except Exception as exc:
                    report["dereverb_engine"] = "skipped"
                    report["dereverb_detail"] = f"wpe_unavailable:{exc.__class__.__name__}"

        audio, sr = sf.read(current, dtype="float32")
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        audio = _normalize_audio(np.asarray(audio, dtype=np.float32))

        audio, spectral_meta = _run_noisereduce_spectral_gate(audio, int(sr))
        report["spectral_gate_engine"] = str((spectral_meta or {}).get("engine", "none"))
        report["spectral_gate_detail"] = str((spectral_meta or {}).get("detail", ""))

        audio, trim_meta = _trim_edge_silence(audio, int(sr))
        report["silence_trim"] = str((trim_meta or {}).get("reason", "none"))
        report["silence_trim_applied"] = bool((trim_meta or {}).get("applied", False))
        if isinstance(trim_meta, dict):
            report["silence_trim_src_sec"] = trim_meta.get("src_sec")
            report["silence_trim_dst_sec"] = trim_meta.get("dst_sec")
            report["silence_trim_removed_head_sec"] = trim_meta.get("removed_head_sec")
            report["silence_trim_removed_tail_sec"] = trim_meta.get("removed_tail_sec")

        sf.write(output_path, _normalize_audio(np.asarray(audio, dtype=np.float32)), sr)
        return report
    finally:
        if verbose:
            print(f"[audio_purification] {report}")
        shutil.rmtree(work_dir, ignore_errors=True)
