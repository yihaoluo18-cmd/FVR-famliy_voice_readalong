"""
# api.py usage

` python api.py -dr "123.wav" -dt "一二三。" -dl "zh" `

## 执行参数:

`-s` - `SoVITS模型路径, 可在 config.py 中指定`
`-g` - `GPT模型路径, 可在 config.py 中指定`

调用请求缺少参考音频时使用
`-dr` - `默认参考音频路径`
`-dt` - `默认参考音频文本`
`-dl` - `默认参考音频语种, "中文","英文","日文","韩文","粤语,"zh","en","ja","ko","yue"`

`-d` - `推理设备, "cuda","cpu"`
`-a` - `绑定地址, 默认"127.0.0.1"`
`-p` - `绑定端口, 默认9880, 可在 config.py 中指定`
`-fp` - `覆盖 config.py 使用全精度`
`-hp` - `覆盖 config.py 使用半精度`
`-sm` - `流式返回模式, 默认不启用, "close","c", "normal","n", "keepalive","k"`
·-mt` - `返回的音频编码格式, 流式默认ogg, 非流式默认wav, "wav", "ogg", "aac"`
·-st` - `返回的音频数据类型, 默认int16, "int16", "int32"`
·-cp` - `文本切分符号设定, 默认为空, 以",.，。"字符串的方式传入`

`-hb` - `cnhubert路径`
`-b` - `bert路径`

## 调用:

### 推理

endpoint: `/`

使用执行参数指定的参考音频:
GET:
    `http://127.0.0.1:9880?text=先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。&text_language=zh`
POST:
```json
{
    "text": "先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。",
    "text_language": "zh"
}
```

使用执行参数指定的参考音频并设定分割符号:
GET:
    `http://127.0.0.1:9880?text=先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。&text_language=zh&cut_punc=，。`
POST:
```json
{
    "text": "先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。",
    "text_language": "zh",
    "cut_punc": "，。",
}
```

手动指定当次推理所使用的参考音频:
GET:
    `http://127.0.0.1:9880?refer_wav_path=123.wav&prompt_text=一二三。&prompt_language=zh&text=先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。&text_language=zh`
POST:
```json
{
    "refer_wav_path": "123.wav",
    "prompt_text": "一二三。",
    "prompt_language": "zh",
    "text": "先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。",
    "text_language": "zh"
}
```

RESP:
成功: 直接返回 wav 音频流， http code 200
失败: 返回包含错误信息的 json, http code 400

手动指定当次推理所使用的参考音频，并提供参数:
GET:
    `http://127.0.0.1:9880?refer_wav_path=123.wav&prompt_text=一二三。&prompt_language=zh&text=先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。&text_language=zh&top_k=20&top_p=0.6&temperature=0.6&speed=1&inp_refs="456.wav"&inp_refs="789.wav"`
POST:
```json
{
    "refer_wav_path": "123.wav",
    "prompt_text": "一二三。",
    "prompt_language": "zh",
    "text": "先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。",
    "text_language": "zh",
    "top_k": 20,
    "top_p": 0.6,
    "temperature": 0.6,
    "speed": 1,
    "inp_refs": ["456.wav","789.wav"]
}
```

RESP:
成功: 直接返回 wav 音频流， http code 200
失败: 返回包含错误信息的 json, http code 400


### 更换默认参考音频

endpoint: `/change_refer`

key与推理端一样

GET:
    `http://127.0.0.1:9880/change_refer?refer_wav_path=123.wav&prompt_text=一二三。&prompt_language=zh`
POST:
```json
{
    "refer_wav_path": "123.wav",
    "prompt_text": "一二三。",
    "prompt_language": "zh"
}
```

RESP:
成功: json, http code 200
失败: json, 400


### 命令控制

endpoint: `/control`

command:
"restart": 重新运行
"exit": 结束运行

GET:
    `http://127.0.0.1:9880/control?command=restart`
POST:
```json
{
    "command": "restart"
}
```

RESP: 无

"""

import argparse
import asyncio
import os
import re
import sys
import json
import base64
import shutil
import threading
import time
from pathlib import Path
from datetime import datetime
from modules.ai_runtime import load_ai_runtime_config


# 定义临时文件目录（添加到代码开头）
TEMP_RAW_DIR = "train/temp_raw_audio"  # 存放原始上传音频（MP3/AMR）
TEMP_WAV_DIR = "train/temp_wav_audio"  # 存放转码后的WAV音频

# 前端"需要录制/展示"的句子数量（索引范围: 0 ~ MAX_READ_SENTENCES-1）
# 注意：训练端仍由 train_api.py 的 MAX_DATASET_SENTENCES 控制（当前为 14）
MAX_READ_SENTENCES = 14

# 确保目录存在
os.makedirs(TEMP_RAW_DIR, exist_ok=True)
os.makedirs(TEMP_WAV_DIR, exist_ok=True)

# Windows 控制台常为 GBK，print/部分日志输出含 ✅、⚠️ 等时会触发 UnicodeEncodeError
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

now_dir = os.getcwd()
sys.path.append(now_dir)

# 需要兼容/复用旧脚本的 import：优先从 modules/tts_backend/tools 解析
tools_dir = os.path.join(os.path.dirname(__file__), "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ==================== 魔法书架：绘本库路径 ====================
LIBRARY_ROOT = os.path.join(PROJECT_ROOT, "modules", "books_library", "绘本集")
MAGIC_INDEX_JSON = os.path.join(PROJECT_ROOT, "modules", "books_library", "library", "magic_books_index.json")
WX_STATIC_ROOT = os.path.join(PROJECT_ROOT, "modules", "wechat_frontend", "wx_static")
sys.path.append("%s/GPT_SoVITS" % (now_dir))

# 设置 NLTK 数据路径，避免下载错误
try:
    import nltk
    nltk_data_dir = os.path.join(now_dir, "venv", "nltk_data")
    if os.path.exists(nltk_data_dir) and nltk_data_dir not in nltk.data.path:
        nltk.data.path.insert(0, nltk_data_dir)
except:
    pass  # 如果导入失败，忽略

import signal
_langseg_import_error = None
try:
    from text.LangSegmenter import LangSegmenter
except Exception as e:
    # 环境里缺少 jieba 等依赖时，允许服务启动；文本分段降级为原样返回
    _langseg_import_error = str(e)

    class LangSegmenter:  # type: ignore
        @staticmethod
        def getTexts(text, lang=None):
            if text is None:
                return []
            return [text]
from time import time as ttime
import torch
_torchaudio_import_error = None
try:
    import torchaudio
except Exception as e:
    # 常见原因：torchaudio 依赖 CUDA 动态库（libc10_cuda.so）但当前环境缺失。
    # 这里允许服务启动，后续用 librosa 做降级加载/重采样。
    torchaudio = None  # type: ignore
    _torchaudio_import_error = str(e)
import librosa
import soundfile as sf
import wave
import audioop
from fastapi import FastAPI, Request, Query, BackgroundTasks
from typing import List, Optional
from fastapi.responses import StreamingResponse, JSONResponse, Response
import uvicorn
from transformers import AutoModelForMaskedLM, AutoTokenizer
import numpy as np
from feature_extractor import cnhubert
from io import BytesIO
from module.models import Generator, SynthesizerTrn, SynthesizerTrnV3
# from peft import LoraConfig, get_peft_model  # 暂时注释，避免版本兼容问题
from AR.models.t2s_lightning_module import Text2SemanticLightningModule
from text import cleaned_text_to_sequence
from text.cleaner import clean_text
from module.mel_processing import spectrogram_torch
import config as global_config
import logging
import subprocess
from fastapi.middleware.cors import CORSMiddleware
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Header
import httpx
import json
import random

# 这里提前初始化 logger，避免后续导入失败分支引用 logger 报未定义
logger = logging.getLogger("uvicorn")

# LangSegmenter 依赖（jieba）缺失时给出提示，但不阻塞服务启动
if _langseg_import_error:
    logger.warning(f"[wx_api] LangSegmenter 导入失败（将降级为不分段）: {_langseg_import_error}")

if _torchaudio_import_error:
    logger.warning(f"[wx_api] torchaudio 导入失败（将降级为 librosa 加载/重采样）: {_torchaudio_import_error}")

# 导入音频预处理模块
try:
    # 新版：仅使用官网 UVR5 的 HP5_only_main_vocal 模型提取主人声
    # 对外统一用 preprocess_audio 接口，内部已经固定为 HP5_only_main_vocal 逻辑
    from audio_preprocess import preprocess_audio
    AUDIO_PREPROCESS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"[wx_api] 音频预处理模块导入失败: {e}，将跳过预处理步骤")
    AUDIO_PREPROCESS_AVAILABLE = False 

class DefaultRefer:
    def __init__(self, path, text, language):
        self.path = args.default_refer_path
        self.text = args.default_refer_text
        self.language = args.default_refer_language

    def is_ready(self) -> bool:
        return is_full(self.path, self.text, self.language)


def is_empty(*items):  # 任意一项不为空返回False
    for item in items:
        if item is not None and item != "":
            return False
    return True


def is_full(*items):  # 任意一项为空返回False
    for item in items:
        if item is None or item == "":
            return False
    return True


bigvgan_model = hifigan_model = sv_cn_model = None


def clean_hifigan_model():
    global hifigan_model
    if hifigan_model:
        hifigan_model = hifigan_model.cpu()
        hifigan_model = None
        try:
            torch.cuda.empty_cache()
        except:
            pass


def clean_bigvgan_model():
    global bigvgan_model
    if bigvgan_model:
        bigvgan_model = bigvgan_model.cpu()
        bigvgan_model = None
        try:
            torch.cuda.empty_cache()
        except:
            pass


def clean_sv_cn_model():
    global sv_cn_model
    if sv_cn_model:
        sv_cn_model.embedding_model = sv_cn_model.embedding_model.cpu()
        sv_cn_model = None
        try:
            torch.cuda.empty_cache()
        except:
            pass


def init_bigvgan():
    global bigvgan_model, hifigan_model, sv_cn_model
    from BigVGAN import bigvgan

    bigvgan_model = bigvgan.BigVGAN.from_pretrained(
        "%s/GPT_SoVITS/pretrained_models/models--nvidia--bigvgan_v2_24khz_100band_256x" % (now_dir,),
        use_cuda_kernel=False,
    )  # if True, RuntimeError: Ninja is required to load C++ extensions
    # remove weight norm in the model and set to eval mode
    bigvgan_model.remove_weight_norm()
    bigvgan_model = bigvgan_model.eval()

    if is_half == True:
        bigvgan_model = bigvgan_model.half().to(device)
    else:
        bigvgan_model = bigvgan_model.to(device)


def init_hifigan():
    global hifigan_model, bigvgan_model, sv_cn_model
    hifigan_model = Generator(
        initial_channel=100,
        resblock="1",
        resblock_kernel_sizes=[3, 7, 11],
        resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        upsample_rates=[10, 6, 2, 2, 2],
        upsample_initial_channel=512,
        upsample_kernel_sizes=[20, 12, 4, 4, 4],
        gin_channels=0,
        is_bias=True,
    )
    hifigan_model.eval()
    hifigan_model.remove_weight_norm()
    state_dict_g = torch.load(
        "%s/GPT_SoVITS/pretrained_models/gsv-v4-pretrained/vocoder.pth" % (now_dir,),
        map_location="cpu",
        weights_only=False,
    )
    print("loading vocoder", hifigan_model.load_state_dict(state_dict_g))
    if is_half == True:
        hifigan_model = hifigan_model.half().to(device)
    else:
        hifigan_model = hifigan_model.to(device)


from sv import SV


def init_sv_cn():
    global hifigan_model, bigvgan_model, sv_cn_model
    try:
        sv_cn_model = SV(device, is_half)
    except FileNotFoundError as e:
        logger.warning(f"SV模型初始化失败: {str(e)}")
        logger.info("SV模型用于说话人验证功能，如果不需要可以忽略此警告")
        sv_cn_model = None
    except Exception as e:
        logger.error(f"SV模型初始化失败: {str(e)}")
        sv_cn_model = None


resample_transform_dict = {}


def resample(audio_tensor, sr0, sr1, device):
    global resample_transform_dict
    if torchaudio is None:
        # fallback: 使用 librosa.resample（在CPU上处理），再转回 torch tensor
        if isinstance(audio_tensor, torch.Tensor):
            x = audio_tensor.detach().cpu()
            if x.dim() == 2:
                x = x[0]
            x_np = x.numpy()
        else:
            x_np = np.asarray(audio_tensor)
        y_np = librosa.resample(x_np, orig_sr=sr0, target_sr=sr1)
        y = torch.from_numpy(y_np).unsqueeze(0).to(device)
        return y
    key = "%s-%s-%s" % (sr0, sr1, str(device))
    if key not in resample_transform_dict:
        resample_transform_dict[key] = torchaudio.transforms.Resample(sr0, sr1).to(device)
    return resample_transform_dict[key](audio_tensor)


from module.mel_processing import mel_spectrogram_torch

spec_min = -12
spec_max = 2


def norm_spec(x):
    return (x - spec_min) / (spec_max - spec_min) * 2 - 1


def denorm_spec(x):
    return (x + 1) / 2 * (spec_max - spec_min) + spec_min


mel_fn = lambda x: mel_spectrogram_torch(
    x,
    **{
        "n_fft": 1024,
        "win_size": 1024,
        "hop_size": 256,
        "num_mels": 100,
        "sampling_rate": 24000,
        "fmin": 0,
        "fmax": None,
        "center": False,
    },
)
mel_fn_v4 = lambda x: mel_spectrogram_torch(
    x,
    **{
        "n_fft": 1280,
        "win_size": 1280,
        "hop_size": 320,
        "num_mels": 100,
        "sampling_rate": 32000,
        "fmin": 0,
        "fmax": None,
        "center": False,
    },
)


sr_model = None


def audio_sr(audio, sr):
    global sr_model
    if sr_model == None:
        from tools.audio_sr import AP_BWE

        try:
            sr_model = AP_BWE(device, DictToAttrRecursive)
        except FileNotFoundError:
            logger.info("你没有下载超分模型的参数，因此不进行超分。如想超分请先参照教程把文件下载")
            return audio.cpu().detach().numpy(), sr
    return sr_model(audio, sr)


class Speaker:
    def __init__(self, name, gpt, sovits, phones=None, bert=None, prompt=None):
        self.name = name
        self.sovits = sovits
        self.gpt = gpt
        self.phones = phones
        self.bert = bert
        self.prompt = prompt


# 说话人缓冲区：key 为 voice_id 或 "default"
speaker_list = {}

# -----------------------------
# 预定义的“我的声音”模型库
# -----------------------------
# 这里注册所有已训练好的个人声音模型，可以通过 voice_id 进行切换
VOICE_LIBRARY = {

    # voice_001: 30秒训练得到的个人声线（预训练模型，用于快速体验）
    "voice_001": {
        "name": "我的30秒中文模型",
        # 使用相对路径，基于now_dir自动解析
        "gpt_path": os.path.abspath(os.path.join(now_dir, "GPT_weights_v2Pro", "30s-e15.ckpt")),
        "sovits_path": os.path.abspath(os.path.join(now_dir, "SoVITS_weights_v2Pro", "30s_e8_s184.pth")),
        "model_type": "pretrained",  # 标记为预训练模型，用于快速体验
    },
    # voice_002: HYM 声音模型（预训练模型）
    "voice_002": {
        "name": "HYM",
        "gpt_path": r"D:\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\GPT_weights_v2Pro\HYM-e15.ckpt",
        "sovits_path": r"D:\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2Pro\HYM_e8_s168.pth",
        "model_type": "pretrained",  # 标记为预训练模型
    }
}


QWEN_BASE_FEMALE_VOICE_ID = "voice_001"
QWEN_BASE_MALE_VOICE_ID = "voice_002"
QWEN_BASE_VOICE_IDS = {QWEN_BASE_FEMALE_VOICE_ID, QWEN_BASE_MALE_VOICE_ID}


def _build_qwen_base_voice_profiles() -> dict:
    return {
        QWEN_BASE_FEMALE_VOICE_ID: {
            "name": "温柔姐姐",
            "model_type": "pretrained",
            "provider": "qwen_tts",
            "qwen_voice": "Cherry",
            "qwen_voice_candidates": ["Cherry", "Clover", "Nora"],
            "is_builtin": True,
            "can_delete": False,
            "can_rename": False,
            "gender": "female",
            "scene": "绘本故事",
            "emotion": "温柔",
            "voice_group": "qwen_base",
            "quick_story": True,
            "trained_at": "",
        },
        QWEN_BASE_MALE_VOICE_ID: {
            "name": "俊朗哥哥",
            "model_type": "pretrained",
            "provider": "qwen_tts",
            "qwen_voice": "Ethan",
            "qwen_voice_candidates": ["Ethan", "Atlas", "Echo"],
            "is_builtin": True,
            "can_delete": False,
            "can_rename": False,
            "gender": "male",
            "scene": "绘本故事",
            "emotion": "自然",
            "voice_group": "qwen_base",
            "quick_story": True,
            "trained_at": "",
        },
    }


def _is_protected_voice(voice_id: str, profile: Optional[dict] = None) -> bool:
    vid = str(voice_id or "").strip()
    info = profile if isinstance(profile, dict) else (VOICE_LIBRARY.get(vid) or {})
    if vid in QWEN_BASE_VOICE_IDS:
        return True
    if bool((info or {}).get("is_builtin")):
        return True
    if (info or {}).get("can_delete") is False:
        return True
    return False


def _is_qwen_voice_profile(profile: Optional[dict]) -> bool:
    p = profile if isinstance(profile, dict) else {}
    provider = str((p or {}).get("provider") or "").strip().lower()
    return provider == "qwen_tts"


def _qwen_voice_candidates(profile: Optional[dict]) -> List[str]:
    p = profile if isinstance(profile, dict) else {}
    raw = p.get("qwen_voice_candidates")
    out = []
    if isinstance(raw, (list, tuple)):
        for it in raw:
            v = str(it or "").strip()
            if v and v not in out:
                out.append(v)
    elif isinstance(raw, str):
        for it in raw.split(','):
            v = str(it or "").strip()
            if v and v not in out:
                out.append(v)

    primary = str(p.get("qwen_voice") or "").strip()
    if primary and primary not in out:
        out.insert(0, primary)

    if not out:
        g = str((p or {}).get("gender") or "").strip().lower()
        out = ["Cherry", "Clover"] if g == "female" else ["Ethan", "Atlas"]
    return out


def _ensure_builtin_base_voices() -> bool:
    changed = False
    builtin = _build_qwen_base_voice_profiles()
    for vid, info in builtin.items():
        current = VOICE_LIBRARY.get(vid)
        if not isinstance(current, dict):
            VOICE_LIBRARY[vid] = dict(info)
            changed = True
            continue
        merged = dict(current)
        # 对基础音色关键能力做强制修正，避免历史脏数据覆盖。
        for key in [
            "name",
            "model_type",
            "provider",
            "qwen_voice",
            "qwen_voice_candidates",
            "is_builtin",
            "can_delete",
            "can_rename",
            "gender",
            "scene",
            "emotion",
            "voice_group",
            "quick_story",
        ]:
            if merged.get(key) != info.get(key):
                merged[key] = info.get(key)
                changed = True
        if merged != current:
            VOICE_LIBRARY[vid] = merged
    return changed


# 缓冲式分段推理任务
BUFFER_TASKS = {}
BUFFER_TASKS_LOCK = threading.Lock()
BUFFER_TASK_TTL_SEC = 3600

TTS_DEBUG = {}
TTS_DEBUG_LOCK = threading.Lock()
TTS_DEBUG_TTL_SEC = 3600

def _cleanup_tts_debug():
    now = time.time()
    with TTS_DEBUG_LOCK:
        expired = [k for k, v in TTS_DEBUG.items() if now - v.get("created_at", now) > TTS_DEBUG_TTL_SEC]
        for k in expired:
            TTS_DEBUG.pop(k, None)

def _new_debug_record(payload: dict) -> str:
    _cleanup_tts_debug()
    debug_id = uuid.uuid4().hex
    rec = {
        "created_at": time.time(),
        "debug_id": debug_id,
        "payload": payload or {},
        "events": [],
        "segments": [],
    }
    with TTS_DEBUG_LOCK:
        TTS_DEBUG[debug_id] = rec
    return debug_id

def _debug_event(debug_id: str, name: str, **fields):
    if not debug_id:
        return
    evt = {"t": time.time(), "name": name, **fields}
    with TTS_DEBUG_LOCK:
        rec = TTS_DEBUG.get(debug_id)
        if rec is None:
            return
        rec["events"].append(evt)

def _debug_set(debug_id: str, **fields):
    if not debug_id:
        return
    with TTS_DEBUG_LOCK:
        rec = TTS_DEBUG.get(debug_id)
        if rec is None:
            return
        rec.update(fields)

def _debug_add_segment(debug_id: str, index: int, **fields):
    if not debug_id:
        return
    with TTS_DEBUG_LOCK:
        rec = TTS_DEBUG.get(debug_id)
        if rec is None:
            return
        seg = {"index": index, **fields}
        rec["segments"].append(seg)

VOICE_LIBRARY_FILE = str(PROJECT_ROOT / "modules" / "tts_backend" / "data" / "voice_library.json")


def _resolve_project_path(path_str):
    p = str(path_str or "").strip()
    if not p:
        return ""
    if os.path.isabs(p):
        return p
    return os.path.abspath(os.path.join(str(PROJECT_ROOT), p))


def load_voice_library_from_file():
    """从文件加载VOICE_LIBRARY，确保多任务之间共享"""
    if not os.path.exists(VOICE_LIBRARY_FILE):
        return
    try:
        with open(VOICE_LIBRARY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            VOICE_LIBRARY.clear()
            VOICE_LIBRARY.update(data)
            
            # 兼容旧数据：如果没有model_type字段，根据路径判断
            for voice_id, profile in VOICE_LIBRARY.items():
                if "model_type" not in profile:
                    # 如果路径包含 train/user_models，标记为用户训练模型
                    gpt_path = _resolve_project_path(profile.get("gpt_path", ""))
                    sovits_path = _resolve_project_path(profile.get("sovits_path", ""))
                    refer_path = _resolve_project_path(profile.get("refer_audio", ""))
                    if gpt_path:
                        profile["gpt_path"] = gpt_path
                    if sovits_path:
                        profile["sovits_path"] = sovits_path
                    if refer_path:
                        profile["refer_audio"] = refer_path

                    if "train/user_models" in str(gpt_path).replace("\\", "/"):
                        profile["model_type"] = "user_trained"
                    else:
                        # 否则默认为预训练模型（用于快速体验）
                        profile["model_type"] = "pretrained"

            ensure_changed = _ensure_builtin_base_voices()
            if ensure_changed:
                save_voice_library_to_file()

            logger.info(f"[声音库] 已从文件加载 {len(VOICE_LIBRARY)} 个模型: {list(VOICE_LIBRARY.keys())}")
    except json.JSONDecodeError as e:
        logger.warning(f"[声音库] voice_library.json 内容损坏: {str(e)}，已备份为 voice_library.corrupt.json")
        backup_path = VOICE_LIBRARY_FILE.replace(".json", ".corrupt.json")
        try:
            shutil.move(VOICE_LIBRARY_FILE, backup_path)
        except Exception as move_err:
            logger.error(f"[声音库] 备份损坏文件失败: {move_err}")
        # 仅当内存中还保留默认模型时再重新保存，避免无限循环
        save_voice_library_to_file()
    except Exception as e:
        if "logger" in globals():
            logger.error(f"[声音库] 加载文件失败: {str(e)}")
        else:
            print(f"[声音库] 加载文件失败: {str(e)}")


def save_voice_library_to_file():
    """将VOICE_LIBRARY写入文件，持久化保存"""
    try:
        tmp_path = VOICE_LIBRARY_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(VOICE_LIBRARY, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, VOICE_LIBRARY_FILE)
        logger.info(f"[声音库] 已保存 {len(VOICE_LIBRARY)} 个模型到文件")
    except Exception as e:
        logger.error(f"[声音库] 保存文件失败: {str(e)}")


def register_voice_model(
    voice_id: str,
    model_name: str,
    gpt_path: str,
    sovits_path: str,
    scene: str = None,
    emotion: str = None,
    trained_at: str = None,
    ref_audio_path: str = None,  # 参考音频路径（训练时提取）
    ref_text: str = None,  # 参考文本（训练时提取）
    ref_language: str = None,  # 参考语言（训练时提取）
    model_type: str = "user_trained",  # 模型类型：pretrained（预训练）或 user_trained（用户训练）
    owner_user_id: str = None,  # 归属用户ID（建议为 openid/unionid）
) -> bool:
    """
    将训练完成的模型注册到VOICE_LIBRARY
    这个函数可以被训练API调用，确保模型正确注册
    
    Args:
        model_type: "pretrained" 表示预训练模型（用于快速体验），"user_trained" 表示用户训练的模型
    """
    try:
        load_voice_library_from_file()
        # 确保路径是绝对路径
        gpt_path_abs = os.path.abspath(gpt_path) if not os.path.isabs(gpt_path) else gpt_path
        sovits_path_abs = os.path.abspath(sovits_path) if not os.path.isabs(sovits_path) else sovits_path
        
        VOICE_LIBRARY[voice_id] = {
            "name": model_name,
            "gpt_path": gpt_path_abs,
            "sovits_path": sovits_path_abs,
            "scene": scene or "",
            "emotion": emotion or "",
            "trained_at": trained_at or datetime.now().isoformat(),
            "ref_audio_path": ref_audio_path,  # 参考音频路径（用于推理）
            "ref_text": ref_text,  # 参考文本（用于推理）
            "ref_language": ref_language,  # 参考语言（用于推理）
            "model_type": model_type,  # 模型类型标记
            "owner_user_id": str(owner_user_id or "").strip(),
        }
        logger.info(f"[注册模型] {voice_id} - {model_name}")
        logger.info(f"[注册模型] 模型类型: {model_type}")
        logger.info(f"[注册模型] GPT路径: {gpt_path_abs}")
        logger.info(f"[注册模型] SoVITS路径: {sovits_path_abs}")
        logger.info(f"[注册模型] 当前VOICE_LIBRARY包含 {len(VOICE_LIBRARY)} 个模型: {list(VOICE_LIBRARY.keys())}")
        save_voice_library_to_file()
        # 同步写入用户管理数据库：确保音色归属与展示查询稳定
        try:
            try:
                from modules.user_mgmt_backend import db as user_mgmt_db
            except Exception:
                from user_mgmt_backend import db as user_mgmt_db
            user_mgmt_db.init_db()
            user_mgmt_db.upsert_voice_model(
                voice_id=voice_id,
                owner_user_id=str(owner_user_id or "").strip(),
                display_name=model_name,
                gpt_path=gpt_path_abs,
                sovits_path=sovits_path_abs,
                scene=scene or "",
                emotion=emotion or "",
                trained_at=trained_at or datetime.now().isoformat(),
                model_type=model_type or "",
                owner_inferred=0,
            )
        except Exception as db_sync_err:
            logger.warning(f"[注册模型] voice_models 同步失败(不影响主流程): {db_sync_err}")
        return True
    except Exception as e:
        logger.error(f"[注册模型] 失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def delete_voice_model(voice_id: str) -> bool:
    """删除指定 voice_id 的模型"""
    load_voice_library_from_file()
    if voice_id not in VOICE_LIBRARY:
        logger.warning(f"[删除模型] {voice_id} 不存在")
        return False
    profile = VOICE_LIBRARY.get(voice_id) or {}
    if _is_protected_voice(voice_id, profile):
        logger.warning(f"[删除模型] {voice_id} 为基础音色，禁止删除")
        raise ValueError("基础音色不可删除")
    try:
        VOICE_LIBRARY.pop(voice_id, None)
        # 清理 speaker list 缓存
        speaker_list.pop(voice_id, None)
        save_voice_library_to_file()
        # 同步删除数据库记录
        try:
            try:
                from modules.user_mgmt_backend import db as user_mgmt_db
            except Exception:
                from user_mgmt_backend import db as user_mgmt_db
            user_mgmt_db.init_db()
            user_mgmt_db.delete_voice_model(voice_id)
        except Exception as db_sync_err:
            logger.warning(f"[删除模型] voice_models 同步失败(不影响主流程): {db_sync_err}")
        logger.info(f"[删除模型] 已删除 {voice_id}，当前模型数：{len(VOICE_LIBRARY)}")
        return True
    except Exception as e:
        logger.error(f"[删除模型] 失败: {str(e)}")
        return False



def rename_voice_model(voice_id: str, new_name: str) -> bool:
    """重命名指定 voice_id 的模型名称并持久化。"""
    load_voice_library_from_file()
    if voice_id not in VOICE_LIBRARY:
        logger.warning(f"[重命名模型] {voice_id} 不存在")
        return False
    profile = VOICE_LIBRARY.get(voice_id) or {}
    if _is_protected_voice(voice_id, profile) or profile.get("can_rename") is False:
        logger.warning(f"[重命名模型] {voice_id} 为基础音色，禁止重命名")
        raise ValueError("基础音色不可重命名")
    try:
        profile["name"] = new_name
        profile["renamed_at"] = datetime.now().isoformat()
        VOICE_LIBRARY[voice_id] = profile
        save_voice_library_to_file()
        # 同步更新数据库展示名
        try:
            try:
                from modules.user_mgmt_backend import db as user_mgmt_db
            except Exception:
                from user_mgmt_backend import db as user_mgmt_db
            user_mgmt_db.init_db()
            user_mgmt_db.rename_voice_model(voice_id, new_name)
        except Exception as db_sync_err:
            logger.warning(f"[重命名模型] voice_models 同步失败(不影响主流程): {db_sync_err}")
        logger.info(f"[重命名模型] {voice_id} -> {new_name}")
        return True
    except Exception as e:
        logger.error(f"[重命名模型] 失败: {str(e)}")
        return False

def generate_voice_id() -> str:
    """生成新的声音模型ID"""
    existing_ids = [vid for vid in VOICE_LIBRARY.keys() if vid.startswith("voice_")]
    if existing_ids:
        max_num = max([int(vid.split("_")[1]) for vid in existing_ids if vid.split("_")[1].isdigit()])
        return f"voice_{max_num + 1:03d}"
    return "voice_001"


def _is_model_pair_valid(gpt_path: str, sovits_path: str) -> bool:
    gpt = str(gpt_path or "").strip()
    sovits = str(sovits_path or "").strip()
    return bool(gpt and sovits and os.path.exists(gpt) and os.path.exists(sovits))


def _find_fallback_voice_for_name(missing_voice_id: str):
    """当指定 voice_id 文件缺失时，按同名模型回退到最新可用条目。"""
    profile = VOICE_LIBRARY.get(missing_voice_id) or {}
    target_name = str(profile.get("name") or "").strip()
    if not target_name:
        return None

    candidates = []
    for vid, info in VOICE_LIBRARY.items():
        if vid == missing_voice_id:
            continue
        if str(info.get("name") or "").strip() != target_name:
            continue
        gp = info.get("gpt_path")
        sp = info.get("sovits_path")
        if _is_model_pair_valid(gp, sp):
            candidates.append((str(info.get("trained_at") or ""), vid, info))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, fallback_vid, fallback_info = candidates[0]
    return fallback_vid, fallback_info


class Sovits:
    def __init__(self, vq_model, hps):
        self.vq_model = vq_model
        self.hps = hps


from process_ckpt import get_sovits_version_from_path_fast, load_sovits_new


def get_sovits_weights(sovits_path):
    # 兼容：Windows 反序列化 Linux 训练产物时可能包含 pathlib.PosixPath
    try:
        import pathlib

        if os.name == "nt" and hasattr(pathlib, "PosixPath"):
            pathlib.PosixPath = pathlib.WindowsPath  # type: ignore[attr-defined]
    except Exception:
        pass
    from config import pretrained_sovits_name

    # 只支持 v2Pro，移除 v3/v4 的引用
    path_sovits_v2pro = pretrained_sovits_name.get("v2Pro", "")
    is_exist_s2gv2pro = os.path.exists(path_sovits_v2pro) if path_sovits_v2pro else False

    version, model_version, if_lora_v3 = get_sovits_version_from_path_fast(sovits_path)
    
    # v2Pro 不支持 LoRA，所以 if_lora_v3 应该始终为 False
    if_lora_v3 = False
    
    # 只支持 v2Pro
    if model_version not in {"v2Pro", "v2ProPlus"}:
        logger.warning(f"不支持的模型版本: {model_version}，将尝试使用 v2Pro")
        model_version = "v2Pro"
    
    is_exist = is_exist_s2gv2pro
    path_sovits = path_sovits_v2pro

    if if_lora_v3 == True and is_exist == False:
        logger.info("SoVITS %s 底模缺失，无法加载相应 LoRA 权重" % model_version)

    dict_s2 = load_sovits_new(sovits_path)

    # 兼容旧格式：如果没有 config 字段，则尝试从 hps/model 中构造
    if "config" not in dict_s2:
        logger.warning(f"[get_sovits_weights] 加载到的 SoVITS 权重中缺少 'config' 字段，尝试兼容旧格式: {sovits_path}")
        legacy_hps = dict_s2.get("hps", {})
        legacy_weight = dict_s2.get("weight") or dict_s2.get("model")
        if not isinstance(legacy_hps, dict):
            legacy_hps = {}
        if legacy_weight is None:
            raise KeyError("'config'")
        dict_s2 = {
            "weight": legacy_weight,
            "config": legacy_hps,
            "info": dict_s2.get("info", f"legacy_{os.path.basename(sovits_path)}"),
        }

    # 兼容：部分训练产物的 config/hps 不完整（缺 train/data/model），用官方 v2Pro 配置兜底补齐。
    try:
        cfg = dict_s2.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
        need_fill = any(k not in cfg for k in ("train", "data", "model"))
        if need_fill:
            base_cfg_path = PROJECT_ROOT / "GPT_SoVITS" / "configs" / "s2v2Pro.json"
            with open(base_cfg_path, "r", encoding="utf-8") as f:
                base_cfg = json.load(f)
            for k in ("train", "data", "model"):
                base_part = base_cfg.get(k) if isinstance(base_cfg.get(k), dict) else {}
                user_part = cfg.get(k) if isinstance(cfg.get(k), dict) else {}
                merged = dict(base_part)
                merged.update(user_part)
                base_cfg[k] = merged
            # 允许覆盖其他顶层字段
            for k, v in cfg.items():
                if k in ("train", "data", "model"):
                    continue
                base_cfg[k] = v
            dict_s2["config"] = base_cfg
    except Exception as e:
        logger.warning(f"[get_sovits_weights] 补齐 v2Pro 配置失败(将继续尝试加载): {e}")

    hps = dict_s2["config"]
    hps = DictToAttrRecursive(hps)
    hps.model.semantic_frame_rate = "25hz"
    if "enc_p.text_embedding.weight" not in dict_s2["weight"]:
        hps.model.version = "v2"  # v3model,v2sybomls
    elif dict_s2["weight"]["enc_p.text_embedding.weight"].shape[0] == 322:
        hps.model.version = "v1"
    else:
        hps.model.version = "v2"

    model_params_dict = vars(hps.model)
    # 只支持 v2Pro，使用 SynthesizerTrn
    if "Pro" in model_version:
        hps.model.version = model_version
        if sv_cn_model == None:
            init_sv_cn()
            if sv_cn_model == None:
                logger.warning("SV模型未加载，v2Pro的说话人验证功能可能不可用")
    else:
        # 如果不是 Pro 版本，默认使用 v2Pro
        hps.model.version = "v2Pro"
        if sv_cn_model == None:
            init_sv_cn()
            if sv_cn_model == None:
                logger.warning("SV模型未加载，v2Pro的说话人验证功能可能不可用")

    vq_model = SynthesizerTrn(
        hps.data.filter_length // 2 + 1,
        hps.train.segment_size // hps.data.hop_length,
        n_speakers=hps.data.n_speakers,
        **model_params_dict,
    )

    model_version = hps.model.version
    logger.info(f"模型版本: {model_version}")
    if "pretrained" not in sovits_path:
        try:
            del vq_model.enc_q
        except:
            pass
    if is_half == True:
        vq_model = vq_model.half().to(device)
    else:
        vq_model = vq_model.to(device)
    vq_model.eval()
    # v2Pro 不支持 LoRA，直接加载权重
    vq_model.load_state_dict(dict_s2["weight"], strict=False)

    sovits = Sovits(vq_model, hps)
    return sovits


class Gpt:
    def __init__(self, max_sec, t2s_model):
        self.max_sec = max_sec
        self.t2s_model = t2s_model


global hz
hz = 50


def get_gpt_weights(gpt_path):
    # 兼容：Windows 反序列化 Linux 训练产物时，ckpt/pth 里可能包含 pathlib.PosixPath
    # 会导致报错：cannot instantiate 'PosixPath' on your system
    try:
        import pathlib

        if os.name == "nt" and hasattr(pathlib, "PosixPath"):
            pathlib.PosixPath = pathlib.WindowsPath  # type: ignore[attr-defined]
    except Exception:
        pass
    dict_s1 = torch.load(gpt_path, map_location="cpu", weights_only=False)

    # 兼容旧格式：如果缺少 config/weight，则尝试从 PyTorch Lightning checkpoint 中转换
    if "config" not in dict_s1 or "weight" not in dict_s1:
        from collections import OrderedDict

        if "state_dict" in dict_s1:
            logger.warning(f"[get_gpt_weights] 检测到旧版 GPT Lightning checkpoint，正在自动转换: {gpt_path}")
            new_ckpt = OrderedDict()
            new_ckpt["weight"] = dict_s1["state_dict"]
            new_ckpt["config"] = dict_s1.get("hyper_parameters", {}).get("config", {})
            new_ckpt["info"] = f"GPT-e{dict_s1.get('epoch', 'N/A')}"
            dict_s1 = new_ckpt
            try:
                # 覆盖原文件，避免下次重复转换
                torch.save(dict_s1, gpt_path)
            except Exception as e:
                logger.warning(f"[get_gpt_weights] 保存转换后的 GPT 权重失败（忽略，仅内存使用）: {e}")
        else:
            # 无法识别的旧格式，直接抛错，让上层返回 400
            raise KeyError("'config'")

    config = dict_s1["config"]
    max_sec = config["data"]["max_sec"]
    t2s_model = Text2SemanticLightningModule(config, "****", is_train=False)
    t2s_model.load_state_dict(dict_s1["weight"])
    if is_half == True:
        t2s_model = t2s_model.half()
    t2s_model = t2s_model.to(device)
    t2s_model.eval()
    # total = sum([param.nelement() for param in t2s_model.parameters()])
    # logger.info("Number of parameter: %.2fM" % (total / 1e6))

    gpt = Gpt(max_sec, t2s_model)
    return gpt


def change_gpt_sovits_weights(gpt_path, sovits_path):
    """
    切换GPT和SoVITS模型权重，并设置为默认说话人
    """
    try:
        logger.info(f"[change_gpt_sovits_weights] 开始加载模型 - GPT: {gpt_path}, SoVITS: {sovits_path}")
        
        # 验证文件路径是否存在
        if not os.path.exists(gpt_path):
            error_msg = f"GPT模型文件不存在: {gpt_path}"
            logger.error(f"[change_gpt_sovits_weights] {error_msg}")
            return JSONResponse({"code": 400, "message": error_msg}, status_code=400)
        
        if not os.path.exists(sovits_path):
            error_msg = f"SoVITS模型文件不存在: {sovits_path}"
            logger.error(f"[change_gpt_sovits_weights] {error_msg}")
            return JSONResponse({"code": 400, "message": error_msg}, status_code=400)
        
        # 加载模型权重
        logger.info("[change_gpt_sovits_weights] 正在加载GPT权重...")
        gpt = get_gpt_weights(gpt_path)
        logger.info("[change_gpt_sovits_weights] GPT权重加载成功")
        
        logger.info("[change_gpt_sovits_weights] 正在加载SoVITS权重...")
        sovits = get_sovits_weights(sovits_path)
        logger.info("[change_gpt_sovits_weights] SoVITS权重加载成功")
        
        # 设置为默认说话人
        speaker_list["default"] = Speaker(name="default", gpt=gpt, sovits=sovits)
        logger.info("[change_gpt_sovits_weights] 模型切换成功，已设置为默认说话人")
        
        return JSONResponse({"code": 0, "message": "Success"}, status_code=200)
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        error_msg = f"模型加载失败: {str(e)}"
        logger.error(f"[change_gpt_sovits_weights] {error_msg}\n{error_detail}")
        return JSONResponse({"code": 400, "message": error_msg}, status_code=400)


def load_voice_profile(voice_id: str):
    """
    根据 voice_id 从 VOICE_LIBRARY 中加载对应的 GPT / SoVITS 权重，
    并将其设为当前默认说话人（speaker_list['default']）。
    """
    load_voice_library_from_file()
    if voice_id not in VOICE_LIBRARY:
        return JSONResponse(
            {"code": 400, "message": f"未知的 voice_id: {voice_id}"}, status_code=400
        )

    profile = VOICE_LIBRARY[voice_id]

    # Qwen 基础音色走 API 直出，不依赖本地 GPT/SoVITS 权重文件。
    if _is_qwen_voice_profile(profile):
        try:
            if "default" in speaker_list:
                speaker_list["default"].name = voice_id
        except Exception:
            pass
        return JSONResponse(
            {
                "code": 0,
                "message": "Success",
                "voice_id": voice_id,
                "provider": "qwen_tts",
                "mode": "api_tts",
            },
            status_code=200,
        )

    gpt_path = profile.get("gpt_path")
    sovits_path = profile.get("sovits_path")

    if not _is_model_pair_valid(gpt_path, sovits_path):
        fallback = _find_fallback_voice_for_name(voice_id)
        if fallback:
            fallback_vid, fallback_info = fallback
            logger.warning(f"[load_voice_profile] {voice_id} 模型文件缺失，自动回退到 {fallback_vid}")
            voice_id = fallback_vid
            profile = fallback_info
            gpt_path = profile.get("gpt_path")
            sovits_path = profile.get("sovits_path")
        else:
            return JSONResponse(
                {
                    "code": 400,
                    "message": f"模型文件不存在，请重新训练或重新选择音色（voice_id={voice_id}）",
                },
                status_code=400,
            )

    # 直接复用原有的权重切换逻辑
    resp = change_gpt_sovits_weights(gpt_path=gpt_path, sovits_path=sovits_path)
    # 将说话人名称更新为 voice_id，便于调试区分
    if "default" in speaker_list:
        speaker_list["default"].name = voice_id
    return resp


# 缓存当前已加载到官方 api.py 的模型路径，避免每次朗读都重复切权重导致卡顿
_OFFICIAL_MODEL_CACHE = {
    "gpt_path": "",
    "sovits_path": "",
}
_OFFICIAL_MODEL_CACHE_LOCK = threading.Lock()

_VOICE_GEN_PROFILE_CACHE = {}
_VOICE_GEN_PROFILE_CACHE_LOCK = threading.Lock()
_INFER_MAX_SEC_OVERRIDE_LOCK = threading.Lock()
try:
    _VOICE_GEN_PROFILE_CACHE_TTL_SEC = max(600.0, float(os.environ.get("VOICE_GEN_PROFILE_CACHE_TTL_SEC", "21600")))
except Exception:
    _VOICE_GEN_PROFILE_CACHE_TTL_SEC = 21600.0


def _ensure_official_model_loaded(official_change_fn, gpt_path_local: str, sovits_path_local: str):
    gpt_abs = os.path.abspath(str(gpt_path_local or ""))
    sovits_abs = os.path.abspath(str(sovits_path_local or ""))
    if not gpt_abs or not sovits_abs:
        raise Exception("模型路径为空")

    with _OFFICIAL_MODEL_CACHE_LOCK:
        if (
            _OFFICIAL_MODEL_CACHE.get("gpt_path") == gpt_abs
            and _OFFICIAL_MODEL_CACHE.get("sovits_path") == sovits_abs
        ):
            return

        result = official_change_fn(gpt_abs, sovits_abs)
        if hasattr(result, "status_code") and result.status_code != 200:
            try:
                body = json.loads(result.body.decode()) if hasattr(result, "body") else {}
                error_msg = body.get("message", "模型加载失败")
            except Exception:
                error_msg = "模型加载失败"
            raise Exception(error_msg)

        _OFFICIAL_MODEL_CACHE["gpt_path"] = gpt_abs
        _OFFICIAL_MODEL_CACHE["sovits_path"] = sovits_abs


def _normalize_gen_profile(profile: dict, base_profile: dict) -> dict:
    base = dict(base_profile or {})
    p = dict(profile or {})

    def _to_int(name: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int(p.get(name, default))
        except Exception:
            v = int(default)
        return max(lo, min(hi, v))

    def _to_float(name: str, default: float, lo: float, hi: float) -> float:
        try:
            v = float(p.get(name, default))
        except Exception:
            v = float(default)
        return max(lo, min(hi, v))

    out = {
        "top_k": _to_int("top_k", int(base.get("top_k", 15)), 8, 80),
        "top_p": _to_float("top_p", float(base.get("top_p", 0.6)), 0.10, 0.99),
        "temperature": _to_float("temperature", float(base.get("temperature", 0.6)), 0.10, 1.20),
        "repetition_penalty": _to_float("repetition_penalty", float(base.get("repetition_penalty", 1.18)), 1.00, 2.00),
        "speed": _to_float("speed", float(base.get("speed", 1.0)), 0.70, 1.20),
        "sample_steps": _to_int("sample_steps", int(base.get("sample_steps", 32)), 16, 72),
    }
    return out


def _build_recent_user_voice_bootstrap_profile(base_profile: dict, voice_profile: dict) -> dict:
    base = _normalize_gen_profile(base_profile or {}, base_profile or {})
    trained_ts = _parse_iso_to_epoch((voice_profile or {}).get("trained_at"))
    if not trained_ts:
        return base

    age_sec = time.time() - float(trained_ts)
    if age_sec > 72 * 3600:
        return base

    tuned = dict(base)
    # 新训练音色给一个“稳中偏快”的冷启动参数，避免首轮就落入重采样高耗时。
    tuned["top_k"] = max(16, int(base["top_k"]))
    tuned["top_p"] = max(0.84, min(0.90, float(base["top_p"])))
    tuned["temperature"] = min(0.40, max(0.30, float(base["temperature"])))
    tuned["repetition_penalty"] = min(1.20, max(1.14, float(base["repetition_penalty"])))
    tuned["speed"] = max(1.02, float(base["speed"]))
    tuned["sample_steps"] = max(28, min(32, int(base["sample_steps"])))
    return _normalize_gen_profile(tuned, base)


def _clamp_cached_user_voice_profile(profile: dict, base_profile: dict, cache_mode: str = "speed") -> dict:
    base = _normalize_gen_profile(base_profile or {}, base_profile or {})
    p = _normalize_gen_profile(profile or {}, base)

    mode = str(cache_mode or "speed").strip().lower()
    if mode in ("quality", "strict", "robust"):
        # 高风险音色允许稍重参数，优先保证完整度，避免被缓存回拉到“过快”配置。
        max_steps = max(32, min(44, int(base.get("sample_steps", 32)) + 8))
        p["sample_steps"] = min(int(p.get("sample_steps", 32)), max_steps)
        p["speed"] = max(float(p.get("speed", 1.0)), max(0.90, min(1.06, float(base.get("speed", 1.0)))))
        p["top_k"] = min(int(p.get("top_k", 18)), 24)
        p["top_p"] = min(float(p.get("top_p", 0.9)), 0.92)
        p["repetition_penalty"] = min(float(p.get("repetition_penalty", 1.18)), 1.26)
    else:
        # 常规音色保留偏快参数，避免总体时延回退。
        max_steps = max(28, min(32, int(base.get("sample_steps", 32)) + 2))
        p["sample_steps"] = min(int(p.get("sample_steps", 32)), max_steps)
        p["speed"] = max(float(p.get("speed", 1.0)), max(1.02, float(base.get("speed", 1.0))))
        p["top_k"] = min(int(p.get("top_k", 16)), 20)
        p["top_p"] = min(float(p.get("top_p", 0.9)), 0.90)
        p["repetition_penalty"] = min(float(p.get("repetition_penalty", 1.18)), 1.22)
    return _normalize_gen_profile(p, base)


def _get_cached_voice_gen_profile(voice_id: str, base_profile: dict):
    vid = str(voice_id or "").strip()
    if not vid:
        return None
    now_ts = time.time()
    with _VOICE_GEN_PROFILE_CACHE_LOCK:
        rec = _VOICE_GEN_PROFILE_CACHE.get(vid)
        if not rec:
            return None
        ts = float(rec.get("ts") or 0.0)
        if (now_ts - ts) > _VOICE_GEN_PROFILE_CACHE_TTL_SEC:
            _VOICE_GEN_PROFILE_CACHE.pop(vid, None)
            return None
        return _normalize_gen_profile(rec.get("profile") or {}, base_profile or {})


def _remember_voice_gen_profile(voice_id: str, profile: dict, source: str = ""):
    vid = str(voice_id or "").strip()
    if not vid:
        return
    normalized = _normalize_gen_profile(profile or {}, profile or {})
    with _VOICE_GEN_PROFILE_CACHE_LOCK:
        _VOICE_GEN_PROFILE_CACHE[vid] = {
            "profile": normalized,
            "ts": time.time(),
            "source": str(source or ""),
        }


def _parse_sovits_steps_from_path(sovits_path: str) -> int:
    name = os.path.basename(str(sovits_path or "")).strip()
    if not name:
        return 0
    m = re.search(r"_s(\d+)\.pth$", name, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"_s(\d+)", name, flags=re.IGNORECASE)
    if not m:
        return 0
    try:
        return max(0, int(m.group(1)))
    except Exception:
        return 0


def _resolve_user_voice_risk_policy(voice_id: str, voice_profile: dict) -> dict:
    p = dict(voice_profile or {})
    model_type = str(p.get("model_type") or "").strip().lower()
    if model_type != "user_trained":
        return {
            "tier": "normal",
            "score": 0,
            "reasons": [],
            "overrides": {},
            "cache_mode": "speed",
        }

    name_l = str(p.get("name") or "").strip().lower()
    steps = _parse_sovits_steps_from_path(p.get("sovits_path"))
    trained_ts = _parse_iso_to_epoch(p.get("trained_at"))
    age_hours = None
    if trained_ts:
        age_hours = max(0.0, (time.time() - float(trained_ts)) / 3600.0)

    score = 0
    reasons = []

    if steps > 0:
        if steps <= 48:
            score += 4
            reasons.append(f"low_steps:{steps}")
        elif steps <= 72:
            score += 3
            reasons.append(f"midlow_steps:{steps}")
        elif steps <= 96:
            score += 1
            reasons.append(f"mid_steps:{steps}")

    if age_hours is not None:
        if age_hours <= 24.0:
            score += 3
            reasons.append(f"newly_trained:{age_hours:.1f}h")
        elif age_hours <= 72.0:
            score += 2
            reasons.append(f"recently_trained:{age_hours:.1f}h")

    if re.search(r"(test|opt)", name_l):
        score += 1
        reasons.append("name_hint:test_or_opt")

    if score >= 5:
        tier = "strict"
    elif score >= 3:
        tier = "risky"
    else:
        tier = "normal"

    if tier == "strict":
        overrides = {
            "hq_user_voice_speed_boost": False,
            "hq_user_voice_min_speed": 1.00,
            "hq_user_voice_fast_decode": False,
            "hq_user_voice_over_retry": True,
            "hq_user_voice_adaptive_fast": False,
            "hq_user_voice_bootstrap": False,
            "hq_user_voice_min_steps": 32,
            "hq_user_voice_segmented_mode": "always",
            "sample_steps": 36,
            "max_text_len": 24,
        }
        cache_mode = "quality"
    elif tier == "risky":
        overrides = {
            "hq_user_voice_speed_boost": False,
            "hq_user_voice_min_speed": 1.00,
            "hq_user_voice_fast_decode": False,
            "hq_user_voice_over_retry": True,
            "hq_user_voice_adaptive_fast": False,
            "hq_user_voice_bootstrap": False,
            "hq_user_voice_min_steps": 30,
            "hq_user_voice_segmented_mode": "always",
            "max_text_len": 28,
        }
        cache_mode = "quality"
    else:
        overrides = {}
        cache_mode = "speed"

    return {
        "tier": tier,
        "score": score,
        "reasons": reasons,
        "overrides": overrides,
        "cache_mode": cache_mode,
        "voice_id": str(voice_id or ""),
        "steps": steps,
        "age_hours": age_hours,
    }


def _apply_user_voice_risk_policy(data: dict, voice_id: str, voice_profile: dict):
    out = dict(data or {})
    policy = _resolve_user_voice_risk_policy(voice_id, voice_profile)

    applied = {}
    for k, v in dict(policy.get("overrides") or {}).items():
        if k not in out:
            out[k] = v
            applied[k] = v

    policy["applied_overrides"] = applied
    policy["applied"] = bool(applied)
    return out, policy


def _apply_voice_risk_tolerance(under_tol: float, over_tol: float, risk_tier: str):
    tier = str(risk_tier or "normal").strip().lower()
    u = float(under_tol or 0.90)
    o = float(over_tol or 1.25)
    if tier == "strict":
        u = min(0.97, u + 0.03)
        o = max(1.12, o - 0.05)
    elif tier == "risky":
        u = min(0.95, u + 0.02)
        o = max(1.15, o - 0.03)
    return u, o


def get_bert_feature(text, word2ph):
    with torch.no_grad():
        inputs = tokenizer(text, return_tensors="pt")
        for i in inputs:
            inputs[i] = inputs[i].to(device)  #####输入是long不用管精度问题，精度随bert_model
        res = bert_model(**inputs, output_hidden_states=True)
        res = torch.cat(res["hidden_states"][-3:-2], -1)[0].cpu()[1:-1]
    assert len(word2ph) == len(text)
    phone_level_feature = []
    for i in range(len(word2ph)):
        repeat_feature = res[i].repeat(word2ph[i], 1)
        phone_level_feature.append(repeat_feature)
    phone_level_feature = torch.cat(phone_level_feature, dim=0)
    # if(is_half==True):phone_level_feature=phone_level_feature.half()
    return phone_level_feature.T


def clean_text_inf(text, language, version):
    language = language.replace("all_", "")
    phones, word2ph, norm_text = clean_text(text, language, version)
    phones = cleaned_text_to_sequence(phones, version)
    return phones, word2ph, norm_text


def get_bert_inf(phones, word2ph, norm_text, language):
    language = language.replace("all_", "")
    if language == "zh":
        bert = get_bert_feature(norm_text, word2ph).to(device)  # .to(dtype)
    else:
        bert = torch.zeros(
            (1024, len(phones)),
            dtype=torch.float16 if is_half == True else torch.float32,
        ).to(device)

    return bert


from text import chinese
# 直接使用官方 api.py 的推理逻辑（延迟导入，避免初始化冲突）

# 定义文本清理和语言检测函数（与 simple_inference.py 一致）
def sanitize_text(s: str) -> str:
    """
    轻量清理：去掉控制字符等奇怪符号，但保留中英文、数字和常用标点。
    与 simple_inference.py 完全一致
    """
    if s is None:
        return ""
    # 允许：中文、全角标点、ASCII 字母数字、空白和常见标点
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\s.,!?;:、，。？！…\"'()\\-]", " ", s)
    # 合并多余空白
    s = re.sub(r"\s+", " ", s).strip()
    return s


# -----------------------------
# 内容安全（恶意/违法/不适宜文本拦截）
# -----------------------------
# 默认开启；可通过环境变量关闭：CONTENT_SAFETY_ENABLED=0

def normalize_ref_text_for_infer(text: str, max_chars: int = 48) -> str:
    """将参考文本裁剪为稳态短提示词，降低新训练音色漏字和卡顿概率。"""
    t = sanitize_text(str(text or ""))
    if not t:
        return ""
    punct = "。！？!?；;"
    cut = min(len(t), max_chars)
    for i, ch in enumerate(t[: max_chars + 1], start=1):
        if ch in punct:
            cut = min(i, max_chars)
            break
    out = t[:cut].strip("，,、；;：:。！？!?")
    if len(out) < 6:
        out = t[: min(len(t), max_chars)]
    out = out.strip()
    if out and out[-1] not in "。！？!?":
        out += "。"
    return out

def _coerce_ref_path_list(raw_value):
    """将请求里的 inp_refs / aux_ref_audio_paths 统一转为路径列表。"""
    if raw_value is None:
        return []

    values = []
    if isinstance(raw_value, (list, tuple, set)):
        values = list(raw_value)
    elif isinstance(raw_value, str):
        s = raw_value.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    values = parsed
                else:
                    values = [s]
            except Exception:
                values = re.split(r"[,;|\n]", s)
        else:
            values = re.split(r"[,;|\n]", s)
    else:
        values = [raw_value]

    out = []
    for item in values:
        p = str(item or "").strip().strip("\"'")
        if p:
            out.append(p)
    return out


def _normalize_ref_audio_path(path_value: str, base_dir: str = None) -> str:
    p = str(path_value or "").strip()
    if not p:
        return ""
    if not os.path.isabs(p):
        p = os.path.abspath(os.path.join(base_dir or now_dir, p))
    return p


class _InpRefFile:
    def __init__(self, name: str):
        self.name = name


def _build_inp_refs_payload(paths, base_dir: str = None):
    payload = []
    for item in paths or []:
        abs_path = _normalize_ref_audio_path(item, base_dir=base_dir or now_dir)
        if not abs_path:
            continue
        if not os.path.exists(abs_path):
            continue
        payload.append(_InpRefFile(abs_path))
    return payload


def _read_text_file_safe(path_value: str, max_chars: int = 240) -> str:
    try:
        with open(path_value, "r", encoding="utf-8") as f:
            raw = f.read(max_chars * 2)
    except Exception:
        return ""
    return sanitize_text((raw or "")[:max_chars])


def _collect_sentence_reference_pairs(dataset_dir: str, max_samples: int = 20):
    if not dataset_dir or (not os.path.isdir(dataset_dir)):
        return []

    pairs = []
    for filename in os.listdir(dataset_dir):
        m = re.match(r"^sentence_(\d+)\.wav$", str(filename or ""), flags=re.IGNORECASE)
        if not m:
            continue
        try:
            idx = int(m.group(1))
        except Exception:
            continue
        wav_path = os.path.join(dataset_dir, filename)
        if not os.path.exists(wav_path):
            continue
        txt_path = os.path.join(dataset_dir, f"sentence_{idx}.txt")
        txt = _read_text_file_safe(txt_path) if os.path.exists(txt_path) else ""
        pairs.append({"idx": idx, "audio_path": wav_path, "text": txt})

    pairs.sort(key=lambda x: int(x.get("idx") or 0))
    if max_samples > 0:
        return pairs[:max_samples]
    return pairs


def _text_overlap_score(source_text: str, target_text: str) -> float:
    s = sanitize_text(str(source_text or ""))
    t = sanitize_text(str(target_text or ""))
    if (not s) or (not t):
        return 0.0

    s_chars = set(ch for ch in s if re.match(r"[0-9A-Za-z一-鿿]", ch))
    t_chars = set(ch for ch in t if re.match(r"[0-9A-Za-z一-鿿]", ch))
    if (not s_chars) or (not t_chars):
        return 0.0

    inter = len(s_chars & t_chars)
    union = len(s_chars | t_chars)
    return float(inter) / float(max(1, union))


def _pick_prompt_text_from_samples(
    samples: list,
    fallback_text: str = "",
    target_text: str = "",
    prompt_max_chars: int = 40,
) -> str:
    candidates = []
    for sample in samples or []:
        txt = sanitize_text(str((sample or {}).get("text") or ""))
        if has_speakable_content(txt):
            candidates.append(txt)

    chosen = ""
    if candidates:
        if has_speakable_content(target_text):
            scored = []
            tgt_len = len(sanitize_text(target_text))
            for txt in candidates:
                overlap = _text_overlap_score(txt, target_text)
                if tgt_len > 0:
                    length_bias = 1.0 - min(abs(len(txt) - tgt_len), 80) / 80.0
                else:
                    length_bias = 0.0
                score = overlap * 0.8 + max(0.0, length_bias) * 0.2
                scored.append((score, txt))
            scored.sort(key=lambda x: x[0], reverse=True)
            chosen = scored[0][1]
        else:
            chosen = candidates[0]

    prompt = normalize_ref_text_for_infer(chosen or fallback_text or "", max_chars=max(16, int(prompt_max_chars or 28)))
    if not prompt:
        prompt = normalize_ref_text_for_infer(fallback_text or "", max_chars=24)
    return prompt


def _parse_iso_to_epoch(ts: str):
    t = str(ts or "").strip()
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _count_voices_sharing_dataset_dir(target_dir_abs: str, current_voice_id: str = "") -> int:
    target = os.path.abspath(str(target_dir_abs or ""))
    if not target:
        return 0

    count = 0
    for vid, info in (VOICE_LIBRARY or {}).items():
        if current_voice_id and str(vid) == str(current_voice_id):
            count += 1
            continue
        p = _normalize_ref_audio_path((info or {}).get("ref_audio_path"), base_dir=now_dir)
        if not p:
            continue
        name = os.path.basename(p).lower()
        if not re.match(r"^sentence_\d+\.wav$", name):
            continue
        d = os.path.abspath(os.path.dirname(p))
        if d == target:
            count += 1
    return count


def _build_voice_reference_guard(
    voice_id: str,
    profile: dict,
    req_max_refs: int,
    req_max_aux_refs: int,
) -> dict:
    max_refs = max(1, min(int(req_max_refs or 6), 20))
    max_aux = max(0, min(int(req_max_aux_refs or 2), 6))
    guard = {
        "max_refs": max_refs,
        "max_aux_refs": max_aux,
        "dataset_scan_enabled": True,
        "reason": "",
        "shared_dataset_voice_count": 0,
        "ref_mtime_after_train": False,
    }

    ref_audio = _normalize_ref_audio_path((profile or {}).get("ref_audio_path"), base_dir=now_dir)
    if not ref_audio:
        return guard

    base = os.path.basename(ref_audio).lower()
    if not re.match(r"^sentence_\d+\.wav$", base):
        return guard

    dataset_dir = os.path.abspath(os.path.dirname(ref_audio))
    shared_count = _count_voices_sharing_dataset_dir(dataset_dir, current_voice_id=voice_id)
    guard["shared_dataset_voice_count"] = shared_count

    reasons = []
    if shared_count > 1:
        # 共享目录在真实生产中较常见（同一用户多次训练）；完全禁用会显著降低可读性。
        # 这里改为温和约束：保留数据集扫描，但限制参考规模，兼顾稳定性和普适性。
        reasons.append("shared_dataset_dir")
        guard["dataset_scan_enabled"] = True
        guard["max_refs"] = min(max(guard["max_refs"], 4), 8)
        guard["max_aux_refs"] = min(max(guard["max_aux_refs"], 1), 2)

    trained_ts = _parse_iso_to_epoch((profile or {}).get("trained_at"))
    try:
        ref_mtime = os.path.getmtime(ref_audio)
    except Exception:
        ref_mtime = None

    if trained_ts and ref_mtime and (ref_mtime > (trained_ts + 120.0)):
        guard["ref_mtime_after_train"] = True
        reasons.append("ref_mtime_after_trained_at")
        # 对“训练后修改”只做收敛，不做一刀切禁用，避免老音色退化成只能读短句。
        guard["dataset_scan_enabled"] = True
        guard["max_refs"] = min(max(guard["max_refs"], 3), 6)
        guard["max_aux_refs"] = min(max(guard["max_aux_refs"], 1), 2)

    guard["reason"] = ",".join(reasons)
    return guard


def _resolve_reference_bundle(
    ref_audio_path: str,
    ref_text: str,
    base_dir: str = None,
    extra_ref_paths=None,
    max_refs: int = 4,
    max_aux_refs: int = 2,
    target_text: str = "",
    prompt_max_chars: int = 40,
    dataset_scan_enabled: bool = True,
    prefer_primary_sentence_text: bool = False,
    prefer_target_primary_sample: bool = False,
) -> dict:
    limit = max(1, min(int(max_refs or 4), 20))
    aux_limit = max(0, min(int(max_aux_refs or 2), 6))
    base_dir = base_dir or now_dir

    samples = []
    seen_paths = set()

    def _add_sample(audio_path: str, text: str = "", source: str = ""):
        abs_path = _normalize_ref_audio_path(audio_path, base_dir=base_dir)
        if (not abs_path) or (abs_path in seen_paths):
            return
        if not os.path.exists(abs_path):
            return
        if len(samples) >= limit:
            return

        clean_text = sanitize_text(str(text or ""))
        if not clean_text:
            txt_path = os.path.splitext(abs_path)[0] + ".txt"
            if os.path.exists(txt_path):
                clean_text = _read_text_file_safe(txt_path)

        samples.append({
            "audio_path": abs_path,
            "text": clean_text,
            "source": source,
        })
        seen_paths.add(abs_path)

    primary_abs = _normalize_ref_audio_path(ref_audio_path, base_dir=base_dir)
    primary_text = sanitize_text(str(ref_text or ""))
    if prefer_primary_sentence_text and primary_abs:
        base = os.path.basename(primary_abs).lower()
        if re.match(r"^sentence_\d+\.wav$", base):
            primary_txt = os.path.splitext(primary_abs)[0] + ".txt"
            if os.path.exists(primary_txt):
                txt = _read_text_file_safe(primary_txt)
                if has_speakable_content(txt):
                    primary_text = txt
                else:
                    primary_text = ""

    _add_sample(ref_audio_path, primary_text, source="primary")
    if dataset_scan_enabled and primary_abs:
        basename = os.path.basename(primary_abs).lower()
        if re.match(r"^sentence_\d+\.wav$", basename):
            dataset_dir = os.path.dirname(primary_abs)
            for item in _collect_sentence_reference_pairs(dataset_dir, max_samples=limit):
                _add_sample(item.get("audio_path"), item.get("text") or "", source="dataset")

    for p in _coerce_ref_path_list(extra_ref_paths):
        _add_sample(p, "", source="extra")

    if (not samples) and primary_abs and os.path.exists(primary_abs):
        _add_sample(primary_abs, primary_text, source="fallback")

    if samples and (not has_speakable_content((samples[0] or {}).get("text") or "")):
        best_idx = -1
        best_score = -1.0
        target_ok = has_speakable_content(target_text)
        for idx, sample in enumerate(samples[1:], start=1):
            txt = sanitize_text(str((sample or {}).get("text") or ""))
            if not has_speakable_content(txt):
                continue
            score = _text_overlap_score(txt, target_text) if target_ok else 0.0
            if (best_idx < 0) or (score > best_score):
                best_idx = idx
                best_score = score
        if best_idx > 0:
            samples.insert(0, samples.pop(best_idx))

    if prefer_target_primary_sample and len(samples) > 1 and has_speakable_content(target_text):
        tgt_len = len(sanitize_text(target_text))
        scored = []
        for idx, sample in enumerate(samples):
            txt = sanitize_text(str((sample or {}).get("text") or ""))
            if not has_speakable_content(txt):
                continue
            overlap = _text_overlap_score(txt, target_text)
            if tgt_len > 0:
                length_bias = 1.0 - min(abs(len(txt) - tgt_len), 80) / 80.0
            else:
                length_bias = 0.0
            score = overlap * 0.8 + max(0.0, length_bias) * 0.2
            scored.append((score, idx))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_idx = scored[0]
            primary_score = next((s for s, i in scored if i == 0), -1.0)
            if best_idx > 0 and best_score >= (primary_score + 0.02):
                samples.insert(0, samples.pop(best_idx))

    primary_ref_audio = samples[0]["audio_path"] if samples else primary_abs
    primary_prompt_raw = ""
    if samples:
        primary_prompt_raw = sanitize_text(str((samples[0] or {}).get("text") or ""))
    if (not primary_prompt_raw) and has_speakable_content(primary_text):
        primary_prompt_raw = sanitize_text(primary_text)

    if has_speakable_content(primary_prompt_raw):
        prompt_text = normalize_ref_text_for_infer(primary_prompt_raw, max_chars=max(16, int(prompt_max_chars or 28)))
    else:
        prompt_text = _pick_prompt_text_from_samples(
            samples=samples,
            fallback_text=primary_text or ref_text,
            target_text=target_text,
            prompt_max_chars=prompt_max_chars,
        )

    aux_candidates = samples[1:] if len(samples) > 1 else []

    if has_speakable_content(target_text) and aux_candidates:
        aux_candidates = sorted(
            aux_candidates,
            key=lambda x: _text_overlap_score((x or {}).get("text") or "", target_text),
            reverse=True,
        )

    aux_ref_audio_paths = [x["audio_path"] for x in aux_candidates[:aux_limit]]

    return {
        "primary_ref_audio": primary_ref_audio,
        "aux_ref_audio_paths": aux_ref_audio_paths,
        "prompt_text": prompt_text,
        "sample_count": len(samples),
        "selected_aux_count": len(aux_ref_audio_paths),
    }


# AI 内容审核（可选）：统一从 modules/ai_runtime.py 读取配置
AI_RUNTIME = load_ai_runtime_config()
SAFETY_AI_ENABLED = AI_RUNTIME.enabled
SAFETY_AI_BASE_URL = AI_RUNTIME.base_url
SAFETY_AI_API_KEY = AI_RUNTIME.api_key
SAFETY_AI_MODEL = AI_RUNTIME.model_for("safety")
SAFETY_AI_TIMEOUT_SEC = AI_RUNTIME.timeout_sec
SAFETY_AI_FAIL_CLOSED = AI_RUNTIME.fail_closed
SAFETY_AI_MAX_CHARS = AI_RUNTIME.max_chars
SAFETY_AI_CACHE_TTL_SEC = AI_RUNTIME.cache_ttl_sec
SAFETY_AI_CACHE_MAX = AI_RUNTIME.cache_max
SAFETY_AI_TTS_MODEL = str(os.environ.get("AI_TTS_MODEL", "") or os.environ.get("AI_MODEL_READALONG_TTS", "") or os.environ.get("AI_MODEL_TTS", "")).strip() or "qwen-omni-turbo"
SAFETY_AI_TTS_TIMEOUT_SEC = max(12.0, float(os.environ.get("AI_TTS_TIMEOUT_SEC", SAFETY_AI_TIMEOUT_SEC or 20)))

def has_speakable_content(text: str) -> bool:
    """判断文本是否包含可发音字符，避免仅标点导致无效音频。"""
    t = sanitize_text(str(text or ""))
    return bool(re.search(r"[0-9A-Za-z\u4e00-\u9fff]", t))


_SAFETY_AI_CACHE = {}
_SAFETY_AI_CACHE_LOCK = threading.Lock()



# 启动可观测性：打印 AI 审核配置（不含密钥）
try:
    logger.info(f"[safety_ai_config] enabled={SAFETY_AI_ENABLED} base_url={SAFETY_AI_BASE_URL or '(empty)'} model={SAFETY_AI_MODEL or '(empty)'} timeout={SAFETY_AI_TIMEOUT_SEC}s fail_closed={SAFETY_AI_FAIL_CLOSED} cache_ttl={SAFETY_AI_CACHE_TTL_SEC}s")
except Exception:
    pass
def _call_openai_compatible_chat_json(prompt: str) -> dict:
    """最小依赖的 openai-compatible 调用：返回解析出的 JSON（失败抛异常）。

    兼容 DashScope OpenAI-compatible：
    - BASE_URL 示例：https://dashscope.aliyuncs.com/compatible-mode/v1
    - 目标 endpoint：{BASE_URL}/chat/completions
    """
    import urllib.request
    import urllib.error

    if not SAFETY_AI_BASE_URL or not SAFETY_AI_API_KEY or not SAFETY_AI_MODEL:
        raise RuntimeError("SAFETY_AI_* not configured")

    url = f"{SAFETY_AI_BASE_URL}/chat/completions"
    payload = {
        "model": SAFETY_AI_MODEL,
        "temperature": 0,
        "max_tokens": 220,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是内容安全审核器。仅输出严格 JSON，不要输出任何额外文本。"
                    "判断输入文本是否涉及违法/不适宜内容，或明显恶意引导/规避审核。"
                    "涵盖类别（非穷举）：仇恨/歧视、骚扰/辱骂、成人/色情、未成年人性相关、"
                    "自残/自杀、暴力、恐怖主义、毒品交易、诈骗/违法交易、隐私泄露/人身信息。"
                    "输出格式固定为：{\"safe\": true/false, \"reason\": \"...\", \"category\": \"...\"}。"
                    "reason 必须简短、友善、不要复述敏感细节或提供可操作性信息。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {SAFETY_AI_API_KEY}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "gpt-sovits-wx-api/1.0")

    # 强制不走系统代理：某些部署环境会设置 http_proxy/https_proxy 指向本机端口（例如 127.0.0.1:7890），
    # 会导致 DashScope/OpenAI-compatible 连接被拒绝。这里显式禁用代理，保证 AI 审核链路稳定。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    try:
        with opener.open(req, timeout=SAFETY_AI_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        raise RuntimeError(f"ai http error: {e.code} {e.reason} body={body[:500]}")

    obj = json.loads(raw)
    content = (((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("empty ai moderation response")

    # 兼容模型偶尔包裹 ```json
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE).strip()
    content = re.sub(r"\s*```$", "", content).strip()

    # 尝试直接 parse；否则抓取首个 { ... }
    try:
        return json.loads(content)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            raise
        return json.loads(m.group(0))



def _check_text_safety_ai(text: str):
    """返回 (ok: bool, reason: str|None, hit: dict|None)。"""
    if not SAFETY_AI_ENABLED:
        return True, None, None

    t = (text or "").strip()
    if not t:
        return True, None, None

    # cache（避免同一句重复调用，降低成本/延迟）
    key = None
    try:
        import hashlib

        key = hashlib.sha256(t.encode("utf-8", errors="ignore")).hexdigest()
        now = time.time()
        with _SAFETY_AI_CACHE_LOCK:
            item = _SAFETY_AI_CACHE.get(key)
            if item and now - item.get("ts", 0) <= SAFETY_AI_CACHE_TTL_SEC:
                return item["ok"], item.get("reason"), item.get("hit")
    except Exception:
        key = None

    # 为了控制成本/时延，超长只取前后
    if len(t) > SAFETY_AI_MAX_CHARS:
        half = max(1, SAFETY_AI_MAX_CHARS // 2)
        t_check = t[:half] + "\n" + t[-half:]
    else:
        t_check = t

    try:
        out = _call_openai_compatible_chat_json(t_check)
        safe = bool(out.get("safe", True))
        category = out.get("category")

        if safe:
            ok, reason, hit = True, None, {"provider": "ai", "category": category}
        else:
            reason = "小朋友不能说这样的话哦"
            ok, reason, hit = False, str(reason), {"provider": "ai", "category": category}

        if key:
            with _SAFETY_AI_CACHE_LOCK:
                if len(_SAFETY_AI_CACHE) >= SAFETY_AI_CACHE_MAX:
                    _SAFETY_AI_CACHE.clear()
                _SAFETY_AI_CACHE[key] = {"ts": time.time(), "ok": ok, "reason": reason, "hit": hit}

        return ok, reason, hit

    except Exception as e:
        logger.warning(f"[safety_ai] 审核失败，将按降级策略处理: {e}")
        if SAFETY_AI_FAIL_CLOSED:
            return False, "内容审核暂时不可用，请稍后再试。", {"provider": "ai", "error": str(e)}
        return True, None, {"provider": "ai", "skipped": True, "error": str(e)}

CONTENT_SAFETY_ENABLED = os.environ.get("CONTENT_SAFETY_ENABLED", "1") not in {"0", "false", "False"}

# 基础规则：命中则拒绝合成（避免为违法/不适宜内容提供语音传播能力）
# 说明：这是轻量规则引擎，主要用于“明显违规”场景；可按需扩展。
_CONTENT_BLOCK_RULES = [
    ("self_harm", re.compile(r"(自杀|轻生|割腕|上吊|跳楼|服毒|suicide|kill\s+myself)", re.IGNORECASE)),
    ("sexual_violence_or_minors", re.compile(r"(强奸|性侵|儿童色情|未成年\s*(性|裸)|rape|child\s*porn)", re.IGNORECASE)),
    ("terror_or_explosives", re.compile(r"(自制\s*(炸弹|炸药)|炸药\s*配方|爆炸物\s*制作|如何\s*做\s*炸弹)", re.IGNORECASE)),
    ("drug_or_illegal_trade", re.compile(r"(制毒|毒品\s*配方|买毒|卖毒|代购\s*毒品|枪支\s*交易|买枪|卖枪)", re.IGNORECASE)),
    ("fraud_or_scam", re.compile(r"(诈骗\s*话术|冒充\s*(客服|公检法)|洗钱|钓鱼\s*链接)", re.IGNORECASE)),
    ("harassment_or_abuse", re.compile(r"(垃圾|滚远点|滚开|恶心|去死|闭嘴|废物|脑残|蠢货|傻[逼叉比Xx]|sb|nmsl|尼玛|你妈的|他妈的|妈的|操你妈|草你妈|艹你妈|去你妈的|我日你仙人|我日你|日你仙人)", re.IGNORECASE)),
]


def _check_text_safety(text: str):
    # 返回 (ok: bool, reason: str|None, hit: dict|None)
    if not CONTENT_SAFETY_ENABLED:
        return True, None, None
    t = (text or "").strip()
    if not t:
        return True, None, None
    # 过长文本只截取前后做规则判断，避免性能问题
    if len(t) > 5000:
        t_check = t[:2500] + "\n" + t[-2500:]
    else:
        t_check = t
    for name, rx in _CONTENT_BLOCK_RULES:
        if rx.search(t_check):
            # 友善提示，不回显命中的敏感片段
            reason = "小朋友不能说这样的话哦"
            return False, reason, {"rule": name}
    # 规则未命中时，再走一次可选的 AI 审核（更强覆盖）
    ok_ai, reason_ai, hit_ai = _check_text_safety_ai(t)
    if not ok_ai:
        return False, reason_ai, hit_ai
    return True, None, hit_ai



def _looks_like_wav_bytes(audio_bytes: bytes) -> bool:
    b = bytes(audio_bytes or b"")
    return len(b) > 44 and b[:4] == b"RIFF" and b[8:12] == b"WAVE"


def _decode_audio_bytes_from_response(content_type: str, body: bytes) -> bytes:
    raw = bytes(body or b"")
    if not raw:
        return b""
    ct = str(content_type or "").lower()
    if ct.startswith("audio/"):
        return raw
    try:
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return raw

    candidates = [
        obj.get("audio"),
        obj.get("data"),
        ((obj.get("output") or {}).get("audio") if isinstance(obj.get("output"), dict) else None),
    ]
    for c in candidates:
        if isinstance(c, str) and c.strip():
            try:
                return base64.b64decode(c)
            except Exception:
                continue
        if isinstance(c, dict):
            for k in ("data", "b64", "audio"):
                v = c.get(k)
                if isinstance(v, str) and v.strip():
                    try:
                        return base64.b64decode(v)
                    except Exception:
                        continue
    return raw


def _pcm16_to_wav_bytes(raw_pcm: bytes, sample_rate: int = 24000) -> bytes:
    pcm = bytes(raw_pcm or b"")
    if not pcm:
        return b""
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm)
    return buf.getvalue()


async def _qwen_tts_openai_speech_once(text: str, voice_name: str) -> bytes:
    base_url = str(SAFETY_AI_BASE_URL or "").strip().rstrip("/")
    api_key = str(SAFETY_AI_API_KEY or "").strip()
    if not base_url or not api_key:
        raise RuntimeError("Qwen TTS 配置缺失")

    url = f"{base_url}/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": SAFETY_AI_TTS_MODEL,
        "voice": str(voice_name or "").strip(),
        "input": str(text or "").strip(),
        "format": "wav",
    }
    async with httpx.AsyncClient(timeout=SAFETY_AI_TTS_TIMEOUT_SEC, trust_env=False) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        audio_bytes = _decode_audio_bytes_from_response(resp.headers.get("content-type", ""), resp.content or b"")
    if not audio_bytes:
        raise RuntimeError("audio/speech empty")
    return audio_bytes


def _trim_qwen_unwanted_tail(text: str) -> str:
    """裁剪 Qwen 偶发追加的客服式结尾，避免绘本朗读多出无关句。"""
    raw = sanitize_text(text)
    if not raw:
        return ""

    trimmed = str(raw)
    markers = [
        "你要是有什么",
        "如果你有什么",
        "要是有什么问题",
        "有什么问题可以",
    ]
    for _ in range(2):
        cut_idx = -1
        near_tail = max(0, len(trimmed) - 90)
        for mk in markers:
            idx = trimmed.rfind(mk)
            if idx >= near_tail:
                cut_idx = idx if cut_idx < 0 else min(cut_idx, idx)
        if cut_idx < 0:
            break
        trimmed = trimmed[:cut_idx].rstrip(" \n\r\t，,。！？!?；;:：…")

    return trimmed or raw


def _normalize_qwen_tts_compare_text(text: str) -> str:
    base = sanitize_text(text)
    if not base:
        return ""
    return re.sub(r"[\s\u3000\n\r\t，,。！？!?；;:：…、\"'“”‘’()（）\-—~·]", "", str(base))


async def _qwen_tts_chat_stream_once(text: str, voice_name: str) -> bytes:
    base_url = str(SAFETY_AI_BASE_URL or "").strip().rstrip("/")
    api_key = str(SAFETY_AI_API_KEY or "").strip()
    if not base_url or not api_key:
        raise RuntimeError("Qwen TTS 配置缺失")

    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    speak_text = str(text or "").strip()
    payload = {
        "model": SAFETY_AI_TTS_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是绘本朗读配音器。只朗读用户给定原文，不做解释，不提问，不添加任何额外句子。",
            },
            {
                "role": "user",
                "content": (
                    "请逐字朗读以下文本，不要增删改，不要追加结尾引导，"
                    "尤其不要添加“你要是有什么...”这类句子。\n"
                    "<朗读文本>\n"
                    f"{speak_text}\n"
                    "</朗读文本>"
                ),
            },
        ],
        "modalities": ["text", "audio"],
        "audio": {"voice": str(voice_name or "").strip(), "format": "pcm16"},
        "stream": True,
        "temperature": 0.0,
    }

    raw_pcm = bytearray()
    spoken_preview = ""
    expected_norm = _normalize_qwen_tts_compare_text(speak_text)
    # 估算文本对应的最小音频字节阈值（pcm16, 24k, mono ~= 48000 bytes/s），
    # 防止转写先行导致“只读前半句就被截断”。
    exp_chars = len(expected_norm)
    est_sec = max(1.8, min(60.0, float(exp_chars) / 5.5)) if exp_chars > 0 else 2.0
    min_pcm_bytes_for_tail_cut = int(est_sec * 48000 * 0.6)
    tail_markers = ("你要是有什么", "如果你有什么", "要是有什么问题", "有什么问题可以")

    async with httpx.AsyncClient(timeout=SAFETY_AI_TTS_TIMEOUT_SEC, trust_env=False) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    obj = json.loads(body)
                except Exception:
                    continue

                delta = ((obj.get("choices") or [{}])[0].get("delta") or {})
                text_piece = delta.get("content")
                if isinstance(text_piece, str):
                    spoken_preview += text_piece
                elif isinstance(text_piece, list):
                    for item in text_piece:
                        if isinstance(item, dict):
                            seg_text = item.get("text") or item.get("content")
                            if isinstance(seg_text, str):
                                spoken_preview += seg_text

                audio = delta.get("audio")
                if isinstance(audio, dict):
                    seg_transcript = audio.get("transcript")
                    if isinstance(seg_transcript, str):
                        spoken_preview += seg_transcript
                    seg = audio.get("data")
                    if isinstance(seg, str) and seg.strip():
                        try:
                            raw_pcm.extend(base64.b64decode(seg))
                        except Exception:
                            continue

                if any(mk in spoken_preview for mk in tail_markers):
                    if len(raw_pcm) >= max(96000, min_pcm_bytes_for_tail_cut):
                        logger.warning("[qwen_tts_chat_stream] 检测到尾句追加倾向，提前结束流式音频")
                        break
                    logger.info("[qwen_tts_chat_stream] 检测到尾句倾向但音频积累不足，继续接收以避免截短")

    wav_bytes = _pcm16_to_wav_bytes(bytes(raw_pcm), sample_rate=24000)
    if not wav_bytes:
        raise RuntimeError("chat_stream_tts empty")
    return wav_bytes


async def _qwen_tts_generate_wav(text: str, profile: Optional[dict] = None):
    text_cleaned = _trim_qwen_unwanted_tail(text)
    if not has_speakable_content(text_cleaned):
        text_cleaned = sanitize_text(text)
    if not has_speakable_content(text_cleaned):
        raise RuntimeError("目标文本缺少可发音字符")

    voices = _qwen_voice_candidates(profile)
    errs = []
    for voice_name in voices:
        speech_err = None
        try:
            audio = await _qwen_tts_openai_speech_once(text_cleaned, voice_name)
            if _looks_like_wav_bytes(audio):
                return audio, voice_name, "qwen_tts_openai_compat"
            speech_err = RuntimeError("audio/speech returned non-wav")
        except Exception as e:
            speech_err = e

        try:
            wav_audio = await _qwen_tts_chat_stream_once(text_cleaned, voice_name)
            return wav_audio, voice_name, "qwen_tts_chat_stream"
        except Exception as chat_err:
            errs.append(f"{voice_name}:speech={str(speech_err)[:120]};chat={str(chat_err)[:120]}")
            continue

    raise RuntimeError("; ".join(errs)[:420] or "qwen tts failed")

def _summarize_sanitize_delta(raw: str, cleaned: str, max_samples: int = 12) -> dict:
    """用于定位“吞字/漏字”是否发生在清洗阶段：统计被替换的字符。"""
    try:
        if raw is None:
            raw = ""
        if cleaned is None:
            cleaned = ""
        # 与 sanitize_text 使用同一套允许字符集
        disallowed = re.findall(
            r"[^0-9A-Za-z\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\s.,!?;:、，。？！…\"'()\\-]",
            raw,
        )
        uniq = []
        seen = set()
        for ch in disallowed:
            if ch in seen:
                continue
            seen.add(ch)
            uniq.append(ch)
            if len(uniq) >= max_samples:
                break
        return {
            "raw_len": len(raw),
            "cleaned_len": len(cleaned),
            "removed_count": len(disallowed),
            "removed_uniq_preview": uniq,
        }
    except Exception:
        return {
            "raw_len": len(raw or ""),
            "cleaned_len": len(cleaned or ""),
        }


def _is_only_punc_segment(s: str) -> bool:
    if s is None:
        return True
    t = s.strip()
    if not t:
        return True
    # 参照 api.py 的 splits + 常见标点（用于避免产生“纯符号段”影响切分/合并）
    punc = set(["，", "。", "？", "！", ",", ".", "?", "!", "~", ":", "：", "—", "…", ";", "；", "、", "(", ")", "\"", "'", "-"])
    return all((ch in punc) for ch in t)


def _is_long_book_text(text: str, threshold_chars: int = 180, threshold_sentences: int = 6) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if len(raw) >= int(threshold_chars):
        return True
    punc_count = len(re.findall(r"[。！？!?；;\n]", raw))
    return len(raw) >= 96 and punc_count >= int(threshold_sentences)


def _split_text_for_buffer(text: str, max_len: int = 80, cut_punc: str = "，。？！,.!?;；") -> list:
    # 将长文本切成短句，避免长句导致漏读。
    # 对中短文本尽量少切，降低对白场景（引号/短句）被切碎导致的漏读。
    if not text:
        return []

    max_len = max(20, int(max_len or 80))
    raw = str(text or "").strip()
    if not raw:
        return []

    if len(raw) <= max_len and "\n" not in raw:
        return [raw]

    pre_split = raw
    try:
        from api import cut_text as official_cut_text
        # 仅当文本明显超过阈值时启用官方按标点切分，避免中短文本过度切碎。
        if len(raw) > int(max_len * 1.2):
            pre_split = official_cut_text(raw, cut_punc)
    except Exception:
        pre_split = raw

    items = [t.strip() for t in str(pre_split).split("\n") if t.strip()]
    if not items:
        items = [raw]

    result = []
    for t in items:
        if len(t) <= max_len:
            result.append(t)
            continue
        pieces = re.split(r"([,.;?!、，。？！；：…])", t)
        merged = ["".join(group) for group in zip(pieces[::2], pieces[1::2])]
        if len(pieces) % 2 == 1:
            merged.append(pieces[-1])
        buf = ""
        for pseg in merged:
            if len(buf) + len(pseg) <= max_len:
                buf += pseg
            else:
                if buf:
                    result.append(buf)
                if len(pseg) <= max_len:
                    buf = pseg
                else:
                    for i in range(0, len(pseg), max_len):
                        result.append(pseg[i:i+max_len])
                    buf = ""
        if buf:
            result.append(buf)

    # 过滤/合并纯标点段，避免下游把它当成独立句子导致边界异常
    filtered = []
    for seg in result:
        seg = (seg or "").strip()
        if not seg:
            continue
        if _is_only_punc_segment(seg):
            if filtered:
                filtered[-1] += seg
            continue
        filtered.append(seg)

    # 对话场景合并：引号开头短段并回前句，避免 “"小蓝鱼说” 这类碎片段。
    merged_dialogue = []
    for seg in filtered:
        cur = str(seg or "").strip()
        if not cur:
            continue
        if merged_dialogue:
            prev = merged_dialogue[-1]
            starts_quote = bool(re.match(r'^["“”‘’\'）)】」』]+', cur))
            prev_open = prev.endswith(("\"", "“", "‘", "'", "（", "("))
            short_units = len(re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", cur))
            if (starts_quote or prev_open or short_units <= 3) and len(prev) + len(cur) <= (max_len * 2):
                merged_dialogue[-1] = prev + cur
                continue
        merged_dialogue.append(cur)

    return merged_dialogue
def _cleanup_buffer_tasks():
    now = time.time()
    with BUFFER_TASKS_LOCK:
        expired = [k for k, v in BUFFER_TASKS.items() if now - v.get("created_at", now) > BUFFER_TASK_TTL_SEC]
        for k in expired:
            BUFFER_TASKS.pop(k, None)


STATIC_ROOT_DIR = ""


def _resolve_static_root_dir() -> str:
    """统一静态根目录，避免挂载目录与写入目录不一致导致 /static/tts 404。"""
    global STATIC_ROOT_DIR
    if STATIC_ROOT_DIR and os.path.isdir(STATIC_ROOT_DIR):
        return STATIC_ROOT_DIR

    # 若 cwd 下仅有 tts/、没有 miniprogram_assets，原先会误选该目录，导致 /static/miniprogram_assets/* 全 404。
    backend_static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wx_static")
    cwd_static = os.path.join(now_dir, "wx_static")
    for c in (backend_static, cwd_static):
        if os.path.isdir(c) and os.path.isdir(os.path.join(c, "miniprogram_assets")):
            STATIC_ROOT_DIR = c
            return STATIC_ROOT_DIR
    # 无 miniprogram_assets 时保持旧行为：优先 cwd，避免误选仅有 fonts 的后端目录导致 tts 目录错位。
    for c in (cwd_static, backend_static):
        if os.path.isdir(c):
            STATIC_ROOT_DIR = c
            return STATIC_ROOT_DIR

    os.makedirs(backend_static, exist_ok=True)
    STATIC_ROOT_DIR = backend_static
    return STATIC_ROOT_DIR


def _resolve_tts_static_dir() -> str:
    tts_dir = os.path.join(_resolve_static_root_dir(), "tts")
    os.makedirs(tts_dir, exist_ok=True)
    return tts_dir


def _save_buffer_segment(audio_bytes: bytes, voice_id: str, task_id: str, index: int) -> str:
    tts_dir = _resolve_tts_static_dir()
    os.makedirs(tts_dir, exist_ok=True)
    fname = f"buf_{task_id}_{index:04d}_{voice_id or 'default'}.wav"
    fpath = os.path.join(tts_dir, fname)
    with open(fpath, "wb") as f:
        f.write(audio_bytes)
    return f"/static/tts/{fname}"



def _static_url_to_path(url: str) -> str:
    """把 /static/tts/xxx.wav 转为磁盘路径。"""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        # 这里只处理本服务静态路径；外链不支持合并
        return ""
    if not url.startswith("/static/tts/"):
        return ""
    fname = url.split("/static/tts/", 1)[1]
    return os.path.join(_resolve_tts_static_dir(), fname)


def _merge_wav_files(in_paths: list, out_path: str) -> None:
    """按顺序拼接多个 WAV（要求采样率/声道/采样宽一致）。"""
    if not in_paths:
        raise ValueError("empty wav list")
    params = None
    for p in in_paths:
        if not p or not os.path.exists(p):
            raise FileNotFoundError(p)
        with wave.open(p, "rb") as wf:
            if params is None:
                params = wf.getparams()
            else:
                if (
                    wf.getnchannels() != params.nchannels
                    or wf.getsampwidth() != params.sampwidth
                    or wf.getframerate() != params.framerate
                ):
                    raise ValueError("wav params mismatch")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with wave.open(out_path, "wb") as out_wf:
        out_wf.setnchannels(params.nchannels)
        out_wf.setsampwidth(params.sampwidth)
        out_wf.setframerate(params.framerate)
        for p in in_paths:
            with wave.open(p, "rb") as wf:
                out_wf.writeframes(wf.readframes(wf.getnframes()))


def _merge_wav_segments_to_static(task_id: str) -> str:
    """若任务所有 segments 已就绪，则合并为单个 wav 并返回静态 URL；否则返回空字符串。"""
    _cleanup_buffer_tasks()
    with BUFFER_TASKS_LOCK:
        task = BUFFER_TASKS.get(task_id)
        if not task:
            return ""
        merged_url = task.get("merged_url")
        if merged_url:
            return merged_url
        seg_urls = list(task.get("segments") or [])
        total = int(task.get("total") or len(seg_urls) or 0)
        voice_id = task.get("voice_id")
        merged_text = str(task.get("adaptive_text") or "").strip()
        is_user_trained_voice = bool(
            task.get("is_user_trained_voice", bool(voice_id and (voice_id not in QWEN_BASE_VOICE_IDS)))
        )
        merged_speed = float(task.get("speed_base", 1.0) or 1.0)

    if total <= 0 or len(seg_urls) < total:
        return ""
    if any((u is None) for u in seg_urls[:total]):
        return ""

    in_paths = [_static_url_to_path(u) for u in seg_urls[:total]]
    if any((not p) for p in in_paths):
        raise ValueError("segment url -> path failed")

    tts_dir = _resolve_tts_static_dir()
    fname = f"merged_{task_id}_{voice_id or 'default'}.wav"
    out_path = os.path.join(tts_dir, fname)
    _merge_wav_files(in_paths, out_path)
    try:
        with open(out_path, "rb") as mf:
            merged_raw = mf.read()
        merged_processed, merge_meta = _postprocess_playable_wav_for_text(
            merged_text,
            merged_raw,
            speed=merged_speed,
            over_tolerance=1.23,
            apply_duration_trim=is_user_trained_voice,
            is_user_trained_voice=is_user_trained_voice,
            context="buffered_merged",
        )
        if merged_processed and (merged_processed != merged_raw):
            with open(out_path, "wb") as mf:
                mf.write(merged_processed)
        if isinstance(merge_meta, dict) and merge_meta.get("changed"):
            logger.info(
                f"[buffered] merged 后处理已应用: task_id={task_id}, voice_id={voice_id}, "
                f"silence_trim={merge_meta.get('silence_trim_applied')}, "
                f"boost={merge_meta.get('boost_applied') or merge_meta.get('boost2_applied')}, "
                f"duration_trim={merge_meta.get('duration_trim_applied')}"
            )
        with BUFFER_TASKS_LOCK:
            task = BUFFER_TASKS.get(task_id)
            if task is not None and isinstance(merge_meta, dict):
                task["merged_post_meta"] = merge_meta
    except Exception as e:
        logger.warning(f"[buffered] merged 后处理失败，保留原音频: task_id={task_id}, err={e}")

    merged_url = f"/static/tts/{fname}"
    with BUFFER_TASKS_LOCK:
        task = BUFFER_TASKS.get(task_id)
        if task is not None:
            task["merged_url"] = merged_url
    return merged_url

def _collect_generator_bytes_with_stats(gen):
    chunks = []
    chunk_count = 0
    byte_count = 0
    for chunk in gen:
        if chunk is None:
            continue
        if isinstance(chunk, (bytes, bytearray)):
            b = bytes(chunk)
        else:
            try:
                b = bytes(chunk)
            except Exception as e:
                raise TypeError(f"Unexpected generator chunk type: {type(chunk)}") from e
        chunks.append(b)
        chunk_count += 1
        byte_count += len(b)
    return b"".join(chunks), {"chunks": chunk_count, "bytes": byte_count}


def _collect_generator_bytes(gen) -> bytes:
    audio, _stats = _collect_generator_bytes_with_stats(gen)
    return audio



def _try_get_wav_info(audio_bytes: bytes) -> dict:
    """Best-effort parse WAV header to get duration; returns {} on failure."""
    if not audio_bytes:
        return {}
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wf:
            sr = wf.getframerate() or 0
            frames = wf.getnframes() or 0
            duration_sec = (float(frames) / float(sr)) if sr else None
            return {
                "sr": int(sr) if sr else 0,
                "frames": int(frames) if frames else 0,
                "duration_sec": duration_sec,
            }
    except Exception:
        return {}


def _boost_low_rms_wav_if_needed(
    audio_bytes: bytes,
    trigger_rms: float = 180.0,
    target_rms: float = 1100.0,
    max_gain: float = 40.0,
):
    """对异常偏小音量进行温和增益，提升可听性。"""
    if not audio_bytes:
        return audio_bytes, {"applied": False, "reason": "empty"}
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels() or 1
            sw = wf.getsampwidth() or 0
            sr = wf.getframerate() or 0
            frames = wf.getnframes() or 0
            raw = wf.readframes(frames)
    except Exception:
        return audio_bytes, {"applied": False, "reason": "wav_parse_failed"}

    if sw <= 0 or not raw:
        return audio_bytes, {"applied": False, "reason": "no_pcm"}

    cur_rms = float(audioop.rms(raw, sw) or 0.0)
    if cur_rms <= 0:
        return audio_bytes, {"applied": False, "reason": "zero_rms"}
    if cur_rms >= float(trigger_rms):
        return audio_bytes, {"applied": False, "reason": "rms_ok", "rms": cur_rms}

    gain = min(float(max_gain), max(1.0, float(target_rms) / cur_rms))
    try:
        boosted = audioop.mul(raw, sw, gain)
    except Exception:
        return audio_bytes, {"applied": False, "reason": "mul_failed", "rms": cur_rms}

    out = BytesIO()
    try:
        with wave.open(out, "wb") as wf_out:
            wf_out.setnchannels(int(channels))
            wf_out.setsampwidth(int(sw))
            wf_out.setframerate(int(sr))
            wf_out.writeframes(boosted)
        out_bytes = out.getvalue()
    except Exception:
        return audio_bytes, {"applied": False, "reason": "wav_write_failed", "rms": cur_rms}

    new_rms = float(audioop.rms(boosted, sw) or 0.0)
    return out_bytes, {
        "applied": True,
        "reason": "boosted",
        "rms_before": cur_rms,
        "rms_after": new_rms,
        "gain": gain,
    }


def _trim_wav_silence_edges_if_needed(
    audio_bytes: bytes,
    rms_threshold: float = 22.0,
    window_ms: int = 20,
    max_trim_ratio: float = 0.28,
    min_keep_sec: float = 0.45,
):
    if not audio_bytes:
        return audio_bytes, {"applied": False, "reason": "empty"}

    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels() or 1
            sw = wf.getsampwidth() or 0
            sr = wf.getframerate() or 0
            frames = wf.getnframes() or 0
            raw = wf.readframes(frames)
    except Exception:
        return audio_bytes, {"applied": False, "reason": "wav_parse_failed"}

    if sw <= 0 or sr <= 0 or frames <= 0 or (not raw):
        return audio_bytes, {"applied": False, "reason": "invalid_pcm"}

    frame_bytes = max(1, int(channels) * int(sw))
    window_frames = max(1, int(float(sr) * (max(5, int(window_ms or 20)) / 1000.0)))
    window_frames = min(window_frames, int(frames))
    threshold = max(6.0, min(260.0, float(rms_threshold or 22.0)))

    trim_ratio = max(0.0, min(0.45, float(max_trim_ratio or 0.28)))
    max_trim_frames = int(float(frames) * trim_ratio)
    max_trim_frames = max(window_frames, max_trim_frames)

    def _chunk_rms(start_frame: int) -> float:
        start_b = max(0, int(start_frame)) * frame_bytes
        end_b = min(len(raw), int(start_frame + window_frames) * frame_bytes)
        if end_b <= start_b:
            return 0.0
        return float(audioop.rms(raw[start_b:end_b], sw) or 0.0)

    head = 0
    while (head + window_frames) < frames and head < max_trim_frames:
        if _chunk_rms(head) >= threshold:
            break
        head += window_frames

    tail = int(frames)
    tail_trim_frames = 0
    while (tail - window_frames) > head and tail_trim_frames < max_trim_frames:
        if _chunk_rms(tail - window_frames) >= threshold:
            break
        tail -= window_frames
        tail_trim_frames += window_frames

    keep_frames = max(0, tail - head)
    if keep_frames <= 0:
        return audio_bytes, {"applied": False, "reason": "trim_to_empty"}

    min_keep_frames = int(max(0.12, float(min_keep_sec or 0.45)) * float(sr))
    if keep_frames < min_keep_frames:
        return audio_bytes, {
            "applied": False,
            "reason": "keep_too_short",
            "keep_sec": float(keep_frames) / float(sr),
        }

    if head <= 0 and tail >= frames:
        return audio_bytes, {
            "applied": False,
            "reason": "no_edge_silence",
            "src_sec": float(frames) / float(sr),
        }

    trimmed_raw = raw[head * frame_bytes : tail * frame_bytes]
    if not trimmed_raw:
        return audio_bytes, {"applied": False, "reason": "trimmed_empty"}

    out = BytesIO()
    try:
        with wave.open(out, "wb") as wf_out:
            wf_out.setnchannels(int(channels))
            wf_out.setsampwidth(int(sw))
            wf_out.setframerate(int(sr))
            wf_out.writeframes(trimmed_raw)
    except Exception:
        return audio_bytes, {"applied": False, "reason": "wav_write_failed"}

    src_sec = float(frames) / float(sr)
    dst_sec = float(keep_frames) / float(sr)
    return out.getvalue(), {
        "applied": True,
        "reason": "trim_edge_silence",
        "src_sec": src_sec,
        "dst_sec": dst_sec,
        "trim_head_sec": float(head) / float(sr),
        "trim_tail_sec": max(0.0, src_sec - dst_sec - (float(head) / float(sr))),
    }


def _estimate_min_duration_sec(text: str, speed: float = 1.0) -> float:
    """粗略估计文本最小时长，用于识别明显漏读。"""
    t = sanitize_text(str(text or ""))
    units = re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", t)
    pauses = re.findall(r"[，。！？；、,!?;:：…]", t)
    n = len(units)
    if n <= 0:
        return 0.0
    spd = max(0.75, min(1.35, float(speed or 1.0)))
    base_sec = float(n) * 0.145 + float(len(pauses)) * 0.09
    return max(0.45, base_sec / spd)


def _estimate_max_duration_sec(text: str, speed: float = 1.0) -> float:
    """粗略估计文本最大合理时长，用于识别明显拖长/重复。"""
    t = sanitize_text(str(text or ""))
    units = re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", t)
    pauses = re.findall(r"[，。！？；、,!?;:：…]", t)
    n = len(units)
    if n <= 0:
        return 0.0
    spd = max(0.75, min(1.35, float(speed or 1.0)))
    base_sec = float(n) * 0.32 + float(len(pauses)) * 0.22 + 0.9
    return max(1.8, base_sec / spd)


def _estimate_infer_max_sec_limit(
    text: str,
    speed: float = 1.0,
    is_user_trained_voice: bool = False,
    risk_tier: str = "normal",
) -> int:
    est_max = _estimate_max_duration_sec(text, speed=speed)
    if est_max <= 0:
        return 0

    if is_user_trained_voice:
        t = sanitize_text(str(text or ""))
        units = len(re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", t))
        pauses = len(re.findall(r"[，。！？；、,!?;:：…]", t))
        spd = max(0.75, min(1.35, float(speed or 1.0)))
        tier = str(risk_tier or "normal").strip().lower()

        if tier == "strict":
            sec = est_max + 3.2 + (0.6 if units <= 45 else 0.0)
            lo, hi = 10, 24
        elif tier == "risky":
            sec = est_max + 2.4 + (0.4 if units <= 45 else 0.0)
            lo, hi = 9, 20
        else:
            if units <= 45:
                fast_est = max(1.8, (float(units) * 0.27 + float(pauses) * 0.20 + 1.0) / spd)
                sec = fast_est + 1.8
                lo, hi = 7, 15
            else:
                sec = est_max + 1.8
                lo, hi = 8, 18
    else:
        sec = est_max + 3.0
        lo, hi = 10, 28

    sec_int = int(float(sec) + 0.999)
    return max(lo, min(hi, sec_int))


def _apply_temporary_infer_max_sec(target_sec: int):
    target = int(target_sec or 0)
    if target <= 0:
        return False, [], None, None

    try:
        import api as _api_mod
    except Exception:
        return False, [], None, None

    candidates = []
    infer_gpt = getattr(_api_mod, "infer_gpt", None)
    if infer_gpt is not None and hasattr(infer_gpt, "max_sec"):
        candidates.append(infer_gpt)

    spk = getattr(_api_mod, "speaker_list", {}).get("default") if hasattr(_api_mod, "speaker_list") else None
    if spk is not None and hasattr(spk, "gpt") and hasattr(spk.gpt, "max_sec"):
        if all(id(spk.gpt) != id(obj) for obj in candidates):
            candidates.append(spk.gpt)

    restore_items = []
    old_vals = []
    new_vals = []
    for obj in candidates:
        try:
            old_sec = float(getattr(obj, "max_sec"))
        except Exception:
            continue

        new_sec = max(6.0, min(float(target), old_sec))
        if new_sec >= old_sec:
            continue

        try:
            setattr(obj, "max_sec", new_sec)
        except Exception:
            continue

        restore_items.append((obj, old_sec))
        old_vals.append(old_sec)
        new_vals.append(new_sec)

    if not restore_items:
        return False, [], None, None

    return True, restore_items, min(old_vals), min(new_vals)


def _restore_temporary_infer_max_sec(restore_items):
    for obj, old_sec in reversed(restore_items or []):
        try:
            setattr(obj, "max_sec", old_sec)
        except Exception:
            pass


def _trim_wav_bytes_to_duration(audio_bytes: bytes, max_duration_sec: float):
    if not audio_bytes:
        return audio_bytes, {"applied": False, "reason": "empty_audio"}
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            if framerate <= 0 or nframes <= 0:
                return audio_bytes, {"applied": False, "reason": "invalid_wav"}
            src_sec = float(nframes) / float(framerate)
            keep_frames = int(max(1.0, float(max_duration_sec or 0.0)) * float(framerate))
            if keep_frames >= nframes:
                return audio_bytes, {
                    "applied": False,
                    "reason": "already_short_enough",
                    "src_sec": src_sec,
                }
            keep_frames = max(1, keep_frames)
            wf.rewind()
            raw = wf.readframes(keep_frames)

        out = BytesIO()
        with wave.open(out, "wb") as wf_out:
            wf_out.setnchannels(channels)
            wf_out.setsampwidth(sample_width)
            wf_out.setframerate(framerate)
            wf_out.writeframes(raw)
        trimmed = out.getvalue()
        return trimmed, {
            "applied": True,
            "reason": "trim_over_generated",
            "src_sec": src_sec,
            "dst_sec": float(keep_frames) / float(framerate),
            "keep_frames": keep_frames,
            "src_frames": nframes,
        }
    except Exception as e:
        return audio_bytes, {"applied": False, "reason": f"trim_failed:{e}"}


def _trim_over_generated_audio_if_needed(
    text: str,
    audio_bytes: bytes,
    speed: float = 1.0,
    over_tolerance: float = 1.25,
):
    info = _try_get_wav_info(audio_bytes)
    duration = float(info.get("duration_sec") or 0.0)
    if duration <= 0:
        return audio_bytes, {"applied": False, "reason": "invalid_duration"}

    max_sec_est = _estimate_max_duration_sec(text, speed=speed)
    if max_sec_est <= 0:
        return audio_bytes, {"applied": False, "reason": "invalid_estimate"}

    over_tol = max(1.0, min(2.2, float(over_tolerance or 1.25)))
    threshold = max_sec_est * over_tol
    if duration <= threshold:
        return audio_bytes, {
            "applied": False,
            "reason": "not_over_generated",
            "duration_sec": duration,
            "threshold_sec": threshold,
        }

    min_sec_est = _estimate_min_duration_sec(text, speed=speed)
    keep_sec = max(max_sec_est * 1.06, min_sec_est * 1.35, 1.2)
    keep_sec = min(keep_sec, duration)
    trimmed, meta = _trim_wav_bytes_to_duration(audio_bytes, keep_sec)
    if isinstance(meta, dict):
        meta.setdefault("duration_sec", duration)
        meta.setdefault("threshold_sec", threshold)
        meta.setdefault("keep_sec", keep_sec)
    return trimmed, meta


def _postprocess_playable_wav_for_text(
    text: str,
    audio_bytes: bytes,
    speed: float = 1.0,
    over_tolerance: float = 1.25,
    apply_duration_trim: bool = False,
    is_user_trained_voice: bool = False,
    context: str = "",
):
    if not audio_bytes:
        return audio_bytes, {"changed": False, "reason": "empty", "context": context}

    source = audio_bytes
    out = audio_bytes

    trim_threshold = 24.0 if is_user_trained_voice else 20.0
    out, silence_meta = _trim_wav_silence_edges_if_needed(
        out,
        rms_threshold=trim_threshold,
        window_ms=20,
        max_trim_ratio=0.30,
        min_keep_sec=0.45,
    )

    units = _count_text_units(text)
    base_trigger = _min_rms_for_text(text)
    boost_trigger = max(110.0, min(260.0, base_trigger * (1.9 if units >= 8 else 2.2)))
    boost_target = max(980.0, boost_trigger * 5.6)
    out, boost_meta = _boost_low_rms_wav_if_needed(
        out,
        trigger_rms=boost_trigger,
        target_rms=boost_target,
        max_gain=52.0,
    )

    rms_after_boost = _estimate_wav_rms(out)
    if rms_after_boost > 0 and rms_after_boost < max(38.0, base_trigger * 0.72):
        out, boost_meta2 = _boost_low_rms_wav_if_needed(
            out,
            trigger_rms=max(48.0, base_trigger * 0.90),
            target_rms=max(1200.0, base_trigger * 8.0),
            max_gain=70.0,
        )
    else:
        boost_meta2 = {"applied": False, "reason": "skip_second_boost", "rms": rms_after_boost}

    if apply_duration_trim:
        out, duration_meta = _trim_over_generated_audio_if_needed(
            text,
            out,
            speed=float(speed or 1.0),
            over_tolerance=over_tolerance,
        )
    else:
        duration_meta = {"applied": False, "reason": "disabled"}

    info_before = _try_get_wav_info(source)
    info_after = _try_get_wav_info(out)
    rms_before = _estimate_wav_rms(source)
    rms_after = _estimate_wav_rms(out)
    changed = (out != source)

    return out, {
        "changed": changed,
        "context": context,
        "silence_trim_applied": bool((silence_meta or {}).get("applied")),
        "boost_applied": bool((boost_meta or {}).get("applied")),
        "boost2_applied": bool((boost_meta2 or {}).get("applied")),
        "duration_trim_applied": bool((duration_meta or {}).get("applied")),
        "silence_trim_meta": silence_meta,
        "boost_meta": boost_meta,
        "boost2_meta": boost_meta2,
        "duration_trim_meta": duration_meta,
        "rms_before": rms_before,
        "rms_after": rms_after,
        "src_sec": info_before.get("duration_sec"),
        "dst_sec": info_after.get("duration_sec"),
    }


def _duration_match_score(text: str, audio_bytes: bytes, speed: float = 1.0) -> float:
    info = _try_get_wav_info(audio_bytes)
    duration = float(info.get("duration_sec") or 0.0)
    if duration <= 0:
        return 1e9
    min_sec = _estimate_min_duration_sec(text, speed=speed)
    max_sec = _estimate_max_duration_sec(text, speed=speed)
    if max_sec < min_sec:
        max_sec = min_sec
    target = (min_sec + max_sec) / 2.0
    return abs(duration - target)


def _is_under_generated_audio(text: str, audio_bytes: bytes, speed: float = 1.0, tolerance: float = 0.90) -> bool:
    info = _try_get_wav_info(audio_bytes)
    duration = float(info.get("duration_sec") or 0.0)
    if duration <= 0:
        return False
    min_sec = _estimate_min_duration_sec(text, speed=speed)
    tol = max(0.60, min(1.00, float(tolerance or 0.90)))
    return min_sec > 0 and duration < (min_sec * tol)


def _is_over_generated_audio(text: str, audio_bytes: bytes, speed: float = 1.0, tolerance: float = 1.25) -> bool:
    info = _try_get_wav_info(audio_bytes)
    duration = float(info.get("duration_sec") or 0.0)
    if duration <= 0:
        return False
    max_sec = _estimate_max_duration_sec(text, speed=speed)
    tol = max(1.00, min(2.20, float(tolerance or 1.25)))
    return max_sec > 0 and duration > (max_sec * tol)


def _estimate_wav_rms(audio_bytes: bytes) -> float:
    if not audio_bytes:
        return 0.0
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wf:
            sw = wf.getsampwidth() or 0
            frames = wf.getnframes() or 0
            if sw <= 0 or frames <= 0:
                return 0.0
            raw = wf.readframes(frames)
        if not raw:
            return 0.0
        return float(audioop.rms(raw, sw))
    except Exception:
        return 0.0


def _min_rms_for_text(text: str) -> float:
    units = _count_text_units(text)
    if units >= 20:
        return 120.0
    if units >= 10:
        return 90.0
    return 65.0


def _is_low_energy_generated_audio(text: str, audio_bytes: bytes, min_rms: float = None) -> bool:
    info = _try_get_wav_info(audio_bytes)
    duration = float(info.get("duration_sec") or 0.0)
    if duration <= 0:
        return False
    rms_val = _estimate_wav_rms(audio_bytes)
    threshold = float(min_rms) if min_rms is not None else _min_rms_for_text(text)
    if rms_val <= 0:
        return duration >= 0.22
    return rms_val < max(35.0, threshold)


def _is_abnormal_generated_audio(
    text: str,
    audio_bytes: bytes,
    speed: float = 1.0,
    under_tolerance: float = 0.90,
    over_tolerance: float = 1.25,
) -> bool:
    return (
        _is_under_generated_audio(text, audio_bytes, speed=speed, tolerance=under_tolerance)
        or _is_over_generated_audio(text, audio_bytes, speed=speed, tolerance=over_tolerance)
        or _is_low_energy_generated_audio(text, audio_bytes)
    )


def _count_text_units(text: str) -> int:
    t = sanitize_text(str(text or ""))
    return len(re.findall(r"[0-9A-Za-z一-鿿]", t))


def _resolve_adaptive_user_voice_sample_steps(
    data: dict,
    text: str,
    default_steps: int = 32,
    is_user_trained_voice: bool = False,
) -> int:
    try:
        base_steps = int(default_steps)
    except Exception:
        base_steps = 32
    base_steps = max(8, min(96, base_steps))

    if not is_user_trained_voice:
        return base_steps

    data = data or {}
    if "sample_steps" in data:
        return base_steps
    if not _coerce_bool_param(data.get("hq_user_voice_adaptive_fast"), True):
        return base_steps

    units = _count_text_units(text)
    if units <= 16:
        target_steps = 24
    elif units <= 40:
        target_steps = 26
    elif units <= 80:
        target_steps = 28
    elif units <= 130:
        target_steps = 30
    else:
        target_steps = 32

    try:
        min_steps = int(data.get("hq_user_voice_min_steps", 24))
    except Exception:
        min_steps = 24
    min_steps = max(20, min(32, min_steps))
    target_steps = max(min_steps, target_steps)

    return max(8, min(base_steps, target_steps))


def _should_use_user_voice_segmented_sync(data: dict, text: str, segments: list) -> bool:
    data = data or {}
    seg_count = len(segments or [])
    if seg_count < 2:
        return False

    if not _coerce_bool_param(data.get("hq_user_voice_segmented"), True):
        return False

    mode = str(data.get("hq_user_voice_segmented_mode", "auto") or "auto").strip().lower()
    if mode in ("always", "force", "on", "true", "1"):
        return True
    if mode in ("off", "false", "0", "never"):
        return False

    if not _coerce_bool_param(data.get("hq_user_voice_segmented_adaptive"), True):
        return True

    units = _count_text_units(text)
    avg_units = units / max(1, seg_count)

    if seg_count >= 4:
        return True
    if units >= 150:
        return True
    if seg_count >= 3 and units >= 90:
        return True
    if seg_count >= 3 and avg_units <= 28:
        return True
    if ("\n" in str(text or "")) and seg_count >= 2 and units >= 80:
        return True

    return False


def _create_buffer_task(
    segments: list,
    data: dict,
    ref_audio_path: str,
    ref_text_cleaned: str,
    api_prompt_lang: str,
    api_text_lang: str,
    voice_id: str,
    aux_ref_audio_paths: list,
    official_get_tts_wav_api,
    debug_id: str = None,
):
    _cleanup_buffer_tasks()
    data = data or {}
    total = len(segments)
    if total == 0:
        raise HTTPException(status_code=400, detail="文本切分为空，无法推理")

    buffer_segments = int(data.get("buffer_segments", 1))
    buffer_segments = max(1, min(buffer_segments, total))

    task_id = uuid.uuid4().hex
    task = {
        "created_at": time.time(),
        "total": total,
        "segments": [None] * total,
        "done": False,
        "error": None,
        "debug_id": debug_id,
        "voice_id": voice_id,
        "merged_url": None,
        "adaptive_text": "",
        "is_user_trained_voice": False,
        "speed_base": 1.0,
    }
    with BUFFER_TASKS_LOCK:
        BUFFER_TASKS[task_id] = task

    top_k_base = int(data.get("top_k", 20))
    top_p_base = float(data.get("top_p", 0.85))
    temperature_base = float(data.get("temperature", 0.45))
    repetition_penalty_base = float(data.get("repetition_penalty", 1.18))
    speed_base = float(data.get("speed", 1.0))
    sample_steps_raw = int(data.get("sample_steps", 32))
    is_user_trained_voice = _coerce_bool_param(data.get("_is_user_trained_voice"), False)
    voice_policy = {
        "tier": "normal",
        "cache_mode": "speed",
        "applied": False,
        "reasons": [],
    }
    if is_user_trained_voice and voice_id:
        data, voice_policy = _apply_user_voice_risk_policy(data, voice_id, VOICE_LIBRARY.get(voice_id) or {})
        if voice_policy.get("applied"):
            logger.info(
                f"[buffered] user_trained 风险分层策略已应用: voice_id={voice_id}, "
                f"tier={voice_policy.get('tier')}, reasons={voice_policy.get('reasons')}, "
                f"overrides={list((voice_policy.get('applied_overrides') or {}).keys())}"
            )
    if is_user_trained_voice and _coerce_bool_param(data.get("hq_user_voice_speed_boost"), True):
        try:
            min_speed = float(data.get("hq_user_voice_min_speed", 1.15))
        except Exception:
            min_speed = 1.15
        min_speed = max(1.00, min(1.25, min_speed))
        speed_base = max(speed_base, min_speed)
    if is_user_trained_voice and _coerce_bool_param(data.get("hq_user_voice_fast_decode"), True):
        top_k_base = min(top_k_base, 16)
        top_p_base = min(top_p_base, 0.78)
        temperature_base = min(temperature_base, 0.30)
        repetition_penalty_base = max(repetition_penalty_base, 1.22)
    adaptive_text = str(data.get("_adaptive_text") or "").strip() or "\n".join(
        [str(s).strip() for s in (segments or []) if str(s).strip()]
    )
    with BUFFER_TASKS_LOCK:
        task["adaptive_text"] = adaptive_text
        task["is_user_trained_voice"] = bool(is_user_trained_voice)
        task["speed_base"] = float(speed_base)
    sample_steps_base = _resolve_adaptive_user_voice_sample_steps(
        data=data,
        text=adaptive_text,
        default_steps=sample_steps_raw,
        is_user_trained_voice=is_user_trained_voice,
    )
    if sample_steps_base != sample_steps_raw:
        logger.info(f"[buffered] user_trained adaptive sample_steps: {sample_steps_raw} -> {sample_steps_base}")
    aux_ref_audio_paths = [str(p).strip() for p in (aux_ref_audio_paths or []) if str(p).strip()]
    inp_refs_payload = _build_inp_refs_payload(aux_ref_audio_paths, base_dir=now_dir)

    def _gen_once(seg_text: str, profile: dict, attempt_tag: str) -> bytes:
        try:
            import api as official_api_module
            official_api_module.stream_mode = "close"
            official_api_module.media_type = "wav"
        except Exception:
            pass

        profile_speed = float(profile.get("speed", speed_base))
        target_max_sec = _estimate_infer_max_sec_limit(
            seg_text,
            speed=profile_speed,
            is_user_trained_voice=is_user_trained_voice,
            risk_tier=voice_policy.get("tier"),
        )
        if (
            is_user_trained_voice
            and str(voice_policy.get("tier") or "").strip().lower() in ("risky", "strict")
            and _coerce_bool_param(data.get("hq_user_voice_relax_max_sec"), True)
        ):
            target_max_sec = 0
        sec_override_applied = False
        sec_override_old = None
        sec_override_new = None
        with _INFER_MAX_SEC_OVERRIDE_LOCK:
            sec_override_applied, sec_restore_items, sec_override_old, sec_override_new = _apply_temporary_infer_max_sec(target_max_sec)
            try:
                gen = official_get_tts_wav_api(
                    ref_wav_path=ref_audio_path,
                    prompt_text=ref_text_cleaned,
                    prompt_language=api_prompt_lang,
                    text=seg_text,
                    text_language=api_text_lang,
                    top_k=int(profile.get("top_k", top_k_base)),
                    top_p=float(profile.get("top_p", top_p_base)),
                    temperature=float(profile.get("temperature", temperature_base)),
                    repetition_penalty=float(profile.get("repetition_penalty", repetition_penalty_base)),
                    speed=profile_speed,
                    inp_refs=inp_refs_payload or None,
                    sample_steps=int(profile.get("sample_steps", sample_steps_base)),
                    if_sr=False,
                    spk="default",
                )
            finally:
                _restore_temporary_infer_max_sec(sec_restore_items)
        t_start = time.time()
        audio_bytes_wav, gen_stats = _collect_generator_bytes_with_stats(gen)
        gen_stats = gen_stats or {}
        _debug_add_segment(
            debug_id,
            -1,
            kind="buffered_call",
            attempt=attempt_tag,
            seg_len=len(seg_text),
            gen_chunks=gen_stats.get("chunks"),
            gen_bytes=gen_stats.get("bytes"),
            cost_ms=int((time.time()-t_start)*1000),
            max_sec_target=target_max_sec or None,
            max_sec_override_applied=bool(sec_override_applied),
            max_sec_before=sec_override_old,
            max_sec_after=sec_override_new,
        )
        if not audio_bytes_wav:
            raise StopIteration("empty audio bytes")
        return audio_bytes_wav

    def _gen_one(seg_text: str) -> bytes:
        seg_units = _count_text_units(seg_text)
        under_tol = 0.92 if seg_units >= 14 else 0.90
        over_tol = 1.20 if seg_units >= 14 else 1.23
        under_tol, over_tol = _apply_voice_risk_tolerance(under_tol, over_tol, voice_policy.get("tier"))

        primary_profile = {
            "top_k": top_k_base,
            "top_p": top_p_base,
            "temperature": temperature_base,
            "repetition_penalty": repetition_penalty_base,
            "speed": speed_base,
            "sample_steps": sample_steps_base,
        }
        audio_bytes_wav = _gen_once(seg_text, primary_profile, "base")

        def _finalize_segment_audio(candidate_bytes: bytes, profile_speed: float) -> bytes:
            processed_bytes, post_meta = _postprocess_playable_wav_for_text(
                seg_text,
                candidate_bytes,
                speed=float(profile_speed or speed_base),
                over_tolerance=over_tol,
                apply_duration_trim=is_user_trained_voice and str(voice_policy.get("tier") or "").strip().lower() != "risky",
                is_user_trained_voice=is_user_trained_voice,
                context="buffered_segment",
            )
            if isinstance(post_meta, dict) and post_meta.get("changed"):
                logger.info(
                    f"[buffered] segment 后处理已应用: voice_id={voice_id}, "
                    f"silence_trim={post_meta.get('silence_trim_applied')}, "
                    f"boost={post_meta.get('boost_applied') or post_meta.get('boost2_applied')}, "
                    f"duration_trim={post_meta.get('duration_trim_applied')}, "
                    f"rms={post_meta.get('rms_before')}->{post_meta.get('rms_after')}"
                )
            return processed_bytes

        if not _is_abnormal_generated_audio(seg_text, audio_bytes_wav, speed=primary_profile["speed"], under_tolerance=under_tol, over_tolerance=over_tol):
            return _finalize_segment_audio(audio_bytes_wav, float(primary_profile.get("speed", speed_base)))

        best_audio_bytes = audio_bytes_wav
        best_score = _duration_match_score(seg_text, audio_bytes_wav, speed=primary_profile["speed"])

        is_under_initial = _is_under_generated_audio(
            seg_text,
            audio_bytes_wav,
            speed=float(primary_profile.get("speed", speed_base)),
            tolerance=under_tol,
        )
        is_over_initial = _is_over_generated_audio(
            seg_text,
            audio_bytes_wav,
            speed=float(primary_profile.get("speed", speed_base)),
            tolerance=over_tol,
        )
        is_low_energy_initial = _is_low_energy_generated_audio(seg_text, audio_bytes_wav)

        if is_user_trained_voice:
            if is_over_initial and (not is_under_initial):
                if _coerce_bool_param(data.get("hq_user_voice_over_retry"), False):
                    retry_profiles = [
                        {
                            "top_k": max(16, top_k_base),
                            "top_p": min(0.88, max(0.80, top_p_base)),
                            "temperature": min(0.40, max(0.30, temperature_base)),
                            "repetition_penalty": min(1.20, max(1.12, repetition_penalty_base)),
                            "speed": max(1.10, speed_base),
                            "sample_steps": max(22, min(28, sample_steps_base)),
                        },
                    ]
                else:
                    logger.info(f"[buffered] user_trained over-generated: skip retry for speed, voice_id={voice_id}")
                    retry_profiles = []
            elif is_under_initial:
                retry_profiles = [
                    {
                        "top_k": max(18, top_k_base),
                        "top_p": max(0.86, top_p_base),
                        "temperature": min(0.38, max(0.30, temperature_base)),
                        "repetition_penalty": min(1.22, max(1.14, repetition_penalty_base)),
                        "speed": min(0.98, speed_base),
                        "sample_steps": max(32, sample_steps_base),
                    },
                    {
                        "top_k": max(20, top_k_base),
                        "top_p": max(0.90, top_p_base),
                        "temperature": min(0.34, max(0.28, temperature_base)),
                        "repetition_penalty": min(1.24, max(1.16, repetition_penalty_base)),
                        "speed": min(0.95, speed_base),
                        "sample_steps": max(40, sample_steps_base + 8),
                    },
                ]
            elif is_low_energy_initial:
                retry_profiles = [
                    {
                        "top_k": max(17, top_k_base),
                        "top_p": max(0.84, top_p_base),
                        "temperature": min(0.38, max(0.30, temperature_base)),
                        "repetition_penalty": min(1.22, max(1.14, repetition_penalty_base)),
                        "speed": max(0.98, speed_base),
                        "sample_steps": max(30, min(36, sample_steps_base + 2)),
                    },
                ]
            else:
                retry_profiles = [
                    {
                        "top_k": max(17, top_k_base),
                        "top_p": max(0.84, top_p_base),
                        "temperature": min(0.38, max(0.30, temperature_base)),
                        "repetition_penalty": min(1.20, max(1.14, repetition_penalty_base)),
                        "speed": max(0.99, speed_base),
                        "sample_steps": max(30, min(36, sample_steps_base + 2)),
                    },
                ]
        else:
            retry_profiles = [
                {
                    "top_k": max(16, top_k_base),
                    "top_p": max(0.82, top_p_base),
                    "temperature": min(0.42, max(0.32, temperature_base)),
                    "repetition_penalty": min(1.20, max(1.14, repetition_penalty_base)),
                    "speed": min(0.98, speed_base),
                    "sample_steps": max(36, sample_steps_base),
                },
                {
                    "top_k": max(18, top_k_base),
                    "top_p": max(0.88, top_p_base),
                    "temperature": min(0.40, max(0.30, temperature_base)),
                    "repetition_penalty": min(1.22, max(1.16, repetition_penalty_base)),
                    "speed": min(0.94, speed_base),
                    "sample_steps": max(44, sample_steps_base),
                },
                {
                    "top_k": max(20, top_k_base),
                    "top_p": max(0.90, top_p_base),
                    "temperature": min(0.36, max(0.28, temperature_base)),
                    "repetition_penalty": min(1.24, max(1.18, repetition_penalty_base)),
                    "speed": min(0.92, speed_base),
                    "sample_steps": max(52, sample_steps_base),
                },
            ]

        if not retry_profiles:
            return _finalize_segment_audio(best_audio_bytes, float(primary_profile.get("speed", speed_base)))

        for ridx, rp in enumerate(retry_profiles, start=1):
            try:
                retry_audio_bytes = _gen_once(seg_text, rp, f"retry{ridx}")
            except StopIteration:
                continue

            retry_info = _try_get_wav_info(retry_audio_bytes)
            retry_duration = float(retry_info.get("duration_sec") or 0.0)
            retry_score = _duration_match_score(seg_text, retry_audio_bytes, speed=rp["speed"])
            if retry_score < best_score:
                best_audio_bytes = retry_audio_bytes
                best_score = retry_score

            if not _is_abnormal_generated_audio(seg_text, retry_audio_bytes, speed=rp["speed"], under_tolerance=under_tol, over_tolerance=over_tol):
                logger.info(f"[buffered] segment 分级重试第{ridx}轮通过，dur={retry_duration:.2f}s")
                return _finalize_segment_audio(retry_audio_bytes, float(rp.get("speed", speed_base)))

        logger.warning("[buffered] segment 分级重试后仍异常，返回最接近期望时长版本")
        return _finalize_segment_audio(best_audio_bytes, float(primary_profile.get("speed", speed_base)))

    ready_urls = []
    for i in range(buffer_segments):
        if debug_id:
            logger.info(f"[buffered][{debug_id}] segment.start i={i}/{total} len={len(segments[i])} text={segments[i][:120]!r}")
        _debug_event(debug_id, "buffered.segment.start", index=i, text=segments[i][:120], seg_len=len(segments[i]))
        audio_bytes = _gen_one(segments[i])
        wav_info = _try_get_wav_info(audio_bytes)
        url = _save_buffer_segment(audio_bytes, voice_id, task_id, i)
        _debug_event(
            debug_id,
            "buffered.segment.ready",
            index=i,
            url=url,
            wav_bytes=len(audio_bytes),
            wav_sec=wav_info.get("duration_sec"),
            wav_sr=wav_info.get("sr"),
            wav_frames=wav_info.get("frames"),
        )
        if debug_id:
            logger.info(f"[buffered][{debug_id}] segment.ready i={i}/{total} wav_sec={wav_info.get('duration_sec')} bytes={len(audio_bytes)} url={url}")
        with BUFFER_TASKS_LOCK:
            task["segments"][i] = url
        ready_urls.append(url)

    def _worker(start_idx: int):
        try:
            for i in range(start_idx, total):
                if debug_id:
                    logger.info(f"[buffered][{debug_id}] segment.start i={i}/{total} len={len(segments[i])} text={segments[i][:120]!r}")
                _debug_event(debug_id, "buffered.segment.start", index=i, text=segments[i][:120], seg_len=len(segments[i]))
                audio_bytes = _gen_one(segments[i])
                wav_info = _try_get_wav_info(audio_bytes)
                url = _save_buffer_segment(audio_bytes, voice_id, task_id, i)
                _debug_event(
                    debug_id,
                    "buffered.segment.ready",
                    index=i,
                    url=url,
                    wav_bytes=len(audio_bytes),
                    wav_sec=wav_info.get("duration_sec"),
                    wav_sr=wav_info.get("sr"),
                    wav_frames=wav_info.get("frames"),
                )
                if debug_id:
                    logger.info(f"[buffered][{debug_id}] segment.ready i={i}/{total} wav_sec={wav_info.get('duration_sec')} bytes={len(audio_bytes)} url={url}")
                with BUFFER_TASKS_LOCK:
                    task["segments"][i] = url
        except Exception as e:
            with BUFFER_TASKS_LOCK:
                task["error"] = str(e)
        finally:
            with BUFFER_TASKS_LOCK:
                task["done"] = True

    start_idx = buffer_segments
    if start_idx < total:
        threading.Thread(target=_worker, args=(start_idx,), daemon=True).start()
    else:
        with BUFFER_TASKS_LOCK:
            task["done"] = True

    return task_id, ready_urls, total


def _generate_wav_via_segmented_buffer_sync(
    segments: list,
    data: dict,
    ref_audio_path: str,
    ref_text_cleaned: str,
    api_prompt_lang: str,
    api_text_lang: str,
    voice_id: str,
    aux_ref_audio_paths: list,
    official_get_tts_wav_api,
    debug_id: str = None,
):
    if not segments:
        raise ValueError("segments is empty")

    sync_data = dict(data or {})
    sync_data["buffer_segments"] = len(segments)
    if not sync_data.get("_adaptive_text"):
        sync_data["_adaptive_text"] = "\n".join([str(s).strip() for s in (segments or []) if str(s).strip()])
    task_id, ready_urls, total = _create_buffer_task(
        segments=segments,
        data=sync_data,
        ref_audio_path=ref_audio_path,
        ref_text_cleaned=ref_text_cleaned,
        api_prompt_lang=api_prompt_lang,
        api_text_lang=api_text_lang,
        voice_id=voice_id,
        aux_ref_audio_paths=aux_ref_audio_paths,
        official_get_tts_wav_api=official_get_tts_wav_api,
        debug_id=debug_id,
    )

    merged_url = _merge_wav_segments_to_static(task_id)
    if not merged_url and total > 0 and len(ready_urls) >= total:
        in_paths = [_static_url_to_path(u) for u in ready_urls[:total]]
        if all((pp and os.path.exists(pp)) for pp in in_paths):
            tts_dir = _resolve_tts_static_dir()
            fname = f"merged_sync_{task_id}_{voice_id or 'default'}.wav"
            out_path = os.path.join(tts_dir, fname)
            _merge_wav_files(in_paths, out_path)
            try:
                with open(out_path, "rb") as mf:
                    merged_raw = mf.read()
                sync_user_voice = bool(
                    sync_data.get("_is_user_trained_voice")
                    or (voice_id and (voice_id not in QWEN_BASE_VOICE_IDS))
                )
                merged_processed, merge_meta = _postprocess_playable_wav_for_text(
                    str(sync_data.get("_adaptive_text") or "").strip(),
                    merged_raw,
                    speed=float(sync_data.get("speed", 1.0) or 1.0),
                    over_tolerance=1.23,
                    apply_duration_trim=sync_user_voice,
                    is_user_trained_voice=sync_user_voice,
                    context="segmented_sync_fallback",
                )
                if merged_processed and (merged_processed != merged_raw):
                    with open(out_path, "wb") as mf:
                        mf.write(merged_processed)
                if isinstance(merge_meta, dict) and merge_meta.get("changed"):
                    logger.info(
                        f"[segmented_sync] merged 后处理已应用: task_id={task_id}, voice_id={voice_id}, "
                        f"silence_trim={merge_meta.get('silence_trim_applied')}, "
                        f"boost={merge_meta.get('boost_applied') or merge_meta.get('boost2_applied')}, "
                        f"duration_trim={merge_meta.get('duration_trim_applied')}"
                    )
            except Exception as e:
                logger.warning(f"[segmented_sync] merged 后处理失败，保留原音频: task_id={task_id}, err={e}")
            merged_url = f"/static/tts/{fname}"

    if not merged_url:
        raise RuntimeError("segmented sync merge failed")

    merged_path = _static_url_to_path(merged_url)
    if (not merged_path) or (not os.path.exists(merged_path)):
        raise RuntimeError(f"merged wav missing: {merged_url}")

    with open(merged_path, "rb") as f:
        merged_bytes = f.read()
    if not merged_bytes:
        raise RuntimeError("merged wav empty")

    return merged_bytes, task_id, merged_url, total


def detect_text_language(s: str) -> str:
    """
    简单语言检测：如果包含中文字符，优先按中文；否则按英文。
    返回值是 inference_webui 中 dict_language 的 key：'Chinese' 或 'English'。
    与 simple_inference.py 完全一致
    """
    if not s:
        return "Chinese"
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", s))
    if has_cjk:
        return "Chinese"
    # 没有中文，默认走英文前端
    return "English"


def get_phones_and_bert(text, language, version, final=False):
    text = re.sub(r' {2,}', ' ', text)
    textlist = []
    langlist = []
    if language == "all_zh":
        for tmp in LangSegmenter.getTexts(text,"zh"):
            langlist.append(tmp["lang"])
            textlist.append(tmp["text"])
    elif language == "all_yue":
        for tmp in LangSegmenter.getTexts(text,"zh"):
            if tmp["lang"] == "zh":
                tmp["lang"] = "yue"
            langlist.append(tmp["lang"])
            textlist.append(tmp["text"])
    elif language == "all_ja":
        for tmp in LangSegmenter.getTexts(text,"ja"):
            langlist.append(tmp["lang"])
            textlist.append(tmp["text"])
    elif language == "all_ko":
        for tmp in LangSegmenter.getTexts(text,"ko"):
            langlist.append(tmp["lang"])
            textlist.append(tmp["text"])
    elif language == "en":
        langlist.append("en")
        textlist.append(text)
    elif language == "auto":
        for tmp in LangSegmenter.getTexts(text):
            langlist.append(tmp["lang"])
            textlist.append(tmp["text"])
    elif language == "auto_yue":
        for tmp in LangSegmenter.getTexts(text):
            if tmp["lang"] == "zh":
                tmp["lang"] = "yue"
            langlist.append(tmp["lang"])
            textlist.append(tmp["text"])
    else:
        for tmp in LangSegmenter.getTexts(text):
            if langlist:
                if (tmp["lang"] == "en" and langlist[-1] == "en") or (tmp["lang"] != "en" and langlist[-1] != "en"):
                    textlist[-1] += tmp["text"]
                    continue
            if tmp["lang"] == "en":
                langlist.append(tmp["lang"])
            else:
                # 因无法区别中日韩文汉字,以用户输入为准
                langlist.append(language)
            textlist.append(tmp["text"])
    phones_list = []
    bert_list = []
    norm_text_list = []
    for i in range(len(textlist)):
        lang = langlist[i]
        phones, word2ph, norm_text = clean_text_inf(textlist[i], lang, version)
        bert = get_bert_inf(phones, word2ph, norm_text, lang)
        phones_list.append(phones)
        norm_text_list.append(norm_text)
        bert_list.append(bert)
    bert = torch.cat(bert_list, dim=1)
    phones = sum(phones_list, [])
    norm_text = "".join(norm_text_list)

def resolve_requested_text_language(requested_language: str, cleaned_text: str) -> str:
    """优先尊重前端指定语言，避免短文本自动检测误判。"""
    lang = str(requested_language or "").strip().lower()

    if lang in {"zh", "zh-cn", "zh_cn", "中文", "chinese", "all_zh"}:
        return "Chinese"
    if lang in {"en", "en-us", "en_us", "英文", "english"}:
        return "English"
    if lang in {"ja", "jp", "日文", "japanese", "all_ja"}:
        return "Japanese"
    if lang in {"ko", "韩文", "korean", "all_ko"}:
        return "Korean"
    if lang in {"auto", "", "mix", "multi"}:
        return detect_text_language(cleaned_text)

    return detect_text_language(cleaned_text)


    if not final and len(phones) < 6:
        return get_phones_and_bert("." + text, language, version, final=True)

    return phones, bert.to(torch.float16 if is_half == True else torch.float32), norm_text


class DictToAttrRecursive(dict):
    def __init__(self, input_dict):
        super().__init__(input_dict)
        for key, value in input_dict.items():
            if isinstance(value, dict):
                value = DictToAttrRecursive(value)
            self[key] = value
            setattr(self, key, value)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(f"Attribute {item} not found")

    def __setattr__(self, key, value):
        if isinstance(value, dict):
            value = DictToAttrRecursive(value)
        super(DictToAttrRecursive, self).__setitem__(key, value)
        super().__setattr__(key, value)

    def __delattr__(self, item):
        try:
            del self[item]
        except KeyError:
            raise AttributeError(f"Attribute {item} not found")


def get_spepc(hps, filename, dtype, device, is_v2pro=False):
    sr1 = int(hps.data.sampling_rate)
    if torchaudio is not None:
        audio, sr0 = torchaudio.load(filename)
    else:
        # librosa: 返回 shape (n,) 或 (n, ch)；这里统一成 (1, n)
        y, sr0 = librosa.load(filename, sr=None, mono=True)
        audio = torch.from_numpy(y).unsqueeze(0)
    if sr0 != sr1:
        audio = audio.to(device)
        if audio.shape[0] == 2:
            audio = audio.mean(0).unsqueeze(0)
        audio = resample(audio, sr0, sr1, device)
    else:
        audio = audio.to(device)
        if audio.shape[0] == 2:
            audio = audio.mean(0).unsqueeze(0)

    maxx = audio.abs().max()
    if maxx > 1:
        audio /= min(2, maxx)
    spec = spectrogram_torch(
        audio,
        hps.data.filter_length,
        hps.data.sampling_rate,
        hps.data.hop_length,
        hps.data.win_length,
        center=False,
    )
    spec = spec.to(dtype)
    if is_v2pro == True:
        audio = resample(audio, sr1, 16000, device).to(dtype)
    return spec, audio


def pack_audio(audio_bytes, data, rate):
    if media_type == "ogg":
        audio_bytes = pack_ogg(audio_bytes, data, rate)
    elif media_type == "aac":
        audio_bytes = pack_aac(audio_bytes, data, rate)
    else:
        # wav无法流式, 先暂存raw
        audio_bytes = pack_raw(audio_bytes, data, rate)

    return audio_bytes


def pack_ogg(audio_bytes, data, rate):
    # Author: AkagawaTsurunaki
    # Issue:
    #   Stack overflow probabilistically occurs
    #   when the function `sf_writef_short` of `libsndfile_64bit.dll` is called
    #   using the Python library `soundfile`
    # Note:
    #   This is an issue related to `libsndfile`, not this project itself.
    #   It happens when you generate a large audio tensor (about 499804 frames in my PC)
    #   and try to convert it to an ogg file.
    # Related:
    #   https://github.com/RVC-Boss/GPT-SoVITS/issues/1199
    #   https://github.com/libsndfile/libsndfile/issues/1023
    #   https://github.com/bastibe/python-soundfile/issues/396
    # Suggestion:
    #   Or split the whole audio data into smaller audio segment to avoid stack overflow?

    def handle_pack_ogg():
        with sf.SoundFile(audio_bytes, mode="w", samplerate=rate, channels=1, format="ogg") as audio_file:
            audio_file.write(data)


    # See: https://docs.python.org/3/library/threading.html
    # The stack size of this thread is at least 32768
    # If stack overflow error still occurs, just modify the `stack_size`.
    # stack_size = n * 4096, where n should be a positive integer.
    # Here we chose n = 4096.
    stack_size = 4096 * 4096
    try:
        threading.stack_size(stack_size)
        pack_ogg_thread = threading.Thread(target=handle_pack_ogg)
        pack_ogg_thread.start()
        pack_ogg_thread.join()
    except RuntimeError as e:
        # If changing the thread stack size is unsupported, a RuntimeError is raised.
        print("RuntimeError: {}".format(e))
        print("Changing the thread stack size is unsupported.")
    except ValueError as e:
        # If the specified stack size is invalid, a ValueError is raised and the stack size is unmodified.
        print("ValueError: {}".format(e))
        print("The specified stack size is invalid.")

    return audio_bytes


def pack_raw(audio_bytes, data, rate):
    audio_bytes.write(data.tobytes())

    return audio_bytes


def pack_wav(audio_bytes, rate):
    if is_int32:
        data = np.frombuffer(audio_bytes.getvalue(), dtype=np.int32)
        wav_bytes = BytesIO()
        sf.write(wav_bytes, data, rate, format="WAV", subtype="PCM_32")
    else:
        data = np.frombuffer(audio_bytes.getvalue(), dtype=np.int16)
        wav_bytes = BytesIO()
        sf.write(wav_bytes, data, rate, format="WAV")
    return wav_bytes


def pack_aac(audio_bytes, data, rate):
    if is_int32:
        pcm = "s32le"
        bit_rate = "256k"
    else:
        pcm = "s16le"
        bit_rate = "128k"
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-f",
            pcm,  # 输入16位有符号小端整数PCM
            "-ar",
            str(rate),  # 设置采样率
            "-ac",
            "1",  # 单声道
            "-i",
            "pipe:0",  # 从管道读取输入
            "-c:a",
            "aac",  # 音频编码器为AAC
            "-b:a",
            bit_rate,  # 比特率
            "-vn",  # 不包含视频
            "-f",
            "adts",  # 输出AAC数据流格式
            "pipe:1",  # 将输出写入管道
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, _ = process.communicate(input=data.tobytes())
    audio_bytes.write(out)

    return audio_bytes


def read_clean_buffer(audio_bytes):
    audio_chunk = audio_bytes.getvalue()
    audio_bytes.truncate(0)
    audio_bytes.seek(0)

    return audio_bytes, audio_chunk


def cut_text(text, punc):
    punc_list = [p for p in punc if p in {",", ".", ";", "?", "!", "、", "，", "。", "？", "！", "；", "：", "…"}]
    if len(punc_list) > 0:
        punds = r"[" + "".join(punc_list) + r"]"
        text = text.strip("\n")
        items = re.split(f"({punds})", text)
        mergeitems = ["".join(group) for group in zip(items[::2], items[1::2])]
        # 在句子不存在符号或句尾无符号的时候保证文本完整
        if len(items) % 2 == 1:
            mergeitems.append(items[-1])
        text = "\n".join(mergeitems)

    while "\n\n" in text:
        text = text.replace("\n\n", "\n")

    return text


def only_punc(text):
    return not any(t.isalnum() or t.isalpha() for t in text)


def split(todo_text):
    """按照标点符号切分文本，返回句子列表（包含标点）"""
    todo_text = todo_text.replace("……", "。").replace("——", "，")
    if todo_text[-1] not in splits:
        todo_text += "。"
    i_split_head = i_split_tail = 0
    len_text = len(todo_text)
    todo_texts = []
    while 1:
        if i_split_head >= len_text:
            break  # 结尾一定有标点，所以直接跳出即可，最后一段在上次已加入
        if todo_text[i_split_head] in splits:
            i_split_head += 1
            todo_texts.append(todo_text[i_split_tail:i_split_head])
            i_split_tail = i_split_head
        else:
            i_split_head += 1
    return todo_texts


def cut1(inp):
    """凑四句一切：每4个句子切一次"""
    inp = inp.strip("\n")
    inps = split(inp)
    split_idx = list(range(0, len(inps), 4))
    split_idx[-1] = None
    if len(split_idx) > 1:
        opts = []
        for idx in range(len(split_idx) - 1):
            opts.append("".join(inps[split_idx[idx] : split_idx[idx + 1]]))
    else:
        opts = [inp]
    opts = [item for item in opts if not set(item).issubset(punctuation)]
    return "\n".join(opts)


def cut2(inp):
    """凑50字一切：每50个字切一次"""
    inp = inp.strip("\n")
    inps = split(inp)
    if len(inps) < 2:
        return inp
    opts = []
    summ = 0
    tmp_str = ""
    for i in range(len(inps)):
        summ += len(inps[i])
        tmp_str += inps[i]
        if summ > 50:
            summ = 0
            opts.append(tmp_str)
            tmp_str = ""
    if tmp_str != "":
        opts.append(tmp_str)
    # 如果最后一个太短了，和前一个合一起
    if len(opts) > 1 and len(opts[-1]) < 50:
        opts[-2] = opts[-2] + opts[-1]
        opts = opts[:-1]
    opts = [item for item in opts if not set(item).issubset(punctuation)]
    return "\n".join(opts)


def process_text(texts):
    """处理文本列表，过滤空文本"""
    _text = []
    if all(text in [None, " ", "\n", ""] for text in texts):
        raise ValueError("请输入有效文本")
    for text in texts:
        if text in [None, " ", ""]:
            pass
        else:
            _text.append(text)
    return _text


def merge_short_text_in_array(texts, threshold):
    """合并短文本，如果文本长度小于阈值，则与前一个合并"""
    if (len(texts)) < 2:
        return texts
    result = []
    text = ""
    for ele in texts:
        text += ele
        if len(text) >= threshold:
            result.append(text)
            text = ""
    if len(text) > 0:
        if len(result) == 0:
            result.append(text)
        else:
            result[len(result) - 1] += text
    return result


splits = {
    "，",
    "。",
    "？",
    "！",
    ",",
    ".",
    "?",
    "!",
    "~",
    ":",
    "：",
    "—",
    "…",
}

punctuation = set(["!", "?", "…", ",", ".", "-", " "])


# ==================== 推理相关函数（已删除旧实现，统一使用官方 get_tts_wav）====================
# 旧的 get_tts_wav 和 handle 函数已删除，统一使用官方的 get_tts_wav
# 所有推理接口都直接调用 GPT_SoVITS.inference_webui.get_tts_wav（与测试脚本 simple_inference.py 一致）

def handle_control(command):
    if command == "restart":
        os.execl(g_config.python_exec, g_config.python_exec, *sys.argv)
    elif command == "exit":
        os.kill(os.getpid(), signal.SIGTERM)
        exit(0)


def handle_change(path, text, language):
    if is_empty(path, text, language):
        return JSONResponse(
            {"code": 400, "message": '缺少任意一项以下参数: "path", "text", "language"'}, status_code=400
        )

    if path != "" or path is not None:
        default_refer.path = path
    if text != "" or text is not None:
        default_refer.text = text
    if language != "" or language is not None:
        default_refer.language = language

    logger.info(f"当前默认参考音频路径: {default_refer.path}")
    logger.info(f"当前默认参考音频文本: {default_refer.text}")
    logger.info(f"当前默认参考音频语种: {default_refer.language}")
    logger.info(f"is_ready: {default_refer.is_ready()}")

    return JSONResponse({"code": 0, "message": "Success"}, status_code=200)


def handle_control(command):
    if command == "restart":
        os.execl(g_config.python_exec, g_config.python_exec, *sys.argv)
    elif command == "exit":
        os.kill(os.getpid(), signal.SIGTERM)
        exit(0)


def handle_change(path, text, language):
    if is_empty(path, text, language):
        return JSONResponse(
            {"code": 400, "message": '缺少任意一项以下参数: "path", "text", "language"'}, status_code=400
        )

    if path != "" or path is not None:
        default_refer.path = path
    if text != "" or text is not None:
        default_refer.text = text
    if language != "" or language is not None:
        default_refer.language = language

    logger.info(f"当前默认参考音频路径: {default_refer.path}")
    logger.info(f"当前默认参考音频文本: {default_refer.text}")
    logger.info(f"当前默认参考音频语种: {default_refer.language}")
    logger.info(f"is_ready: {default_refer.is_ready()}")

    return JSONResponse({"code": 0, "message": "Success"}, status_code=200)


# handle 函数已删除，统一使用官方的 get_tts_wav
# 所有推理接口都直接调用 GPT_SoVITS.inference_webui.get_tts_wav（与测试脚本 simple_inference.py 一致）
    

import subprocess
import os

# 音频切分工具函数
def split_audio_to_segments(audio_path: str, segment_duration: float = 7.5, output_dir: str = None) -> list:
    """
    将音频切分为固定时长的片段（7~8秒）
    
    Args:
        audio_path: 输入音频路径
        segment_duration: 每个片段的时长（秒），默认7.5秒
        output_dir: 输出目录，如果为None则使用输入文件所在目录
    
    Returns:
        返回切分后的音频片段列表，每个元素包含：
        {
            "path": 音频文件路径,
            "start_time": 开始时间（秒）,
            "end_time": 结束时间（秒）,
            "duration": 时长（秒）
        }
    """
    try:
        import librosa
        import soundfile as sf
    except ImportError:
        logger.error("[split_audio_to_segments] 需要安装 librosa 和 soundfile")
        return []
    
    try:
        # 加载音频
        audio, sr = librosa.load(audio_path, sr=16000, mono=True)
        total_duration = len(audio) / sr
        
        logger.info(f"[split_audio_to_segments] 音频总时长: {total_duration:.2f}秒, 采样率: {sr}Hz")
        
        # 如果音频时长小于等于segment_duration，直接返回原音频
        if total_duration <= segment_duration:
            logger.info(f"[split_audio_to_segments] 音频时长小于等于{segment_duration}秒，无需切分")
            return [{
                "path": audio_path,
                "start_time": 0.0,
                "end_time": total_duration,
                "duration": total_duration
            }]
        
        # 设置输出目录
        if output_dir is None:
            output_dir = os.path.dirname(audio_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成输出文件名前缀
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        
        segments = []
        num_segments = int(np.ceil(total_duration / segment_duration))
        
        logger.info(f"[split_audio_to_segments] 将切分为 {num_segments} 个片段")
        
        for i in range(num_segments):
            start_time = i * segment_duration
            end_time = min((i + 1) * segment_duration, total_duration)
            
            # 计算采样点
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            
            # 提取音频片段
            segment_audio = audio[start_sample:end_sample]
            actual_duration = len(segment_audio) / sr
            
            # 生成输出文件名
            segment_filename = f"{base_name}_seg_{i+1:03d}.wav"
            segment_path = os.path.join(output_dir, segment_filename)
            
            # 保存音频片段
            sf.write(segment_path, segment_audio, sr)
            
            segments.append({
                "path": segment_path,
                "start_time": start_time,
                "end_time": end_time,
                "duration": actual_duration
            })
            
            logger.info(f"[split_audio_to_segments] 片段 {i+1}/{num_segments}: {start_time:.2f}s - {end_time:.2f}s ({actual_duration:.2f}s)")
        
        logger.info(f"[split_audio_to_segments] 切分完成，共 {len(segments)} 个片段")
        return segments
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"[split_audio_to_segments] 切分失败: {str(e)}\n{error_detail}")
        return []


def split_text_by_time_ratio(full_text: str, segments: list, total_duration: float) -> list:
    """
    根据音频切分的时间比例，切分对应的文本
    
    Args:
        full_text: 完整文本
        segments: 音频片段列表（包含start_time和end_time）
        total_duration: 音频总时长
    
    Returns:
        返回切分后的文本列表，与segments一一对应
    """
    if not full_text or not segments or total_duration <= 0:
        return [full_text] * len(segments) if segments else []
    
    try:
        text_segments = []
        text_length = len(full_text)
        
        for segment in segments:
            # 计算该片段在总时长中的比例
            start_ratio = segment["start_time"] / total_duration
            end_ratio = segment["end_time"] / total_duration
            
            # 根据比例切分文本
            start_char = int(start_ratio * text_length)
            end_char = int(end_ratio * text_length)
            
            # 确保不越界
            start_char = max(0, min(start_char, text_length))
            end_char = max(start_char, min(end_char, text_length))
            
            segment_text = full_text[start_char:end_char].strip()
            
            # 如果文本为空，使用完整文本
            if not segment_text:
                segment_text = full_text
            
            text_segments.append(segment_text)
        
        return text_segments
        
    except Exception as e:
        logger.error(f"[split_text_by_time_ratio] 文本切分失败: {str(e)}")
        # 如果切分失败，每个片段都使用完整文本
        return [full_text] * len(segments) if segments else []


# 音频切分工具函数
def split_audio_to_segments(audio_path: str, segment_duration: float = 7.5, output_dir: str = None) -> list:
    """
    将音频切分为固定时长的片段（7~8秒）
    
    Args:
        audio_path: 输入音频路径
        segment_duration: 每个片段的时长（秒），默认7.5秒
        output_dir: 输出目录，如果为None则使用输入文件所在目录
    
    Returns:
        返回切分后的音频片段列表，每个元素包含：
        {
            "path": 音频文件路径,
            "start_time": 开始时间（秒）,
            "end_time": 结束时间（秒）,
            "duration": 时长（秒）
        }
    """
    try:
        import librosa
        import soundfile as sf
    except ImportError:
        logger.error("[split_audio_to_segments] 需要安装 librosa 和 soundfile")
        return []
    
    try:
        # 加载音频
        audio, sr = librosa.load(audio_path, sr=16000, mono=True)
        total_duration = len(audio) / sr
        
        logger.info(f"[split_audio_to_segments] 音频总时长: {total_duration:.2f}秒, 采样率: {sr}Hz")
        
        # 如果音频时长小于等于segment_duration，直接返回原音频
        if total_duration <= segment_duration:
            logger.info(f"[split_audio_to_segments] 音频时长小于等于{segment_duration}秒，无需切分")
            return [{
                "path": audio_path,
                "start_time": 0.0,
                "end_time": total_duration,
                "duration": total_duration
            }]
        
        # 设置输出目录
        if output_dir is None:
            output_dir = os.path.dirname(audio_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成输出文件名前缀
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        
        segments = []
        num_segments = int(np.ceil(total_duration / segment_duration))
        
        logger.info(f"[split_audio_to_segments] 将切分为 {num_segments} 个片段")
        
        for i in range(num_segments):
            start_time = i * segment_duration
            end_time = min((i + 1) * segment_duration, total_duration)
            
            # 计算采样点
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            
            # 提取音频片段
            segment_audio = audio[start_sample:end_sample]
            actual_duration = len(segment_audio) / sr
            
            # 生成输出文件名
            segment_filename = f"{base_name}_seg_{i+1:03d}.wav"
            segment_path = os.path.join(output_dir, segment_filename)
            
            # 保存音频片段
            sf.write(segment_path, segment_audio, sr)
            
            segments.append({
                "path": segment_path,
                "start_time": start_time,
                "end_time": end_time,
                "duration": actual_duration
            })
            
            logger.info(f"[split_audio_to_segments] 片段 {i+1}/{num_segments}: {start_time:.2f}s - {end_time:.2f}s ({actual_duration:.2f}s)")
        
        logger.info(f"[split_audio_to_segments] 切分完成，共 {len(segments)} 个片段")
        return segments
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"[split_audio_to_segments] 切分失败: {str(e)}\n{error_detail}")
        return []


def split_text_by_time_ratio(full_text: str, segments: list, total_duration: float) -> list:
    """
    根据音频切分的时间比例，切分对应的文本
    
    Args:
        full_text: 完整文本
        segments: 音频片段列表（包含start_time和end_time）
        total_duration: 音频总时长
    
    Returns:
        返回切分后的文本列表，与segments一一对应
    """
    if not full_text or not segments or total_duration <= 0:
        return [full_text] * len(segments) if segments else []
    
    try:
        text_segments = []
        text_length = len(full_text)
        
        for segment in segments:
            # 计算该片段在总时长中的比例
            start_ratio = segment["start_time"] / total_duration
            end_ratio = segment["end_time"] / total_duration
            
            # 根据比例切分文本
            start_char = int(start_ratio * text_length)
            end_char = int(end_ratio * text_length)
            
            # 确保不越界
            start_char = max(0, min(start_char, text_length))
            end_char = max(start_char, min(end_char, text_length))
            
            segment_text = full_text[start_char:end_char].strip()
            
            # 如果文本为空，使用完整文本
            if not segment_text:
                segment_text = full_text
            
            text_segments.append(segment_text)
        
        return text_segments
        
    except Exception as e:
        logger.error(f"[split_text_by_time_ratio] 文本切分失败: {str(e)}")
        # 如果切分失败，每个片段都使用完整文本
        return [full_text] * len(segments) if segments else []


# 测试ffmpeg是否正常工作
def test_ffmpeg_installation() -> dict:
    """
    测试ffmpeg是否安装并能正常工作
    返回测试结果字典，包含是否成功、版本信息、错误信息等
    """
    result = {
        "installed": False,
        "working": False,
        "version": None,
        "error": None,
        "test_convert": False,
        "test_convert_error": None
    }
    
    try:
        # 1. 检查ffmpeg是否在PATH中
        import shutil
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            result["error"] = "ffmpeg未在PATH中找到，请确保已安装ffmpeg"
            logger.error("[test_ffmpeg] " + result["error"])
            return result
        
        result["installed"] = True
        logger.info(f"[test_ffmpeg] ffmpeg路径: {ffmpeg_path}")
        
        # 2. 获取ffmpeg版本信息
        try:
            import subprocess
            import platform
            use_shell = platform.system() == "Windows"
            version_result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=use_shell
            )
            if version_result.returncode == 0:
                # 提取版本号（第一行）
                # ffmpeg在不同系统上可能将版本信息输出到stdout或stderr
                version_output = version_result.stdout if version_result.stdout else version_result.stderr
                if version_output:
                    version_lines = version_output.split('\n')
                    if version_lines:
                        result["version"] = version_lines[0].strip()
                        logger.info(f"[test_ffmpeg] ffmpeg版本: {result['version']}")
            else:
                result["error"] = f"无法获取ffmpeg版本信息，返回码: {version_result.returncode}"
                logger.warning("[test_ffmpeg] " + result["error"])
        except subprocess.TimeoutExpired:
            result["error"] = "获取ffmpeg版本信息超时"
            logger.error("[test_ffmpeg] " + result["error"])
            return result
        except Exception as e:
            result["error"] = f"获取ffmpeg版本信息失败: {str(e)}"
            logger.error("[test_ffmpeg] " + result["error"])
            return result
        
        # 3. 测试音频转换功能（创建一个简单的测试音频）
        try:
            import tempfile
            import os
            
            # 创建临时测试文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as test_input:
                test_input_path = test_input.name
                # 创建一个简单的WAV文件头（1秒静音，16kHz，单声道）
                # WAV文件头（44字节）+ 32000字节数据（16000采样率 * 2字节/采样 * 1秒）
                wav_header = (
                    b'RIFF' + (32044).to_bytes(4, 'little') + b'WAVE' +
                    b'fmt ' + (16).to_bytes(4, 'little') +  # fmt chunk size
                    (1).to_bytes(2, 'little') +  # audio format (PCM)
                    (1).to_bytes(2, 'little') +  # channels (mono)
                    (16000).to_bytes(4, 'little') +  # sample rate
                    (32000).to_bytes(4, 'little') +  # byte rate
                    (2).to_bytes(2, 'little') +  # block align
                    (16).to_bytes(2, 'little') +  # bits per sample
                    b'data' + (32000).to_bytes(4, 'little')  # data chunk size
                )
                test_input.write(wav_header)
                test_input.write(b'\x00' * 32000)  # 静音数据
                test_input.flush()
            
            # 创建临时输出文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as test_output:
                test_output_path = test_output.name
            
            # 测试转换
            test_success = convert_to_wav(test_input_path, test_output_path)
            
            # 清理测试文件
            try:
                if os.path.exists(test_input_path):
                    os.remove(test_input_path)
                if os.path.exists(test_output_path):
                    os.remove(test_output_path)
            except:
                pass
            
            if test_success:
                result["test_convert"] = True
                result["working"] = True
                logger.info("[test_ffmpeg] 音频转换测试成功")
            else:
                result["test_convert_error"] = "音频转换测试失败"
                logger.error("[test_ffmpeg] " + result["test_convert_error"])
                
        except Exception as e:
            result["test_convert_error"] = f"音频转换测试异常: {str(e)}"
            logger.error("[test_ffmpeg] " + result["test_convert_error"])
            import traceback
            logger.error(traceback.format_exc())
        
        if result["working"]:
            logger.info("[test_ffmpeg] ✓ ffmpeg测试通过，可以正常使用")
        else:
            logger.warning("[test_ffmpeg] ✗ ffmpeg测试未完全通过")
            
    except Exception as e:
        result["error"] = f"测试过程异常: {str(e)}"
        logger.error("[test_ffmpeg] " + result["error"])
        import traceback
        logger.error(traceback.format_exc())
    
    return result


# 音频转码工具函数（必须在wx_upload_audio接口前定义）
def convert_to_wav(input_path: str, output_path: str) -> bool:
    """
    音频转码为WAV（16kHz，单声道），返回转码是否成功
    包含完整的调试信息和错误处理
    """
    try:
        # 转换为绝对路径，避免相对路径问题
        input_path = os.path.abspath(input_path)
        output_path = os.path.abspath(output_path)
        
        # 检查输入文件是否存在
        if not os.path.exists(input_path):
            logger.error(f"[convert_to_wav] 输入文件不存在: {input_path}")
            print(f"[convert_to_wav] 输入文件不存在: {input_path}")
            return False
        
        input_size = os.path.getsize(input_path)
        logger.info(f"[convert_to_wav] 开始转码: {input_path} (大小: {input_size} 字节) -> {output_path}")
        print(f"[convert_to_wav] 开始转码: {input_path} (大小: {input_size} 字节) -> {output_path}")
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建ffmpeg命令
        # 使用-f wav明确指定输出格式，避免格式识别问题
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",                  # 覆盖已有输出文件
            "-i", input_path,      # 输入文件路径
            "-f", "wav",           # 明确指定输出格式为WAV
            "-acodec", "pcm_s16le",# 编码格式：16bit PCM
            "-ar", "16000",        # 采样率：16kHz（模型推荐）
            "-ac", "1",            # 单声道
            output_path            # 输出文件路径
        ]
        
        logger.info(f"[convert_to_wav] 执行命令: {' '.join(ffmpeg_cmd)}")
        print(f"[convert_to_wav] 执行命令: {' '.join(ffmpeg_cmd)}")
        
        # 执行ffmpeg转码
        # Linux环境不需要shell=True，Windows需要
        import platform
        use_shell = platform.system() == "Windows"
        
        try:
            result = subprocess.run(
                ffmpeg_cmd,
                check=False,  # 不抛出异常，手动检查返回码
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=use_shell,
                timeout=30  # 30秒超时
            )
        except subprocess.TimeoutExpired:
            logger.error(f"[convert_to_wav] ffmpeg执行超时（30秒）")
            print(f"[convert_to_wav] ffmpeg执行超时（30秒）")
            return False
        
        logger.info(f"[convert_to_wav] ffmpeg返回码: {result.returncode}")
        print(f"[convert_to_wav] ffmpeg返回码: {result.returncode}")
        
        # ffmpeg会将信息输出到stderr，即使成功也会输出，所以主要看返回码
        stderr_output = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
        stdout_output = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
        
        # 检查ffmpeg是否执行成功（返回码0表示成功）
        if result.returncode != 0:
            # 提取真正的错误信息（排除版本信息等）
            error_lines = [line for line in stderr_output.split('\n') 
                          if line and 'error' in line.lower() and 'version' not in line.lower()]
            error_msg = '\n'.join(error_lines) if error_lines else stderr_output[-500:]  # 取最后500字符
            logger.error(f"[convert_to_wav] ffmpeg执行失败 (返回码: {result.returncode})")
            logger.error(f"[convert_to_wav] 错误信息: {error_msg}")
            print(f"[convert_to_wav] ffmpeg执行失败 (返回码: {result.returncode})")
            print(f"[convert_to_wav] 错误信息: {error_msg}")
            return False
        
        # 即使返回码为0，也检查输出文件是否存在
        # 因为某些情况下ffmpeg可能返回0但文件未生成
        
        # 等待一小段时间，确保文件写入完成
        time.sleep(0.1)
        
        # 检查输出文件是否生成
        if not os.path.exists(output_path):
            logger.error(f"[convert_to_wav] 输出文件未生成: {output_path}")
            logger.error(f"[convert_to_wav] stderr输出（最后500字符）: {stderr_output[-500:]}")
            print(f"[convert_to_wav] 输出文件未生成: {output_path}")
            return False
        
        output_size = os.path.getsize(output_path)
        if output_size == 0:
            logger.error(f"[convert_to_wav] 输出文件为空: {output_path}")
            print(f"[convert_to_wav] 输出文件为空: {output_path}")
            return False
        
        # 记录成功信息（只记录关键信息，不记录完整的stderr，因为ffmpeg会将信息输出到stderr）
        logger.info(f"[convert_to_wav] 转码成功! 输出文件: {output_path} (大小: {output_size} 字节)")
        print(f"[convert_to_wav] 转码成功! 输出文件: {output_path} (大小: {output_size} 字节)")
        return True
        
    except subprocess.TimeoutExpired as e:
        logger.error(f"[convert_to_wav] ffmpeg执行超时（30秒）")
        print(f"[convert_to_wav] ffmpeg执行超时（30秒）")
        return False
    except FileNotFoundError:
        logger.error(f"[convert_to_wav] ffmpeg未安装或不在PATH中")
        print(f"[convert_to_wav] ffmpeg未安装或不在PATH中")
        return False
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"[convert_to_wav] 其它异常: {str(e)}\n{error_detail}")
        print(f"[convert_to_wav] 其它异常: {str(e)}")
        return False

# --------------------------------
# 初始化部分
# --------------------------------
dict_language = {
    "中文": "all_zh",
    "粤语": "all_yue",
    "英文": "en",
    "日文": "all_ja",
    "韩文": "all_ko",
    "中英混合": "zh",
    "粤英混合": "yue",
    "日英混合": "ja",
    "韩英混合": "ko",
    "多语种混合": "auto",  # 多语种启动切分识别语种
    "多语种混合(粤语)": "auto_yue",
    "all_zh": "all_zh",
    "all_yue": "all_yue",
    "en": "en",
    "all_ja": "all_ja",
    "all_ko": "all_ko",
    "zh": "zh",
    "yue": "yue",
    "ja": "ja",
    "ko": "ko",
    "auto": "auto",
    "auto_yue": "auto_yue",
}

# logger
logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
logger = logging.getLogger("uvicorn")

# 初始化时尝试从文件加载，如果文件不存在则保存一次
if not os.path.exists(VOICE_LIBRARY_FILE):
    save_voice_library_to_file()
else:
    load_voice_library_from_file()

if _ensure_builtin_base_voices():
    save_voice_library_to_file()

# 启动时测试ffmpeg
logger.info("[启动] 开始测试ffmpeg安装和功能...")
ffmpeg_test_result = test_ffmpeg_installation()
if ffmpeg_test_result["working"]:
    logger.info("[启动] ✓ ffmpeg测试通过，可以正常使用")
else:
    logger.warning("[启动] ✗ ffmpeg测试未通过，音频转码功能可能无法使用")
    logger.warning(f"[启动] 错误信息: {ffmpeg_test_result.get('error') or ffmpeg_test_result.get('test_convert_error', '未知错误')}")

# 获取配置
g_config = global_config.Config()

# 获取参数
parser = argparse.ArgumentParser(description="GPT-SoVITS api")

parser.add_argument("-s", "--sovits_path", type=str, default=g_config.sovits_path, help="SoVITS模型路径")
parser.add_argument("-g", "--gpt_path", type=str, default=g_config.gpt_path, help="GPT模型路径")
parser.add_argument("-dr", "--default_refer_path", type=str, default="", help="默认参考音频路径")
parser.add_argument("-dt", "--default_refer_text", type=str, default="", help="默认参考音频文本")
parser.add_argument("-dl", "--default_refer_language", type=str, default="", help="默认参考音频语种")
parser.add_argument("-d", "--device", type=str, default=g_config.infer_device, help="cuda / cpu")
parser.add_argument("-a", "--bind_addr", type=str, default="0.0.0.0", help="default: 0.0.0.0")
parser.add_argument("-p", "--port", type=int, default=g_config.api_port, help="default: 9880")
parser.add_argument(
    "-fp", "--full_precision", action="store_true", default=False, help="覆盖config.is_half为False, 使用全精度"
)
parser.add_argument(
    "-hp", "--half_precision", action="store_true", default=False, help="覆盖config.is_half为True, 使用半精度"
)
# bool值的用法为 `python ./api.py -fp ...`
# 此时 full_precision==True, half_precision==False
parser.add_argument("-sm", "--stream_mode", type=str, default="close", help="流式返回模式, close / normal / keepalive")
parser.add_argument("-mt", "--media_type", type=str, default="wav", help="音频编码格式, wav / ogg / aac")
parser.add_argument("-st", "--sub_type", type=str, default="int16", help="音频数据类型, int16 / int32")
parser.add_argument("-cp", "--cut_punc", type=str, default="", help="文本切分符号设定, 符号范围,.;?!、，。？！；：…")
# 切割常用分句符为 `python ./api.py -cp ".?!。？！"`
parser.add_argument("-hb", "--hubert_path", type=str, default=g_config.cnhubert_path, help="覆盖config.cnhubert_path")
parser.add_argument("-b", "--bert_path", type=str, default=g_config.bert_path, help="覆盖config.bert_path")

args = parser.parse_args()
sovits_path = args.sovits_path
gpt_path = args.gpt_path
device = args.device
port = args.port
host = args.bind_addr
cnhubert_base_path = args.hubert_path
bert_path = args.bert_path
default_cut_punc = args.cut_punc

# 自动选择空闲GPU（如果指定了cuda但没有指定具体GPU）
# 注意：在设置了 CUDA_VISIBLE_DEVICES 后，进程内可见索引会重映射为 0..N-1。
if device == "cuda" and torch.cuda.is_available():
    import subprocess
    try:
        visible_count = int(torch.cuda.device_count() or 0)
        if visible_count <= 0:
            raise RuntimeError("torch.cuda.is_available()=True 但 device_count=0")
        # 使用nvidia-smi查找空闲GPU
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            free_gpus = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(', ')
                    if len(parts) >= 3:
                        gpu_idx = int(parts[0])
                        # 仅保留当前进程可见的逻辑索引，避免 physical index 越界
                        if gpu_idx < 0 or gpu_idx >= visible_count:
                            continue
                        mem_used = int(parts[1])
                        mem_total = int(parts[2])
                        mem_free = mem_total - mem_used
                        # 如果空闲内存大于2GB，认为可用
                        if mem_free > 2048:  # 2GB in MB
                            free_gpus.append((gpu_idx, mem_free))
            
            if free_gpus:
                # 选择空闲内存最多的GPU
                free_gpus.sort(key=lambda x: x[1], reverse=True)
                selected_gpu = free_gpus[0][0]
                device = f"cuda:{selected_gpu}"
                logger.info(f"自动选择GPU {selected_gpu} (空闲内存: {free_gpus[0][1]/1024:.2f}GB)")
            else:
                logger.warning("所有可见GPU空闲内存不足，尝试使用cuda:0")
                device = "cuda:0"
        else:
            logger.warning("无法查询GPU状态，使用cuda:0")
            device = "cuda:0"
    except Exception as e:
        logger.warning(f"GPU选择失败: {e}，使用cuda:0")
        device = "cuda:0"

# 应用参数配置
default_refer = DefaultRefer(args.default_refer_path, args.default_refer_text, args.default_refer_language)

# 模型路径检查与fallback
# 获取项目根目录（now_dir 已在前面定义，使用脚本所在目录更可靠）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 优先使用 now_dir（当前工作目录），如果路径解析失败则使用脚本目录
BASE_DIR = now_dir

# 将相对路径转换为绝对路径
def resolve_path(path):
    """解析路径，如果是相对路径则基于项目根目录"""
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path.replace('/', os.sep).replace('\\', os.sep))

if sovits_path == "":
    sovits_path = g_config.pretrained_sovits_path
    logger.warning(f"未指定SoVITS模型路径, fallback后当前值: {sovits_path}")
if gpt_path == "":
    gpt_path = g_config.pretrained_gpt_path
    logger.warning(f"未指定GPT模型路径, fallback后当前值: {gpt_path}")

# 解析路径为绝对路径
sovits_path = resolve_path(sovits_path)
gpt_path = resolve_path(gpt_path)

# 如果指定的模型路径不存在，尝试使用v2Pro预训练模型
if not os.path.exists(sovits_path):
    logger.warning(f"SoVITS模型路径不存在: {sovits_path}")
    # 尝试使用v2Pro预训练模型
    v2pro_sovits = resolve_path("GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth")
    if os.path.exists(v2pro_sovits):
        sovits_path = v2pro_sovits
        logger.info(f"使用v2Pro预训练SoVITS模型: {sovits_path}")
    else:
        logger.error(f"无法找到可用的SoVITS模型，请检查路径: {sovits_path} 或 {v2pro_sovits}")

if not os.path.exists(gpt_path):
    logger.warning(f"GPT模型路径不存在: {gpt_path}")
    # 尝试使用v2Pro预训练模型
    v2pro_gpt = resolve_path("GPT_SoVITS/pretrained_models/s1v3.ckpt")
    if os.path.exists(v2pro_gpt):
        gpt_path = v2pro_gpt
        logger.info(f"使用v2Pro预训练GPT模型: {gpt_path}")
    else:
        logger.error(f"无法找到可用的GPT模型，请检查路径: {gpt_path} 或 {v2pro_gpt}")

logger.info(f"[初始化] 最终使用的模型路径 - GPT: {gpt_path}, SoVITS: {sovits_path}")

# 指定默认参考音频, 调用方 未提供/未给全 参考音频参数时使用
if default_refer.path == "" or default_refer.text == "" or default_refer.language == "":
    default_refer.path, default_refer.text, default_refer.language = "", "", ""
    logger.info("未指定默认参考音频")
else:
    logger.info(f"默认参考音频路径: {default_refer.path}")
    logger.info(f"默认参考音频文本: {default_refer.text}")
    logger.info(f"默认参考音频语种: {default_refer.language}")

# 获取半精度
is_half = g_config.is_half
if args.full_precision:
    is_half = False
if args.half_precision:
    is_half = True
if args.full_precision and args.half_precision:
    is_half = g_config.is_half  # 炒饭fallback
logger.info(f"半精: {is_half}")

# 流式返回模式
if args.stream_mode.lower() in ["normal", "n"]:
    stream_mode = "normal"
    logger.info("流式返回已开启")
else:
    stream_mode = "close"

# 音频编码格式
if args.media_type.lower() in ["aac", "ogg"]:
    media_type = args.media_type.lower()
elif stream_mode == "close":
    media_type = "wav"
else:
    media_type = "ogg"
logger.info(f"编码格式: {media_type}")

# 音频数据类型
if args.sub_type.lower() == "int32":
    is_int32 = True
    logger.info("数据类型: int32")
else:
    is_int32 = False
    logger.info("数据类型: int16")

# 初始化模型
cnhubert.cnhubert_base_path = cnhubert_base_path

# 检查并加载BERT模型
try:
    logger.info(f"正在加载BERT模型: {bert_path}")
    if os.path.exists(bert_path):
        logger.info("使用本地BERT模型")
        tokenizer = AutoTokenizer.from_pretrained(bert_path, local_files_only=True)
        bert_model = AutoModelForMaskedLM.from_pretrained(bert_path, local_files_only=True)
    else:
        logger.warning(f"本地BERT路径不存在: {bert_path}，将尝试从HuggingFace下载")
        tokenizer = AutoTokenizer.from_pretrained(bert_path)
        bert_model = AutoModelForMaskedLM.from_pretrained(bert_path)
    logger.info("BERT模型加载成功")
except Exception as e:
    logger.error(f"BERT模型加载失败: {str(e)}")
    logger.error("请检查模型路径或网络连接")
    raise e

# 加载SSL模型
try:
    ssl_model = cnhubert.get_model()
    logger.info("SSL模型加载成功")
except Exception as e:
    logger.error(f"SSL模型加载失败: {str(e)}")
    raise e

# 设置模型精度和设备（带错误处理和自动切换GPU）
def load_models_to_device(bert_model, ssl_model, device, is_half):
    """加载模型到GPU；若GPU不可用则直接报错（不回退CPU）。"""
    max_retries = 3
    current_device = device
    
    # 清理GPU缓存
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    for attempt in range(max_retries):
        try:
            if is_half:
                bert_model = bert_model.half().to(current_device)
                ssl_model = ssl_model.half().to(current_device)
            else:
                bert_model = bert_model.to(current_device)
                ssl_model = ssl_model.to(current_device)
            logger.info(f"模型成功加载到设备: {current_device}")
            return bert_model, ssl_model, current_device
        except torch.cuda.OutOfMemoryError as e:
            logger.warning(f"设备 {current_device} 内存不足: {e}")
            if attempt < max_retries - 1:
                # 尝试切换到其他GPU
                if torch.cuda.is_available() and "cuda" in str(current_device):
                    import subprocess
                    try:
                        result = subprocess.run(
                            ['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=5
                        )
                        if result.returncode == 0:
                            free_gpus = []
                            for line in result.stdout.strip().split('\n'):
                                if line:
                                    parts = line.split(', ')
                                    if len(parts) >= 3:
                                        gpu_idx = int(parts[0])
                                        mem_used = int(parts[1])
                                        mem_total = int(parts[2])
                                        mem_free = mem_total - mem_used
                                        # 如果空闲内存大于4GB，认为可用
                                        if mem_free > 4096:  # 4GB in MB
                                            free_gpus.append((gpu_idx, mem_free))
                            
                            if free_gpus:
                                free_gpus.sort(key=lambda x: x[1], reverse=True)
                                selected_gpu = free_gpus[0][0]
                                current_device = f"cuda:{selected_gpu}"
                                logger.info(f"切换到GPU {selected_gpu} (空闲内存: {free_gpus[0][1]/1024:.2f}GB)")
                                # 清理之前的设备
                                torch.cuda.empty_cache()
                                continue
                    except:
                        pass
                
                # 如果无法切换GPU，继续下一次重试（保持GPU语义，不降级到CPU）
                logger.warning("无法切换到其他GPU，将继续重试当前/默认GPU")
                if str(current_device) == "cuda":
                    current_device = "cuda:0"
                continue
            else:
                # 最后一次仍失败：保持GPU要求并抛错，避免静默降级到CPU
                raise RuntimeError(f"所有可见GPU均内存不足，无法在GPU上加载模型（last_device={current_device}）") from e
        except Exception as e:
            err = str(e)
            # 常见场景：外部按物理卡号设置 CUDA_VISIBLE_DEVICES 后，
            # 进程内可见设备索引会被重映射，直接用 cuda:N 可能越界。
            if "invalid device ordinal" in err.lower():
                # 强制GPU：先改用可见逻辑索引0重试，不允许降级CPU
                logger.warning(f"设备索引无效({current_device})，改用 cuda:0 重试（不回退CPU）")
                if torch.cuda.is_available() and int(torch.cuda.device_count() or 0) > 0:
                    current_device = "cuda:0"
                    continue
                raise RuntimeError("未检测到可用CUDA设备，无法按GPU模式运行") from e
            logger.error(f"加载模型到设备失败: {e}")
            raise e
    
    return bert_model, ssl_model, current_device

bert_model, ssl_model, device = load_models_to_device(bert_model, ssl_model, device, is_half)

# 加载GPT-SoVITS权重
try:
    logger.info(f"[初始化] 开始加载默认模型 - GPT: {gpt_path}, SoVITS: {sovits_path}")
    
    # 再次验证文件是否存在
    if not os.path.exists(gpt_path):
        raise FileNotFoundError(f"GPT模型文件不存在: {gpt_path}")
    if not os.path.exists(sovits_path):
        raise FileNotFoundError(f"SoVITS模型文件不存在: {sovits_path}")
    
    # 调用加载函数（注意：change_gpt_sovits_weights返回JSONResponse，需要检查其内容）
    # 但这里我们直接调用内部逻辑，因为我们需要确保加载成功
    logger.info("[初始化] 正在加载GPT权重...")
    gpt = get_gpt_weights(gpt_path)
    logger.info("[初始化] GPT权重加载成功")
    
    logger.info("[初始化] 正在加载SoVITS权重...")
    sovits = get_sovits_weights(sovits_path)
    logger.info("[初始化] SoVITS权重加载成功")
    
    # 设置为默认说话人
    speaker_list["default"] = Speaker(name="default", gpt=gpt, sovits=sovits)
    
    # 验证是否成功创建
    if "default" not in speaker_list:
        raise RuntimeError("speaker_list中未找到'default'，模型加载可能失败")
    
    logger.info("[初始化] GPT-SoVITS模型权重加载成功，默认说话人已就绪")
    print("[初始化] ✅ 模型加载成功，推理功能已就绪")
    
except FileNotFoundError as e:
    logger.error(f"[初始化] 模型文件不存在: {str(e)}")
    logger.warning("[初始化] ⚠️ 服务将继续启动，但推理功能不可用。请通过 /set_model 接口手动加载模型。")
    print(f"[初始化] ⚠️ 模型文件不存在: {str(e)}")
except Exception as e:
    import traceback
    error_detail = traceback.format_exc()
    logger.error(f"[初始化] 模型权重加载失败: {str(e)}\n{error_detail}")
    logger.warning("[初始化] ⚠️ 服务将继续启动，但推理功能可能不可用。请稍后通过 /set_model 接口手动加载模型。")
    print(f"[初始化] ⚠️ 模型加载失败: {str(e)}")
    # 不直接raise，允许服务启动，但会在推理时提示用户先加载模型


# --------------------------------
# 接口部分
# --------------------------------
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# 提供静态资源服务（用于托管小程序中引用的大图片等，减小前端包体积）
# 兼容不同启动目录：统一使用与合成音频写入相同的静态根目录
static_dir = _resolve_static_root_dir()
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    images_dir = os.path.join(static_dir, "images")
    if os.path.isdir(images_dir):
        app.mount("/images", StaticFiles(directory=images_dir), name="images")

admin_static_dir = str(PROJECT_ROOT / "modules" / "user_mgmt_backend" / "static" / "admin")
if os.path.isdir(admin_static_dir):
    app.mount("/admin/static", StaticFiles(directory=admin_static_dir), name="admin_static")

# 统一资源根目录：你已将静态素材迁移到 assets/*
assets_dir = str(PROJECT_ROOT / "assets")
if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# 伴读/宠物 3D 等资源：与小程序 pets-catalog 中 /ar_companion/assets/<物种>/... 对齐
# 资源已统一迁移到 assets/animal
animal_dir = str(PROJECT_ROOT / "assets" / "animal")
if os.path.isdir(animal_dir):
    app.mount("/ar_companion/assets", StaticFiles(directory=animal_dir), name="ar_companion_assets")

# 练习/题库静态资源（speaker/跟读配图、coloring 静态图等）
practice_dir = str(PROJECT_ROOT / "assets" / "practice")
if os.path.isdir(practice_dir):
    # 例如：
    # - /practice_static/speaker_images_index.json
    # - /practice_static/speaker_images/q001.png
    app.mount("/practice_static", StaticFiles(directory=practice_dir), name="practice_static")

# 画图题库静态资源：paint_basement / paint_basement_generated（均在 assets 下）
paint_basement_dir = str(PROJECT_ROOT / "assets" / "paint_basement")
if os.path.isdir(paint_basement_dir):
    app.mount("/paint_basement_static", StaticFiles(directory=paint_basement_dir), name="paint_basement_static")

paint_gen_dir = str(PROJECT_ROOT / "assets" / "paint_basement_generated")
paint_regionmap_dir = os.path.join(paint_gen_dir, "regionmap")
if os.path.isdir(paint_regionmap_dir):
    app.mount(
        "/paint_basement_gen_static/regionmap",
        StaticFiles(directory=paint_regionmap_dir),
        name="paint_basement_gen_static_regionmap",
    )

paint_offsets_dir = os.path.join(paint_gen_dir, "offsets")
if os.path.isdir(paint_offsets_dir):
    app.mount(
        "/paint_basement_gen_static/offsets",
        StaticFiles(directory=paint_offsets_dir),
        name="paint_basement_gen_static_offsets",
    )

paint_masks_dir = str(PROJECT_ROOT / "assets" / "paint_basement_masks")
if os.path.isdir(paint_masks_dir):
    app.mount("/paint_basement_masks", StaticFiles(directory=paint_masks_dir), name="paint_basement_masks")

# 配置跨域（允许小程序请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源，生产环境需指定具体域名
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/admin")
def admin_index():
    for name in ("index.html", "users.html"):
        target = os.path.join(admin_static_dir, name)
        if os.path.isfile(target):
            return FileResponse(target, media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=404, detail="admin ui not found")

# [ai_story_bridge_begin]
READALONG_PROXY_BASE = (os.environ.get("READALONG_PROXY_BASE") or "http://127.0.0.1:9881").rstrip("/")
STORY_GEN_ENABLED = os.environ.get("STORY_GEN_ENABLED", "1") in {"1", "true", "True"}
STORY_GEN_ALLOW_HEURISTIC_FALLBACK = os.environ.get("STORY_GEN_ALLOW_HEURISTIC_FALLBACK", "0") in {"1", "true", "True"}
STORY_GEN_TIMEOUT_SEC = float(os.environ.get("STORY_GEN_TIMEOUT_SEC", "20"))
STORY_GEN_MAX_TOKENS = int(os.environ.get("STORY_GEN_MAX_TOKENS", "520"))
STORY_GEN_MODEL = AI_RUNTIME.model_for("story")


def _looks_like_placeholder_key(k):
    t = str(k or "").strip().lower()
    if not t:
        return True
    weak_markers = ["替换", "留空", "your", "example", "placeholder", "xxx", "sk-xxx"]
    return any(m in t for m in weak_markers)


def _is_weak_caption_text(text):
    t = str(text or "").strip()
    if not t or len(t) < 6:
        return True
    weak_hints = [
        "这是一张图片",
        "很有趣的图片",
        "你可以说说里面发生了什么",
        "请你先说说看到了什么",
        "当前为兜底描述",
    ]
    return any(h in t for h in weak_hints)


def _heuristic_image_caption(file_bytes):
    """本地轻量兜底：在无视觉模型时给出比通用占位文案更可用的描述。"""
    try:
        from PIL import Image
        import numpy as _np
        img = Image.open(BytesIO(file_bytes)).convert("RGB")
        arr = _np.asarray(img)
        if arr.size == 0:
            return "照片里有一个温暖的生活场景。"

        h, w = arr.shape[:2]
        mean_rgb = arr.reshape(-1, 3).mean(axis=0)
        r, g, b = [float(x) for x in mean_rgb]
        bright = (r + g + b) / 3.0

        place = "室外" if g > r and g > b else ("水边或天空场景" if b > r and b > g else "日常场景")
        mood = "阳光明亮" if bright >= 120 else "光线柔和"

        # 尝试做人脸数粗估，帮助区分“人物活动”类场景
        people_hint = ""
        try:
            import cv2
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
            cnt = 0 if faces is None else len(faces)
            if cnt >= 3:
                people_hint = "有一群小朋友在活动"
            elif cnt >= 1:
                people_hint = "有人物在画面中活动"
        except Exception:
            people_hint = ""

        if not people_hint and place == "室外":
            people_hint = "画面里像是在户外活动"

        size_hint = "近景" if max(h, w) < 900 else "中远景"
        base = f"这是一张{mood}的{place}{size_hint}照片"
        if people_hint:
            return f"{base}，{people_hint}，周围环境真实自然。"
        return f"{base}，主体清晰，适合改编成儿童故事。"
    except Exception:
        return "这是一张温暖的生活照片，画面中有明确的主体和场景。"


async def _proxy_readalong_image_caption(file_bytes, filename, content_type):
    target = f"{READALONG_PROXY_BASE}/readalong/image_caption"
    async with httpx.AsyncClient(timeout=18.0, trust_env=False) as client:
        files = {
            "file": (filename or "image.jpg", file_bytes, content_type or "application/octet-stream")
        }
        resp = await client.post(target, files=files)
        return resp


async def _proxy_readalong_tts(text: str):
    target = f"{READALONG_PROXY_BASE}/readalong/tts"
    async with httpx.AsyncClient(timeout=45.0, trust_env=False) as client:
        resp = await client.get(target, params={"text": text or ""})
        return resp


async def _proxy_readalong_audio(audio_id: str):
    target = f"{READALONG_PROXY_BASE}/readalong/audio/{audio_id}"
    async with httpx.AsyncClient(timeout=45.0, trust_env=False) as client:
        resp = await client.get(target)
        return resp


async def _proxy_readalong_evaluate(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    expected_text: str,
    book_id: str,
    sentence_index: str,
    audio_format: str,
    eval_mode: str,
):
    target = f"{READALONG_PROXY_BASE}/readalong/evaluate"
    async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
        files = {
            "file": (filename or f"input.{audio_format or 'wav'}", file_bytes, content_type or "application/octet-stream")
        }
        data = {
            "expected_text": expected_text or "",
            "book_id": book_id or "",
            "sentence_index": sentence_index or "0",
            "audio_format": audio_format or "wav",
            "eval_mode": eval_mode or "free_description",
        }
        resp = await client.post(target, files=files, data=data)
        return resp


def _build_story_pages_from_caption(caption, age_label, align_keywords):
    age = str(age_label or "4-5岁")
    hero = "小宝贝" if age == "2-3岁" else ("小小探险家" if age == "6-8岁" else "小朋友")

    kws = []
    for k in str(align_keywords or "").split(','):
        kk = str(k).strip()
        if kk and kk not in kws:
            kws.append(kk)
    kw_text = "、".join(kws[:3])

    p1 = f"今天，{hero}看到这样一幕：{caption}"
    p2 = f"{hero}仔细观察，发现画面里的细节都在讲述一个真实的小故事。"
    if kw_text:
        p3 = f"故事里还出现了{kw_text}，让这次经历更加生动。"
    else:
        p3 = f"{hero}把看到的景象和感受慢慢串起来，故事变得越来越完整。"
    p4 = f"最后，{hero}把这段经历分享给家人，大家都说：明天还要继续探索！"
    return [p1, p2, p3, p4]


async def _generate_story_from_llm(caption, age, tone, lang, custom_prompt, align_keywords):
    """调用 openai-compatible 模型生成绘本，返回 {title, pages, model}。失败抛异常。"""
    if not STORY_GEN_ENABLED:
        raise RuntimeError("story generation disabled")

    api_key = str(SAFETY_AI_API_KEY or "").strip()
    base_url = str(SAFETY_AI_BASE_URL or "").strip().rstrip("/")
    model = str(STORY_GEN_MODEL or "").strip()
    if _looks_like_placeholder_key(api_key) or not base_url or not model:
        raise RuntimeError("story llm not configured")

    keywords = [x.strip() for x in str(align_keywords or "").split(",") if x.strip()]
    keyword_line = f"关键词锚点：{'、'.join(keywords[:6])}。" if keywords else ""

    user_prompt = (
        "请基于以下图片描述，生成4页儿童绘本故事。\n"
        f"图片描述：{caption}\n"
        f"年龄段：{age}\n"
        f"语气风格：{tone}\n"
        f"语言：{lang}\n"
        f"{keyword_line}\n"
        "硬性要求：\n"
        "1) 必须紧贴图片描述，不可臆造未出现的关键角色/地点/事件。\n"
        "2) 必须输出4页，且每页1-2句。\n"
        "3) 要有起承转合，结尾温暖完整，不要开放式。\n"
        "4) 用词符合儿童理解。\n"
        "5) 仅输出JSON，不要解释。\n"
        "JSON格式：{\"title\":\"...\",\"pages\":[\"...\",\"...\",\"...\",\"...\"]}\n"
    )
    if str(custom_prompt or "").strip():
        user_prompt += f"补充要求：{str(custom_prompt).strip()}\n"

    body = {
        "model": model,
        "temperature": 0.5,
        "max_tokens": STORY_GEN_MAX_TOKENS,
        "messages": [
            {
                "role": "system",
                "content": "你是高质量儿童绘本作者。严格按用户给定JSON格式输出。禁止输出JSON以外文本。",
            },
            {"role": "user", "content": user_prompt},
        ],
    }

    target = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "gpt-sovits-wx-story/1.0",
    }
    async with httpx.AsyncClient(timeout=STORY_GEN_TIMEOUT_SEC, trust_env=False) as client:
        resp = await client.post(target, headers=headers, json=body)

    if resp.status_code >= 300:
        raise RuntimeError(f"story llm http {resp.status_code}: {resp.text[:300]}")

    obj = resp.json()
    content = (((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("empty story llm response")

    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE).strip()
    content = re.sub(r"\s*```$", "", content).strip()
    parsed = None
    try:
        parsed = json.loads(content)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            parsed = json.loads(m.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError("invalid story json")

    title = str(parsed.get("title") or "宝宝的照片故事").strip()[:30]
    pages = parsed.get("pages") or []
    if not isinstance(pages, list):
        raise RuntimeError("story pages is not list")
    norm_pages = [str(x).strip() for x in pages if str(x).strip()]
    if len(norm_pages) < 4:
        raise RuntimeError("story pages too short")

    return {
        "title": title,
        "pages": norm_pages[:4],
        "model": model,
    }


@app.post("/readalong/image_caption")
async def wx_readalong_image_caption(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    filename = getattr(file, "filename", None) or "image.jpg"
    content_type = getattr(file, "content_type", None) or "application/octet-stream"

    # 优先转发到 9881 readalong；若不可用或返回弱描述，则本地启发式兜底
    try:
        resp = await _proxy_readalong_image_caption(data, filename, content_type)
        if resp.status_code < 300:
            payload = resp.json()
            cap = str((payload or {}).get("caption") or "").strip()
            if cap and not _is_weak_caption_text(cap):
                payload["source"] = payload.get("source") or "readalong_proxy"
                return payload
    except Exception as e:
        logger.warning(f"[/readalong/image_caption] proxy failed, fallback to local heuristic: {e}")

    local_caption = _heuristic_image_caption(data)
    return {
        "ok": True,
        "caption": local_caption,
        "source": "wx_local_heuristic",
    }


@app.get("/readalong/tts")
async def wx_readalong_tts(text: str = ""):
    t = str(text or "").strip()
    if not t:
        return {"ok": False, "audio_url": "", "source": "fallback", "error": "empty_text"}

    try:
        resp = await _proxy_readalong_tts(t)
        if resp.status_code < 300:
            payload = resp.json() if resp.content else {}
            if isinstance(payload, dict):
                payload["source"] = payload.get("source") or "readalong_proxy"
            return payload
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"readalong tts proxy failed: {e}")


@app.get("/readalong/audio/{audio_id}")
async def wx_readalong_audio(audio_id: str):
    aid = str(audio_id or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="invalid audio_id")
    try:
        resp = await _proxy_readalong_audio(aid)
        if resp.status_code >= 300:
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
        media_type = (resp.headers.get("content-type") or "audio/mpeg").split(";")[0].strip() or "audio/mpeg"
        return Response(content=resp.content or b"", media_type=media_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"readalong audio proxy failed: {e}")


@app.post("/readalong/evaluate")
async def wx_readalong_evaluate(
    file: UploadFile = File(...),
    expected_text: str = Form(""),
    book_id: str = Form(""),
    sentence_index: str = Form("0"),
    audio_format: str = Form("wav"),
    eval_mode: str = Form("free_description"),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    filename = getattr(file, "filename", None) or f"input.{audio_format or 'wav'}"
    content_type = getattr(file, "content_type", None) or "application/octet-stream"

    # ✅ 关键：涂色作品打分走 9880 本地离线评测（稳定可用，不依赖 9881 或外部密钥）
    # 前端会设置：eval_mode=coloring_evaluation 且上传 PNG/JPG
    try:
        ct = str(content_type or "").lower()
        fmt = str(audio_format or "").lower().strip()
        em = str(eval_mode or "").strip()
        is_image = ct.startswith("image/") or fmt in {"png", "jpg", "jpeg", "webp"} or em == "coloring_evaluation"
        if is_image and em == "coloring_evaluation":
            import io
            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(data)).convert("RGB")
            arr = np.asarray(img).astype(np.float32)
            h, w = arr.shape[:2]
            if h < 8 or w < 8:
                score = 70
            else:
                near_white = (arr[..., 0] > 245) & (arr[..., 1] > 245) & (arr[..., 2] > 245)
                non_white_ratio = float(1.0 - near_white.mean())

                small = arr[:: max(1, h // 160), :: max(1, w // 160), :].reshape(-1, 3)
                q = (small // 32).astype(np.int32)
                codes = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
                uniq = int(len(np.unique(codes)))
                uniq_norm = min(1.0, max(0.0, (uniq - 4) / 12.0))

                mx = arr.max(axis=2)
                mn = arr.min(axis=2)
                sat = (mx - mn) / (mx + 1e-6)
                sat_mean = float(np.clip(sat.mean(), 0.0, 1.0))
                sat_std = float(np.clip(sat.std(), 0.0, 1.0))

                # 主要关注“颜色好看”：色彩丰富度 + 适度饱和度 + 大致覆盖度
                harmony_score = 70.0 * (0.6 * uniq_norm + 0.4 * sat_mean)
                cover_score = 30.0 * float(np.clip(non_white_ratio / 0.45, 0.0, 1.0))
                raw = harmony_score + cover_score
                # 整体分数偏高一点，且下限不要太低
                score = int(round(float(np.clip(raw, 70.0, 100.0))))

            def score_to_stars(s: int) -> int:
                if s >= 90:
                    return 5
                if s >= 80:
                    return 4
                if s >= 70:
                    return 3
                if s >= 60:
                    return 2
                return 1

            stars = score_to_stars(score)
            # 从 expected_text 里提取对象名（由前端隐式传入：对象：xxx）
            subj = ""
            try:
                et = str(expected_text or "")
                if "对象：" in et:
                    subj = et.split("对象：", 1)[1].strip().splitlines()[0].strip()
                # 去掉前缀题号，如“3 水母”
                if subj and subj[:2].isdigit():
                    subj = subj.lstrip("0123456789").strip()
            except Exception:
                subj = ""

            # 常见配色建议（只做正向引导，不当“纠错”）
            COMMON_COLORS = {
                "水母": "常见颜色：浅蓝、粉紫、薄荷绿、珍珠白；也可以加一点亮黄做小点缀。",
                "小狗": "常见颜色：米白、浅棕、焦糖棕、奶油黄；鼻子/眼睛用深灰或黑色会更灵动。",
                "企鹅": "常见颜色：黑白配最经典；也可以用浅灰做过渡，嘴和脚用明黄更可爱。",
                "苹果": "常见颜色：红色或青绿色最常见；叶子用绿色，梗用棕色会很自然。",
                "螃蟹": "常见颜色：橘红、珊瑚红最常见；加一点浅粉或浅橙做层次更漂亮。",
                "鲸鱼": "常见颜色：深蓝、海蓝、浅蓝；肚皮用浅灰或白色会更温柔。",
                "西瓜": "常见颜色：绿色外皮 + 红色果肉；籽用黑色或深棕点一点就很像。",
                "蝴蝶": "常见颜色：对比色很出彩，比如蓝+黄、紫+粉、橙+蓝；翅膀边缘加深更有层次。",
                "彩虹": "常见颜色：红橙黄绿蓝靛紫；也可以把颜色做成淡淡的渐变，更梦幻。",
            }
            common_line = ""
            if subj:
                for k, v in COMMON_COLORS.items():
                    if k in subj:
                        common_line = v
                        break

            praise = "你配色太棒啦！" if score >= 90 else ("你画得很用心，颜色很好看！" if score >= 80 else "你已经很勇敢地涂完这张图了！")
            tips = []
            # 建议全部围绕“颜色选择”，不强调出线/错误
            if score < 88:
                tips.append("可以给主角选一个你最喜欢的主色，再配两种温柔的辅色，会更有故事感。")
            tips.append("同一块区域尽量用相近的颜色慢慢涂匀，画面会更柔和漂亮。")
            tips.append("可以大胆试试一点点对比色做小装饰，比如帽子、背景小星星。")
            tips = tips[:4]
            feedback = praise
            if common_line:
                feedback += f" {common_line}"
            feedback += " " + " ".join([f"{i+1}){t}" for i, t in enumerate(tips)])

            return {
                "ok": True,
                "accuracy": float(score),
                "stars": int(stars),
                "feedback": feedback,
                "feedback_text": feedback,
                "transcript": "",
                "recognized_text": "",
                "feedback_audio_url": "",
                "source": "coloring_local_heuristic_9880",
            }
    except Exception as e:
        # 兜底：不要让前端无响应
        fb = "我已经看到你的作品啦！可以再把边边涂得更满一点点，再试试两三种颜色搭配，会更漂亮。"
        return {
            "ok": True,
            "accuracy": 72.0,
            "stars": 3,
            "feedback": fb,
            "feedback_text": fb,
            "transcript": "",
            "recognized_text": "",
            "feedback_audio_url": "",
            "source": f"coloring_local_fallback_9880:{str(e)[:80]}",
        }

    try:
        resp = await _proxy_readalong_evaluate(
            data,
            filename,
            content_type,
            expected_text,
            book_id,
            sentence_index,
            audio_format,
            eval_mode,
        )
        if resp.status_code < 300:
            payload = resp.json()
            if isinstance(payload, dict):
                payload["source"] = payload.get("source") or "readalong_proxy"
            return payload
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"readalong proxy failed: {e}")


@app.post("/practice/ai_story_from_image")
@app.post("/readalong/ai_story_from_image")
@app.post("/ai_story_from_image")
async def ai_story_from_image(
    file: UploadFile = File(...),
    age: str = Form("4-5岁"),
    tone: str = Form("温暖鼓励"),
    lang: str = Form("中文"),
    image_caption: str = Form(""),
    custom_prompt: str = Form(""),
    align_keywords: str = Form(""),
    require_image_faithfulness: str = Form("1"),
    alignment_mode: str = Form("strict"),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    caption = str(image_caption or "").strip()
    if _is_weak_caption_text(caption):
        caption = ""

    if not caption:
        try:
            resp = await _proxy_readalong_image_caption(data, getattr(file, "filename", None), getattr(file, "content_type", None))
            if resp.status_code < 300:
                payload = resp.json()
                cap = str((payload or {}).get("caption") or "").strip()
                if cap and not _is_weak_caption_text(cap):
                    caption = cap
        except Exception as e:
            logger.warning(f"[/ai_story_from_image] readalong proxy failed: {e}")

    if not caption:
        caption = _heuristic_image_caption(data)

    llm_used = False
    story_model = None
    title_age = "小宝贝" if str(age) == "2-3岁" else ("小小探险家" if str(age) == "6-8岁" else "小朋友")
    title = f"{title_age}的真实照片故事"

    pages = None
    story_err = None
    try:
        out = await _generate_story_from_llm(
            caption=caption,
            age=age,
            tone=tone,
            lang=lang,
            custom_prompt=custom_prompt,
            align_keywords=align_keywords,
        )
        pages = out.get("pages") or []
        title = str(out.get("title") or title)
        story_model = out.get("model")
        llm_used = True
    except Exception as e:
        story_err = str(e)
        logger.warning(f"[/ai_story_from_image] llm story failed: {e}")

    if not pages:
        if not STORY_GEN_ALLOW_HEURISTIC_FALLBACK:
            raise HTTPException(
                status_code=503,
                detail=(
                    "绘本大模型不可用（或未配置有效密钥），已阻止低质量兜底故事。"
                    "请检查 wx_api.env 中 SAFETY_AI_BASE_URL / SAFETY_AI_MODEL / SAFETY_AI_API_KEY。"
                ),
            )
        pages = _build_story_pages_from_caption(caption, age, align_keywords)

    # 返回结构与前端 normalize 逻辑兼容
    return {
        "ok": True,
        "code": 0,
        "title": title,
        "pages": pages,
        "caption": caption,
        "ai_used": bool(llm_used),
        "source": "wx_story_bridge",
        "meta": {
            "tone": str(tone or ""),
            "lang": str(lang or ""),
            "alignment_mode": str(alignment_mode or ""),
            "faithfulness": str(require_image_faithfulness or ""),
            "custom_prompt_passed": bool(str(custom_prompt or "").strip()),
            "story_model": story_model,
            "story_llm_used": bool(llm_used),
            "story_error": story_err,
            "heuristic_fallback_enabled": bool(STORY_GEN_ALLOW_HEURISTIC_FALLBACK),
        },
    }

# [ai_story_bridge_end]

# --------------------------------
# 魔法书架（/magic_books/*）& 伴宠模块（/ar_companion/*）
# 目标：让小程序“同一个 9880 端口”即可访问这些后端存储接口
# --------------------------------
from pathlib import Path
import re
from fastapi.responses import FileResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 统一以 book_new 为绘本主库（文本 + 图片都从这里读取）
MAGIC_BOOK_ROOT = PROJECT_ROOT / "modules" / "books_library" / "book_new"
MAGIC_IMAGE_ROOT = MAGIC_BOOK_ROOT
MAGIC_TEXT_ROOT_NEW = MAGIC_BOOK_ROOT
MAGIC_TEXT_ROOT_OLD = PROJECT_ROOT / "modules" / "books_library" / "绘本集"
MAGIC_INDEX_JSON = PROJECT_ROOT / "modules" / "books_library" / "library" / "magic_books_index.json"

_magic_index_cache = None
_magic_index_mtime = None


def load_magic_books_index():
    """优先从 book_new 动态扫描绘本索引；静态 json 仅用于补充 tags/icon。"""
    global _magic_index_cache, _magic_index_mtime
    try:
        # 动态索引以 book_new 目录变更时间为主，保证搬运/修复后即时生效
        stat = MAGIC_BOOK_ROOT.stat()
        mtime = stat.st_mtime
        if _magic_index_cache is not None and _magic_index_mtime == mtime:
            return _magic_index_cache

        meta_json = {}
        try:
            with open(MAGIC_INDEX_JSON, "r", encoding="utf-8") as f:
                meta_json = json.load(f) or {}
        except Exception:
            meta_json = {}

        data = {}
        if MAGIC_BOOK_ROOT.is_dir():
            for p in sorted(MAGIC_BOOK_ROOT.iterdir(), key=lambda x: x.name):
                if not p.is_dir():
                    continue
                title = p.name
                txt = p / f"{title}.txt"
                if not txt.is_file():
                    txts = sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() == ".txt"], key=lambda x: x.name)
                    if not txts:
                        continue
                    txt = txts[0]

                pages = {}
                for f in p.iterdir():
                    if not f.is_file():
                        continue
                    if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                        continue
                    m = re.match(r"^第(\d+)段(?:_\d+)?\.(jpg|jpeg|png|webp)$", f.name, flags=re.IGNORECASE)
                    if not m:
                        continue
                    k = str(int(m.group(1)))
                    pages.setdefault(k, []).append(f.name)
                for k in list(pages.keys()):
                    pages[k] = sorted(pages[k])

                meta = meta_json.get(title) if isinstance(meta_json, dict) else None
                meta = meta if isinstance(meta, dict) else {}
                data[title] = {
                    "dir": title,
                    "file": txt.name,
                    "tags": meta.get("tags") or [],
                    "icon": meta.get("icon") or "",
                    "pages": pages,
                }

        _magic_index_cache = data
        _magic_index_mtime = mtime
        return data
    except Exception as e:
        logger.error(f"[magic_books] 加载索引失败: {e}")
        return {}


def _read_magic_text_map(txt_path: Path):
    text_map = {}
    raw = txt_path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        line = (line or "").strip()
        if not line:
            continue
        m = re.match(r"^(\d+)[\.、．](.*)$", line)
        if not m:
            continue
        page_num = int(m.group(1))
        text_map[page_num] = str(m.group(2) or "").strip()
    return text_map


def _resolve_magic_text_path(book_dir: str, txt_filename: str, title: str):
    candidates = []
    if txt_filename:
        candidates.append(MAGIC_TEXT_ROOT_NEW / book_dir / txt_filename)
        candidates.append(MAGIC_TEXT_ROOT_OLD / book_dir / txt_filename)
    # 防止历史索引里 file 与目录不完全同名
    candidates.append(MAGIC_TEXT_ROOT_NEW / book_dir / f"{title}.txt")
    candidates.append(MAGIC_TEXT_ROOT_OLD / book_dir / f"{title}.txt")
    for p in candidates:
        if p.is_file():
            return p
    return None


@app.get("/magic_books/index")
def magic_books_index():
    index_data = load_magic_books_index() or {}
    items = []

    for title, entry in index_data.items():
        if not isinstance(entry, dict):
            continue

        book_dir = str(entry.get("dir") or title)
        txt_filename = str(entry.get("file") or "")
        pages_obj = entry.get("pages") or {}
        page_numbers = []
        for k in pages_obj.keys():
            try:
                page_numbers.append(int(k))
            except Exception:
                continue
        page_numbers.sort()

        cover_filename = ""
        if page_numbers:
            cover_imgs = pages_obj.get(str(page_numbers[0])) or []
            if isinstance(cover_imgs, list) and cover_imgs:
                cover_filename = str(cover_imgs[0] or "")

        cover_url = f"/magic_books_static/{book_dir}/{cover_filename}" if cover_filename else ""

        text_count = 0
        try:
            txt_path = _resolve_magic_text_path(book_dir, txt_filename, str(title))
            if txt_path is not None:
                text_count = len(_read_magic_text_map(txt_path))
        except Exception:
            text_count = 0
        total_pages = text_count if text_count > 0 else len(page_numbers)

        items.append(
            {
                "title": str(title),
                "id": str(title),
                "cover_url": cover_url,
                "page_count": total_pages,
                "total_pages": total_pages,
                # 可选字段：小程序端不会强依赖这些，但保留便于调试/扩展
                "tags": entry.get("tags") or [],
                "icon": entry.get("icon") or "",
            }
        )

    return {"items": items}


@app.get("/magic_books/book")
def magic_books_book(title: str = Query(..., description="绘本标题（magic_books_index.json 的 key）")):
    index_data = load_magic_books_index() or {}
    entry = index_data.get(title)
    if not entry or not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail="book not found")

    book_dir = str(entry.get("dir") or title)
    txt_filename = str(entry.get("file") or "")
    txt_path = _resolve_magic_text_path(book_dir, txt_filename, str(title))

    if txt_path is None:
        raise HTTPException(status_code=404, detail="book text not found")

    # 解析 txt：格式形如 `1.小女孩捡到一支红色画笔...`
    text_map = {}
    try:
        text_map = _read_magic_text_map(txt_path)
    except Exception as e:
        logger.error(f"[magic_books] 读取/解析 txt 失败: {e}")
        raise HTTPException(status_code=500, detail="book parse failed") from e

    pages_obj = entry.get("pages") or {}
    page_numbers = set()
    for k in pages_obj.keys():
        try:
            page_numbers.add(int(k))
        except Exception:
            continue
    for k in text_map.keys():
        try:
            page_numbers.add(int(k))
        except Exception:
            continue
    page_numbers = sorted(page_numbers)

    paras = []
    for page_num in page_numbers:
        imgs = pages_obj.get(str(page_num)) or []
        images_urls = []
        if isinstance(imgs, list):
            for img in imgs:
                if img is None:
                    continue
                img_str = str(img or "")
                if not img_str:
                    continue
                images_urls.append(f"/magic_books_static/{book_dir}/{img_str}")

        paras.append(
            {
                "images": images_urls,
                "text": text_map.get(page_num, ""),
                "prompt": "",
            }
        )

    # 小程序端只用到 title/paras
    return {"title": str(title), "paras": paras}


@app.get("/magic_books_static/{book_dir}/{image_name}")
def magic_books_static(book_dir: str, image_name: str):
    # 防路径穿越：确保最终路径落在 MAGIC_IMAGE_ROOT 下
    try:
        candidate = (MAGIC_IMAGE_ROOT / str(book_dir) / str(image_name)).resolve()
        root = MAGIC_IMAGE_ROOT.resolve()
        if str(candidate).find(str(root)) != 0:
            raise HTTPException(status_code=404, detail="not found")
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="not found")

        suffix = candidate.suffix.lower()
        media_type = "image/jpeg"
        if suffix in [".png"]:
            media_type = "image/png"
        elif suffix in [".webp"]:
            media_type = "image/webp"

        return FileResponse(str(candidate), media_type=media_type)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="not found")


# 尝试挂载 ar_companion_backend：如果导入/初始化失败，不阻断主服务
try:
    from modules.ar_companion_backend.api import router as ar_companion_router

    app.include_router(ar_companion_router)
    logger.info("[magic_books] 已注册 ar_companion_backend 路由: /ar_companion/*")
except Exception as e:
    logger.error(f"[ar_companion_backend] 路由挂载失败: {e}")

# 尝试挂载 coloring_artist：让“小画家”能读取题库线稿
try:
    try:
        from modules.coloring_artist.backend.coloring_api import router as coloring_router
    except Exception:
        from coloring_api import router as coloring_router

    app.include_router(coloring_router)
    logger.info("[magic_books] 已注册 coloring_api 路由: /coloring/*")
except Exception as e:
    logger.error(f"[coloring_api] 路由挂载失败: {e}")

# 尝试挂载用户管理接口（登录/资料/后台管理）
try:
    try:
        from modules.user_mgmt_backend.user_api import router as user_mgmt_router
    except Exception:
        from user_mgmt_backend.user_api import router as user_mgmt_router
    app.include_router(user_mgmt_router)
    logger.info("[magic_books] 已注册 user_mgmt 路由: /auth/* /users/* /admin/*")
except Exception as e:
    logger.error(f"[user_mgmt] 路由挂载失败: {e}")

# 题库选图（speaker）数据接口
@app.get("/practice/speaker/questions")
def practice_speaker_questions(limit: int = 200, skip: int = 0, locale: str = "zh-CN"):
    """
    小程序“题库选图”读取接口。
    返回结构：{ ok: bool, items: [...], total: int, count: int }
    """
    questions_file = str(PROJECT_ROOT / "assets" / "practice" / "speaker_questions_zh.json")
    try:
        if not os.path.isfile(questions_file):
            raise FileNotFoundError(f"questions file not found: {questions_file}")

        with open(questions_file, "r", encoding="utf-8") as f:
            obj = json.load(f) or {}

        items = obj.get("items", []) or []
        if not isinstance(items, list):
            items = []

        # 基础分页
        limit = max(1, int(limit or 1))
        skip = max(0, int(skip or 0))
        paginated = items[skip : skip + limit]

        return {"ok": True, "items": paginated, "total": len(items), "count": len(paginated)}
    except Exception as e:
        logger.error(f"[practice/speaker/questions] load failed: {e}")
        return {"ok": False, "items": [], "total": 0, "count": 0, "error": str(e)}

# 临时目录配置（确保目录存在，使用绝对路径）
TEMP_RAW_DIR = os.path.abspath("./train/temp_raw_audio")  # 原始音频（MP3/AMR）
TEMP_WAV_DIR = os.path.abspath("./train/temp_wav_audio")  # 转码后的WAV
os.makedirs(TEMP_RAW_DIR, exist_ok=True)
os.makedirs(TEMP_WAV_DIR, exist_ok=True)
logger.info(f"[初始化] 临时目录配置 - RAW: {TEMP_RAW_DIR}, WAV: {TEMP_WAV_DIR}")
print(f"[初始化] 临时目录配置 - RAW: {TEMP_RAW_DIR}, WAV: {TEMP_WAV_DIR}")

@app.post("/wx/upload_audio")
async def wx_upload_audio(
    user_id: str = Form(...),  # 必传参数：用户ID（用于区分不同用户的音频）
    file: UploadFile = File(...),  # 必传参数：音频文件
    prompt_text: str = Form(None),  # 参考文本（可选）
    prompt_language: str = Form("all_zh")  # 参考文本语言（可选）
):
    """处理小程序上传的音频，转码为WAV后返回临时路径"""
    logger.info(f"[wx/upload_audio] 收到上传请求 - user_id: {user_id}, filename: {file.filename}")
    print(f"[wx/upload_audio] 收到上传请求 - user_id: {user_id}, filename: {file.filename}")
    
    # 1. 验证用户ID（避免空值）
    if not user_id.strip():
        logger.warning("[wx/upload_audio] user_id为空")
        raise HTTPException(status_code=400, detail="user_id不能为空")

    # 2. 验证文件名和格式
    if not file.filename:
        logger.warning("[wx/upload_audio] 文件名为空")
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    # 提取文件扩展名（处理不带扩展名的情况）
    if "." not in file.filename:
        logger.warning(f"[wx/upload_audio] 文件名无扩展名: {file.filename}")
        raise HTTPException(status_code=400, detail="文件名必须包含扩展名（如.mp3）")
    
    file_ext = file.filename.split(".")[-1].lower()
    allowed_ext = ["mp3", "amr", "wav"]  # 支持的格式
    if file_ext not in allowed_ext:
        logger.warning(f"[wx/upload_audio] 不支持的格式: {file_ext}")
        raise HTTPException(status_code=400, detail=f"仅支持{allowed_ext}格式音频，当前格式：{file_ext}")

    # 3. 保存原始音频到临时目录（用UUID生成唯一文件名，避免冲突）
    raw_filename = f"{uuid.uuid4()}_{user_id}.{file_ext}"  # 加入user_id便于追溯
    raw_path = os.path.abspath(os.path.join(TEMP_RAW_DIR, raw_filename))
    
    logger.info(f"[wx/upload_audio] 准备保存文件到: {raw_path}")
    print(f"[wx/upload_audio] 准备保存文件到: {raw_path}")
    
    try:
        # 读取并保存上传的文件内容
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size == 0:
            logger.error("[wx/upload_audio] 上传的音频文件为空")
            raise HTTPException(status_code=400, detail="上传的音频文件为空")
        
        logger.info(f"[wx/upload_audio] 文件大小: {file_size} 字节")
        print(f"[wx/upload_audio] 文件大小: {file_size} 字节")
        
        # 确保目录存在
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        
        with open(raw_path, "wb") as f:
            f.write(file_content)
        
        # 验证文件是否成功保存
        if not os.path.exists(raw_path):
            logger.error(f"[wx/upload_audio] 文件保存失败，路径不存在: {raw_path}")
            raise HTTPException(status_code=500, detail="文件保存失败")
        
        saved_size = os.path.getsize(raw_path)
        logger.info(f"[wx/upload_audio] 文件保存成功: {raw_path}, 大小: {saved_size} 字节")
        print(f"[wx/upload_audio] 文件保存成功: {raw_path}, 大小: {saved_size} 字节, 存在: {os.path.exists(raw_path)}")
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"[wx/upload_audio] 保存原始音频失败: {str(e)}\n{error_detail}")
        print(f"[wx/upload_audio] 保存原始音频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存原始音频失败：{str(e)}")

    # 4. 转码为WAV格式（模型通常需要WAV格式）
    wav_filename = f"{uuid.uuid4()}_{user_id}.wav"
    wav_path = os.path.abspath(os.path.join(TEMP_WAV_DIR, wav_filename))
    
    logger.info(f"[wx/upload_audio] 开始转码: {raw_path} -> {wav_path}")
    print(f"[wx/upload_audio] 开始转码: {raw_path} -> {wav_path}")
    
    if not convert_to_wav(raw_path, wav_path):
        # 转码失败时清理原始文件，避免占用空间
        logger.error(f"[wx/upload_audio] 转码失败，清理原始文件: {raw_path}")
        if os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except:
                pass
        raise HTTPException(status_code=500, detail="音频转码为WAV失败，请检查文件是否损坏或ffmpeg是否正确安装")

    # 验证转码后的文件
    if not os.path.exists(wav_path):
        logger.error(f"[wx/upload_audio] 转码后文件不存在: {wav_path}")
        raise HTTPException(status_code=500, detail="转码后文件生成失败")
    
    wav_size = os.path.getsize(wav_path)
    logger.info(f"[wx/upload_audio] 转码成功: {wav_path}, 大小: {wav_size} 字节")
    print(f"[wx/upload_audio] 转码成功: {wav_path}, 大小: {wav_size} 字节")

    # 5. 转码成功后，清理原始文件（只保留WAV）
    try:
        if os.path.exists(raw_path):
            os.remove(raw_path)
            logger.info(f"[wx/upload_audio] 已清理原始文件: {raw_path}")
    except Exception as e:
        logger.warning(f"[wx/upload_audio] 清理原始文件失败: {str(e)}")  # 仅打印警告，不阻断流程
        print(f"[wx/upload_audio] 清理原始文件失败: {str(e)}")

    # 6. 自动切分音频为7~8秒的片段
    logger.info(f"[wx/upload_audio] 开始切分音频...")
    segments = split_audio_to_segments(wav_path, segment_duration=7.5, output_dir=TEMP_WAV_DIR)
    
    if not segments:
        logger.warning(f"[wx/upload_audio] 音频切分失败，使用原始音频")
        segments = [{
            "path": wav_path,
            "start_time": 0.0,
            "end_time": 0.0,
            "duration": 0.0
        }]
    
    # 7. 如果提供了参考文本，根据时间比例切分文本
    text_segments = []
    if prompt_text:
        # 获取音频总时长
        try:
            import librosa
            audio, sr = librosa.load(wav_path, sr=16000, mono=True)
            total_duration = len(audio) / sr
            text_segments = split_text_by_time_ratio(prompt_text, segments, total_duration)
        except Exception as e:
            logger.warning(f"[wx/upload_audio] 获取音频时长失败: {str(e)}，使用完整文本")
            text_segments = [prompt_text] * len(segments)
    else:
        # 如果没有提供文本，每个片段使用空文本
        text_segments = [""] * len(segments)
    
    # 8. 构建返回的片段信息
    segment_info = []
    for i, (seg, text) in enumerate(zip(segments, text_segments)):
        segment_info.append({
            "index": i + 1,
            "audio_path": seg["path"],
            "start_time": seg["start_time"],
            "end_time": seg["end_time"],
            "duration": seg["duration"],
            "text": text,
            "language": prompt_language or "all_zh"
        })
    
    # 9. 返回切分后的音频片段信息
    logger.info(f"[wx/upload_audio] 上传并切分完成，共 {len(segment_info)} 个片段")
    return {
        "code": 200,
        "message": f"音频上传并切分成功，共 {len(segment_info)} 个片段",
        "temp_wav_path": wav_path,  # 保留原始完整音频路径（兼容旧接口）
        "segments": segment_info,  # 切分后的片段列表
        "segment_count": len(segment_info),
        "recommended_segment": segment_info[0] if segment_info else None  # 推荐使用第一个片段
    }

@app.post("/upload_audio")
async def upload_audio(file: UploadFile = File(...)):
    """通用音频上传接口（可用于其他场景，如网页端）"""
    # 验证文件名
    if not file.filename or "." not in file.filename:
        raise HTTPException(status_code=400, detail="文件名必须包含扩展名（如.mp3）")
    
    # 生成唯一文件名
    file_ext = file.filename.split(".")[-1].lower()
    temp_filename = f"{uuid.uuid4()}.{file_ext}"
    temp_path = os.path.join(TEMP_RAW_DIR, temp_filename)
    
    # 保存文件
    try:
        file_content = await file.read()
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")
        
        with open(temp_path, "wb") as f:
            f.write(file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败：{str(e)}")
    
    return {"code": 200, "temp_path": temp_path}

# 新增：合成接口（前端请求的 /synthesize）


# 内容安全检测接口（调试用）：只返回判定结果，不做合成
@app.post("/safety/check")
async def safety_check(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须为 JSON")
    text = data.get("text") or ""
    ok, reason, hit = _check_text_safety(text)
    return {
        "ok": bool(ok),
        "reason": reason,
        "hit": hit,
        "ai_enabled": bool(SAFETY_AI_ENABLED),
        "ai_base_url": SAFETY_AI_BASE_URL or None,
        "ai_model": SAFETY_AI_MODEL or None,
        "ai_story_model": STORY_GEN_MODEL or None,
        "ai_fail_closed": bool(SAFETY_AI_FAIL_CLOSED),
    }

@app.post("/synthesize")
async def synthesize(request: Request):
    """
    统一合成接口（推荐给微信小程序使用）
    
    支持两种调用方式：
    1）指定 voice_id：
        {
          "voice_id": "voice_003",
          "text": "要合成的文本",
          "text_language": "zh" / "中文" / ...
        }
    2）指定 user_id / model_name（== 用户编号）：
        {
          "user_id": "176xxxxxxx",
          "text": "要合成的文本",
          "text_language": "zh"
        }
    后端会：
    - 根据 voice_id 或 user_id 在 VOICE_LIBRARY 中找到对应模型
    - 自动使用训练时记录的参考音频与文本
    - 调用底层 handle()/get_tts_wav 完成合成
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须为 JSON")

    voice_id = data.get("voice_id")
    user_id = data.get("user_id") or data.get("model_name")
    text = data.get("text")
    text_language = data.get("text_language") or data.get("language") or "zh"
    speed = float(data.get("speed", 1.0))
    
    # 支持直接传递参考音频和文本（兼容前端调用）
    refer_wav_path = data.get("refer_wav_path") or data.get("ref_wav_path")
    prompt_text = data.get("prompt_text")
    prompt_language = data.get("prompt_language") or "中文"
    raw_aux_refs = data.get("inp_refs")
    if raw_aux_refs is None:
        raw_aux_refs = data.get("aux_ref_audio_paths")
    if raw_aux_refs is None:
        raw_aux_refs = data.get("ref_audio_paths")

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="缺少要合成的文本 text")

    ok, reason, _hit = _check_text_safety(text)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    profile_ref_guard = None
    profile = {}
    pre_ref_risk_tier = "normal"

    # 如果提供了 refer_wav_path 和 prompt_text，直接使用（兼容前端调用）
    if refer_wav_path and prompt_text:
        ref_audio_path = refer_wav_path
        ref_text = prompt_text
        ref_language_raw = prompt_language
        
        # 转换为绝对路径
        if not os.path.isabs(ref_audio_path):
            ref_audio_path = os.path.abspath(os.path.join(now_dir, ref_audio_path))
        
        # 检查参考音频文件是否存在
        if not os.path.exists(ref_audio_path):
            raise HTTPException(
                status_code=400, 
                detail=f"参考音频文件不存在: {ref_audio_path}"
            )
    
        # 如果没有指定 voice_id，使用默认模型路径（从环境变量或配置获取）
        gpt_path = data.get("gpt_path") or os.environ.get("gpt_path")
        sovits_path = data.get("sovits_path") or os.environ.get("sovits_path")

        if not gpt_path or not sovits_path:
            gpt_path = gpt_path or globals().get("gpt_path")
            sovits_path = sovits_path or globals().get("sovits_path")
        
        if not gpt_path or not sovits_path:
            raise HTTPException(status_code=400, detail="使用参考音频模式时，需要提供 gpt_path 和 sovits_path，或先加载模型")
    else:
        # 使用 voice_id 或 user_id 从 VOICE_LIBRARY 获取
        load_voice_library_from_file()
        if not voice_id and user_id:
            for vid, info in VOICE_LIBRARY.items():
                if info.get("name") == user_id:
                    voice_id = vid
                    break

        if not voice_id:
            raise HTTPException(status_code=400, detail="请提供 voice_id/user_id/model_name 或 refer_wav_path+prompt_text 来选择声音模型")

        if voice_id not in VOICE_LIBRARY:
            raise HTTPException(status_code=404, detail=f"未找到 voice_id 对应的模型: {voice_id}")

        profile = VOICE_LIBRARY[voice_id]
        if str((profile or {}).get("model_type") or "").strip().lower() == "user_trained":
            try:
                pre_ref_risk_tier = str((_resolve_user_voice_risk_policy(voice_id, profile) or {}).get("tier") or "normal").strip().lower()
            except Exception:
                pre_ref_risk_tier = "normal"

        if _is_qwen_voice_profile(profile):
            text_cleaned = sanitize_text(text)
            if not has_speakable_content(text_cleaned):
                raise HTTPException(status_code=400, detail="目标文本缺少可发音字符，请输入完整句子后重试")

            if bool(data.get("buffered")):
                strict_segmented = _coerce_bool_param(data.get("strict_segmented"), False)
                long_text_stream = _coerce_bool_param(data.get("long_text_stream"), False)
                long_book_text = _is_long_book_text(text_cleaned) or long_text_stream
                default_cut_punc = "，。？！；：,.!?;:、…" if strict_segmented else ("。？！；：!?;:…" if long_book_text else "。？！!?；;")
                cut_punc = data.get("cut_punc", None) or default_cut_punc
                max_text_len = int(data.get("max_text_len", 72 if long_book_text else 96))
                max_text_len = max(24, min(160, max_text_len))
                segments = _split_text_for_buffer(text_cleaned, max_len=max_text_len, cut_punc=cut_punc)
                if not segments:
                    segments = [text_cleaned]

                _cleanup_buffer_tasks()
                task_id = uuid.uuid4().hex
                task = {
                    "created_at": time.time(),
                    "total": len(segments),
                    "segments": [None] * len(segments),
                    "done": False,
                    "error": None,
                    "debug_id": None,
                    "voice_id": voice_id,
                    "merged_url": None,
                    "adaptive_text": text_cleaned,
                    "is_user_trained_voice": False,
                    "speed_base": float(data.get("speed", 1.0) or 1.0),
                }
                with BUFFER_TASKS_LOCK:
                    BUFFER_TASKS[task_id] = task

                ready_urls = []
                used_voice = ""
                source_tag = "qwen_tts"
                for i, seg in enumerate(segments):
                    try:
                        seg_audio_wav, seg_voice, seg_source = await _qwen_tts_generate_wav(seg, profile)
                    except Exception as qe:
                        err_msg = f"Qwen基础音色分段合成失败: {qe}"
                        with BUFFER_TASKS_LOCK:
                            task["error"] = err_msg
                            task["done"] = True
                        raise HTTPException(status_code=503, detail=err_msg)
                    used_voice = used_voice or seg_voice
                    source_tag = seg_source or source_tag
                    url = _save_buffer_segment(seg_audio_wav, voice_id, task_id, i)
                    with BUFFER_TASKS_LOCK:
                        task["segments"][i] = url
                    ready_urls.append(url)

                with BUFFER_TASKS_LOCK:
                    task["done"] = True

                merged_url = ""
                try:
                    merged_url = _merge_wav_segments_to_static(task_id)
                except Exception as merge_err:
                    logger.warning(f"[qwen_buffered] 合并分片失败(可忽略): {merge_err}")

                return JSONResponse({
                    "code": 0,
                    "task_id": task_id,
                    "segments": ready_urls,
                    "total_segments": len(segments),
                    "merged_url": merged_url,
                    "source": source_tag,
                    "voice_used": used_voice,
                }, status_code=200)

            try:
                audio_bytes_wav, used_voice, source_tag = await _qwen_tts_generate_wav(text_cleaned, profile)
            except Exception as qe:
                raise HTTPException(status_code=503, detail=f"Qwen基础音色合成失败: {qe}")

            return_url = bool(data.get("return_url"))
            if return_url or len(audio_bytes_wav) > 10 * 1024 * 1024:
                tts_dir = _resolve_tts_static_dir()
                os.makedirs(tts_dir, exist_ok=True)
                fname = f"synth_{voice_id or 'default'}_{int(time.time())}_{uuid.uuid4().hex[:8]}.wav"
                fpath = os.path.join(tts_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(audio_bytes_wav)
                audio_url = f"/static/tts/{fname}"
                return JSONResponse({
                    "code": 0,
                    "audio_url": audio_url,
                    "size": len(audio_bytes_wav),
                    "source": source_tag,
                    "voice_used": used_voice,
                }, status_code=200)

            return StreamingResponse(
                BytesIO(audio_bytes_wav),
                media_type="audio/wav",
                headers={"Content-Disposition": f"attachment; filename=synthesized_{voice_id}.wav"},
            )

        ref_audio_path = profile.get("ref_audio_path")
        ref_text = profile.get("ref_text")
        ref_language_raw = profile.get("ref_language", "中文")
        profile_ref_guard = _build_voice_reference_guard(
              voice_id=voice_id,
              profile=profile,
              req_max_refs=int(data.get("max_ref_samples", 6)),
              req_max_aux_refs=int(data.get("max_aux_refs", 2)),
          )
        
        # 获取模型路径
        gpt_path = profile.get("gpt_path")
        sovits_path = profile.get("sovits_path")

        # 参考信息校验
        if not ref_audio_path:
            raise HTTPException(status_code=400, detail="该模型未记录有效的参考音频，无法自动推理")
        # ref_text 允许为空，后续会从同目录 sentence_*.txt 自动补全
    # 参考包组装：主参考 + 辅助参考（默认仅少量，避免卡顿）
    effective_max_refs = int(data.get("max_ref_samples", 6))
    effective_max_aux_refs = int(data.get("max_aux_refs", 2))
    dataset_scan_enabled = True
    if profile_ref_guard:
        effective_max_refs = int(profile_ref_guard.get("max_refs", effective_max_refs))
        effective_max_aux_refs = int(profile_ref_guard.get("max_aux_refs", effective_max_aux_refs))
        dataset_scan_enabled = bool(profile_ref_guard.get("dataset_scan_enabled", True))
        if profile_ref_guard.get("reason"):
            logger.warning(
                f"[ref_guard] voice_id={voice_id} 启用参考保护: reason={profile_ref_guard.get('reason')}, "
                f"max_refs={effective_max_refs}, max_aux_refs={effective_max_aux_refs}, "
                f"dataset_scan_enabled={dataset_scan_enabled}"
            )

    text_for_ref_match = sanitize_text(text)
    ref_bundle = _resolve_reference_bundle(
        ref_audio_path=ref_audio_path,
        ref_text=ref_text,
        base_dir=now_dir,
        extra_ref_paths=raw_aux_refs,
        max_refs=effective_max_refs,
        max_aux_refs=effective_max_aux_refs,
        target_text=text_for_ref_match,
        prompt_max_chars=int(data.get("prompt_max_chars", 40)),
        dataset_scan_enabled=dataset_scan_enabled,
        prefer_primary_sentence_text=bool(profile_ref_guard),
        prefer_target_primary_sample=bool(profile_ref_guard) and pre_ref_risk_tier in ("risky", "strict"),
    )
    ref_audio_path = ref_bundle.get("primary_ref_audio")
    aux_ref_audio_paths = ref_bundle.get("aux_ref_audio_paths") or []
    ref_text = ref_bundle.get("prompt_text") or ""

    if not ref_audio_path:
        raise HTTPException(status_code=400, detail="参考音频路径为空，无法推理")
    if not os.path.exists(ref_audio_path):
        raise HTTPException(
            status_code=400,
            detail=f"参考音频文件不存在: {ref_audio_path}。请检查模型配置中的 ref_audio_path。"
        )
    if not ref_text:
        raise HTTPException(status_code=400, detail="参考文本为空，无法推理")

    ref_language = dict_language.get(ref_language_raw, "all_zh")
    if ref_language not in dict_language.values():
        ref_language = "all_zh"

    logger.info(
        f"[synthesize] 使用 voice_id={voice_id}, ref={ref_audio_path}, "
        f"aux_refs={len(aux_ref_audio_paths)}, lang={ref_language_raw}->{ref_language}"
    )

    # 完全使用 simple_inference.py 的推理流程（简洁、已验证可用）
    try:
        # 模型路径已在上面获取（通过 voice_id 或直接传递）
        if not gpt_path or not sovits_path:
            raise HTTPException(status_code=400, detail="模型路径未配置")
        
        # 检查模型文件是否存在
        if not os.path.exists(gpt_path):
            raise HTTPException(status_code=400, detail=f"GPT模型文件不存在: {gpt_path}")
        if not os.path.exists(sovits_path):
            raise HTTPException(status_code=400, detail=f"SoVITS模型文件不存在: {sovits_path}")
        
        # 设置 GPU（与 simple_inference.py 一致，从环境变量或配置获取，默认 "0"）
        gpu_id = data.get("gpu", "0")
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
        
        # 设置模型路径到环境变量（与 simple_inference.py 完全一致）
        os.environ["gpt_path"] = gpt_path
        os.environ["sovits_path"] = sovits_path
        
        # 文本清理（使用 simple_inference.py 的函数）
        ref_text_cleaned = normalize_ref_text_for_infer(ref_text, max_chars=max(20, int(data.get("prompt_max_chars", 40))))
        text_cleaned = sanitize_text(text)
        if not has_speakable_content(text_cleaned):
            raise HTTPException(status_code=400, detail="目标文本缺少可发音字符，请输入完整句子后重试")
        debug_id = None
        if bool(data.get("debug")):
            debug_payload = {
                "voice_id": voice_id,
                "user_id": user_id,
                "return_url": bool(data.get("return_url")),
                "buffered": bool(data.get("buffered")),
            }
            debug_id = _new_debug_record(debug_payload)
            _debug_set(debug_id, text_raw=str(text), text_cleaned=str(text_cleaned), ref_text_raw=str(ref_text), ref_text_cleaned=str(ref_text_cleaned))
            _td = _summarize_sanitize_delta(str(text), str(text_cleaned))
            _rd = _summarize_sanitize_delta(str(ref_text), str(ref_text_cleaned))
            _debug_set(debug_id, text_sanitize=_td, ref_text_sanitize=_rd)
            logger.info(f"[synthesize][{debug_id}] sanitize.text={_td} sanitize.ref={_rd}")
            _debug_event(debug_id, "synthesize.input", text_len=len(text_cleaned), ref_len=len(ref_text_cleaned))
            try:
                import api as _api_mod
                _hz = getattr(_api_mod, "hz", None)
                _max_sec = None
                _infer_gpt = getattr(_api_mod, "infer_gpt", None)
                if _infer_gpt is not None:
                    _max_sec = getattr(_infer_gpt, "max_sec", None)
                if _max_sec is None:
                    _spk = getattr(_api_mod, "speaker_list", {}).get("default") if hasattr(_api_mod, "speaker_list") else None
                    if _spk is not None and hasattr(_spk, "gpt"):
                        _max_sec = getattr(_spk.gpt, "max_sec", None)
                _early_stop_num = None
                if _hz is not None and _max_sec is not None:
                    try:
                        _early_stop_num = int(float(_hz) * float(_max_sec))
                    except Exception:
                        _early_stop_num = None
                _debug_set(debug_id, hz=_hz, max_sec=_max_sec, early_stop_num=_early_stop_num)
            except Exception:
                pass

        
        # ============ 详细的参考信息日志 ============
        logger.info("="*60)
        logger.info("[synthesize] === 推理参数详情 ===")
        logger.info(f"[synthesize] 参考音频路径: {ref_audio_path}")
        logger.info(f"[synthesize] 参考音频文件存在: {os.path.exists(ref_audio_path)}")
        if os.path.exists(ref_audio_path):
            file_size = os.path.getsize(ref_audio_path) / 1024  # KB
            logger.info(f"[synthesize] 参考音频文件大小: {file_size:.2f} KB")
        logger.info(f"[synthesize] 参考文本(原始): {ref_text}")
        logger.info(f"[synthesize] 参考文本(清理后): {ref_text_cleaned}")
        logger.info(f"[synthesize] 参考文本长度: {len(ref_text_cleaned)} 字符")
        logger.info(f"[synthesize] 目标文本(原始): {text}")
        logger.info(f"[synthesize] 目标文本(清理后): {text_cleaned}")
        logger.info(f"[synthesize] 目标文本长度: {len(text_cleaned)} 字符")
        logger.info(f"[synthesize] 参考语言(原始): {ref_language_raw}")
        logger.info(f"[synthesize] 参考语言(映射后): {ref_language}")
        # ============ 详细日志结束 ============
        
        # 语言检测（与 simple_inference.py 完全一致）
        # 参考音频固定按中文；目标文本根据内容自动判断
        prompt_language = "Chinese"
        text_language_final = detect_text_language(text_cleaned)  # 完全使用自动检测，与 simple_inference.py 一致
        
        logger.info(f"[synthesize] 使用GPT模型: {gpt_path}")
        logger.info(f"[synthesize] 使用SoVITS模型: {sovits_path}")
        logger.info(f"[synthesize] 参考语言(用于推理): {prompt_language}, 目标语言(用于推理): {text_language_final}")
        logger.info("="*60)
        
        # 直接使用官方 api.py 的推理逻辑
        try:
            # 动态导入官方 api.py（延迟加载，避免初始化冲突）
            from api import (
                get_tts_wav as official_get_tts_wav_api,
                change_gpt_sovits_weights as official_change_gpt_sovits_weights,
                speaker_list as api_speaker_list,
                cut_text as official_cut_text,
            )
            USE_OFFICIAL_API = True
        except Exception as e:
            logger.warning(f"[synthesize] 无法导入官方 api.py: {e}，使用 inference_webui")
            USE_OFFICIAL_API = False
            from GPT_SoVITS.inference_webui import (
                get_tts_wav as official_get_tts_wav_webui,
            )
        
        if USE_OFFICIAL_API:
            # 使用缓存感知的切权重，避免同一模型重复加载导致额外等待。
            try:
                _ensure_official_model_loaded(official_change_gpt_sovits_weights, gpt_path, sovits_path)
                if "default" in api_speaker_list and api_speaker_list["default"] is not None:
                    try:
                        api_speaker_list["default"].name = str(voice_id or "default")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"[synthesize] 模型加载失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise HTTPException(status_code=500, detail=f"模型加载失败: {str(e)}")

# 语言映射：api.py 的 dict_language 使用中文键（"中文"、"英文"、"日文"等）
            # 需要将 detect_text_language 返回的 "Chinese"/"English" 映射到 dict_language 的键
            # dict_language = {"中文": "all_zh", "英文": "en", "日文": "all_ja", ...}
            
            # 映射 prompt_language: "Chinese" -> "中文"
            if "中文" in prompt_language or "Chinese" in prompt_language:
                api_prompt_lang = "中文"
            elif "英文" in prompt_language or "English" in prompt_language or "english" in prompt_language.lower():
                api_prompt_lang = "英文"
            elif "日文" in prompt_language or "Japanese" in prompt_language:
                api_prompt_lang = "日文"
            elif "韩文" in prompt_language or "Korean" in prompt_language:
                api_prompt_lang = "韩文"
            else:
                # 如果已经是 dict_language 的键，直接使用；否则转为小写尝试
                api_prompt_lang = prompt_language.lower()
            
            # 映射 text_language_final: "English" -> "英文", "Chinese" -> "中文"
            if text_language_final == "auto":
                api_text_lang = "auto"
            elif "中文" in text_language_final or "Chinese" in text_language_final:
                api_text_lang = "中文"
            elif "英文" in text_language_final or "English" in text_language_final or "english" in text_language_final.lower():
                api_text_lang = "英文"
            elif "日文" in text_language_final or "Japanese" in text_language_final:
                api_text_lang = "日文"
            elif "韩文" in text_language_final or "Korean" in text_language_final:
                api_text_lang = "韩文"
            else:
                # 如果已经是 dict_language 的键，直接使用；否则转为小写尝试
                api_text_lang = text_language_final.lower()


            # 文本切分：默认中等切分，strict 才走更密，避免过碎导致卡顿/漏字
            is_buffered_req = bool(data.get("buffered"))
            strict_segmented = _coerce_bool_param(data.get("strict_segmented"), False)
            long_text_stream = _coerce_bool_param(data.get("long_text_stream"), False)
            long_book_text = _is_long_book_text(text_cleaned) or long_text_stream

            default_cut_punc = "，。？！；：,.!?;:、…" if strict_segmented else ("。？！；：!?;:…" if long_book_text else "。？！!?；;")
            cut_punc = data.get("cut_punc", None) or default_cut_punc

            _max_text_len_val = data.get("max_text_len") if "max_text_len" in data else None
            if _max_text_len_val is None:
                if strict_segmented:
                    max_text_len = 46 if is_buffered_req else 58
                elif long_book_text:
                    max_text_len = 72 if is_buffered_req else 110
                else:
                    max_text_len = 80

                _ms = None
                try:
                    import api as _api_mod2
                    _spk2 = getattr(_api_mod2, "speaker_list", {}).get("default") if hasattr(_api_mod2, "speaker_list") else None
                    if _spk2 is not None and hasattr(_spk2, "gpt"):
                        _ms = getattr(_spk2.gpt, "max_sec", None)
                except Exception:
                    _ms = None
                if _ms is not None:
                    try:
                        cps = 5 if strict_segmented else (7 if long_book_text else 9)
                        floor_len = 32 if strict_segmented else (48 if long_book_text else 60)
                        max_text_len = max(floor_len, min(max_text_len, int(float(_ms) * cps)))
                    except Exception:
                        pass
            else:
                max_text_len = max(20, int(_max_text_len_val))

            segments = _split_text_for_buffer(text_cleaned, max_len=max_text_len, cut_punc=cut_punc)
            text_final = "\n".join(segments) if segments else text_cleaned
            if len(segments) > 1:
                logger.info(f"[synthesize] 目标文本已切分为 {len(segments)} 段，max_len={max_text_len}, strict={strict_segmented}")

            is_user_trained_voice = str((profile or {}).get("model_type") or "").strip().lower() == "user_trained"
            runtime_data = dict(data or {})
            voice_policy = {
                "tier": "normal",
                "cache_mode": "speed",
                "applied": False,
                "reasons": [],
            }
            if is_user_trained_voice and voice_id:
                runtime_data, voice_policy = _apply_user_voice_risk_policy(runtime_data, voice_id, profile)
                if voice_policy.get("applied"):
                    logger.info(
                        f"[synthesize] user_trained 风险分层策略已应用: voice_id={voice_id}, "
                        f"tier={voice_policy.get('tier')}, reasons={voice_policy.get('reasons')}, "
                        f"overrides={list((voice_policy.get('applied_overrides') or {}).keys())}"
                    )

            if is_user_trained_voice and voice_policy.get("tier") in ("risky", "strict") and len(segments) < 2:
                try:
                    forced_max_len = int(runtime_data.get("max_text_len", 24 if voice_policy.get("tier") == "strict" else 28))
                except Exception:
                    forced_max_len = 24 if voice_policy.get("tier") == "strict" else 28
                forced_max_len = max(16, min(56, forced_max_len))
                forced_cut_punc = runtime_data.get("cut_punc") or "，。？！；：,.!?;:、…"
                forced_segments = _split_text_for_buffer(text_cleaned, max_len=forced_max_len, cut_punc=forced_cut_punc)
                if len(forced_segments) >= 2:
                    segments = forced_segments
                    text_final = "\n".join(segments)
                    logger.info(
                        f"[synthesize] user_trained 高风险音色启用细粒度分段: "
                        f"voice_id={voice_id}, tier={voice_policy.get('tier')}, "
                        f"segments={len(segments)}, max_len={forced_max_len}"
                    )

            adaptive_text_payload = text_cleaned if text_cleaned else text_final

            inp_refs_payload = _build_inp_refs_payload(aux_ref_audio_paths, base_dir=now_dir)
            if runtime_data.get("buffered"):
                buffered_data = dict(runtime_data or {})
                buffered_data["_is_user_trained_voice"] = is_user_trained_voice
                buffered_data["_adaptive_text"] = adaptive_text_payload
                task_id, ready_urls, total = _create_buffer_task(
                    segments=segments,
                    data=buffered_data,
                    ref_audio_path=ref_audio_path,
                    ref_text_cleaned=ref_text_cleaned,
                    api_prompt_lang=api_prompt_lang,
                    api_text_lang=api_text_lang,
                    voice_id=voice_id,
                    aux_ref_audio_paths=aux_ref_audio_paths,
                    official_get_tts_wav_api=official_get_tts_wav_api,
                    debug_id=debug_id,
                )
                if debug_id:
                    _debug_set(debug_id, task_id=task_id, total_segments=total, segments_preview=[s[:120] for s in segments[:10]])
                    _debug_event(debug_id, "buffered.created", task_id=task_id, total=total)
                return JSONResponse({
                    "code": 0,
                    "task_id": task_id,
                    "debug_id": debug_id,
                    "segments": ready_urls,
                    "total_segments": total,
                }, status_code=200)

            segmented_sync_enabled = (
                is_user_trained_voice
                and _should_use_user_voice_segmented_sync(runtime_data, text_cleaned, segments)
            )
            if debug_id and is_user_trained_voice and len(segments) >= 2:
                _debug_event(
                    debug_id,
                    "segmented_sync.route",
                    enabled=segmented_sync_enabled,
                    segments=len(segments),
                    text_units=_count_text_units(text_cleaned),
                )
            if segmented_sync_enabled:
                try:
                    seg_sync_data = dict(runtime_data or {})
                    seg_sync_data["_is_user_trained_voice"] = True
                    seg_sync_data["_adaptive_text"] = adaptive_text_payload
                    audio_bytes_wav, seg_task_id, seg_merged_url, seg_total = _generate_wav_via_segmented_buffer_sync(
                        segments=segments,
                        data=seg_sync_data,
                        ref_audio_path=ref_audio_path,
                        ref_text_cleaned=ref_text_cleaned,
                        api_prompt_lang=api_prompt_lang,
                        api_text_lang=api_text_lang,
                        voice_id=voice_id,
                        aux_ref_audio_paths=aux_ref_audio_paths,
                        official_get_tts_wav_api=official_get_tts_wav_api,
                        debug_id=debug_id,
                    )
                    if debug_id:
                        _debug_set(
                            debug_id,
                            segmented_sync_task_id=seg_task_id,
                            segmented_sync_total=seg_total,
                            segmented_sync_merged_url=seg_merged_url,
                        )
                        _debug_event(
                            debug_id,
                            "segmented_sync.done",
                            task_id=seg_task_id,
                            total=seg_total,
                            merged_url=seg_merged_url,
                            wav_bytes=len(audio_bytes_wav),
                        )

                    if voice_id and (voice_id not in QWEN_BASE_VOICE_IDS):
                        audio_bytes_wav, boost_meta = _boost_low_rms_wav_if_needed(audio_bytes_wav)
                        if boost_meta.get("applied"):
                            logger.info(
                                f"[synthesize] 低音量补偿已应用 voice_id={voice_id}: "
                                f"gain={boost_meta.get('gain'):.2f}, rms {boost_meta.get('rms_before'):.1f}->{boost_meta.get('rms_after'):.1f}"
                            )

                    logger.info(
                        f"[synthesize] user_trained segmented_sync 成功: voice_id={voice_id}, "
                        f"segments={seg_total}, merged={seg_merged_url}"
                    )

                    if debug_id:
                        wav_info = _try_get_wav_info(audio_bytes_wav)
                        _debug_set(
                            debug_id,
                            wav_bytes=len(audio_bytes_wav),
                            wav_sec=wav_info.get("duration_sec"),
                            wav_sr=wav_info.get("sr"),
                            wav_frames=wav_info.get("frames"),
                        )

                    return_url = bool(runtime_data.get("return_url"))
                    if return_url or len(audio_bytes_wav) > 10 * 1024 * 1024:
                        tts_dir = _resolve_tts_static_dir()
                        os.makedirs(tts_dir, exist_ok=True)
                        fname = f"synth_{voice_id or 'default'}_{int(time.time())}_{uuid.uuid4().hex[:8]}.wav"
                        fpath = os.path.join(tts_dir, fname)
                        with open(fpath, "wb") as f:
                            f.write(audio_bytes_wav)
                        audio_url = f"/static/tts/{fname}"
                        return JSONResponse({
                            "code": 0,
                            "audio_url": audio_url,
                            "size": len(audio_bytes_wav),
                            "debug_id": debug_id,
                            "source": "segmented_sync",
                        }, status_code=200)

                    _headers = {"Content-Disposition": f"attachment; filename=synthesized_{voice_id}.wav"}
                    if debug_id:
                        _headers["X-Debug-Id"] = debug_id
                    return StreamingResponse(
                        BytesIO(audio_bytes_wav),
                        media_type="audio/wav",
                        headers=_headers,
                    )
                except Exception as seg_sync_err:
                    logger.warning(f"[synthesize] segmented_sync 失败，回退单次生成: {seg_sync_err}")

            # 调用官方 api.py 的 get_tts_wav（返回 WAV 字节流）
            # 官方函数签名：get_tts_wav(ref_wav_path, prompt_text, prompt_language, text, text_language,
            #                            top_k=15, top_p=0.6, temperature=0.6, speed=1, inp_refs=inp_refs_payload or None,
            #                            sample_steps=32, if_sr=False, spk="default")
            try:
                import api as official_api_module
                official_api_module.stream_mode = "close"
                official_api_module.media_type = "wav"
            except Exception:
                pass
            top_k_base = int(runtime_data.get("top_k", 15))
            top_p_base = float(runtime_data.get("top_p", 0.6))
            temperature_base = float(runtime_data.get("temperature", 0.6))
            repetition_penalty_base = float(runtime_data.get("repetition_penalty", 1.18))
            speed_base = float(runtime_data.get("speed", 1.0))
            if is_user_trained_voice and _coerce_bool_param(runtime_data.get("hq_user_voice_speed_boost"), True):
                try:
                    min_speed = float(runtime_data.get("hq_user_voice_min_speed", 1.15))
                except Exception:
                    min_speed = 1.15
                min_speed = max(1.00, min(1.25, min_speed))
                speed_base = max(speed_base, min_speed)
            if is_user_trained_voice and _coerce_bool_param(runtime_data.get("hq_user_voice_fast_decode"), True):
                top_k_base = min(top_k_base, 16)
                top_p_base = min(top_p_base, 0.78)
                temperature_base = min(temperature_base, 0.30)
                repetition_penalty_base = max(repetition_penalty_base, 1.22)
            sample_steps_raw = int(runtime_data.get("sample_steps", 32))
            sample_steps_base = _resolve_adaptive_user_voice_sample_steps(
                data=runtime_data,
                text=text_final,
                default_steps=sample_steps_raw,
                is_user_trained_voice=is_user_trained_voice,
            )
            if sample_steps_base != sample_steps_raw:
                logger.info(f"[synthesize] user_trained adaptive sample_steps: {sample_steps_raw} -> {sample_steps_base}")

            def _gen_once_with_profile(profile: dict, attempt_tag: str) -> bytes:
                profile_speed = float(profile.get("speed", speed_base))
                target_max_sec = _estimate_infer_max_sec_limit(
                    text_final,
                    speed=profile_speed,
                    is_user_trained_voice=is_user_trained_voice,
                    risk_tier=voice_policy.get("tier"),
                )
                if (
                    is_user_trained_voice
                    and str(voice_policy.get("tier") or "").strip().lower() in ("risky", "strict")
                    and _coerce_bool_param(runtime_data.get("hq_user_voice_relax_max_sec"), True)
                ):
                    target_max_sec = 0
                sec_override_applied = False
                sec_override_old = None
                sec_override_new = None
                with _INFER_MAX_SEC_OVERRIDE_LOCK:
                    sec_override_applied, sec_restore_items, sec_override_old, sec_override_new = _apply_temporary_infer_max_sec(target_max_sec)
                    try:
                        gen_local = official_get_tts_wav_api(
                            ref_wav_path=ref_audio_path,
                            prompt_text=ref_text_cleaned,
                            prompt_language=api_prompt_lang,
                            text=text_final,
                            text_language=api_text_lang,
                            top_k=int(profile.get("top_k", top_k_base)),
                            top_p=float(profile.get("top_p", top_p_base)),
                            temperature=float(profile.get("temperature", temperature_base)),
                            repetition_penalty=float(profile.get("repetition_penalty", repetition_penalty_base)),
                            speed=profile_speed,
                            inp_refs=inp_refs_payload or None,
                            sample_steps=int(profile.get("sample_steps", sample_steps_base)),
                            if_sr=False,
                            spk="default",
                        )
                    finally:
                        _restore_temporary_infer_max_sec(sec_restore_items)
                t_start_local = time.time()
                audio_local, gen_stats_local = _collect_generator_bytes_with_stats(gen_local)
                if debug_id:
                    _debug_event(
                        debug_id,
                        "synthesize.gen.done",
                        attempt=attempt_tag,
                        gen_chunks=gen_stats_local.get("chunks"),
                        gen_bytes=gen_stats_local.get("bytes"),
                        cost_ms=int((time.time()-t_start_local)*1000),
                        max_sec_target=target_max_sec or None,
                        max_sec_override_applied=bool(sec_override_applied),
                        max_sec_before=sec_override_old,
                        max_sec_after=sec_override_new,
                    )
                if not audio_local:
                    raise StopIteration("empty audio bytes")
                return audio_local

            primary_profile = {
                "top_k": top_k_base,
                "top_p": top_p_base,
                "temperature": temperature_base,
                "repetition_penalty": repetition_penalty_base,
                "speed": speed_base,
                "sample_steps": sample_steps_base,
            }
            effective_primary_profile = dict(primary_profile)
            hint_source = ""
            if is_user_trained_voice and voice_id:
                cached_profile = _get_cached_voice_gen_profile(voice_id, primary_profile)
                if cached_profile:
                    effective_primary_profile = _clamp_cached_user_voice_profile(cached_profile, primary_profile, cache_mode=voice_policy.get("cache_mode", "speed"))
                    hint_source = "cache"
                elif _coerce_bool_param(runtime_data.get("hq_user_voice_bootstrap"), True):
                    boot_profile = _build_recent_user_voice_bootstrap_profile(primary_profile, profile)
                    if boot_profile != primary_profile:
                        effective_primary_profile = boot_profile
                        hint_source = "recent_voice_bootstrap"
            if hint_source:
                logger.info(f"[synthesize] user_trained 使用参数提示: voice_id={voice_id}, source={hint_source}, profile={effective_primary_profile}")
            if is_user_trained_voice and _coerce_bool_param(runtime_data.get("hq_user_voice_fast_decode"), True):
                effective_primary_profile["top_k"] = min(int(effective_primary_profile.get("top_k", top_k_base)), 16)
                effective_primary_profile["top_p"] = min(float(effective_primary_profile.get("top_p", top_p_base)), 0.78)
                effective_primary_profile["temperature"] = min(float(effective_primary_profile.get("temperature", temperature_base)), 0.30)
                effective_primary_profile["repetition_penalty"] = max(float(effective_primary_profile.get("repetition_penalty", repetition_penalty_base)), 1.22)

            audio_bytes_wav = _gen_once_with_profile(effective_primary_profile, "base")
            best_profile = dict(effective_primary_profile)

            seg_units = _count_text_units(text_final)
            under_tol = 0.92 if seg_units >= 14 else 0.90
            over_tol = 1.20 if seg_units >= 14 else 1.23
            under_tol, over_tol = _apply_voice_risk_tolerance(under_tol, over_tol, voice_policy.get("tier"))

            if _is_abnormal_generated_audio(text_final, audio_bytes_wav, speed=best_profile["speed"], under_tolerance=under_tol, over_tolerance=over_tol):
                best_audio_bytes = audio_bytes_wav
                best_score = _duration_match_score(text_final, audio_bytes_wav, speed=best_profile["speed"])
                is_under_initial = _is_under_generated_audio(
                    text_final,
                    audio_bytes_wav,
                    speed=float(best_profile.get("speed", speed_base)),
                    tolerance=under_tol,
                )
                is_over_initial = _is_over_generated_audio(
                    text_final,
                    audio_bytes_wav,
                    speed=float(best_profile.get("speed", speed_base)),
                    tolerance=over_tol,
                )
                is_low_energy_initial = _is_low_energy_generated_audio(text_final, audio_bytes_wav)

                if is_user_trained_voice:
                    if is_over_initial and (not is_under_initial):
                        # 对“明显偏长”默认直接返回 base，避免重试纯增时延；需要时可显式开启重试。
                        if _coerce_bool_param(runtime_data.get("hq_user_voice_over_retry"), False):
                            retry_profiles = [
                                {
                                    "top_k": max(16, top_k_base),
                                    "top_p": min(0.88, max(0.80, top_p_base)),
                                    "temperature": min(0.40, max(0.30, temperature_base)),
                                    "repetition_penalty": min(1.20, max(1.12, repetition_penalty_base)),
                                    "speed": max(1.10, speed_base),
                                    "sample_steps": max(22, min(28, sample_steps_base)),
                                },
                            ]
                        else:
                            retry_profiles = []
                            logger.info(f"[synthesize] user_trained over-generated: skip retry for speed, voice_id={voice_id}")
                    elif is_under_initial:
                        # 过短时再做“稳质补偿”，但最多两轮。
                        retry_profiles = [
                            {
                                "top_k": max(18, top_k_base),
                                "top_p": max(0.86, top_p_base),
                                "temperature": min(0.38, max(0.30, temperature_base)),
                                "repetition_penalty": min(1.22, max(1.14, repetition_penalty_base)),
                                "speed": min(0.98, speed_base),
                                "sample_steps": max(32, sample_steps_base),
                            },
                            {
                                "top_k": max(20, top_k_base),
                                "top_p": max(0.90, top_p_base),
                                "temperature": min(0.36, max(0.28, temperature_base)),
                                "repetition_penalty": min(1.24, max(1.16, repetition_penalty_base)),
                                "speed": min(0.95, speed_base),
                                "sample_steps": max(36, sample_steps_base + 4),
                            },
                        ]
                    elif is_low_energy_initial:
                        retry_profiles = [
                            {
                                "top_k": max(17, top_k_base),
                                "top_p": max(0.84, top_p_base),
                                "temperature": min(0.38, max(0.30, temperature_base)),
                                "repetition_penalty": min(1.22, max(1.14, repetition_penalty_base)),
                                "speed": max(0.98, speed_base),
                                "sample_steps": max(30, min(36, sample_steps_base + 2)),
                            },
                        ]
                    else:
                        retry_profiles = [
                            {
                                "top_k": max(17, top_k_base),
                                "top_p": max(0.84, top_p_base),
                                "temperature": min(0.38, max(0.30, temperature_base)),
                                "repetition_penalty": min(1.20, max(1.14, repetition_penalty_base)),
                                "speed": max(0.99, speed_base),
                                "sample_steps": max(30, min(36, sample_steps_base + 2)),
                            },
                        ]
                else:
                    retry_profiles = [
                        {
                            "top_k": max(16, top_k_base),
                            "top_p": max(0.82, top_p_base),
                            "temperature": min(0.42, max(0.32, temperature_base)),
                            "repetition_penalty": min(1.20, max(1.14, repetition_penalty_base)),
                            "speed": min(0.98, speed_base),
                            "sample_steps": max(36, sample_steps_base),
                        },
                        {
                            "top_k": max(18, top_k_base),
                            "top_p": max(0.88, top_p_base),
                            "temperature": min(0.40, max(0.30, temperature_base)),
                            "repetition_penalty": min(1.22, max(1.16, repetition_penalty_base)),
                            "speed": min(0.94, speed_base),
                            "sample_steps": max(44, sample_steps_base),
                        },
                        {
                            "top_k": max(20, top_k_base),
                            "top_p": max(0.90, top_p_base),
                            "temperature": min(0.36, max(0.28, temperature_base)),
                            "repetition_penalty": min(1.24, max(1.18, repetition_penalty_base)),
                            "speed": min(0.92, speed_base),
                            "sample_steps": max(52, sample_steps_base),
                        },
                    ]
                for ridx, rp in enumerate(retry_profiles, start=1):
                    try:
                        retry_audio_bytes = _gen_once_with_profile(rp, f"retry{ridx}")
                    except StopIteration:
                        continue
                    retry_score = _duration_match_score(text_final, retry_audio_bytes, speed=rp["speed"])
                    if retry_score < best_score:
                        best_audio_bytes = retry_audio_bytes
                        best_score = retry_score
                        best_profile = dict(rp)
                    if not _is_abnormal_generated_audio(text_final, retry_audio_bytes, speed=rp["speed"], under_tolerance=under_tol, over_tolerance=over_tol):
                        logger.info(f"[synthesize] 分级重试第{ridx}轮通过")
                        best_audio_bytes = retry_audio_bytes
                        best_profile = dict(rp)
                        break

                # 兜底：若仍明显漏读，再做一轮更保守参数尝试。
                if _is_under_generated_audio(text_final, best_audio_bytes, speed=float(best_profile.get("speed", speed_base)), tolerance=0.85):
                    rescue_speed = min(0.94, speed_base) if is_user_trained_voice else min(0.88, speed_base)
                    rescue_steps = max(40, sample_steps_base + 6) if is_user_trained_voice else max(60, sample_steps_base)
                    rescue_profile = {
                        "top_k": max(20, top_k_base),
                        "top_p": max(0.92, top_p_base),
                        "temperature": min(0.34, max(0.26, temperature_base)),
                        "repetition_penalty": min(1.26, max(1.18, repetition_penalty_base)),
                        "speed": rescue_speed,
                        "sample_steps": rescue_steps,
                    }
                    try:
                        rescue_audio = _gen_once_with_profile(rescue_profile, "rescue")
                        rescue_score = _duration_match_score(text_final, rescue_audio, speed=rescue_profile["speed"])
                        if (rescue_score <= best_score * 1.20) or (not _is_under_generated_audio(text_final, rescue_audio, speed=rescue_profile["speed"], tolerance=0.90)):
                            logger.info("[synthesize] 兜底重试通过")
                            best_audio_bytes = rescue_audio
                            best_profile = dict(rescue_profile)
                    except StopIteration:
                        pass

                audio_bytes_wav = best_audio_bytes
                if is_user_trained_voice and str(voice_policy.get("tier") or "").strip().lower() != "risky":
                    audio_bytes_wav, trim_meta = _trim_over_generated_audio_if_needed(
                        text_final,
                        audio_bytes_wav,
                        speed=float(best_profile.get("speed", speed_base)),
                        over_tolerance=over_tol,
                    )
                    if trim_meta.get("applied"):
                        logger.info(
                            f"[synthesize] over-generated 裁剪已应用: "
                            f"voice_id={voice_id}, src={trim_meta.get('src_sec')}, dst={trim_meta.get('dst_sec')}"
                        )

            if is_user_trained_voice and voice_id:
                source = "retry_or_bootstrap" if (best_profile != primary_profile) else "base"
                cache_profile = _clamp_cached_user_voice_profile(best_profile, primary_profile, cache_mode=voice_policy.get("cache_mode", "speed"))
                _remember_voice_gen_profile(voice_id, cache_profile, source=source)

            # 仅对训练音色做低音量兜底放大，避免“有时几乎听不见”。
            if voice_id and (voice_id not in QWEN_BASE_VOICE_IDS):
                audio_bytes_wav, boost_meta = _boost_low_rms_wav_if_needed(audio_bytes_wav)
                if boost_meta.get("applied"):
                    logger.info(
                        f"[synthesize] 低音量补偿已应用 voice_id={voice_id}: "
                        f"gain={boost_meta.get('gain'):.2f}, rms {boost_meta.get('rms_before'):.1f}->{boost_meta.get('rms_after'):.1f}"
                    )

            logger.info(f"[synthesize] 推理成功（使用官方 api.py），WAV 音频大小: {len(audio_bytes_wav)} 字节")

            if debug_id:
                wav_info = _try_get_wav_info(audio_bytes_wav)
                _debug_set(
                    debug_id,
                    wav_bytes=len(audio_bytes_wav),
                    wav_sec=wav_info.get("duration_sec"),
                    wav_sr=wav_info.get("sr"),
                    wav_frames=wav_info.get("frames"),
                )


            # 大文件可返回URL（避免小程序内存/解码限制）
            return_url = bool(runtime_data.get("return_url"))
            if return_url or len(audio_bytes_wav) > 10 * 1024 * 1024:
                tts_dir = _resolve_tts_static_dir()
                os.makedirs(tts_dir, exist_ok=True)
                fname = f"synth_{voice_id or 'default'}_{int(time.time())}_{uuid.uuid4().hex[:8]}.wav"
                fpath = os.path.join(tts_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(audio_bytes_wav)
                audio_url = f"/static/tts/{fname}"
                return JSONResponse({"code": 0, "audio_url": audio_url, "size": len(audio_bytes_wav), "debug_id": debug_id}, status_code=200)

            # 直接返回 WAV 字节流
            _headers = {"Content-Disposition": f"attachment; filename=synthesized_{voice_id}.wav"}
            if debug_id:
                _headers["X-Debug-Id"] = debug_id
            return StreamingResponse(
                BytesIO(audio_bytes_wav),
                media_type="audio/wav",
                headers=_headers
            )
        else:
            # 回退方案：使用 inference_webui
            logger.warning("[synthesize] 使用回退方案 inference_webui")
            gen = official_get_tts_wav_webui(
                ref_wav_path=ref_audio_path,
                prompt_text=ref_text_cleaned,
                prompt_language=prompt_language,
                text=text_cleaned,
                text_language=text_language_final,
                how_to_cut="不切",
                top_k=int(data.get("top_k", 20)),
                top_p=float(data.get("top_p", 0.6)),
                temperature=float(data.get("temperature", 0.6)),
            repetition_penalty=float(data.get("repetition_penalty", 1.35)),
                ref_free=False,
                speed=float(data.get("speed", 1.0)),
                if_freeze=False,
                inp_refs=inp_refs_payload or None,
                sample_steps=int(data.get("sample_steps", 8)),
                if_sr=False,
                pause_second=0.3,
            )
            sr, audio_np = next(gen)
            audio_bytes = BytesIO()
            sf.write(audio_bytes, audio_np.astype("int16"), sr, format='WAV')
            audio_bytes.seek(0)
            audio_data = audio_bytes.getvalue()

            return_url = bool(runtime_data.get("return_url"))
            if return_url or len(audio_data) > 10 * 1024 * 1024:
                tts_dir = _resolve_tts_static_dir()
                os.makedirs(tts_dir, exist_ok=True)
                fname = f"synth_{voice_id or 'default'}_{int(time.time())}_{uuid.uuid4().hex[:8]}.wav"
                fpath = os.path.join(tts_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(audio_data)
                audio_url = f"/static/tts/{fname}"
                return JSONResponse({"code": 0, "audio_url": audio_url, "size": len(audio_data)}, status_code=200)

            return StreamingResponse(
                BytesIO(audio_data),
                media_type="audio/wav",
                headers={
                    "Content-Disposition": f"attachment; filename=synthesized_{voice_id}.wav"
                }
            )
        
    except StopIteration:
        logger.error("[synthesize] get_tts_wav generator 没有返回数据")
        raise HTTPException(status_code=500, detail="推理失败：生成器未返回音频数据")
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"[synthesize] 推理失败: {str(e)}\n{error_detail}")
        raise HTTPException(status_code=500, detail=f"推理失败: {str(e)}")
    


@app.get("/synthesize/buffered/segment")
async def synthesize_buffered_segment(task_id: str, index: int):
    _cleanup_buffer_tasks()
    with BUFFER_TASKS_LOCK:
        task = BUFFER_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    total = task.get("total", 0)
    if index < 0 or index >= total:
        raise HTTPException(status_code=400, detail="段索引超出范围")
    url = task.get("segments", [None] * total)[index]
    if url:
        return JSONResponse({"code": 0, "audio_url": url, "index": index, "done": task.get("done", False)}, status_code=200)
    if task.get("error"):
        raise HTTPException(status_code=500, detail=task.get("error"))
    return JSONResponse({"code": 1, "status": "pending"}, status_code=202)



@app.get("/synthesize/buffered/status")
async def synthesize_buffered_status(task_id: str):
    """查询 buffered 任务整体状态（用于前端判断是否已生成完整音频）。"""
    _cleanup_buffer_tasks()
    with BUFFER_TASKS_LOCK:
        task = BUFFER_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        segs = list(task.get("segments") or [])
        total = int(task.get("total") or len(segs) or 0)
        ready = sum(1 for u in segs[:total] if u)
        done = bool(task.get("done", False))
        err = task.get("error")
        merged_url = task.get("merged_url")
    return JSONResponse({"code": 0, "task_id": task_id, "total": total, "ready": ready, "done": done, "error": err, "merged_url": merged_url})


@app.get("/synthesize/buffered/merged")
async def synthesize_buffered_merged(task_id: str):
    """当所有分段都就绪后，合并为单个 WAV 并返回 URL；未就绪则 202。"""
    _cleanup_buffer_tasks()
    with BUFFER_TASKS_LOCK:
        task = BUFFER_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        err = task.get("error")
        merged_url = task.get("merged_url")
        segs = list(task.get("segments") or [])
        total = int(task.get("total") or len(segs) or 0)
    if err:
        raise HTTPException(status_code=500, detail=err)
    if merged_url:
        return JSONResponse({"code": 0, "audio_url": merged_url, "task_id": task_id}, status_code=200)
    if total <= 0 or len(segs) < total or any((u is None) for u in segs[:total]):
        return JSONResponse({"code": 1, "status": "pending"}, status_code=202)

    try:
        merged_url = _merge_wav_segments_to_static(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并失败: {str(e)}")

    if not merged_url:
        return JSONResponse({"code": 1, "status": "pending"}, status_code=202)
    return JSONResponse({"code": 0, "audio_url": merged_url, "task_id": task_id}, status_code=200)



@app.get("/debug/tts")
async def debug_tts_list(limit: int = 20):
    _cleanup_tts_debug()
    limit = max(1, min(int(limit), 200))
    with TTS_DEBUG_LOCK:
        items = sorted(TTS_DEBUG.values(), key=lambda r: r.get("created_at", 0), reverse=True)[:limit]
        return JSONResponse({"code": 0, "items": [{"debug_id": r.get("debug_id"), "created_at": r.get("created_at"), "text_len": len((r.get("text_cleaned") or ""))} for r in items]})

@app.get("/debug/tts/{debug_id}")
async def debug_tts_get(debug_id: str):
    _cleanup_tts_debug()
    with TTS_DEBUG_LOCK:
        rec = TTS_DEBUG.get(debug_id)
    if not rec:
        raise HTTPException(status_code=404, detail="debug_id 不存在或已过期")
    return JSONResponse({"code": 0, "record": rec})

@app.get("/debug/tts/by_task/{task_id}")
async def debug_tts_by_task(task_id: str):
    _cleanup_tts_debug()
    with BUFFER_TASKS_LOCK:
        task = BUFFER_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    debug_id = task.get("debug_id")
    if not debug_id:
        raise HTTPException(status_code=404, detail="该任务未开启 debug")
    with TTS_DEBUG_LOCK:
        rec = TTS_DEBUG.get(debug_id)
    if not rec:
        raise HTTPException(status_code=404, detail="debug_id 不存在或已过期")
    return JSONResponse({"code": 0, "debug_id": debug_id, "record": rec})
def _wave_header_chunk(frame_input=b"", channels=1, sample_width=2, sample_rate=32000):
    wav_buf = BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(frame_input)
    wav_buf.seek(0)
    return wav_buf.read()


def _coerce_bool_param(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def _normalize_stream_request_data(data: dict, format_hint: str = "wav") -> dict:
    payload = dict(data or {})

    if not payload.get("format"):
        media_type = str(payload.get("media_type") or "").strip().lower()
        if media_type in {"wav", "wave", "audio/wav", "audio/x-wav", "aac", "audio/aac"}:
            payload["format"] = "wav"
        elif format_hint:
            payload["format"] = format_hint

    payload["debug"] = _coerce_bool_param(payload.get("debug"), False)
    payload["strict_segmented"] = _coerce_bool_param(payload.get("strict_segmented"), False)
    payload["long_text_stream"] = _coerce_bool_param(payload.get("long_text_stream"), False)
    return payload


async def _synthesize_stream_impl(request: Request, data: dict, chunk_ms: int = 200, format: str = "wav", route_name: str = "synthesize/stream"):
    data = _normalize_stream_request_data(data, format_hint=format)

    voice_id = data.get("voice_id")
    user_id = data.get("user_id") or data.get("model_name")
    text = data.get("text")
    text_language = data.get("text_language") or data.get("language") or "zh"
    _format = (data.get("format") or format or "wav").lower()
    chunk_ms = int(data.get("chunk_ms", chunk_ms or 200))
    chunk_ms = max(50, min(1000, chunk_ms))
    debug_id = None

    if bool(data.get("debug")):
        debug_id = _new_debug_record({
            "voice_id": voice_id,
            "user_id": user_id,
            "route": route_name,
            "format": _format,
            "chunk_ms": chunk_ms,
        })

    refer_wav_path = data.get("refer_wav_path") or data.get("ref_wav_path") or data.get("ref_audio")
    prompt_text = data.get("prompt_text")
    prompt_language = data.get("prompt_language") or "中文"
    raw_aux_refs = data.get("inp_refs")
    if raw_aux_refs is None:
        raw_aux_refs = data.get("aux_ref_audio_paths")
    if raw_aux_refs is None:
        raw_aux_refs = data.get("ref_audio_paths")

    if not text or not str(text).strip():
        raise HTTPException(status_code=400, detail="缺少要合成的文本 text")

    profile_ref_guard = None
    profile = {}
    pre_ref_risk_tier = "normal"

    # 选择模型与参考信息
    if refer_wav_path and prompt_text:
        ref_audio_path = refer_wav_path
        ref_text = prompt_text
        ref_language_raw = prompt_language
        if not os.path.isabs(ref_audio_path):
            ref_audio_path = os.path.abspath(os.path.join(now_dir, ref_audio_path))
        if not os.path.exists(ref_audio_path):
            raise HTTPException(status_code=400, detail=f"参考音频文件不存在: {ref_audio_path}")
        gpt_path_local = data.get("gpt_path") or os.environ.get("gpt_path")
        sovits_path_local = data.get("sovits_path") or os.environ.get("sovits_path")
        if not gpt_path_local or not sovits_path_local:
            gpt_path_local = gpt_path_local or globals().get("gpt_path")
            sovits_path_local = sovits_path_local or globals().get("sovits_path")
        if not gpt_path_local or not sovits_path_local:
            raise HTTPException(status_code=400, detail="使用参考音频模式时，需要提供 gpt_path 和 sovits_path，或先加载模型")
    else:
        load_voice_library_from_file()
        if not voice_id and user_id:
            for vid, info in VOICE_LIBRARY.items():
                if info.get("name") == user_id:
                    voice_id = vid
                    break
        if not voice_id:
            raise HTTPException(status_code=400, detail="请提供 voice_id/user_id/model_name 或 refer_wav_path+prompt_text 来选择声音模型")
        if voice_id not in VOICE_LIBRARY:
            raise HTTPException(status_code=404, detail=f"未找到 voice_id 对应的模型: {voice_id}")
        profile = VOICE_LIBRARY[voice_id]
        if str((profile or {}).get("model_type") or "").strip().lower() == "user_trained":
            try:
                pre_ref_risk_tier = str((_resolve_user_voice_risk_policy(voice_id, profile) or {}).get("tier") or "normal").strip().lower()
            except Exception:
                pre_ref_risk_tier = "normal"

        if _is_qwen_voice_profile(profile):
            text_cleaned = sanitize_text(text)
            if not has_speakable_content(text_cleaned):
                raise HTTPException(status_code=400, detail="目标文本缺少可发音字符，请输入完整句子后重试")
            try:
                audio_bytes_wav, used_voice, source_tag = await _qwen_tts_generate_wav(text_cleaned, profile)
            except Exception as qe:
                raise HTTPException(status_code=503, detail=f"Qwen基础音色流式合成失败: {qe}")

            wav_reader = wave.open(BytesIO(audio_bytes_wav), "rb")
            sample_rate = wav_reader.getframerate()
            channels = wav_reader.getnchannels()
            sample_width = wav_reader.getsampwidth()
            frames_per_chunk = max(1, int(sample_rate * (chunk_ms / 1000.0)))

            media_type = "audio/wav" if _format in ["wav", "wave"] else "application/octet-stream"
            headers = {
                "X-Sample-Rate": str(sample_rate),
                "X-Channels": str(channels),
                "X-Sample-Width": str(sample_width),
                "X-PCM-Format": "s16le",
                "X-Qwen-Voice": str(used_voice or ""),
                "X-Qwen-Source": str(source_tag or "qwen_tts"),
            }

            async def generator():
                try:
                    if _format in ["wav", "wave"]:
                        yield _wave_header_chunk(channels=channels, sample_width=sample_width, sample_rate=sample_rate)
                    while True:
                        if await request.is_disconnected():
                            break
                        data_chunk = wav_reader.readframes(frames_per_chunk)
                        if not data_chunk:
                            break
                        yield data_chunk
                finally:
                    try:
                        wav_reader.close()
                    except Exception:
                        pass

            return StreamingResponse(generator(), media_type=media_type, headers=headers)

        ref_audio_path = profile.get("ref_audio_path")
        ref_text = profile.get("ref_text")
        ref_language_raw = profile.get("ref_language", "中文")
        profile_ref_guard = _build_voice_reference_guard(
              voice_id=voice_id,
              profile=profile,
              req_max_refs=int(data.get("max_ref_samples", 6)),
              req_max_aux_refs=int(data.get("max_aux_refs", 2)),
          )
        gpt_path_local = profile.get("gpt_path")
        sovits_path_local = profile.get("sovits_path")
        if not ref_audio_path:
            raise HTTPException(status_code=400, detail="该模型未记录有效的参考音频，无法自动推理")
        # ref_text 允许为空，后续会从同目录 sentence_*.txt 自动补全
        if not os.path.isabs(ref_audio_path):
            ref_audio_path = os.path.abspath(os.path.join(now_dir, ref_audio_path))
        if not os.path.exists(ref_audio_path):
            raise HTTPException(status_code=400, detail=f"参考音频文件不存在: {ref_audio_path}。请检查模型配置中的 ref_audio_path。")
    # 参考包组装：主参考 + 辅助参考（默认仅少量，避免卡顿）
    effective_max_refs = int(data.get("max_ref_samples", 6))
    effective_max_aux_refs = int(data.get("max_aux_refs", 2))
    dataset_scan_enabled = True
    if profile_ref_guard:
        effective_max_refs = int(profile_ref_guard.get("max_refs", effective_max_refs))
        effective_max_aux_refs = int(profile_ref_guard.get("max_aux_refs", effective_max_aux_refs))
        dataset_scan_enabled = bool(profile_ref_guard.get("dataset_scan_enabled", True))
        if profile_ref_guard.get("reason"):
            logger.warning(
                f"[ref_guard] voice_id={voice_id} 启用参考保护: reason={profile_ref_guard.get('reason')}, "
                f"max_refs={effective_max_refs}, max_aux_refs={effective_max_aux_refs}, "
                f"dataset_scan_enabled={dataset_scan_enabled}"
            )

    text_for_ref_match = sanitize_text(text)
    ref_bundle = _resolve_reference_bundle(
        ref_audio_path=ref_audio_path,
        ref_text=ref_text,
        base_dir=now_dir,
        extra_ref_paths=raw_aux_refs,
        max_refs=effective_max_refs,
        max_aux_refs=effective_max_aux_refs,
        target_text=text_for_ref_match,
        prompt_max_chars=int(data.get("prompt_max_chars", 40)),
        dataset_scan_enabled=dataset_scan_enabled,
        prefer_primary_sentence_text=bool(profile_ref_guard),
        prefer_target_primary_sample=bool(profile_ref_guard) and pre_ref_risk_tier in ("risky", "strict"),
    )
    ref_audio_path = ref_bundle.get("primary_ref_audio")
    aux_ref_audio_paths = ref_bundle.get("aux_ref_audio_paths") or []
    ref_text = ref_bundle.get("prompt_text") or ""

    if not ref_audio_path:
        raise HTTPException(status_code=400, detail="参考音频路径为空，无法推理")
    if not os.path.exists(ref_audio_path):
        raise HTTPException(status_code=400, detail=f"参考音频文件不存在: {ref_audio_path}。请检查模型配置中的 ref_audio_path。")
    if not ref_text:
        raise HTTPException(status_code=400, detail="参考文本为空，无法推理")

    ref_language = dict_language.get(ref_language_raw, "all_zh")
    if ref_language not in dict_language.values():
        ref_language = "all_zh"

    logger.info(
        f"[synthesize/stream] 使用 voice_id={voice_id}, ref={ref_audio_path}, "
        f"aux_refs={len(aux_ref_audio_paths)}, lang={ref_language_raw}->{ref_language}"
    )

    inp_refs_payload = _build_inp_refs_payload(aux_ref_audio_paths, base_dir=now_dir)

    # 文本清理与语言检测
    ref_text_cleaned = normalize_ref_text_for_infer(ref_text, max_chars=max(20, int(data.get("prompt_max_chars", 40))))
    text_cleaned = sanitize_text(text)
    if not has_speakable_content(text_cleaned):
        raise HTTPException(status_code=400, detail="目标文本缺少可发音字符，请输入完整句子后重试")

    prompt_language_final = "Chinese"
    text_language_final = detect_text_language(text_cleaned)

    try:
        from api import (
            get_tts_wav as official_get_tts_wav_api,
            change_gpt_sovits_weights as official_change_gpt_sovits_weights,
            speaker_list as api_speaker_list,
            cut_text as official_cut_text,
        )
        USE_OFFICIAL_API = True
    except Exception as e:
        logger.warning(f"[synthesize/stream] 无法导入官方 api.py: {e}，使用 inference_webui")
        USE_OFFICIAL_API = False
        from GPT_SoVITS.inference_webui import (
            get_tts_wav as official_get_tts_wav_webui,
        )

    if USE_OFFICIAL_API:
        # 使用缓存感知的切权重，避免同一模型重复加载。
        if gpt_path_local and sovits_path_local:
            try:
                _ensure_official_model_loaded(official_change_gpt_sovits_weights, gpt_path_local, sovits_path_local)
                if "default" in api_speaker_list and api_speaker_list["default"] is not None:
                    try:
                        api_speaker_list["default"].name = str(voice_id or "default")
                    except Exception:
                        pass
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        if "中文" in prompt_language_final or "Chinese" in prompt_language_final:
            api_prompt_lang = "中文"
        elif "英文" in prompt_language_final or "English" in prompt_language_final or "english" in prompt_language_final.lower():
            api_prompt_lang = "英文"
        elif "日文" in prompt_language_final or "Japanese" in prompt_language_final:
            api_prompt_lang = "日文"
        elif "韩文" in prompt_language_final or "Korean" in prompt_language_final:
            api_prompt_lang = "韩文"
        else:
            api_prompt_lang = prompt_language_final.lower()

        if text_language_final == "auto":
            api_text_lang = "auto"
        elif "中文" in text_language_final or "Chinese" in text_language_final:
            api_text_lang = "中文"
        elif "英文" in text_language_final or "English" in text_language_final or "english" in text_language_final.lower():
            api_text_lang = "英文"
        elif "日文" in text_language_final or "Japanese" in text_language_final:
            api_text_lang = "日文"
        elif "韩文" in text_language_final or "Korean" in text_language_final:
            api_text_lang = "韩文"
        else:
            api_text_lang = text_language_final.lower()

        strict_segmented = _coerce_bool_param(data.get("strict_segmented"), False)
        long_text_stream = _coerce_bool_param(data.get("long_text_stream"), False)
        long_book_text = _is_long_book_text(text_cleaned) or long_text_stream

        cut_punc = data.get("cut_punc", None)
        if not cut_punc:
            cut_punc = "，。？！；：,.!?;:、…" if strict_segmented else ("。？！；：!?;:…" if long_book_text else "。？！!?；;")

        _max_text_len_val = data.get("max_text_len") if "max_text_len" in data else None
        if _max_text_len_val is None:
            if strict_segmented:
                max_text_len = 58
            elif long_book_text:
                max_text_len = 100
            else:
                max_text_len = 96
        else:
            max_text_len = max(20, int(_max_text_len_val))

        segments = _split_text_for_buffer(text_cleaned, max_len=max_text_len, cut_punc=cut_punc)
        text_final = "\n".join(segments) if segments else text_cleaned
        if len(segments) > 1:
            logger.info(f"[synthesize/stream] 目标文本已切分为 {len(segments)} 段，max_len={max_text_len}, strict={strict_segmented}")

        try:
            import api as official_api_module
            official_api_module.stream_mode = "close"
            official_api_module.media_type = "wav"
        except Exception:
            pass

        is_user_trained_voice = str((profile or {}).get("model_type") or "").strip().lower() == "user_trained"
        runtime_data = dict(data or {})
        voice_policy = {
            "tier": "normal",
            "cache_mode": "speed",
            "applied": False,
            "reasons": [],
        }
        if is_user_trained_voice and voice_id:
            runtime_data, voice_policy = _apply_user_voice_risk_policy(runtime_data, voice_id, profile)
            if voice_policy.get("applied"):
                logger.info(
                    f"[synthesize/stream] user_trained 风险分层策略已应用: voice_id={voice_id}, "
                    f"tier={voice_policy.get('tier')}, reasons={voice_policy.get('reasons')}, "
                    f"overrides={list((voice_policy.get('applied_overrides') or {}).keys())}"
                )

        if is_user_trained_voice and voice_policy.get("tier") in ("risky", "strict") and len(segments) < 2:
            try:
                forced_max_len = int(runtime_data.get("max_text_len", 24 if voice_policy.get("tier") == "strict" else 28))
            except Exception:
                forced_max_len = 24 if voice_policy.get("tier") == "strict" else 28
            forced_max_len = max(16, min(56, forced_max_len))
            forced_cut_punc = runtime_data.get("cut_punc") or "，。？！；：,.!?;:、…"
            forced_segments = _split_text_for_buffer(text_cleaned, max_len=forced_max_len, cut_punc=forced_cut_punc)
            if len(forced_segments) >= 2:
                segments = forced_segments
                text_final = "\n".join(segments)
                logger.info(
                    f"[synthesize/stream] user_trained 高风险音色启用细粒度分段: "
                    f"voice_id={voice_id}, tier={voice_policy.get('tier')}, "
                    f"segments={len(segments)}, max_len={forced_max_len}"
                )

        segmented_sync_enabled = (
            is_user_trained_voice
            and _should_use_user_voice_segmented_sync(runtime_data, text_cleaned, segments)
        )
        if debug_id and is_user_trained_voice and len(segments) >= 2:
            _debug_event(
                debug_id,
                "segmented_sync.route",
                enabled=segmented_sync_enabled,
                segments=len(segments),
                text_units=_count_text_units(text_cleaned),
            )

        audio_bytes_wav = None
        if segmented_sync_enabled:
            try:
                seg_sync_data = dict(runtime_data or {})
                seg_sync_data["_is_user_trained_voice"] = True
                seg_sync_data["_adaptive_text"] = text_cleaned
                audio_bytes_wav, seg_task_id, seg_merged_url, seg_total = _generate_wav_via_segmented_buffer_sync(
                    segments=segments,
                    data=seg_sync_data,
                    ref_audio_path=ref_audio_path,
                    ref_text_cleaned=ref_text_cleaned,
                    api_prompt_lang=api_prompt_lang,
                    api_text_lang=api_text_lang,
                    voice_id=voice_id,
                    aux_ref_audio_paths=aux_ref_audio_paths,
                    official_get_tts_wav_api=official_get_tts_wav_api,
                    debug_id=debug_id,
                )
                if debug_id:
                    _debug_event(
                        debug_id,
                        "segmented_sync.done",
                        task_id=seg_task_id,
                        total=seg_total,
                        merged_url=seg_merged_url,
                        wav_bytes=len(audio_bytes_wav),
                    )
            except Exception as seg_sync_err:
                logger.warning(f"[synthesize/stream] segmented_sync 失败，回退单次生成: {seg_sync_err}")
                audio_bytes_wav = None

        if audio_bytes_wav is None:
            top_k_base = int(runtime_data.get("top_k", 15))
            top_p_base = float(runtime_data.get("top_p", 0.6))
            temperature_base = float(runtime_data.get("temperature", 0.6))
            repetition_penalty_base = float(runtime_data.get("repetition_penalty", 1.35))
            speed_base = float(runtime_data.get("speed", 1.0))
            if is_user_trained_voice and _coerce_bool_param(runtime_data.get("hq_user_voice_speed_boost"), True):
                try:
                    min_speed = float(runtime_data.get("hq_user_voice_min_speed", 1.15))
                except Exception:
                    min_speed = 1.15
                min_speed = max(1.00, min(1.25, min_speed))
                speed_base = max(speed_base, min_speed)
            if is_user_trained_voice and _coerce_bool_param(runtime_data.get("hq_user_voice_fast_decode"), True):
                top_k_base = min(top_k_base, 16)
                top_p_base = min(top_p_base, 0.78)
                temperature_base = min(temperature_base, 0.30)
                repetition_penalty_base = max(repetition_penalty_base, 1.22)
            sample_steps_raw = int(runtime_data.get("sample_steps", 32))
            sample_steps_base = _resolve_adaptive_user_voice_sample_steps(
                data=runtime_data,
                text=text_final,
                default_steps=sample_steps_raw,
                is_user_trained_voice=is_user_trained_voice,
            )
            if sample_steps_base != sample_steps_raw:
                logger.info(f"[synthesize/stream] user_trained adaptive sample_steps: {sample_steps_raw} -> {sample_steps_base}")

            def _stream_gen_once(profile: dict, attempt_tag: str) -> bytes:
                profile_speed = float(profile.get("speed", speed_base))
                target_max_sec = _estimate_infer_max_sec_limit(
                    text_final,
                    speed=profile_speed,
                    is_user_trained_voice=is_user_trained_voice,
                    risk_tier=voice_policy.get("tier"),
                )
                if (
                    is_user_trained_voice
                    and str(voice_policy.get("tier") or "").strip().lower() in ("risky", "strict")
                    and _coerce_bool_param(runtime_data.get("hq_user_voice_relax_max_sec"), True)
                ):
                    target_max_sec = 0
                sec_override_applied = False
                sec_override_old = None
                sec_override_new = None
                with _INFER_MAX_SEC_OVERRIDE_LOCK:
                    sec_override_applied, sec_restore_items, sec_override_old, sec_override_new = _apply_temporary_infer_max_sec(target_max_sec)
                    try:
                        gen = official_get_tts_wav_api(
                            ref_wav_path=ref_audio_path,
                            prompt_text=ref_text_cleaned,
                            prompt_language=api_prompt_lang,
                            text=text_final,
                            text_language=api_text_lang,
                            top_k=int(profile.get("top_k", top_k_base)),
                            top_p=float(profile.get("top_p", top_p_base)),
                            temperature=float(profile.get("temperature", temperature_base)),
                            repetition_penalty=float(profile.get("repetition_penalty", repetition_penalty_base)),
                            speed=profile_speed,
                            inp_refs=inp_refs_payload or None,
                            sample_steps=int(profile.get("sample_steps", sample_steps_base)),
                            if_sr=False,
                            spk="default",
                        )
                    finally:
                        _restore_temporary_infer_max_sec(sec_restore_items)
                t_start = time.time()
                audio_local, gen_stats = _collect_generator_bytes_with_stats(gen)
                if debug_id:
                    _debug_event(
                        debug_id,
                        "synthesize.gen.done",
                        attempt=attempt_tag,
                        gen_chunks=gen_stats.get("chunks"),
                        gen_bytes=gen_stats.get("bytes"),
                        cost_ms=int((time.time()-t_start)*1000),
                        max_sec_target=target_max_sec or None,
                        max_sec_override_applied=bool(sec_override_applied),
                        max_sec_before=sec_override_old,
                        max_sec_after=sec_override_new,
                    )
                if not audio_local:
                    raise StopIteration("empty audio bytes")
                return audio_local

            primary_profile = {
                "top_k": top_k_base,
                "top_p": top_p_base,
                "temperature": temperature_base,
                "repetition_penalty": repetition_penalty_base,
                "speed": speed_base,
                "sample_steps": sample_steps_base,
            }
            effective_primary_profile = dict(primary_profile)
            hint_source = ""
            if is_user_trained_voice and voice_id:
                cached_profile = _get_cached_voice_gen_profile(voice_id, primary_profile)
                if cached_profile:
                    effective_primary_profile = _clamp_cached_user_voice_profile(cached_profile, primary_profile, cache_mode=voice_policy.get("cache_mode", "speed"))
                    hint_source = "cache"
                elif _coerce_bool_param(runtime_data.get("hq_user_voice_bootstrap"), True):
                    boot_profile = _build_recent_user_voice_bootstrap_profile(primary_profile, profile)
                    if boot_profile != primary_profile:
                        effective_primary_profile = boot_profile
                        hint_source = "recent_voice_bootstrap"
            if hint_source:
                logger.info(f"[synthesize/stream] user_trained 使用参数提示: voice_id={voice_id}, source={hint_source}, profile={effective_primary_profile}")
            if is_user_trained_voice and _coerce_bool_param(runtime_data.get("hq_user_voice_fast_decode"), True):
                effective_primary_profile["top_k"] = min(int(effective_primary_profile.get("top_k", top_k_base)), 16)
                effective_primary_profile["top_p"] = min(float(effective_primary_profile.get("top_p", top_p_base)), 0.78)
                effective_primary_profile["temperature"] = min(float(effective_primary_profile.get("temperature", temperature_base)), 0.30)
                effective_primary_profile["repetition_penalty"] = max(float(effective_primary_profile.get("repetition_penalty", repetition_penalty_base)), 1.22)

            try:
                audio_bytes_wav = _stream_gen_once(effective_primary_profile, "base")
            except StopIteration:
                raise HTTPException(status_code=500, detail="推理失败：生成器未返回音频数据")
            best_profile = dict(effective_primary_profile)

            if is_user_trained_voice:
                seg_units = _count_text_units(text_final)
                under_tol = 0.92 if seg_units >= 14 else 0.90
                over_tol = 1.20 if seg_units >= 14 else 1.23
                under_tol, over_tol = _apply_voice_risk_tolerance(under_tol, over_tol, voice_policy.get("tier"))
                if _is_abnormal_generated_audio(text_final, audio_bytes_wav, speed=best_profile["speed"], under_tolerance=under_tol, over_tolerance=over_tol):
                    best_audio_bytes = audio_bytes_wav
                    best_score = _duration_match_score(text_final, audio_bytes_wav, speed=best_profile["speed"])
                    is_under_initial = _is_under_generated_audio(
                        text_final,
                        audio_bytes_wav,
                        speed=float(best_profile.get("speed", speed_base)),
                        tolerance=under_tol,
                    )
                    is_over_initial = _is_over_generated_audio(
                        text_final,
                        audio_bytes_wav,
                        speed=float(best_profile.get("speed", speed_base)),
                        tolerance=over_tol,
                    )
                    is_low_energy_initial = _is_low_energy_generated_audio(text_final, audio_bytes_wav)
                    if is_over_initial and (not is_under_initial):
                        if _coerce_bool_param(runtime_data.get("hq_user_voice_over_retry"), False):
                            retry_profile = {
                                "top_k": max(16, top_k_base),
                                "top_p": min(0.86, max(0.80, top_p_base)),
                                "temperature": min(0.38, max(0.28, temperature_base)),
                                "repetition_penalty": min(1.18, max(1.10, repetition_penalty_base)),
                                "speed": max(1.10, speed_base),
                                "sample_steps": max(22, min(28, sample_steps_base)),
                            }
                        else:
                            retry_profile = None
                            logger.info(f"[synthesize/stream] user_trained over-generated: skip retry for speed, voice_id={voice_id}")
                    elif is_under_initial:
                        retry_profile = {
                            "top_k": max(18, top_k_base),
                            "top_p": max(0.86, top_p_base),
                            "temperature": min(0.40, max(0.30, temperature_base)),
                            "repetition_penalty": min(1.22, max(1.14, repetition_penalty_base)),
                            "speed": min(0.97, speed_base),
                            "sample_steps": max(34, sample_steps_base),
                        }
                    elif is_low_energy_initial:
                        retry_profile = {
                            "top_k": max(17, top_k_base),
                            "top_p": max(0.84, top_p_base),
                            "temperature": min(0.38, max(0.30, temperature_base)),
                            "repetition_penalty": min(1.22, max(1.14, repetition_penalty_base)),
                            "speed": max(0.99, speed_base),
                            "sample_steps": max(30, min(36, sample_steps_base + 2)),
                        }
                    else:
                        retry_profile = {
                            "top_k": max(17, top_k_base),
                            "top_p": max(0.84, top_p_base),
                            "temperature": min(0.38, max(0.30, temperature_base)),
                            "repetition_penalty": min(1.20, max(1.14, repetition_penalty_base)),
                            "speed": max(0.99, speed_base),
                            "sample_steps": max(30, min(36, sample_steps_base + 2)),
                        }
                    if retry_profile is not None:
                        try:
                            retry_audio = _stream_gen_once(retry_profile, "retry1")
                            retry_score = _duration_match_score(text_final, retry_audio, speed=retry_profile["speed"])
                            if retry_score < best_score:
                                best_audio_bytes = retry_audio
                                best_score = retry_score
                                best_profile = dict(retry_profile)
                            if not _is_abnormal_generated_audio(text_final, retry_audio, speed=retry_profile["speed"], under_tolerance=under_tol, over_tolerance=over_tol):
                                logger.info("[synthesize/stream] user_trained 质量重试通过")
                                best_audio_bytes = retry_audio
                                best_profile = dict(retry_profile)
                            else:
                                logger.warning("[synthesize/stream] user_trained 质量重试后仍异常，返回更优时长版本")
                        except StopIteration:
                            logger.warning("[synthesize/stream] user_trained 质量重试无音频返回，沿用基础结果")

                    audio_bytes_wav = best_audio_bytes
                    if str(voice_policy.get("tier") or "").strip().lower() != "risky":
                        audio_bytes_wav, trim_meta = _trim_over_generated_audio_if_needed(
                            text_final,
                            audio_bytes_wav,
                            speed=float(best_profile.get("speed", speed_base)),
                            over_tolerance=over_tol,
                        )
                        if trim_meta.get("applied"):
                            logger.info(
                                f"[synthesize/stream] over-generated 裁剪已应用: "
                                f"voice_id={voice_id}, src={trim_meta.get('src_sec')}, dst={trim_meta.get('dst_sec')}"
                            )

            if is_user_trained_voice and voice_id:
                source = "retry_or_bootstrap" if (best_profile != primary_profile) else "base"
                cache_profile = _clamp_cached_user_voice_profile(best_profile, primary_profile, cache_mode=voice_policy.get("cache_mode", "speed"))
                _remember_voice_gen_profile(voice_id, cache_profile, source=source)
    else:
        gen = official_get_tts_wav_webui(
            ref_wav_path=ref_audio_path,
            prompt_text=ref_text_cleaned,
            prompt_language=prompt_language_final,
            text=text_cleaned,
            text_language=text_language_final,
            how_to_cut="不切",
            top_k=int(data.get("top_k", 20)),
            top_p=float(data.get("top_p", 0.6)),
            temperature=float(data.get("temperature", 0.6)),
            repetition_penalty=float(data.get("repetition_penalty", 1.35)),
            ref_free=False,
            speed=float(data.get("speed", 1.0)),
            if_freeze=False,
            inp_refs=inp_refs_payload or None,
            sample_steps=int(data.get("sample_steps", 8)),
            if_sr=False,
            pause_second=0.3,
        )
        sr, audio_np = next(gen)
        audio_buf = BytesIO()
        sf.write(audio_buf, audio_np.astype("int16"), sr, format="WAV")
        audio_buf.seek(0)
        audio_bytes_wav = audio_buf.read()

    if voice_id and (voice_id not in QWEN_BASE_VOICE_IDS):
        audio_bytes_wav, boost_meta = _boost_low_rms_wav_if_needed(audio_bytes_wav)
        if boost_meta.get("applied"):
            logger.info(
                f"[synthesize/stream] 低音量补偿已应用 voice_id={voice_id}: "
                f"gain={boost_meta.get('gain'):.2f}, rms {boost_meta.get('rms_before'):.1f}->{boost_meta.get('rms_after'):.1f}"
            )

    # 解析 WAV，分块输出
    wav_reader = wave.open(BytesIO(audio_bytes_wav), "rb")
    sample_rate = wav_reader.getframerate()
    channels = wav_reader.getnchannels()
    sample_width = wav_reader.getsampwidth()
    frames_per_chunk = max(1, int(sample_rate * (chunk_ms / 1000.0)))

    media_type = "audio/wav" if _format in ["wav", "wave"] else "application/octet-stream"
    headers = {
        "X-Sample-Rate": str(sample_rate),
        "X-Channels": str(channels),
        "X-Sample-Width": str(sample_width),
        "X-PCM-Format": "s16le",
    }

    async def generator():
        try:
            if _format in ["wav", "wave"]:
                yield _wave_header_chunk(channels=channels, sample_width=sample_width, sample_rate=sample_rate)
            while True:
                if await request.is_disconnected():
                    break
                data_chunk = wav_reader.readframes(frames_per_chunk)
                if not data_chunk:
                    break
                yield data_chunk
        finally:
            try:
                wav_reader.close()
            except Exception:
                pass

    return StreamingResponse(generator(), media_type=media_type, headers=headers)


@app.post("/synthesize/stream")
async def synthesize_stream(request: Request, chunk_ms: int = 200, format: str = "wav"):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须为 JSON")
    return await _synthesize_stream_impl(request, data, chunk_ms=chunk_ms, format=format, route_name="synthesize/stream")


@app.get("/synthesize/stream")
async def synthesize_stream_get(request: Request, chunk_ms: int = 200, format: str = "wav"):
    data = dict(request.query_params)
    return await _synthesize_stream_impl(request, data, chunk_ms=chunk_ms, format=format, route_name="synthesize/stream")


@app.post("/synthesize_stream")
async def synthesize_stream_legacy_post(request: Request, chunk_ms: int = 200, format: str = "wav"):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须为 JSON")
    return await _synthesize_stream_impl(request, data, chunk_ms=chunk_ms, format=format, route_name="synthesize_stream")


@app.get("/synthesize_stream")
async def synthesize_stream_legacy_get(request: Request, chunk_ms: int = 200, format: str = "wav"):
    data = dict(request.query_params)
    return await _synthesize_stream_impl(request, data, chunk_ms=chunk_ms, format=format, route_name="synthesize_stream")


@app.post("/set_model")
async def set_model(request: Request):
    json_post_raw = await request.json()
    return change_gpt_sovits_weights(
        gpt_path=json_post_raw.get("gpt_model_path"), sovits_path=json_post_raw.get("sovits_model_path")
    )


@app.get("/test/ffmpeg")
async def test_ffmpeg_endpoint():
    """
    测试ffmpeg是否安装并能正常工作
    返回详细的测试结果
    """
    result = test_ffmpeg_installation()
    if result["working"]:
        return JSONResponse({
            "code": 200,
            "message": "ffmpeg测试通过",
            "result": result
        }, status_code=200)
    else:
        return JSONResponse({
            "code": 500,
            "message": "ffmpeg测试未通过",
            "result": result
        }, status_code=500)


def _voices_optional_user_id(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    try:
        try:
            from modules.user_mgmt_backend.user_api import verify_user_token, _extract_bearer
        except Exception:
            from user_mgmt_backend.user_api import verify_user_token, _extract_bearer

        tok = _extract_bearer(authorization)
        if not tok:
            return None
        payload = verify_user_token(tok)
        if not payload:
            return None
        uid = str(payload.get("uid") or "").strip()
        return uid or None
    except Exception:
        return None


def _voice_is_builtin_or_pretrained(voice_id: str, info: dict) -> bool:
    vid = str(voice_id or "").strip()
    if _is_protected_voice(vid, info):
        return True
    mt = str((info or {}).get("model_type") or "").strip().lower()
    return mt == "pretrained"


@app.get("/voices")
async def list_voices(authorization: Optional[str] = Header(None, alias="Authorization")):
    """
    列出 VOICE_LIBRARY 中的声音模型。
    - 未带登录态：返回全部（便于未登录/联调测试看到所有音色）。
    - 带 Authorization Bearer：仅返回「预置/内置」+ 当前用户 owner 的模型。
    """
    load_voice_library_from_file()
    uid = _voices_optional_user_id(authorization)
    owned_ids: set = set()
    if uid:
        try:
            try:
                from modules.user_mgmt_backend import db as user_mgmt_db
            except Exception:
                from user_mgmt_backend import db as user_mgmt_db

            user_mgmt_db.init_db()
            owned_ids = set(user_mgmt_db.list_voice_ids_for_owner(uid))
        except Exception as e:
            logger.warning(f"[查询声音列表] 读取用户归属音色失败(将仅按库内 owner 字段过滤): {e}")

    data = []
    for vid, info in VOICE_LIBRARY.items():
        if uid:
            owner = str((info or {}).get("owner_user_id") or "").strip()
            allow = (
                _voice_is_builtin_or_pretrained(vid, info)
                or (owner and owner == uid)
                or (vid in owned_ids)
            )
            if not allow:
                continue
        protected = _is_protected_voice(vid, info)
        can_rename = (info or {}).get("can_rename", True) is not False
        data.append(
            {
                "voice_id": vid,
                "name": info.get("name", vid),
                "gpt_path": info.get("gpt_path"),
                "sovits_path": info.get("sovits_path"),
                "scene": info.get("scene", ""),
                "emotion": info.get("emotion", ""),
                "trained_at": info.get("trained_at", ""),
                "model_type": info.get("model_type", ""),
                "provider": info.get("provider", ""),
                "gender": info.get("gender", ""),
                "voice_group": info.get("voice_group", ""),
                "is_builtin": bool((info or {}).get("is_builtin")) or protected,
                "can_delete": not protected,
                "can_rename": (not protected) and can_rename,
            }
        )
    logger.info(
        f"[查询声音列表] user_scope={'login:' + uid if uid else 'guest_all'} "
        f"返回 {len(data)} 个模型（库内共 {len(VOICE_LIBRARY)}）"
    )
    return JSONResponse({"code": 0, "voices": data}, status_code=200)


@app.get("/debug/voice_library")
async def debug_voice_library():
    """用于排查部署环境实际读取的 voice_library.json 路径与当前内存库内容。"""
    try:
        load_voice_library_from_file()
    except Exception:
        pass
    try:
        return JSONResponse(
            {
                "code": 0,
                "voice_library_file": VOICE_LIBRARY_FILE,
                "count": len(VOICE_LIBRARY),
                "voice_ids": list(VOICE_LIBRARY.keys()),
            },
            status_code=200,
        )
    except Exception as e:
        return JSONResponse({"code": 500, "message": str(e)}, status_code=500)


@app.post("/voices/rename")
async def rename_voice(request: Request):
    """重命名声音模型，供小程序“保存并应用”步骤调用。"""
    try:
        json_post_raw = await request.json()
    except Exception:
        json_post_raw = {}

    voice_id = str((json_post_raw or {}).get("voice_id") or "").strip()
    new_name = str(((json_post_raw or {}).get("name") or (json_post_raw or {}).get("new_name") or "")).strip()

    if not voice_id:
        return JSONResponse({"code": 400, "message": "缺少参数: voice_id"}, status_code=400)
    if not new_name:
        return JSONResponse({"code": 400, "message": "缺少参数: name"}, status_code=400)
    if len(new_name) > 32:
        return JSONResponse({"code": 400, "message": "名称最多32字符"}, status_code=400)

    try:
        ok = rename_voice_model(voice_id, new_name)
        if not ok:
            return JSONResponse({"code": 404, "message": "模型不存在"}, status_code=404)
        return JSONResponse(
            {
                "code": 0,
                "message": "重命名成功",
                "voice_id": voice_id,
                "name": new_name,
            },
            status_code=200,
        )
    except ValueError as ve:
        return JSONResponse({"code": 400, "message": str(ve)}, status_code=400)
    except Exception as e:
        logger.error(f"[重命名模型] 接口异常: {str(e)}")
        return JSONResponse({"code": 500, "message": "重命名失败，请检查日志"}, status_code=500)


@app.get("/train/history_models")
async def list_history_models():
    """
    返回历史使用过的模型名称列表，供前端训练页做下拉搜索/选择。

    设计原则：
    1. 只要用户在 user_datasets 下有对应目录（即录过数据），就认为是“历史模型名”；
    2. 如果该模型已经训练成功并写入 VOICE_LIBRARY，则补充 voice_id、trained_at 等信息；
    3. 去重后返回。
    """
    load_voice_library_from_file()

    # 1. 先从 VOICE_LIBRARY 中收集所有已注册模型（包含内置 + 用户训练）
    name_to_model: dict[str, dict] = {}
    for vid, info in VOICE_LIBRARY.items():
        name = info.get("name") or ""
        if not name:
            continue
        if name in name_to_model:
            # 如果重复，以第一个为准，避免覆盖
            continue
        name_to_model[name] = {
            "model_name": name,
            "voice_id": vid,
            "trained_at": info.get("trained_at", ""),
            "scene": info.get("scene", ""),
            "emotion": info.get("emotion", ""),
            "has_trained_model": True,
        }

    # 2. 再从 train/user_datasets 目录中扫描所有已有数据集的用户ID/模型名
    user_datasets_root = os.path.join(now_dir, "train", "user_datasets")
    if os.path.isdir(user_datasets_root):
        for entry in os.listdir(user_datasets_root):
            dataset_dir = os.path.join(user_datasets_root, entry)
            if not os.path.isdir(dataset_dir):
                continue
            model_name = entry
            # 注意：保留所有目录，包括数字命名的目录（如 "1"），由前端决定展示策略

            # 简单检查：目录下是否存在任何录音或文本文件（递归查找，包括 v2Pro 子目录）
            has_any_data = False
            try:
                for root, _, files in os.walk(dataset_dir):
                    for fn in files:
                        if fn.endswith(".wav") or fn.endswith(".txt"):
                            has_any_data = True
                            break
                    if has_any_data:
                        break
            except Exception as e:
                logger.warning(f"[history_models] 扫描数据集目录出错: {dataset_dir}, err={e}")
                continue

            if not has_any_data:
                continue

            if model_name in name_to_model:
                # 已在 VOICE_LIBRARY 中记录，说明有训练好的模型了，保持 has_trained_model=True
                continue

            # 只有数据集，尚未训练成功的情况
            name_to_model[model_name] = {
                "model_name": model_name,
                "voice_id": "",
                "trained_at": "",
                "scene": "",
                "emotion": "",
                "has_trained_model": False,
            }

    results = list(name_to_model.values())
    # 为了稳定性，排序一下（字典序）
    results.sort(key=lambda x: x["model_name"])

    logger.info(f"[history_models] 返回 {len(results)} 个历史模型名称: {[m['model_name'] for m in results]}")
    return JSONResponse(
        {
            "code": 200,
            "models": results,
            "total": len(results),
        },
        status_code=200,
    )


@app.delete("/voices/{voice_id}")
async def remove_voice(voice_id: str):
    """
    删除指定 voice_id 的声音模型（不允许删除内置模型）
    """
    try:
        deleted = delete_voice_model(voice_id)
        if deleted:
            return JSONResponse({"code": 0, "message": f"已删除 {voice_id}"})
        return JSONResponse({"code": 404, "message": "模型不存在"}, status_code=404)
    except ValueError as ve:
        return JSONResponse({"code": 400, "message": str(ve)}, status_code=400)
    except Exception as e:
        logger.error(f"[删除模型] 接口异常：{str(e)}")
        return JSONResponse({"code": 500, "message": "删除失败，请检查日志"}, status_code=500)


@app.post("/use_voice")
async def use_voice(request: Request):
    """
    根据 voice_id 切换当前使用的声音模型。
    前端在选择“我的声音”后调用该接口，即可让后续合成使用对应权重。
    """
    try:
        json_post_raw = await request.json()
    except Exception as e:
        logger.warning(f"[use_voice] 非法JSON请求: err={e}")
        return JSONResponse({"code": 400, "message": "请求体必须为 JSON"}, status_code=400)

    if not isinstance(json_post_raw, dict):
        logger.warning(f"[use_voice] 请求体类型错误: type={type(json_post_raw).__name__}")
        return JSONResponse({"code": 400, "message": "请求体必须为对象"}, status_code=400)

    raw_voice_id = json_post_raw.get("voice_id")
    voice_id = str(raw_voice_id or "").strip()
    req_keys = sorted([str(k) for k in json_post_raw.keys()])

    if not voice_id:
        logger.warning(f"[use_voice] 缺少voice_id: keys={req_keys}, payload={json_post_raw}")
        return JSONResponse({"code": 400, "message": "缺少参数: voice_id"}, status_code=400)

    load_voice_library_from_file()
    if voice_id not in VOICE_LIBRARY:
        logger.warning(
            f"[use_voice] 未找到voice_id: voice_id={voice_id}, "
            f"keys={req_keys}, available={list(VOICE_LIBRARY.keys())[:12]}"
        )
        return JSONResponse({"code": 400, "message": f"未知的 voice_id: {voice_id}"}, status_code=400)

    profile = VOICE_LIBRARY.get(voice_id) or {}
    logger.info(
        f"[use_voice] 请求切换: voice_id={voice_id}, "
        f"name={profile.get('name')}, model_type={profile.get('model_type')}, provider={profile.get('provider')}"
    )
    resp = load_voice_profile(voice_id)
    try:
        code = getattr(resp, "status_code", None)
        logger.info(f"[use_voice] 切换结果: voice_id={voice_id}, status_code={code}")
    except Exception:
        pass
    return resp


@app.get("/set_model")
async def set_model(
    gpt_model_path: str = None,
    sovits_model_path: str = None,
):
    return change_gpt_sovits_weights(gpt_path=gpt_model_path, sovits_path=sovits_model_path)


@app.get("/test/model_combo")
@app.post("/test/model_combo")
async def test_model_combo(request: Request = None, combo: str = None):
    """
    测试不同的模型组合
    
    支持的组合：
    - combo_a: 官方 GPT (30s-e15) + 官方 SoVITS (30s_e8_s184)
    - combo_b: 用户 GPT (voice_2_3e0d5e13-e30) + 官方 SoVITS (30s_e8_s184)
    - combo_c: 官方 GPT (30s-e15) + 用户 SoVITS (voice_2_3e0d5e13_e10_s70)
    - combo_d: 用户 GPT (voice_2_3e0d5e13-e30) + 用户 SoVITS (voice_2_3e0d5e13_e10_s70)
    
    使用方法：
    GET: /test/model_combo?combo=combo_b
    POST: {"combo": "combo_b"}
    """
    try:
        # 获取组合参数
        if request:
            try:
                json_data = await request.json()
                combo = json_data.get("combo", combo)
            except:
                pass
        
        if not combo:
            return JSONResponse({
                "code": 400,
                "message": "请指定组合名称 (combo_a, combo_b, combo_c, combo_d)",
                "available_combos": {
                    "combo_a": "官方 GPT + 官方 SoVITS",
                    "combo_b": "用户 GPT + 官方 SoVITS",
                    "combo_c": "官方 GPT + 用户 SoVITS",
                    "combo_d": "用户 GPT + 用户 SoVITS"
                }
            }, status_code=400)
        
        # 定义模型路径
        base_dir = os.path.abspath(os.path.dirname(__file__))
        model_paths = {
            "combo_a": {
                "gpt": os.path.join(base_dir, "GPT_weights_v2Pro", "30s-e15.ckpt"),
                "sovits": os.path.join(base_dir, "SoVITS_weights_v2Pro", "30s_e8_s184.pth"),
                "description": "官方 GPT + 官方 SoVITS"
            },
            "combo_b": {
                "gpt": os.path.join(base_dir, "GPT_weights_v2Pro", "voice_2_3e0d5e13-e30.ckpt"),
                "sovits": os.path.join(base_dir, "SoVITS_weights_v2Pro", "30s_e8_s184.pth"),
                "description": "用户 GPT + 官方 SoVITS"
            },
            "combo_c": {
                "gpt": os.path.join(base_dir, "GPT_weights_v2Pro", "30s-e15.ckpt"),
                "sovits": os.path.join(base_dir, "SoVITS_weights_v2Pro", "voice_2_3e0d5e13_e10_s70.pth"),
                "description": "官方 GPT + 用户 SoVITS"
            },
            "combo_d": {
                "gpt": os.path.join(base_dir, "GPT_weights_v2Pro", "voice_2_3e0d5e13-e30.ckpt"),
                "sovits": os.path.join(base_dir, "SoVITS_weights_v2Pro", "voice_2_3e0d5e13_e10_s70.pth"),
                "description": "用户 GPT + 用户 SoVITS"
            }
        }
        
        if combo not in model_paths:
            return JSONResponse({
                "code": 400,
                "message": f"未知的组合: {combo}",
                "available_combos": list(model_paths.keys())
            }, status_code=400)
        
        paths = model_paths[combo]
        logger.info(f"[test_model_combo] 切换到组合: {combo} ({paths['description']})")
        logger.info(f"[test_model_combo] GPT: {paths['gpt']}")
        logger.info(f"[test_model_combo] SoVITS: {paths['sovits']}")
        
        # 切换模型
        result = change_gpt_sovits_weights(
            gpt_path=paths["gpt"],
            sovits_path=paths["sovits"]
        )
        
        # 如果成功，返回详细信息
        if result.status_code == 200:
            return JSONResponse({
                "code": 0,
                "message": f"成功切换到组合: {combo}",
                "combo": combo,
                "description": paths["description"],
                "gpt_path": paths["gpt"],
                "sovits_path": paths["sovits"],
                "gpt_exists": os.path.exists(paths["gpt"]),
                "sovits_exists": os.path.exists(paths["sovits"])
            }, status_code=200)
        else:
            return result
            
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"[test_model_combo] 错误: {str(e)}\n{error_detail}")
        return JSONResponse({
            "code": 500,
            "message": f"切换组合失败: {str(e)}"
        }, status_code=500)


@app.post("/control")
async def control(request: Request):
    json_post_raw = await request.json()
    return handle_control(json_post_raw.get("command"))


@app.get("/control")
async def control(command: str = None):
    return handle_control(command)


@app.post("/change_refer")
async def change_refer(request: Request):
    json_post_raw = await request.json()
    return handle_change(
        json_post_raw.get("refer_wav_path"), json_post_raw.get("prompt_text"), json_post_raw.get("prompt_language")
    )


@app.get("/change_refer")
async def change_refer(refer_wav_path: str = None, prompt_text: str = None, prompt_language: str = None):
    return handle_change(refer_wav_path, prompt_text, prompt_language)


@app.post("/")
async def tts_endpoint(request: Request):
    """
    兼容旧接口：重定向到 /synthesize 接口
    使用 simple_inference.py 的推理逻辑
    """
    # 直接调用 /synthesize 接口的逻辑
    return await synthesize(request)


@app.get("/")
async def tts_endpoint_get(
    refer_wav_path: str = None,
    prompt_text: str = None,
    prompt_language: str = None,
    text: str = None,
    text_language: str = None,
    voice_id: str = None,
    speed: float = 1.0,
    top_k: int = 15,
    top_p: float = 0.85,
    temperature: float = 1.0,
    sample_steps: int = 8,
):
    """
    兼容旧 GET 接口：重定向到 /synthesize 接口
    使用 simple_inference.py 的推理逻辑
    """
    # 构建请求数据，转换为 POST 格式
    from fastapi import Request
    from starlette.requests import Request as StarletteRequest
    import json
    from starlette.datastructures import Headers
    
    request_data = {
        "voice_id": voice_id,
        "refer_wav_path": refer_wav_path,
        "prompt_text": prompt_text,
        "prompt_language": prompt_language,
        "text": text,
        "text_language": text_language,
        "speed": speed,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "sample_steps": sample_steps,
    }
    
    # 创建模拟的 Request 对象
    class MockRequest:
        def __init__(self, data):
            self._data = data
        
        async def json(self):
            return self._data
    
    mock_request = MockRequest(request_data)
    return await synthesize(mock_request)


# ==================== 模型训练相关API ====================
# 从 train_api 导入训练相关功能
try:
    # 导入训练相关的函数和变量
    import sys
    from pathlib import Path
    train_api_path = Path(__file__).parent / "train_api.py"
    logger.info(f"检查训练API模块: {train_api_path} (存在: {train_api_path.exists()})")
    if train_api_path.exists():
        # 动态导入训练模块
        import importlib.util
        spec = importlib.util.spec_from_file_location("train_api_module", train_api_path)
        train_api_module = importlib.util.module_from_spec(spec)
        sys.modules["train_api_module"] = train_api_module
        spec.loader.exec_module(train_api_module)
        
        # 导入训练相关的函数和变量
        from train_api_module import (
            train_tasks, TrainParams, model_versions,
            get_dict_language, run_training,
            DATASET_DIR, TRAIN_OUTPUT_DIR, TRAIN_LOG_DIR,
            cleanup_all_processes, active_processes
        )
        # uuid 和 os 已在文件顶部导入，无需重复导入
        
        MIN_TRAIN_SENTENCE_COUNT = max(1, int(os.getenv("WX_MIN_TRAIN_SENTENCE_COUNT", "5")))
        MIN_TRAIN_AUDIO_SECONDS = float(os.getenv("WX_MIN_TRAIN_AUDIO_SECONDS", "4.0"))
        MIN_TRAIN_TEXT_MIN_CHARS = max(1, int(os.getenv("WX_MIN_TRAIN_TEXT_CHARS", "2")))

        def _safe_wav_duration_seconds(audio_path: str) -> float:
            try:
                with wave.open(audio_path, "rb") as wf:
                    frame_rate = wf.getframerate() or 0
                    n_frames = wf.getnframes() or 0
                if frame_rate <= 0:
                    return 0.0
                return float(n_frames) / float(frame_rate)
            except Exception:
                return 0.0

        def _collect_valid_dataset_pairs(dataset_dir: str, sentence_only: bool = False):
            valid_pairs = []
            weak_pairs = 0
            if not os.path.exists(dataset_dir):
                return valid_pairs, weak_pairs

            for filename in os.listdir(dataset_dir):
                if not filename.endswith(".wav"):
                    continue
                if sentence_only and not filename.startswith("sentence_"):
                    continue

                if sentence_only:
                    idx_str = filename.replace("sentence_", "").replace(".wav", "")
                    try:
                        idx = int(idx_str)
                    except ValueError:
                        continue
                    if idx < 0 or idx >= 100:
                        continue
                    base_name = f"sentence_{idx}"
                else:
                    base_name = os.path.splitext(filename)[0]

                audio_path = os.path.join(dataset_dir, f"{base_name}.wav")
                text_path = os.path.join(dataset_dir, f"{base_name}.txt")
                if not (os.path.exists(audio_path) and os.path.exists(text_path)):
                    continue

                if os.path.getsize(audio_path) <= 0 or os.path.getsize(text_path) <= 0:
                    weak_pairs += 1
                    continue

                try:
                    with open(text_path, "r", encoding="utf-8") as f:
                        text_content = f.read().strip()
                except Exception:
                    weak_pairs += 1
                    continue

                if len(text_content) < MIN_TRAIN_TEXT_MIN_CHARS:
                    weak_pairs += 1
                    continue

                audio_seconds = _safe_wav_duration_seconds(audio_path)
                if audio_seconds < MIN_TRAIN_AUDIO_SECONDS:
                    weak_pairs += 1
                    continue

                valid_pairs.append({
                    "audio_path": audio_path,
                    "text_path": text_path,
                    "audio_seconds": audio_seconds,
                })

            valid_pairs.sort(key=lambda x: x["audio_path"])
            return valid_pairs, weak_pairs

        def _build_train_min_sentence_message(valid_count: int, weak_pairs: int) -> str:
            extra = f"，另有{weak_pairs}句因时长/文本不达标未计入" if weak_pairs > 0 else ""
            return (
                f"训练至少需要{MIN_TRAIN_SENTENCE_COUNT}句有效录音（每句>= {MIN_TRAIN_AUDIO_SECONDS:.1f}s）"
                f"，当前仅{valid_count}句{extra}。请继续补录后再训练。"
            )

        @app.post("/upload_dataset")
        async def upload_dataset(
            user_id: str = Form(...),
            model_version: str = Form("v2Pro"),
            files: List[UploadFile] = File(...)
        ):
            """上传用户音频数据集（WAV）和对应文本（TXT），需一一对应（只支持 v2Pro）"""
            if model_version != "v2Pro":
                return {"code": 400, "message": "只支持 v2Pro 版本"}
            
            # 创建用户数据集目录
            user_dataset_dir = os.path.join(DATASET_DIR, user_id, model_version)
            os.makedirs(user_dataset_dir, exist_ok=True)

            # 保存上传的文件
            audio_count = 0
            text_count = 0
            for file in files:
                if file.filename.endswith(".wav"):
                    file_path = os.path.join(user_dataset_dir, file.filename)
                    with open(file_path, "wb") as f:
                        f.write(await file.read())
                    audio_count += 1
                elif file.filename.endswith(".txt"):
                    file_path = os.path.join(user_dataset_dir, file.filename)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write((await file.read()).decode("utf-8"))
                    text_count += 1
                else:
                    return {"code": 400, "message": f"仅支持WAV和TXT文件：{file.filename}"}

            # 校验音频和文本数量是否匹配
            if audio_count != text_count:
                return {"code": 400, "message": f"音频文件（{audio_count}个）与文本文件（{text_count}个）数量不匹配"}

            return {
                "code": 200,
                "message": f"成功上传{audio_count}个音频和{text_count}个文本",
                "dataset_path": user_dataset_dir
            }

        # 兼容旧接口路径 /train/upload（前端使用单个音频文件+文本）
        @app.post("/train/upload")
        async def train_upload_compat(
            audio: UploadFile = File(...),
            text: str = Form(...),
            model_name: str = Form(...),
            language: str = Form("中文"),
            scene: str = Form(""),
            emotion: str = Form(""),
            user_id: str = Form("wx_clone_user")
        ):
            """兼容旧接口路径 /train/upload，接受单个音频文件和文本"""
            try:
                # 生成任务ID
                task_id = str(uuid.uuid4())
                
                # 创建用户数据集目录
                model_version = "v2Pro"
                user_dataset_dir = os.path.join(DATASET_DIR, user_id, model_version)
                os.makedirs(user_dataset_dir, exist_ok=True)
                
                # 生成文件名（使用任务ID避免冲突）
                audio_filename = f"{task_id}.wav"
                text_filename = f"{task_id}.txt"
                
                # 保存音频文件
                audio_path = os.path.join(user_dataset_dir, audio_filename)
                with open(audio_path, "wb") as f:
                    content = await audio.read()
                    f.write(content)
                
                # 保存文本文件
                text_path = os.path.join(user_dataset_dir, text_filename)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(text)
                
                # 初始化训练任务状态（兼容旧格式）
                train_tasks[task_id] = {
                    "status": "pending",  # pending/running/completed/failed
                    "progress": 0,
                    "message": "等待开始训练",
                    "audio_path": audio_path,
                    "text": text,
                    "model_name": model_name,
                    "language": language,
                    "scene": scene,
                    "emotion": emotion,
                    "user_id": user_id,
                    "version": model_version
                }
                
                return {
                    "code": 0,  # 前端期望 code: 0
                    "task_id": task_id,
                    "message": "训练数据上传成功，请调用 /train/start 开始训练"
                }
                
            except Exception as e:
                logger.error(f"上传训练数据失败: {str(e)}")
                return {
                    "code": 400,
                    "message": f"上传失败: {str(e)}"
                }
        
        # 逐句上传接口
        @app.post("/train/upload_sentence")
        async def upload_sentence(
            user_id: str = Form(...),
            sentence_index: str = Form(...),
            sentence_text: str = Form(...),
            language: str = Form("中文"),
            audio: UploadFile = File(...)
        ):
            """接收逐句的音频和文本，保存到用户数据集目录"""
            try:
                sentence_idx = int(sentence_index)
                if sentence_idx < 0 or sentence_idx >= 100:  # 放宽限制到100句
                    return JSONResponse({
                        "code": 400,
                        "message": f"句子索引无效: {sentence_index}，应在0-99之间"
                    }, status_code=400)
                
                # 创建用户数据集目录
                model_version = "v2Pro"
                user_dataset_dir = os.path.join(DATASET_DIR, user_id, model_version)
                os.makedirs(user_dataset_dir, exist_ok=True)
                
                # 生成文件名（格式：sentence_0.wav, sentence_0.txt）
                audio_filename = f"sentence_{sentence_idx}.wav"
                text_filename = f"sentence_{sentence_idx}.txt"
                
                # 如果目标文件已存在（重录情况），先删除旧文件，确保新文件正确覆盖
                final_audio_path = os.path.join(user_dataset_dir, audio_filename)
                if os.path.exists(final_audio_path):
                    try:
                        os.remove(final_audio_path)
                        logger.info(f"[upload_sentence] 删除旧音频文件（重录）: {final_audio_path}")
                    except Exception as e:
                        logger.warning(f"[upload_sentence] 删除旧音频文件失败: {e}")
                
                # 保存上传的原始音频到临时文件（注意：这里不保证是 wav，因此用 raw_ 前缀区分）
                raw_audio_path = os.path.join(user_dataset_dir, f"raw_{audio_filename}")
                audio_content = await audio.read()
                with open(raw_audio_path, "wb") as f:
                    f.write(audio_content)
                
                # 转码为WAV（先保存到临时路径，避免与 raw 文件同名导致被误删）
                temp_wav_path = os.path.join(user_dataset_dir, f"temp_wav_{audio_filename}")
                if not convert_to_wav(raw_audio_path, temp_wav_path):
                    if os.path.exists(raw_audio_path):
                        os.remove(raw_audio_path)
                    return JSONResponse({
                        "code": 400,
                        "message": "音频转码失败，请检查文件格式。请确保音频文件格式正确（支持mp3/wav/amr），或检查服务器是否安装了ffmpeg"
                    }, status_code=400)
                
                # 清理原始临时文件
                if os.path.exists(raw_audio_path):
                    os.remove(raw_audio_path)
                
                # ========== 自动音频预处理：HP5_only_main_vocal 提取主人声 ==========
                final_audio_path = os.path.join(user_dataset_dir, audio_filename)
                
                if AUDIO_PREPROCESS_AVAILABLE:
                    # 统一使用绝对路径，避免工作目录变化导致 exists 检测失败
                    temp_wav_path = os.path.abspath(temp_wav_path)
                    final_audio_path = os.path.abspath(final_audio_path)
                    logger.info(f"[upload_sentence] 开始对音频进行预处理（HP5_only_main_vocal 提取主人声）: {temp_wav_path} -> {final_audio_path}")
                    print(f"[upload_sentence] 开始对音频进行预处理（HP5_only_main_vocal 提取主人声）: {temp_wav_path} -> {final_audio_path}")
                    
                    try:
                        if not os.path.exists(temp_wav_path):
                            logger.warning(f"[upload_sentence] 预处理前发现 temp_wav_path 不存在: {temp_wav_path}")
                        # 直接使用 HP5_only_main_vocal 预处理，输出主人声 wav
                        preprocessed_path = preprocess_audio(
                            temp_wav_path,
                            final_audio_path,
                            device="cuda",  # 可按需改为 "cpu"
                            is_half=True,
                        )
                        
                        if preprocessed_path and os.path.exists(preprocessed_path):
                            # 验证预处理后的文件是否有效（检查文件大小和格式）
                            file_size = os.path.getsize(preprocessed_path)
                            if file_size > 0:
                                logger.info(f"[upload_sentence] 音频预处理成功: {temp_wav_path} -> {final_audio_path} (大小: {file_size} bytes)")
                                print(f"[upload_sentence] ✅ 音频预处理成功: {final_audio_path} (大小: {file_size} bytes)")
                                
                                # 确保最终文件存在且有效
                                if os.path.exists(final_audio_path) and os.path.getsize(final_audio_path) > 0:
                                    # 清理临时WAV文件
                                    if os.path.exists(temp_wav_path) and temp_wav_path != final_audio_path:
                                        try:
                                            os.remove(temp_wav_path)
                                        except:
                                            pass
                                else:
                                    logger.error(f"[upload_sentence] 预处理后的文件无效: {final_audio_path}")
                                    print(f"[upload_sentence] ❌ 预处理后的文件无效: {final_audio_path}")
                                    # 如果预处理后的文件无效，尝试使用转码后的原始WAV文件
                                    if os.path.exists(temp_wav_path) and os.path.getsize(temp_wav_path) > 0:
                                        logger.warning(f"[upload_sentence] 使用转码后的原始WAV文件作为备选")
                                        shutil.copy(temp_wav_path, final_audio_path)
                                        os.remove(temp_wav_path)
                                    else:
                                        logger.error(f"[upload_sentence] 转码后的WAV文件也不存在或无效: {temp_wav_path}")
                            else:
                                logger.warning(f"[upload_sentence] 预处理后的文件大小为0: {preprocessed_path}")
                                print(f"[upload_sentence] ⚠️ 预处理后的文件大小为0: {preprocessed_path}")
                                # 预处理后的文件无效，使用转码后的WAV文件
                                if os.path.exists(temp_wav_path) and os.path.getsize(temp_wav_path) > 0:
                                    logger.warning(f"[upload_sentence] 使用转码后的原始WAV文件")
                                    shutil.copy(temp_wav_path, final_audio_path)
                                    os.remove(temp_wav_path)
                                else:
                                    logger.error(f"[upload_sentence] 转码后的WAV文件也不存在或无效: {temp_wav_path}")
                        else:
                            logger.warning(f"[upload_sentence] 音频预处理失败，使用转码后的原始WAV文件")
                            print(f"[upload_sentence] ⚠️ 音频预处理失败，使用转码后的原始WAV文件")
                            # 预处理失败，使用转码后的WAV文件
                            if os.path.exists(temp_wav_path) and os.path.getsize(temp_wav_path) > 0:
                                shutil.copy(temp_wav_path, final_audio_path)
                                os.remove(temp_wav_path)
                            else:
                                logger.error(f"[upload_sentence] 转码后的WAV文件也不存在或无效: {temp_wav_path}")
                    except Exception as e:
                        logger.error(f"[upload_sentence] 音频预处理异常: {str(e)}")
                        import traceback
                        logger.error(traceback.format_exc())
                        print(f"[upload_sentence] ❌ 音频预处理异常: {str(e)}")
                        # 预处理异常，使用转码后的WAV文件
                        if os.path.exists(temp_wav_path):
                            shutil.copy(temp_wav_path, final_audio_path)
                            os.remove(temp_wav_path)
                else:
                    # 如果没有预处理模块，直接使用转码后的WAV文件
                    logger.info(f"[upload_sentence] 音频预处理模块不可用，使用转码后的原始WAV文件")
                    print(f"[upload_sentence] ⚠️ 音频预处理模块不可用，使用转码后的原始WAV文件")
                    if os.path.exists(temp_wav_path):
                        shutil.copy(temp_wav_path, final_audio_path)
                        os.remove(temp_wav_path)
                
                # 保存文本文件
                text_path = os.path.join(user_dataset_dir, text_filename)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(sentence_text)
                
                logger.info(f"[upload_sentence] 用户 {user_id} 上传句子 {sentence_idx}: {audio_filename}, {text_filename}")
                print(f"[upload_sentence] ✅ 用户 {user_id} 上传句子 {sentence_idx} 完成: {audio_filename}, {text_filename}")
                
                return JSONResponse({
                    "code": 200,
                    "message": f"句子 {sentence_idx + 1} 上传成功",
                    "sentence_index": sentence_idx,
                    "audio_path": final_audio_path,
                    "text_path": text_path
                }, status_code=200)
                
            except ValueError:
                return JSONResponse({
                    "code": 400,
                    "message": f"句子索引格式错误: {sentence_index}"
                }, status_code=400)
            except Exception as e:
                logger.error(f"[upload_sentence] 上传失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse({
                    "code": 500,
                    "message": f"上传失败: {str(e)}"
                }, status_code=500)
        
        # 查询用户已上传的句子列表
        @app.get("/train/check_uploaded_sentences")
        async def check_uploaded_sentences(
            user_id: str = Query(...)
        ):
            """查询用户已上传的句子索引列表"""
            try:
                model_version = "v2Pro"
                # 确保使用绝对路径（DATASET_DIR 可能是相对路径）
                if os.path.isabs(DATASET_DIR):
                    dataset_base = DATASET_DIR
                else:
                    # 获取项目根目录（以进程工作目录为准）
                    dataset_base = os.path.join(now_dir, DATASET_DIR)
                user_dataset_dir = os.path.join(dataset_base, user_id, model_version)
                
                # 检查目录是否存在
                if not os.path.exists(user_dataset_dir):
                    return JSONResponse({
                        "code": 200,
                        "uploaded_sentences": [],
                        "message": "用户数据集目录不存在"
                    }, status_code=200)
                
                # 检查已上传的句子（同时存在 audio 和 text 文件）
                # 自动扫描所有 sentence_*.txt 文件，不再限制为13句
                uploaded_indices = []
                text_files = [f for f in os.listdir(user_dataset_dir) if f.startswith("sentence_") and f.endswith(".txt")]
                
                for text_file in text_files:
                    # 提取索引：sentence_13.txt -> 13
                    try:
                        idx_str = text_file.replace("sentence_", "").replace(".txt", "")
                        i = int(idx_str)
                        audio_path = os.path.join(user_dataset_dir, f"sentence_{i}.wav")
                        text_path = os.path.join(user_dataset_dir, f"sentence_{i}.txt")
                        
                        # 只有同时存在音频和文本文件才算已上传
                        if os.path.exists(audio_path) and os.path.exists(text_path):
                            # 检查文件大小，确保不是空文件
                            if os.path.getsize(audio_path) > 0 and os.path.getsize(text_path) > 0:
                                uploaded_indices.append(i)
                    except ValueError:
                        continue  # 跳过格式不正确的文件名
                
                uploaded_indices.sort()  # 按索引排序
                # 只保留前 N 句（前端展示/录制用）
                uploaded_indices = [i for i in uploaded_indices if i < MAX_READ_SENTENCES]
                
                logger.info(f"[check_uploaded_sentences] 用户 {user_id} 已上传 {len(uploaded_indices)} 句: {uploaded_indices}")
                
                valid_pairs, weak_pairs = _collect_valid_dataset_pairs(user_dataset_dir, sentence_only=True)
                valid_sentence_count = len(valid_pairs)

                return JSONResponse({
                    "code": 200,
                    "uploaded_sentences": uploaded_indices,
                    "valid_sentence_count": valid_sentence_count,
                    "weak_sentence_count": weak_pairs,
                    "min_required_sentences": MIN_TRAIN_SENTENCE_COUNT,
                    "can_start_training": valid_sentence_count >= MIN_TRAIN_SENTENCE_COUNT,
                    "message": f"已查询到 {len(uploaded_indices)} 句已上传"
                }, status_code=200)
                
            except Exception as e:
                logger.error(f"[check_uploaded_sentences] 查询失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse({
                    "code": 500,
                    "message": f"查询失败: {str(e)}",
                    "uploaded_sentences": []
                }, status_code=500)
        
        # 列出用户数据集中的所有文件（文本和音频）
        @app.get("/train/list_dataset_files")
        async def list_dataset_files(
            user_id: str = Query(...),
            model_version: str = Query("v2Pro")
        ):
            """列出用户数据集目录中的所有文本和音频文件，返回文件列表和文本内容"""
            try:
                # 确保使用绝对路径（DATASET_DIR 可能是相对路径）
                if os.path.isabs(DATASET_DIR):
                    dataset_base = DATASET_DIR
                else:
                    # 获取项目根目录（以进程工作目录为准）
                    dataset_base = os.path.join(now_dir, DATASET_DIR)
                user_dataset_dir = os.path.join(dataset_base, user_id, model_version)
                
                if not os.path.exists(user_dataset_dir):
                    return JSONResponse({
                        "code": 200,
                        "files": [],
                        "message": "用户数据集目录不存在"
                    }, status_code=200)
                
                files = []
                # 扫描所有 sentence_*.txt 文件
                for filename in sorted(os.listdir(user_dataset_dir)):
                    if filename.startswith("sentence_") and filename.endswith(".txt"):
                        try:
                            # 提取索引
                            idx_str = filename.replace("sentence_", "").replace(".txt", "")
                            idx = int(idx_str)
                            
                            text_path = os.path.join(user_dataset_dir, filename)
                            audio_path = os.path.join(user_dataset_dir, f"sentence_{idx}.wav")
                            
                            # 读取文本内容
                            text_content = ""
                            if os.path.exists(text_path):
                                with open(text_path, "r", encoding="utf-8") as f:
                                    text_content = f.read().strip()
                            
                            files.append({
                                "index": idx,
                                "text_file": filename,
                                "audio_file": f"sentence_{idx}.wav" if os.path.exists(audio_path) else None,
                                "text_content": text_content,
                                "has_audio": os.path.exists(audio_path) and os.path.getsize(audio_path) > 0,
                                "has_text": os.path.exists(text_path) and os.path.getsize(text_path) > 0
                            })
                        except ValueError:
                            continue  # 跳过格式不正确的文件名
                
                # 按索引排序
                files.sort(key=lambda x: x["index"])
                # 只返回前 N 句（前端展示/录制用）
                files = [x for x in files if x["index"] < MAX_READ_SENTENCES]
                
                logger.info(f"[list_dataset_files] 用户 {user_id} 数据集共有 {len(files)} 个文件")
                
                return JSONResponse({
                    "code": 200,
                    "files": files,
                    "total": len(files),
                    "message": f"共返回 {len(files)} 个文件（已限制为前{MAX_READ_SENTENCES}句）"
                }, status_code=200)
                
            except Exception as e:
                logger.error(f"[list_dataset_files] 查询失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse({
                    "code": 500,
                    "message": f"查询失败: {str(e)}",
                    "files": []
                }, status_code=500)
        
        # 获取已上传的音频文件（用于试听）
        @app.get("/train/get_uploaded_audio")
        async def get_uploaded_audio(
            user_id: str = Query(...),
            sentence_index: int = Query(...),
            model_version: str = Query("v2Pro")
        ):
            """获取已上传的音频文件，用于前端试听"""
            try:
                # 确保使用绝对路径（DATASET_DIR 可能是相对路径）
                if os.path.isabs(DATASET_DIR):
                    dataset_base = DATASET_DIR
                else:
                    # 获取项目根目录（以进程工作目录为准）
                    dataset_base = os.path.join(now_dir, DATASET_DIR)
                
                user_dataset_dir = os.path.join(dataset_base, user_id, model_version)
                audio_path = os.path.join(user_dataset_dir, f"sentence_{sentence_index}.wav")
                
                logger.info(f"[get_uploaded_audio] 请求参数: user_id={user_id}, sentence_index={sentence_index}, model_version={model_version}")
                logger.info(f"[get_uploaded_audio] DATASET_DIR={DATASET_DIR}")
                logger.info(f"[get_uploaded_audio] user_dataset_dir={user_dataset_dir}")
                logger.info(f"[get_uploaded_audio] audio_path={audio_path}")
                logger.info(f"[get_uploaded_audio] 文件是否存在: {os.path.exists(audio_path)}")
                
                if not os.path.exists(audio_path):
                    # 列出目录中的所有文件，用于调试
                    if os.path.exists(user_dataset_dir):
                        files_in_dir = os.listdir(user_dataset_dir)
                        logger.warning(f"[get_uploaded_audio] 目录 {user_dataset_dir} 中的文件: {files_in_dir}")
                    else:
                        logger.warning(f"[get_uploaded_audio] 目录 {user_dataset_dir} 不存在")
                    
                    return JSONResponse({
                        "code": 404,
                        "message": f"音频文件不存在: sentence_{sentence_index}.wav (路径: {audio_path})"
                    }, status_code=404)
                
                # 检查文件大小
                if os.path.getsize(audio_path) == 0:
                    return JSONResponse({
                        "code": 400,
                        "message": "音频文件为空"
                    }, status_code=400)
                
                # 返回音频文件
                def iterfile():
                    with open(audio_path, "rb") as f:
                        yield from f
                
                # 获取文件的修改时间，用于ETag
                file_mtime = os.path.getmtime(audio_path)
                
                return StreamingResponse(
                    iterfile(),
                    media_type="audio/wav",
                    headers={
                        "Content-Disposition": f"attachment; filename=sentence_{sentence_index}.wav",
                        "Cache-Control": "no-cache, no-store, must-revalidate",  # 禁用缓存
                        "Pragma": "no-cache",  # HTTP/1.0 兼容
                        "Expires": "0",  # 立即过期
                        "ETag": f'"{int(file_mtime)}"',  # 使用文件修改时间作为ETag
                        "Last-Modified": datetime.fromtimestamp(file_mtime).strftime("%a, %d %b %Y %H:%M:%S GMT")
                    }
                )
                
            except Exception as e:
                logger.error(f"[get_uploaded_audio] 获取音频失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse({
                    "code": 500,
                    "message": f"获取音频失败: {str(e)}"
                }, status_code=500)
        
        # 检查模型名称是否已存在（冲突检测）
        @app.get("/train/check_model_name")
        async def check_model_name(
            model_name: str = Query(...)
        ):
            """检查模型名称是否已存在，用于冲突检测"""
            try:
                if not model_name or not model_name.strip():
                    return JSONResponse({
                        "code": 400,
                        "exists": False,
                        "message": "模型名称不能为空"
                    }, status_code=400)
                
                model_name = model_name.strip()
                exists = False
                conflict_info = []
                
                # 1. 检查 voice_library.json 中是否已有同名模型
                load_voice_library_from_file()
                for voice_id, voice_info in VOICE_LIBRARY.items():
                    if voice_info.get("name") == model_name:
                        exists = True
                        conflict_info.append({
                            "type": "已训练模型",
                            "voice_id": voice_id,
                            "trained_at": voice_info.get("trained_at", "未知时间")
                        })
                        break
                
                # 2. 检查正在训练的任务中是否有同名模型
                for task_id, task_info in train_tasks.items():
                    if task_info.get("model_name") == model_name:
                        task_status = task_info.get("status", "unknown")
                        if task_status in ["pending", "running"]:
                            exists = True
                            conflict_info.append({
                                "type": "正在训练",
                                "task_id": task_id,
                                "status": task_status
                            })
                        break
                
                if exists:
                    logger.warning(f"[check_model_name] 模型名称 '{model_name}' 已存在，冲突信息: {conflict_info}")
                    return JSONResponse({
                        "code": 200,
                        "exists": True,
                        "message": f"模型名称 '{model_name}' 已存在",
                        "conflict_info": conflict_info
                    }, status_code=200)
                else:
                    return JSONResponse({
                        "code": 200,
                        "exists": False,
                        "message": f"模型名称 '{model_name}' 可用"
                    }, status_code=200)
                    
            except Exception as e:
                logger.error(f"[check_model_name] 检查失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse({
                    "code": 500,
                    "exists": False,
                    "message": f"检查失败: {str(e)}"
                }, status_code=500)
        
        # 从已上传的句子开始训练
        @app.post("/train/start_from_sentences")
        async def start_train_from_sentences(
            request: Request,
            background_tasks: BackgroundTasks = BackgroundTasks()
        ):
            """从已上传的逐句数据开始训练"""
            try:
                json_data = await request.json()
                # 用户编号即模型名：模型名与 user_id 绑定
                user_id = (json_data.get("user_id") or json_data.get("model_name") or "wx_clone_user").strip()
                model_name = (json_data.get("model_name") or "").strip()
                # 如果前端未单独提供 model_name，则使用 user_id 作为模型名
                if not model_name:
                    model_name = user_id
                # 强制约定：模型名等于用户编号，避免前后不一致
                model_name = user_id
                language = json_data.get("language", "中文")
                scene = json_data.get("scene", "绘本故事")
                emotion = json_data.get("emotion", "中性")
                fast_mode = bool(json_data.get("fast_mode", True))
                req_epochs = int(json_data.get("epochs", 5 if fast_mode else 30))

                raw_session_uploaded_sentences = json_data.get("session_uploaded_sentences", None)
                session_uploaded_sentences = None
                if raw_session_uploaded_sentences is not None:
                    if not isinstance(raw_session_uploaded_sentences, list):
                        return {
                            "code": 400,
                            "message": "参数 session_uploaded_sentences 格式无效，应为数组"
                        }
                    session_uploaded_sentences = []
                    for item in raw_session_uploaded_sentences:
                        try:
                            idx = int(item)
                        except Exception:
                            continue
                        if 0 <= idx < 100:
                            session_uploaded_sentences.append(idx)
                    session_uploaded_sentences = sorted(set(session_uploaded_sentences))
                
                if not user_id:
                    return {
                        "code": 400,
                        "message": "缺少参数: user_id（用户编号 / 模型名）"
                    }
                
                # 检查模型名称是否已存在（冲突检测，仅用于提示，不再强制禁止）
                exists = False
                conflict_info = []
                
                # 1. 检查 voice_library.json 中是否已有同名模型
                load_voice_library_from_file()
                for voice_id, voice_info in VOICE_LIBRARY.items():
                    if voice_info.get("name") == model_name:
                        exists = True
                        conflict_info.append({
                            "type": "已训练模型",
                            "voice_id": voice_id,
                            "trained_at": voice_info.get("trained_at", "未知时间")
                        })
                        break
                
                # 2. 检查正在训练的任务中是否有同名模型
                for task_id, task_info in train_tasks.items():
                    if task_info.get("model_name") == model_name:
                        task_status = task_info.get("status", "unknown")
                        if task_status in ["pending", "running"]:
                            exists = True
                            conflict_info.append({
                                "type": "正在训练",
                                "task_id": task_id,
                                "status": task_status
                            })
                        break
                # 对于存在的模型名，只做警告日志和前端提示，不再阻止继续训练
                if exists:
                    conflict_msg = f"模型名称 '{model_name}' 已存在（允许继续使用同名模型）。"
                    logger.warning(f"[start_from_sentences] 模型名称冲突但允许继续: {model_name}, 冲突信息: {conflict_info}")
                
                # 检查用户数据集目录
                model_version = "v2Pro"
                user_dataset_dir = os.path.join(DATASET_DIR, user_id, model_version)
                
                if not os.path.exists(user_dataset_dir):
                    return {
                        "code": 400,
                        "message": f"用户数据集目录不存在: {user_dataset_dir}"
                    }
                
                # 检查已上传的句子文件：至少需要 MIN_TRAIN_SENTENCE_COUNT 句有效语音文本对
                valid_pairs, weak_pairs = _collect_valid_dataset_pairs(user_dataset_dir, sentence_only=True)
                valid_sentence_count = len(valid_pairs)

                if valid_sentence_count < MIN_TRAIN_SENTENCE_COUNT:
                    return {
                        "code": 400,
                        "message": _build_train_min_sentence_message(valid_sentence_count, weak_pairs)
                    }

                # 若前端提供了“本轮上传索引”，则额外校验本轮有效句数，避免历史残留数据误触发训练
                if session_uploaded_sentences is not None:
                    if len(session_uploaded_sentences) < MIN_TRAIN_SENTENCE_COUNT:
                        return {
                            "code": 400,
                            "message": f"本轮至少需要上传{MIN_TRAIN_SENTENCE_COUNT}句录音后才能训练。"
                        }

                    valid_sentence_indices = set()
                    for pair in valid_pairs:
                        audio_name = os.path.basename(pair.get("audio_path", ""))
                        if not audio_name.startswith("sentence_") or not audio_name.endswith(".wav"):
                            continue
                        try:
                            idx = int(audio_name.replace("sentence_", "").replace(".wav", ""))
                        except Exception:
                            continue
                        valid_sentence_indices.add(idx)

                    session_valid_count = len([idx for idx in session_uploaded_sentences if idx in valid_sentence_indices])
                    if session_valid_count < MIN_TRAIN_SENTENCE_COUNT:
                        return {
                            "code": 400,
                            "message": (
                                f"本轮仅检测到{session_valid_count}句有效新录音，"
                                f"至少需要{MIN_TRAIN_SENTENCE_COUNT}句后才能训练。"
                            )
                        }

                # 生成任务ID
                task_id = str(uuid.uuid4())
                
                # 准备训练参数
                params = train_api_module.TrainParams(
                    user_id=user_id,
                    task_id=task_id,
                    dataset_path=user_dataset_dir,
                    model_name=model_name,
                    language=language,
                    scene=scene,
                    emotion=emotion,
                    fast_mode=fast_mode,
                    epochs=req_epochs,
                    batch_size=4,
                    model_version=model_version
                )
                
                # 准备路径
                output_path = os.path.join(TRAIN_OUTPUT_DIR, user_id, task_id)
                log_path = os.path.join(TRAIN_LOG_DIR, f"{task_id}.log")
                os.makedirs(output_path, exist_ok=True)
                os.makedirs(TRAIN_LOG_DIR, exist_ok=True)
                
                # 初始化训练任务状态
                train_tasks[task_id] = {
                    "status": "running",
                    "progress": 0,
                    "message": "训练已启动",
                    "audio_path": user_dataset_dir,  # 数据集目录
                    "text": "",  # 文本已保存在文件中
                    "model_name": model_name,
                    "language": language,
                    "scene": scene,
                    "emotion": emotion,
                    "user_id": user_id,
                    "version": model_version,
                    "dataset_type": "sentences",  # 标记为逐句数据集
                    "sentence_count": valid_sentence_count,
                    "log_path": log_path,
                    "model_path": ""
                }
                
                # 启动训练任务（传递正确的参数）
                background_tasks.add_task(
                    train_api_module.run_training,
                    task_id=task_id,
                    dataset_path=user_dataset_dir,
                    output_path=output_path,
                    log_path=log_path,
                    params=params
                )
                
                logger.info(f"[start_from_sentences] 启动训练任务: {task_id}, 用户: {user_id}, 数据集: {user_dataset_dir}")
                
                return {
                    "code": 200,
                    "task_id": task_id,
                    "message": "训练任务已启动"
                }
                
            except Exception as e:
                logger.error(f"[start_from_sentences] 启动训练失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return {
                    "code": 500,
                    "message": f"启动训练失败: {str(e)}"
                }
        
        # 兼容旧接口路径 /train/start
        @app.post("/train/start")
        async def train_start_compat(
            request: Request,
            background_tasks: BackgroundTasks = BackgroundTasks()
        ):
            # 兼容 application/x-www-form-urlencoded 和 application/json
            try:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    json_data = await request.json()
                    task_id = json_data.get("task_id")
                else:
                    # 表单数据
                    form_data = await request.form()
                    task_id = form_data.get("task_id")
                
                if not task_id:
                    return {
                        "code": 400,
                        "message": "缺少参数: task_id"
                    }
            except Exception as e:
                return {
                    "code": 400,
                    "message": f"解析请求参数失败: {str(e)}"
                }
            """兼容旧接口路径 /train/start，启动训练任务"""
            try:
                if task_id not in train_tasks:
                    return {
                        "code": 400,
                        "message": "任务ID不存在，请先上传训练数据"
                    }
                
                task = train_tasks[task_id]
                if task["status"] != "pending":
                    return {
                        "code": 400,
                        "message": f"任务状态不正确，当前状态: {task['status']}"
                    }
                
                # 准备训练参数
                params = TrainParams(
                    user_id=task.get("user_id", "wx_clone_user"),
                    model_version=task.get("version", "v2Pro"),
                    epochs=50,  # 默认值
                    batch_size=8,
                    learning_rate=1e-5,
                    language=task.get("language", "中文")
                )
                
                # 准备路径
                dataset_path = os.path.join(DATASET_DIR, params.user_id, params.model_version)
                valid_pairs, weak_pairs = _collect_valid_dataset_pairs(dataset_path, sentence_only=False)
                if len(valid_pairs) < MIN_TRAIN_SENTENCE_COUNT:
                    return {
                        "code": 400,
                        "message": _build_train_min_sentence_message(len(valid_pairs), weak_pairs)
                    }

                output_path = os.path.join(TRAIN_OUTPUT_DIR, params.user_id, task_id)
                log_path = os.path.join(TRAIN_LOG_DIR, f"{task_id}.log")
                os.makedirs(output_path, exist_ok=True)
                
                # 更新任务状态
                train_tasks[task_id].update({
                    "status": "running",
                    "progress": 5,
                    "message": "训练已启动",
                    "log_path": log_path,
                    "model_path": "",
                    "ref_audio_path": None,
                    "ref_text": None,
                    "ref_language": None
                })
                
                # 后台启动训练
                background_tasks.add_task(
                    run_training,
                    task_id=task_id,
                    dataset_path=dataset_path,
                    output_path=output_path,
                    log_path=log_path,
                    params=params
                )
                
                return {
                    "code": 0,  # 前端期望 code: 0
                    "task_id": task_id,
                    "message": "训练任务已启动，请使用 /train/status 查询进度"
                }
                
            except Exception as e:
                logger.error(f"启动训练失败: {str(e)}")
                return {
                    "code": 400,
                    "message": f"启动训练失败: {str(e)}"
                }
        
        # 兼容旧接口路径 /train/status
        @app.get("/train/status")
        async def train_status_compat(task_id: str = Query(...)):
            """兼容旧接口路径 /train/status，查询训练任务状态和进度"""
            try:
                if task_id not in train_tasks:
                    return {
                        "code": 400,
                        "message": "任务ID不存在"
                    }
                
                task = train_tasks[task_id]
                status = task["status"]
                
                # 转换状态格式（running -> running, completed -> completed, failed -> failed）
                status_map = {
                    "running": "running",
                    "completed": "completed",
                    "failed": "failed",
                    "pending": "pending"
                }
                
                # 获取 voice_id（如果已注册）
                voice_id = task.get("voice_id")
                if not voice_id and status == "completed":
                    # 如果训练完成但还没有 voice_id，尝试从路径推断或返回空
                    voice_id = None
                
                return {
                    "code": 0,  # 前端期望 code: 0
                    "task_id": task_id,
                    "status": status_map.get(status, status),
                    "progress": task.get("progress", 0),
                    "message": task.get("message", ""),
                    "voice_id": voice_id,  # 训练完成时应该有值
                    "gpt_path": task.get("gpt_path", ""),
                    "sovits_path": task.get("sovits_path", "")
                }
                
            except Exception as e:
                logger.error(f"查询训练状态失败: {str(e)}")
                return {
                    "code": 400,
                    "message": f"查询失败: {str(e)}"
                }

        @app.post("/start_training")
        async def start_training(
            params: TrainParams,
            background_tasks: BackgroundTasks
        ):
            """启动模型训练任务"""
            # 校验模型版本
            if params.model_version not in model_versions:
                return {"code": 400, "message": f"模型版本无效，支持版本：{model_versions}"}
            
            # 检查数据集是否存在
            dataset_path = os.path.join(DATASET_DIR, params.user_id, params.model_version)
            if not os.path.exists(dataset_path):
                return {"code": 400, "message": f"用户数据集目录不存在: {dataset_path}"}

            valid_pairs, weak_pairs = _collect_valid_dataset_pairs(dataset_path, sentence_only=False)
            if len(valid_pairs) < MIN_TRAIN_SENTENCE_COUNT:
                return {
                    "code": 400,
                    "message": _build_train_min_sentence_message(len(valid_pairs), weak_pairs)
                }

            # 创建任务ID和输出目录
            task_id = str(uuid.uuid4())
            output_path = os.path.join(TRAIN_OUTPUT_DIR, params.user_id, task_id)
            log_path = os.path.join(TRAIN_LOG_DIR, f"{task_id}.log")
            os.makedirs(output_path, exist_ok=True)

            # 初始化任务状态
            train_tasks[task_id] = {
                "status": "running",  # running/completed/failed
                "progress": 0,
                "log_path": log_path,
                "model_path": "",
                "version": params.model_version,
                "user_id": params.user_id  # 用户ID
            }

            # 后台启动训练
            background_tasks.add_task(
                run_training,
                task_id=task_id,
                dataset_path=dataset_path,
                output_path=output_path,
                log_path=log_path,
                params=params
            )

            return {
                "code": 200,
                "task_id": task_id,
                "message": f"训练已启动（模型版本：{params.model_version}）",
                "log_path": log_path
            }

        @app.get("/get_train_status")
        async def get_train_status(task_id: str = Query(...)):
            """查询训练进度"""
            if task_id not in train_tasks:
                return {"code": 400, "message": "任务ID不存在"}
            task = train_tasks[task_id]
            return {
                "code": 200,
                "status": task["status"],
                "progress": task.get("progress", 0),
                "message": task.get("message", ""),
                "model_path": task.get("model_path", ""),
                "gpt_path": task.get("gpt_path", ""),
                "sovits_path": task.get("sovits_path", ""),
                "version": task.get("version", "v2Pro"),
                "log_path": task.get("log_path", "")
            }


        @app.get("/list_model_versions")
        async def list_model_versions():
            """获取支持的模型版本列表（只支持 v2Pro）"""
            return {
                "code": 200,
                "versions": model_versions,
                "default": "v2Pro"
            }

        @app.get("/get_language_options")
        async def get_language_options(version: str = Query("v2Pro")):
            """获取指定模型版本支持的语言选项（只支持 v2Pro）"""
            if version != "v2Pro":
                return {"code": 400, "message": "只支持 v2Pro 版本"}
            return {
                "code": 200,
                "languages": list(get_dict_language(version).keys())
            }
        
        logger.info("训练API接口已加载到 api.py")
        logger.info(f"已注册的训练端点包括: /train/check_uploaded_sentences, /train/check_model_name")
    else:
        logger.warning("train_api.py 不存在，训练功能不可用")
except Exception as e:
    logger.error(f"加载训练API失败: {e}，训练功能不可用")
    import traceback
    logger.error(traceback.format_exc())
if __name__ == "__main__":
    print("Starting API server...")
    # 注册关闭时的清理函数
    import atexit
    import signal
    
    # 防止重复清理的标志
    _cleanup_done = False
    
    def cleanup_on_exit():
        """API关闭时清理所有训练进程"""
        global _cleanup_done
        if _cleanup_done:
            return  # 避免重复清理
        _cleanup_done = True
        
        print("\n" + "="*60)
        print("API服务正在关闭，清理所有训练进程和GPU资源...")
        print("="*60)
        try:
            # 使用导入的清理函数
            cleanup_func = None
            if 'cleanup_all_processes' in globals():
                cleanup_func = globals()['cleanup_all_processes']
            elif 'train_api_module' in globals():
                cleanup_func = getattr(train_api_module, 'cleanup_all_processes', None)
            
            if cleanup_func:
                cleanup_func()
            else:
                print("警告: 无法找到清理函数，尝试手动清理...")
                # 手动清理训练进程（添加超时，避免阻塞）
                try:
                    result = subprocess.run(
                        ['pgrep', '-f', 'prepare_datasets|s1_train.py|s2_train.py'],
                        capture_output=True,
                        text=True,
                        timeout=2  # 2秒超时
                    )
                    if result.returncode == 0:
                        for pid_str in result.stdout.strip().split('\n'):
                            if pid_str:
                                try:
                                    pid = int(pid_str)
                                    if pid != os.getpid():
                                        print(f"  终止训练进程 (PID: {pid})")
                                        try:
                                            os.kill(pid, 15)  # SIGTERM
                                            import time as time_module
                                            time_module.sleep(0.3)  # 减少等待时间
                                            os.kill(pid, 9)  # SIGKILL
                                        except ProcessLookupError:
                                            pass  # 进程已不存在
                                        except:
                                            pass
                                except:
                                    pass
                except subprocess.TimeoutExpired:
                    print("  清理进程超时，跳过")
                except:
                    pass
                
                # 清理GPU缓存
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        print("  GPU缓存已清理")
                except:
                    pass
        except Exception as e:
            print(f"清理进程时出错: {e}")
            import traceback
            traceback.print_exc()
        print("="*60)
        print("清理完成")
        print("="*60)
    
    # 注册退出处理
    atexit.register(cleanup_on_exit)
    
    # 注册信号处理（Ctrl+C, kill等）
    def signal_handler(signum, frame):
        print(f"\n收到信号 {signum}，正在关闭服务器...")
        cleanup_on_exit()
        # 直接退出，不等待其他清理
        os._exit(0)  # 使用 os._exit 强制退出，不执行 atexit
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        uvicorn.run(app, host=host, port=port, workers=1, reload=False, access_log=True)
    except KeyboardInterrupt:
        print("\n收到中断信号，正在关闭...")
    except Exception as e:
        # 捕获所有异常（包括端口占用等），确保能正常退出
        print(f"\n服务器启动失败: {e}")
        if "address already in use" in str(e) or "Errno 98" in str(e):
            print("端口已被占用，请先停止占用端口的进程")
    finally:
        cleanup_on_exit()
        print("API server stopped.")
