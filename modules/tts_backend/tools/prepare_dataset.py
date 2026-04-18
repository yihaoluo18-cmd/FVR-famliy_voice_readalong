#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据准备脚本：将dataset文件夹中的音频和文本文件转换为训练所需的格式
"""

import os
import sys
import glob
from pathlib import Path

def prepare_dataset(dataset_dir, output_file, exp_name="my_dataset", lang="ZH"):
    """
    准备训练数据集
    
    Args:
        dataset_dir: 数据集目录（包含sentence_X.wav和sentence_X.txt文件）
        output_file: 输出的训练数据列表文件路径
        exp_name: 实验名称
        lang: 语言代码（ZH/EN/JA等），必须是支持的语言代码
    """
    # 支持的语言代码映射（确保使用正确的大写格式）
    supported_langs = {
        "ZH": "ZH", "zh": "ZH", "中文": "ZH",
        "EN": "EN", "en": "EN", "英文": "EN",
        "JA": "JA", "ja": "JA", "日文": "JA",
        "JP": "JA", "jp": "JA",
        "KO": "KO", "ko": "KO", "韩文": "KO",
    }
    
    # 规范化语言代码
    lang_upper = lang.upper() if lang else "ZH"
    if lang_upper not in ["ZH", "EN", "JA", "KO"]:
        # 尝试从映射中获取
        lang_normalized = supported_langs.get(lang, "ZH")
        if lang_normalized != lang_upper:
            print(f"警告: 语言代码 '{lang}' 已规范化为 '{lang_normalized}'")
        lang = lang_normalized
    else:
        lang = lang_upper
    
    dataset_dir = os.path.abspath(dataset_dir)
    output_file = os.path.abspath(output_file)
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # 获取所有音频文件
    audio_files = sorted(glob.glob(os.path.join(dataset_dir, "sentence_*.wav")))
    
    if not audio_files:
        print(f"错误: 在 {dataset_dir} 中未找到任何音频文件（sentence_*.wav）")
        return False
    
    print(f"找到 {len(audio_files)} 个音频文件")
    print(f"使用语言代码: {lang}")
    
    # 生成训练数据列表
    data_lines = []
    missing_text_count = 0
    
    for audio_file in audio_files:
        # 获取对应的文本文件
        base_name = os.path.splitext(os.path.basename(audio_file))[0]
        text_file = os.path.join(dataset_dir, f"{base_name}.txt")
        
        if not os.path.exists(text_file):
            print(f"警告: 未找到文本文件 {text_file}，跳过该音频")
            missing_text_count += 1
            continue
        
        # 读取文本内容
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                text = f.read().strip()
            
            if not text:
                print(f"警告: 文本文件 {text_file} 为空，跳过")
                missing_text_count += 1
                continue
            
            # 格式：音频路径|实验名|语言|文本
            # 注意：路径使用相对路径或绝对路径，Windows使用反斜杠，Linux使用正斜杠
            audio_path = audio_file.replace('\\', '/')  # 统一使用正斜杠
            line = f"{audio_path}|{exp_name}|{lang}|{text}"
            data_lines.append(line)
            
        except Exception as e:
            print(f"错误: 读取文本文件 {text_file} 时出错: {e}")
            missing_text_count += 1
            continue
    
    if not data_lines:
        print("错误: 没有有效的训练数据")
        return False
    
    # 写入输出文件
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(data_lines) + '\n')
        
        print(f"成功生成训练数据列表: {output_file}")
        print(f"  - 有效数据: {len(data_lines)} 条")
        if missing_text_count > 0:
            print(f"  - 跳过数据: {missing_text_count} 条")
        
        return True
        
    except Exception as e:
        print(f"错误: 写入文件 {output_file} 时出错: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python prepare_dataset.py <dataset_dir> <output_file> [exp_name] [lang]")
        print("示例: python prepare_dataset.py dataset output/my_dataset.list my_dataset ZH")
        sys.exit(1)
    
    dataset_dir = sys.argv[1]
    output_file = sys.argv[2]
    exp_name = sys.argv[3] if len(sys.argv) > 3 else "my_dataset"
    lang = sys.argv[4] if len(sys.argv) > 4 else "ZH"
    
    if not os.path.exists(dataset_dir):
        print(f"错误: 数据集目录不存在: {dataset_dir}")
        sys.exit(1)
    
    success = prepare_dataset(dataset_dir, output_file, exp_name, lang)
    sys.exit(0 if success else 1)

