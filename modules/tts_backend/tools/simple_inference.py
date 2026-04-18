#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的推理脚本 - 使用训练好的模型进行文本到语音合成
直接使用官方inference接口
"""

import os
import sys
import argparse
import json
from pathlib import Path

# 设置项目根目录
now_dir = os.getcwd()
sys.path.insert(0, now_dir)

os.environ["version"] = "v2Pro"
os.environ["no_proxy"] = "localhost, 127.0.0.1, ::1"
os.environ["all_proxy"] = ""

import torch
import soundfile as sf
import numpy as np
from GPT_SoVITS.inference_webui import get_tts_wav


def sanitize_text(s: str) -> str:
    """
    轻量清理：去掉控制字符等奇怪符号，但保留中英文、数字和常用标点。
    这样既不会因为脏字符打挂前端处理，又不会破坏英文内容。
    """
    import re

    if s is None:
        return ""
    # 允许：中文、全角标点、ASCII 字母数字、空白和常见标点
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\s.,!?;:、，。？！…\"'()\\-]", " ", s)
    # 合并多余空白
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_text_language(s: str) -> str:
    """
    简单语言检测：如果包含中文字符，优先按中文；否则按英文。
    返回值是 inference_webui 中 dict_language 的 key：'Chinese' 或 'English'。
    """
    import re

    if not s:
        return "Chinese"
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", s))
    if has_cjk:
        return "Chinese"
    # 没有中文，默认走英文前端
    return "English"


def find_latest_model(exp_name, model_type, version="v2Pro"):
    """查找最新的模型文件"""
    if model_type == "sovits":
        weight_dir = f"SoVITS_weights_{version}"
        pattern = f"{exp_name}_e*.pth"
    else:  # gpt
        weight_dir = f"GPT_weights_{version}"
        pattern = f"{exp_name}-e*.ckpt"
    
    if not os.path.exists(weight_dir):
        return None
    
    import glob
    files = glob.glob(os.path.join(weight_dir, pattern))
    if not files:
        return None
    
    # 按修改时间排序，返回最新的
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def load_reference_audio(dataset_dir, index=0):
    """从数据集中加载参考音频"""
    import glob
    audio_files = sorted(glob.glob(os.path.join(dataset_dir, "sentence_*.wav")))
    
    if not audio_files:
        return None, None
    
    if index >= len(audio_files):
        index = 0
    
    audio_path = audio_files[index]
    text_path = audio_path.replace(".wav", ".txt")
    
    ref_text = ""
    if os.path.exists(text_path):
        with open(text_path, 'r', encoding='utf-8') as f:
            ref_text = f.read().strip()
    
    return audio_path, ref_text


def infer_text(gpt_model_path, sovits_model_path, text, ref_audio_path, ref_text, 
               output_path, gpu="0", top_k=15, top_p=0.85, temperature=1.0):
    """
    使用训练好的模型进行推理
    
    Args:
        gpt_model_path: GPT模型路径
        sovits_model_path: SoVITS模型路径
        text: 要合成的文本
        ref_audio_path: 参考音频路径
        ref_text: 参考文本
        output_path: 输出音频路径
        gpu: GPU编号
        top_k, top_p, temperature: 采样参数
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    
    # 设置模型路径到环境变量（inference_webui.py会在导入时加载）
    os.environ["gpt_path"] = gpt_model_path
    os.environ["sovits_path"] = sovits_model_path
    
    # 实际调用官方的 get_tts_wav 进行推理并保存为 wav
    try:
        print(f"使用GPT模型: {gpt_model_path}")
        print(f"使用SoVITS模型: {sovits_model_path}")
        print(f"参考音频: {ref_audio_path}")
        # 轻量净化，保留中英文内容
        ref_text = sanitize_text(ref_text)
        text = sanitize_text(text)
        print(f"参考文本(清理后): {ref_text}")
        print(f"目标文本(清理后): {text}")
        print(f"生成音频: {output_path}")

        # 参考音频是你的中文数据集，这里固定按中文；目标文本根据内容自动判“中文/英文”
        prompt_language = "Chinese"
        text_language = detect_text_language(text)

        # get_tts_wav 是一个 generator，这里只取第一次 yield 的 (sr, audio)
        gen = get_tts_wav(
            ref_wav_path=ref_audio_path,
            prompt_text=ref_text,
            prompt_language=prompt_language,
            text=text,
            text_language=text_language,
            how_to_cut="不切",
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

        sr, audio_np = next(gen)  # audio_np: int16 numpy array

        # 写出到 wav 文件
        sf.write(output_path, audio_np.astype("int16"), sr)

        print(f"\n✓ 推理完成，音频已保存到: {output_path}")
        return True
        
    except Exception as e:
        print(f"错误: 推理失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="GPT-SoVITS-v2Pro 简化推理脚本")
    parser.add_argument("--exp_name", type=str, required=True,
                       help="实验名称（用于自动查找模型）")
    parser.add_argument("--text", type=str, required=True,
                       help="要合成的文本")
    parser.add_argument("--ref_audio", type=str, default=None,
                       help="参考音频路径（如果不指定，将从数据集中选择第一个）")
    parser.add_argument("--ref_text", type=str, default=None,
                       help="参考文本（如果不指定，将从对应的txt文件读取）")
    parser.add_argument("--ref_index", type=int, default=0,
                       help="参考音频索引（如果使用数据集中的音频）")
    parser.add_argument("--dataset_dir", type=str, default="dataset",
                       help="数据集目录（用于查找参考音频）")
    parser.add_argument("--gpt_model", type=str, default=None,
                       help="GPT模型路径（如果不指定，将自动查找）")
    parser.add_argument("--sovits_model", type=str, default=None,
                       help="SoVITS模型路径（如果不指定，将自动查找）")
    parser.add_argument("--output", type=str, default="output.wav",
                       help="输出音频路径")
    parser.add_argument("--gpu", type=str, default="0",
                       help="GPU编号")
    parser.add_argument("--top_k", type=int, default=15,
                       help="top_k采样参数")
    parser.add_argument("--top_p", type=float, default=0.85,
                       help="top_p采样参数")
    parser.add_argument("--temperature", type=float, default=1.0,
                       help="温度参数")
    
    args = parser.parse_args()
    
    # 查找模型
    if not args.gpt_model:
        args.gpt_model = find_latest_model(args.exp_name, "gpt")
        if not args.gpt_model:
            print(f"错误: 未找到GPT模型，请指定 --gpt_model")
            return
    
    if not args.sovits_model:
        args.sovits_model = find_latest_model(args.exp_name, "sovits")
        if not args.sovits_model:
            print(f"错误: 未找到SoVITS模型，请指定 --sovits_model")
            return
    
    # 处理参考音频
    if not args.ref_audio:
        args.ref_audio, ref_text_from_file = load_reference_audio(args.dataset_dir, args.ref_index)
        if not args.ref_audio:
            print(f"错误: 未找到参考音频")
            return
        if not args.ref_text:
            args.ref_text = ref_text_from_file
    
    if not args.ref_text:
        # 尝试从txt文件读取
        text_path = args.ref_audio.replace(".wav", ".txt")
        if os.path.exists(text_path):
            with open(text_path, 'r', encoding='utf-8') as f:
                args.ref_text = f.read().strip()
    
    if not args.ref_text:
        print("警告: 未指定参考文本，可能会影响合成效果")
        args.ref_text = args.text  # 使用目标文本作为参考
    
    print("="*60)
    print("GPT-SoVITS-v2Pro 推理")
    print("="*60)
    print(f"GPT模型: {args.gpt_model}")
    print(f"SoVITS模型: {args.sovits_model}")
    print(f"参考音频: {args.ref_audio}")
    print(f"参考文本: {args.ref_text}")
    print(f"目标文本: {args.text}")
    print(f"输出文件: {args.output}")
    print("="*60)
    
    # 进行推理
    success = infer_text(
        args.gpt_model,
        args.sovits_model,
        args.text,
        args.ref_audio,
        args.ref_text,
        args.output,
        gpu=args.gpu,
        top_k=args.top_k,
        top_p=args.top_p,
        temperature=args.temperature
    )
    
    if success:
        print(f"\n✓ 推理完成，音频已保存到: {args.output}")
    else:
        print("\n推理脚本需要进一步完善，建议使用WebUI或API接口")


if __name__ == "__main__":
    main()

