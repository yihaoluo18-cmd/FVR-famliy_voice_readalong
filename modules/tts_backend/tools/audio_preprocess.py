#!/usr/bin/env python3
"""
音频预处理模块：降噪、去混响、去延迟
集成官网的音频预处理功能
"""

import os
import sys
import traceback
import logging
from pathlib import Path
import tempfile
import shutil

logger = logging.getLogger(__name__)

# 添加必要的路径
now_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, now_dir)
sys.path.insert(0, os.path.join(now_dir, "tools"))
sys.path.insert(0, os.path.join(now_dir, "tools", "uvr5"))

# 全局变量存储模型实例（避免重复加载）
_denoise_pipeline = None
_uvr5_models = {}


def get_denoise_pipeline():
    """获取降噪模型（延迟加载）"""
    global _denoise_pipeline
    if _denoise_pipeline is None:
        try:
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks
            
            # 优先使用本地模型，否则从 ModelScope 下载
            path_denoise = os.path.join(now_dir, "tools", "denoise-model", "speech_frcrn_ans_cirm_16k")
            if not os.path.exists(path_denoise):
                path_denoise = "damo/speech_frcrn_ans_cirm_16k"
                logger.info(f"[audio_preprocess] 使用 ModelScope 模型: {path_denoise}")
            else:
                logger.info(f"[audio_preprocess] 使用本地降噪模型: {path_denoise}")
            
            _denoise_pipeline = pipeline(Tasks.acoustic_noise_suppression, model=path_denoise)
            logger.info("[audio_preprocess] 降噪模型加载成功")
        except Exception as e:
            logger.error(f"[audio_preprocess] 降噪模型加载失败: {e}")
            traceback.print_exc()
            _denoise_pipeline = None
    return _denoise_pipeline


def denoise_audio(input_path, output_path=None):
    """
    对音频进行降噪处理
    
    Args:
        input_path: 输入音频文件路径
        output_path: 输出音频文件路径（如果为None，则覆盖原文件）
    
    Returns:
        bool: 是否成功
    """
    try:
        if not os.path.exists(input_path):
            logger.error(f"[audio_preprocess] 输入文件不存在: {input_path}")
            return False
        
        pipeline = get_denoise_pipeline()
        if pipeline is None:
            logger.error("[audio_preprocess] 降噪模型未加载")
            return False
        
        if output_path is None:
            output_path = input_path
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        
        logger.info(f"[audio_preprocess] 开始降噪处理: {input_path} -> {output_path}")
        pipeline(input_path, output_path=output_path)
        logger.info(f"[audio_preprocess] 降噪处理完成: {output_path}")
        return True
    except Exception as e:
        logger.error(f"[audio_preprocess] 降噪处理失败: {e}")
        traceback.print_exc()
        return False


def get_uvr5_model(model_name, device="cuda", is_half=True):
    """
    获取UVR5模型（延迟加载）
    
    Args:
        model_name: 模型名称（如 "VR-DeEchoNormal", "onnx_dereverb_By_FoxJoy" 等）
        device: 设备（"cuda" 或 "cpu"）
        is_half: 是否使用半精度
    
    Returns:
        模型实例或None
    """
    global _uvr5_models
    
    cache_key = f"{model_name}_{device}_{is_half}"
    if cache_key in _uvr5_models:
        return _uvr5_models[cache_key]
    
    try:
        weight_uvr5_root = os.path.join(now_dir, "tools", "uvr5", "uvr5_weights")
        
        if model_name == "onnx_dereverb_By_FoxJoy":
            from mdxnet import MDXNetDereverb
            model = MDXNetDereverb(15)
            logger.info(f"[audio_preprocess] UVR5模型加载成功: {model_name} (ONNX)")
        elif "roformer" in model_name.lower():
            from bsroformer import Roformer_Loader
            model_path = os.path.join(weight_uvr5_root, model_name + ".ckpt")
            config_path = os.path.join(weight_uvr5_root, model_name + ".yaml")
            
            if not os.path.exists(model_path):
                logger.error(f"[audio_preprocess] 模型文件不存在: {model_path}")
                return None
            
            model = Roformer_Loader(
                model_path=model_path,
                config_path=config_path if os.path.exists(config_path) else None,
                device=device,
                is_half=is_half,
            )
            logger.info(f"[audio_preprocess] UVR5模型加载成功: {model_name} (Roformer)")
        else:
            # VR-DeEcho系列或其他模型
            from vr import AudioPre, AudioPreDeEcho
            
            model_path = os.path.join(weight_uvr5_root, model_name + ".pth")
            if not os.path.exists(model_path):
                logger.error(f"[audio_preprocess] 模型文件不存在: {model_path}")
                return None
            
            func = AudioPre if "DeEcho" not in model_name else AudioPreDeEcho
            agg = 10  # 默认聚合度，可以根据需要调整
            
            model = func(
                agg=int(agg),
                model_path=model_path,
                device=device,
                is_half=is_half,
            )
            logger.info(f"[audio_preprocess] UVR5模型加载成功: {model_name} (VR)")
        
        _uvr5_models[cache_key] = model
        return model
    except Exception as e:
        logger.error(f"[audio_preprocess] UVR5模型加载失败: {e}")
        traceback.print_exc()
        return None


