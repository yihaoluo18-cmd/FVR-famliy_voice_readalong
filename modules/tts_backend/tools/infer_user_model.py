#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户模型推理脚本 - 简化版
输入待合成文本，自动使用训练好的模型和用户数据集的参考音频进行推理
"""

import os
import sys
import argparse
import glob
from pathlib import Path

# 设置项目根目录
now_dir = os.getcwd()
sys.path.insert(0, now_dir)
# 确保 GPT_SoVITS 目录在路径中，以便导入 text 模块
sys.path.insert(0, os.path.join(now_dir, "GPT_SoVITS"))

os.environ["version"] = "v2Pro"
os.environ["no_proxy"] = "localhost, 127.0.0.1, ::1"
os.environ["all_proxy"] = ""

import torch
import soundfile as sf
import numpy as np
from GPT_SoVITS.inference_webui import get_tts_wav
from GPT_SoVITS.inference_webui import change_gpt_weights
from GPT_SoVITS.inference_webui import change_sovits_weights


def sanitize_text(s: str) -> str:
    """清理文本：去掉控制字符等奇怪符号"""
    import re
    if s is None:
        return ""
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\s.,!?;:、，。？！…\"'()\\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_text_language(s: str) -> str:
    """简单语言检测"""
    import re
    if not s:
        return "Chinese"
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", s))
    return "Chinese" if has_cjk else "English"


def find_latest_model(model_name, model_type, version="v2Pro"):
    """
    查找最新的模型文件
    
    Args:
        model_name: 模型名称（如 "lyh_test"）
        model_type: "gpt" 或 "sovits"
        version: 模型版本，默认 "v2Pro"
    
    Returns:
        模型文件路径，如果未找到返回 None
    """
    if model_type == "sovits":
        weight_dir = f"SoVITS_weights_{version}"
        # 匹配模式：voice_{model_name}_*.pth
        pattern = os.path.join(weight_dir, f"voice_{model_name}_*.pth")
    else:  # gpt
        weight_dir = f"GPT_weights_{version}"
        # 匹配模式：voice_{model_name}_*.ckpt
        pattern = os.path.join(weight_dir, f"voice_{model_name}_*.ckpt")
    
    if not os.path.exists(weight_dir):
        return None
    
    files = glob.glob(pattern)
    if not files:
        return None
    
    # 按修改时间排序，返回最新的
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def load_reference_from_dataset(model_name, ref_index=13, version="v2Pro"):
    """
    从用户数据集加载参考音频和文本
    
    Args:
        model_name: 模型名称（如 "lyh_test"）
        ref_index: 参考音频索引（默认13）
        version: 数据集版本，默认 "v2Pro"
    
    Returns:
        (ref_audio_path, ref_text) 元组，如果未找到返回 (None, None)
    """
    dataset_dir = os.path.join("user_datasets", model_name, version)
    
    if not os.path.exists(dataset_dir):
        return None, None
    
    # 查找参考音频
    audio_path = os.path.join(dataset_dir, f"sentence_{ref_index}.wav")
    text_path = os.path.join(dataset_dir, f"sentence_{ref_index}.txt")
    
    if not os.path.exists(audio_path):
        # 如果指定的索引不存在，尝试找第一个可用的
        audio_files = sorted(glob.glob(os.path.join(dataset_dir, "sentence_*.wav")))
        if not audio_files:
            return None, None
        audio_path = audio_files[0]
        text_path = audio_path.replace(".wav", ".txt")
    
    # 读取参考文本
    ref_text = ""
    if os.path.exists(text_path):
        with open(text_path, 'r', encoding='utf-8') as f:
            ref_text = f.read().strip()
    
    return audio_path, ref_text


def infer_text_simple(text, model_name="lyh_test", ref_index=13, output_path="output.wav", 
                     gpu="0", top_k=15, top_p=0.85, temperature=1.0, how_to_cut="凑四句一切"):
    """
    简化的推理函数
    
    Args:
        text: 待合成的文本
        model_name: 模型名称（默认 "lyh_test"）
        ref_index: 参考音频索引（默认13）
        output_path: 输出音频路径
        gpu: GPU编号
        top_k, top_p, temperature: 采样参数
        how_to_cut: 文本切分方式（默认"凑四句一切"）
    
    Returns:
        True 如果成功，False 如果失败
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    
    print("="*60)
    print("GPT-SoVITS-v2Pro 用户模型推理")
    print("="*60)
    
    # 1. 查找模型文件
    print(f"\n[1/4] 查找模型文件（模型名称: {model_name}）...")
    gpt_path = find_latest_model(model_name, "gpt")
    sovits_path = find_latest_model(model_name, "sovits")
    
    if not gpt_path:
        print(f"❌ 错误: 未找到GPT模型（查找路径: GPT_weights_v2Pro/voice_{model_name}_*.ckpt）")
        return False
    
    if not sovits_path:
        print(f"❌ 错误: 未找到SoVITS模型（查找路径: SoVITS_weights_v2Pro/voice_{model_name}_*.pth）")
        return False
    
    print(f"✓ GPT模型: {gpt_path}")
    print(f"✓ SoVITS模型: {sovits_path}")
    
    # 2. 加载参考音频和文本
    print(f"\n[2/4] 加载参考音频和文本（索引: {ref_index}）...")
    ref_audio_path, ref_text = load_reference_from_dataset(model_name, ref_index)
    
    if not ref_audio_path:
        print(f"❌ 错误: 未找到参考音频（查找路径: user_datasets/{model_name}/v2Pro/sentence_{ref_index}.wav）")
        return False
    
    if not ref_text:
        print(f"⚠️  警告: 未找到参考文本，将使用目标文本作为参考")
        ref_text = text
    
    print(f"✓ 参考音频: {ref_audio_path}")
    print(f"✓ 参考文本: {ref_text}")
    
    # 3. 设置模型路径并加载模型
    print(f"\n[3/4] 加载模型...")
    os.environ["gpt_path"] = gpt_path
    os.environ["sovits_path"] = sovits_path
    
    try:
        change_gpt_weights(gpt_path)
        change_sovits_weights(sovits_path)
        print("✓ 模型加载成功")
    except Exception as e:
        print(f"⚠️  警告: 模型加载函数调用失败（可能已加载）: {str(e)}")
    
    # 4. 文本清理和语言检测
    print(f"\n[4/4] 文本处理和推理...")
    ref_text_cleaned = sanitize_text(ref_text)
    text_cleaned = sanitize_text(text)
    
    prompt_language = "Chinese"  # 参考音频固定按中文
    text_language = detect_text_language(text_cleaned)
    
    print(f"✓ 参考文本(清理后): {ref_text_cleaned}")
    print(f"✓ 目标文本(清理后): {text_cleaned}")
    print(f"✓ 参考语言: {prompt_language}, 目标语言: {text_language}")
    print(f"✓ 文本切分方式: {how_to_cut}")
    
    # 5. 调用官方 get_tts_wav 进行推理
    try:
        gen = get_tts_wav(
            ref_wav_path=ref_audio_path,
            prompt_text=ref_text_cleaned,
            prompt_language=prompt_language,
            text=text_cleaned,
            text_language=text_language,
            how_to_cut=how_to_cut,
            top_k=top_k,
            top_p=top_p,
            temperature=temperature,
            ref_free=False,
            speed=1.0,
            if_freeze=False,
            inp_refs=None,
            sample_steps=8,
            if_sr=False,
            pause_second=0.3,
        )
        
        # get_tts_wav 是一个 generator，取第一次 yield 的 (sr, audio)
        sr, audio_np = next(gen)  # audio_np: int16 numpy array
        
        # 保存音频
        sf.write(output_path, audio_np.astype("int16"), sr)
        
        print(f"\n{'='*60}")
        print(f"✓ 推理成功！")
        print(f"✓ 采样率: {sr} Hz")
        print(f"✓ 音频长度: {len(audio_np)} samples ({len(audio_np)/sr:.2f} 秒)")
        print(f"✓ 音频已保存到: {output_path}")
        print(f"{'='*60}")
        
        return True
        
    except StopIteration:
        print(f"❌ 错误: get_tts_wav generator 没有返回数据")
        return False
    except Exception as e:
        print(f"❌ 错误: 推理失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="GPT-SoVITS-v2Pro 用户模型推理脚本（简化版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本用法：输入文本，自动使用 lyh_test 模型
  python infer_user_model.py --text "你好，这是一段测试文本"

  # 指定模型名称
  python infer_user_model.py --text "你好" --model_name lyh_test

  # 指定参考音频索引
  python infer_user_model.py --text "你好" --ref_index 0

  # 指定输出文件
  python infer_user_model.py --text "你好" --output my_output.wav

  # 指定采样参数
  python infer_user_model.py --text "你好" --top_k 20 --top_p 0.9 --temperature 0.8
        """
    )
    
    parser.add_argument("--text", type=str, required=True,
                       help="待合成的文本（必需）")
    parser.add_argument("--model_name", type=str, default="lyh_test",
                       help="模型名称（默认: lyh_test）")
    parser.add_argument("--ref_index", type=int, default=13,
                       help="参考音频索引（默认: 13）")
    parser.add_argument("--output", type=str, default="output.wav",
                       help="输出音频路径（默认: output.wav）")
    parser.add_argument("--gpu", type=str, default="0",
                       help="GPU编号（默认: 0）")
    parser.add_argument("--top_k", type=int, default=15,
                       help="top_k采样参数（默认: 15）")
    parser.add_argument("--top_p", type=float, default=0.85,
                       help="top_p采样参数（默认: 0.85）")
    parser.add_argument("--temperature", type=float, default=1.0,
                       help="温度参数（默认: 1.0）")
    parser.add_argument("--how_to_cut", type=str, default="凑四句一切",
                       choices=["不切", "凑四句一切", "凑50字一切", "按中文句号。切", "按英文句号.切", "按标点符号切"],
                       help="文本切分方式（默认: 凑四句一切）")
    
    args = parser.parse_args()
    
    # 进行推理
    success = infer_text_simple(
        text=args.text,
        model_name=args.model_name,
        ref_index=args.ref_index,
        output_path=args.output,
        gpu=args.gpu,
        top_k=args.top_k,
        top_p=args.top_p,
        temperature=args.temperature,
        how_to_cut=args.how_to_cut
    )
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

