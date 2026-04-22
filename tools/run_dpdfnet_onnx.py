import argparse
from pathlib import Path

import librosa
import numpy as np
import onnxruntime as ort
import soundfile as sf


def _load_mono_16k(path: Path) -> np.ndarray:
    audio, sr = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    if sr != 16000:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
    return audio.astype(np.float32)


def _enhance_with_dpdfnet(sess: ort.InferenceSession, audio: np.ndarray) -> np.ndarray:
    # DPDFNet4 ONNX usually uses n_fft=320 (161 bins), hop=160 @16k
    n_fft = 320
    hop = 160
    win = 320
    window = np.hanning(win).astype(np.float32)

    spec = librosa.stft(audio, n_fft=n_fft, hop_length=hop, win_length=win, window=window, center=True)
    # spec shape: [freq_bins, frames], complex64
    freq_bins, frames = spec.shape
    if freq_bins != 161:
        raise RuntimeError(f"Unexpected freq bins: {freq_bins}, expected 161")

    state = np.zeros((52592,), dtype=np.float32)
    out_spec = np.zeros_like(spec, dtype=np.complex64)

    for t in range(frames):
        frame = spec[:, t]
        inp = np.stack([frame.real, frame.imag], axis=-1).astype(np.float32)  # [161,2]
        inp = inp[np.newaxis, np.newaxis, :, :]  # [1,1,161,2]
        spec_e, state = sess.run(
            None,
            {
                "spec": inp,
                "state_in": state,
            },
        )
        cplx = spec_e[0, 0, :, 0] + 1j * spec_e[0, 0, :, 1]
        out_spec[:, t] = cplx.astype(np.complex64)

    enhanced = librosa.istft(out_spec, hop_length=hop, win_length=win, window=window, length=len(audio))
    peak = float(np.max(np.abs(enhanced))) if enhanced.size else 0.0
    if peak > 1.0:
        enhanced = enhanced / peak
    return enhanced.astype(np.float32)


def run_folder(model_path: Path, in_dir: Path, out_dir: Path, providers: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = ort.InferenceSession(str(model_path), providers=providers)
    files = sorted(in_dir.glob("*.wav"))
    for i, wav in enumerate(files, 1):
        audio = _load_mono_16k(wav)
        enhanced = _enhance_with_dpdfnet(sess, audio)
        sf.write(str(out_dir / wav.name), enhanced, 16000, subtype="PCM_16")
        if i % 20 == 0 or i == len(files):
            print(f"{in_dir.name}: {i}/{len(files)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()

    providers = ["CPUExecutionProvider"] if args.cpu else ["CUDAExecutionProvider", "CPUExecutionProvider"]
    run_folder(Path(args.model), Path(args.input), Path(args.output), providers=providers)


if __name__ == "__main__":
    main()