def extract_vocal_hp5(input_path: str, output_path: str, device: str = "cuda", is_half: bool = True, format0: str = "wav") -> bool:
    """
    使用官网 UVR5 的 HP5_only_main_vocal 模型进行人声提取（只保留主人声）。
    处理完成后，保留的文件为“vocal_xxx”风格的主人声音频，最终复制到 output_path（始终为 wav）。

    Args:
        input_path: 输入音频文件路径
        output_path: 输出人声文件路径（最终为 wav）
        device: 设备（"cuda" 或 "cpu"）
        is_half: 是否使用半精度
        format0: 传给 UVR5 的导出格式（此处固定使用 "wav"）

    Returns:
        bool: 是否成功
    """
    try:
        if not os.path.exists(input_path):
            logger.error(f"[audio_preprocess] 输入文件不存在: {input_path}")
            return False

        # 固定使用 HP5_only_main_vocal 模型
        model_name = "HP5_only_main_vocal"
        model = get_uvr5_model(model_name, device, is_half)
        if model is None:
            logger.error(f"[audio_preprocess] 无法加载UVR5模型: {model_name}")
            return False

        # 确保输出目录存在
        output_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else "."
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"[audio_preprocess] 开始 HP5_only_main_vocal 预处理: {input_path} -> {output_path}")

        # 统一转为 44100Hz 双声道，保证 UVR5 工作正常
        reformatted_path = os.path.join(
            tempfile.gettempdir(),
            f"hp5_reformatted_{os.path.basename(input_path)}",
        )
        os.system(f'ffmpeg -i "{input_path}" -vn -acodec pcm_s16le -ac 2 -ar 44100 "{reformatted_path}" -y')
        actual_input = reformatted_path if os.path.exists(reformatted_path) else input_path

        # 建立临时输出目录（vocal / instrumental）
        temp_vocal_dir = os.path.join(tempfile.gettempdir(), f"hp5_vocal_{os.path.basename(input_path)}")
        temp_ins_dir = os.path.join(tempfile.gettempdir(), f"hp5_ins_{os.path.basename(input_path)}")
        os.makedirs(temp_vocal_dir, exist_ok=True)
        os.makedirs(temp_ins_dir, exist_ok=True)

        is_hp3 = "HP3" in model_name  # 对 HP5 实际为 False，但保持接口一致
        # HP 系列：_path_audio_(music_file, vocal_root, ins_root, format, is_hp3)
        model._path_audio_(actual_input, temp_vocal_dir, temp_ins_dir, "wav", is_hp3)

        # 在两个目录里都查找 vocal_*.wav（HP 系列有时会把 vocal/instrument 写反）
        vocal_candidates = []
        dir_candidates = []
        for d in [temp_vocal_dir, temp_ins_dir]:
            if os.path.exists(d):
                files = [f for f in os.listdir(d) if f.startswith("vocal_") and f.endswith(".wav")]
                for f in files:
                    vocal_candidates.append(os.path.join(d, f))
                    dir_candidates.append(d)

        # 如果没找到 vocal_，则退而求其次：把所有 wav 都列出来，至少给你一个可听的结果
        if not vocal_candidates:
            logger.warning("[audio_preprocess] 未找到 vocal_*.wav，尝试使用任意 wav 文件作为输出")
            for d in [temp_vocal_dir, temp_ins_dir]:
                if os.path.exists(d):
                    files = [f for f in os.listdir(d) if f.endswith(".wav")]
                    for f in files:
                        vocal_candidates.append(os.path.join(d, f))
                        dir_candidates.append(d)

        if not vocal_candidates:
            logger.error(f"[audio_preprocess] HP5_only_main_vocal 未找到任何 wav 输出，vocal_dir={temp_vocal_dir}, ins_dir={temp_ins_dir}")
            if os.path.exists(temp_vocal_dir):
                logger.error(f"[audio_preprocess] vocal 目录下文件: {os.listdir(temp_vocal_dir)}")
            if os.path.exists(temp_ins_dir):
                logger.error(f"[audio_preprocess] ins 目录下文件: {os.listdir(temp_ins_dir)}")
            return False

        # 选择第一个候选文件
        vocal_path = vocal_candidates[0]
        logger.info(f"[audio_preprocess] 已选定作为输出的人声文件: {vocal_path}")

        # 验证源文件是否有效（检查文件大小）
        if not os.path.exists(vocal_path):
            logger.error(f"[audio_preprocess] 选定的vocal文件不存在: {vocal_path}")
            return False
        
        source_size = os.path.getsize(vocal_path)
        if source_size == 0:
            logger.error(f"[audio_preprocess] 选定的vocal文件大小为0: {vocal_path}")
            return False
        
        logger.info(f"[audio_preprocess] vocal源文件大小: {source_size} bytes")

        # 拷贝为最终输出（始终是 wav）
        # 如果输出文件已存在，先删除以确保覆盖
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception as e:
                logger.warning(f"[audio_preprocess] 删除旧输出文件失败: {e}")
        
        shutil.copy(vocal_path, output_path)
        
        # 验证输出文件是否成功创建且有效
        if not os.path.exists(output_path):
            logger.error(f"[audio_preprocess] 输出文件创建失败: {output_path}")
            return False
        
        output_size = os.path.getsize(output_path)
        if output_size == 0:
            logger.error(f"[audio_preprocess] 输出文件大小为0: {output_path}")
            return False
        
        if output_size != source_size:
            logger.warning(f"[audio_preprocess] 输出文件大小与源文件不一致: 源={source_size}, 输出={output_size}")
        
        logger.info(f"[audio_preprocess] HP5_only_main_vocal 预处理完成，输出: {output_path} (大小: {output_size} bytes)")

        # 清理临时文件和目录（原始 /tmp 不再保留）
        try:
            if os.path.exists(reformatted_path):
                os.remove(reformatted_path)
        except:
            pass
        for tmp_dir in [temp_vocal_dir, temp_ins_dir]:
            try:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir)
            except:
                pass

        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"[audio_preprocess] HP5_only_main_vocal 预处理失败: {e}")
        traceback.print_exc()
        return False


def preprocess_audio(input_path, output_path=None, device="cuda", is_half=True):
    """
    音频预处理流程（新版）：仅使用官网 HP5_only_main_vocal 模型提取主人声。

    - 不再单独做“去混响 + 再降噪”的两步流程；
    - 直接调用 HP5_only_main_vocal，输出 vocal_xxx 风格的人声音频；
    - 最终结果为 wav 格式，保存在 output_path。

    Args:
        input_path: 输入音频文件路径
        output_path: 输出音频文件路径（如果为None，则覆盖原文件）
        device: 设备（"cuda" 或 "cpu"）
        is_half: 是否使用半精度

    Returns:
        str: 输出文件路径，失败返回None
    """
    try:
        if not os.path.exists(input_path):
            logger.error(f"[audio_preprocess] 输入文件不存在: {input_path}")
            return None

        # 确定输出路径
        if output_path is None:
            output_path = input_path
        else:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

        ok = extract_vocal_hp5(input_path, output_path, device=device, is_half=is_half, format0="wav")
        if not ok:
            logger.error("[audio_preprocess] 使用 HP5_only_main_vocal 预处理失败")
            return None

        logger.info(f"[audio_preprocess] 音频预处理完成（HP5_only_main_vocal）: {output_path}")
        return output_path if os.path.exists(output_path) else None

    except Exception as e:
        logger.error(f"[audio_preprocess] 音频预处理失败: {e}")
        traceback.print_exc()
        return None


def preprocess_audio_two_steps(input_path, output_path, device="cuda", is_half=True):
    """
    兼容旧接口：内部直接调用单步的 HP5_only_main_vocal 预处理。
    保留函数是为了兼容已有调用，但逻辑已经统一为“只用 HP5_only_main_vocal 提取人声”。
    """
    return preprocess_audio(input_path, output_path, device=device, is_half=is_half)


def preprocess_audio_two_steps_loop(input_path, output_path, loops=2, device="cuda", is_half=True):
    """
    多次循环执行“两步音频预处理”：
    - 每一轮都会执行一次 preprocess_audio_two_steps（去混响 + 降噪）
    - 下一轮的输入是上一轮的输出
    - 最终结果写到 output_path

    Args:
        input_path: 初始输入音频文件路径
        output_path: 最终输出音频文件路径
        loops: 循环次数（>=1），例如 2 表示在第一次结果基础上再处理一次
        device: 设备（"cuda" 或 "cpu"）
        is_half: 是否使用半精度

    Returns:
        str: 最终输出文件路径，失败返回 None
    """
    try:
        if loops <= 0:
            logger.error(f"[audio_preprocess] 循环次数 loops 必须 >= 1，当前: {loops}")
            return None

        current_input = input_path
        # 如果只有一轮，直接调用两步预处理，输出到指定路径
        if loops == 1:
            return preprocess_audio_two_steps(current_input, output_path, device=device, is_half=is_half)

        logger.info("=" * 60)
        logger.info(f"[audio_preprocess] 开始循环两步音频预处理，共 {loops} 轮")
        logger.info(f"[audio_preprocess] 初始输入文件: {input_path}")
        logger.info(f"[audio_preprocess] 最终输出文件: {output_path}")
        logger.info("=" * 60)

        temp_files = []
        for i in range(1, loops + 1):
            # 最后一轮输出到真正的 output_path，其余轮输出到临时文件
            if i == loops:
                round_output = output_path
            else:
                round_output = os.path.join(
                    tempfile.gettempdir(),
                    f"loop{i}_{os.path.basename(output_path) or os.path.basename(input_path)}",
                )
                temp_files.append(round_output)

            logger.info(f"\n[audio_preprocess] === 第 {i} 轮预处理开始 ===")
            logger.info(f"[audio_preprocess] 本轮输入: {current_input}")
            logger.info(f"[audio_preprocess] 本轮输出: {round_output}")

            result = preprocess_audio_two_steps(current_input, round_output, device=device, is_half=is_half)
            if not result or not os.path.exists(result):
                logger.error(f"[audio_preprocess] 第 {i} 轮预处理失败")
                # 清理已生成的临时文件
                for f in temp_files:
                    try:
                        if os.path.exists(f):
                            os.remove(f)
                    except:
                        pass
                return None

            logger.info(f"[audio_preprocess] 第 {i} 轮预处理完成，结果: {result}")
            current_input = result

        # 清理中间轮次的临时文件（最后一轮的结果保留）
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except:
                pass

        logger.info("=" * 60)
        logger.info(f"[audio_preprocess] ✅ 循环两步预处理全部完成，最终结果: {output_path}")
        logger.info("=" * 60)

        return output_path if os.path.exists(output_path) else None

    except Exception as e:
        logger.error(f"[audio_preprocess] 循环两步音频预处理失败: {e}")
        traceback.print_exc()
        return None


def list_available_models():
    """列出所有可用的UVR5模型"""
    weight_uvr5_root = os.path.join(now_dir, "tools", "uvr5", "uvr5_weights")
    models = []
    
    if os.path.exists(weight_uvr5_root):
        for name in os.listdir(weight_uvr5_root):
            if name.endswith(".pth") or name.endswith(".ckpt"):
                models.append(name.replace(".pth", "").replace(".ckpt", ""))
            elif name == "onnx_dereverb_By_FoxJoy" and os.path.isdir(os.path.join(weight_uvr5_root, name)):
                models.append(name)
    
    return models


if __name__ == "__main__":
    # 测试代码
    import argparse
    
    parser = argparse.ArgumentParser(description="音频预处理工具")
    parser.add_argument("-i", "--input", type=str, required=True, help="输入音频文件")
    parser.add_argument("-o", "--output", type=str, help="输出音频文件（默认覆盖输入文件）")
    parser.add_argument("--two-steps", action="store_true", help="使用两步预处理流程（去混响+降噪）")
    parser.add_argument("--loops", type=int, default=1, help="两步预处理循环次数（>=1），仅在 --two-steps 时生效")
    parser.add_argument("--denoise", action="store_true", help="启用降噪")
    parser.add_argument("--dereverb", action="store_true", help="启用去混响")
    parser.add_argument("--dereverb-model", type=str, default="onnx_dereverb_By_FoxJoy", help="去混响模型名称（默认：onnx_dereverb_By_FoxJoy）")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"], help="设备")
    parser.add_argument("--list-models", action="store_true", help="列出所有可用的UVR5模型")
    
    args = parser.parse_args()
    
    if args.list_models:
        models = list_available_models()
        print("可用的UVR5模型:")
        for model in models:
            print(f"  - {model}")
        sys.exit(0)
    
    if not args.input:
        parser.print_help()
        sys.exit(1)
    
    # 两步预处理流程（去混响+降噪）
    if args.two_steps:
        target_output = args.output or args.input.replace(".wav", "_preprocessed.wav")
        # 如果 loops > 1，则进行循环处理
        if args.loops and args.loops > 1:
            result = preprocess_audio_two_steps_loop(
                args.input,
                target_output,
                loops=args.loops,
                device=args.device,
            )
        else:
            result = preprocess_audio_two_steps(
                args.input,
                target_output,
                device=args.device,
            )
        if result:
            if args.loops and args.loops > 1:
                print(f"✓ 循环两步预处理完成 (loops={args.loops}): {result}")
            else:
                print(f"✓ 两步预处理完成: {result}")
        else:
            print("✗ 两步预处理失败")
            sys.exit(1)
    else:
        # 原有的预处理流程
        result = preprocess_audio(
            args.input,
            args.output,
            enable_denoise=args.denoise,
            enable_dereverb=args.dereverb,
            dereverb_model=args.dereverb_model,
            device=args.device,
        )
        if result:
            print(f"✓ 预处理完成: {result}")
        else:
            print("✗ 预处理失败")
            sys.exit(1)

