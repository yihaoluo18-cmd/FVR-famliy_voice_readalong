#!/usr/bin/env python3
"""
查看最近一次推理的参考音频和文本信息
从日志中提取信息，或检查 voice_library.json
"""

import json
import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]

def check_voice_library(voice_id=None):
    """检查声音库中注册的模型信息"""
    voice_library_path = BASE_DIR / "data" / "voice_library.json"
    
    if not voice_library_path.exists():
        print("❌ voice_library.json 不存在")
        return
    
    with open(voice_library_path, 'r', encoding='utf-8') as f:
        voice_library = json.load(f)
    
    if voice_id:
        if voice_id in voice_library:
            profile = voice_library[voice_id]
            print(f"\n📊 模型信息: {voice_id}")
            print(f"{'='*60}")
            print(f"模型名称: {profile.get('name', 'N/A')}")
            print(f"GPT模型路径: {profile.get('gpt_path', 'N/A')}")
            print(f"SoVITS模型路径: {profile.get('sovits_path', 'N/A')}")
            print(f"参考音频路径: {profile.get('ref_audio_path', 'N/A')}")
            
            ref_audio_path = profile.get('ref_audio_path')
            if ref_audio_path:
                full_path = Path(ref_audio_path) if os.path.isabs(ref_audio_path) else BASE_DIR / ref_audio_path
                if full_path.exists():
                    file_size = full_path.stat().st_size / 1024
                    print(f"参考音频文件大小: {file_size:.2f} KB")
                else:
                    print(f"⚠️  参考音频文件不存在: {full_path}")
            
            print(f"参考文本: {profile.get('ref_text', 'N/A')}")
            print(f"参考语言: {profile.get('ref_language', 'N/A')}")
            print(f"{'='*60}\n")
        else:
            print(f"❌ 未找到 voice_id: {voice_id}")
    else:
        print(f"\n📋 已注册的模型列表 ({len(voice_library)} 个):\n")
        for vid, profile in voice_library.items():
            print(f"  {vid}: {profile.get('name', 'N/A')}")
            print(f"    参考音频: {profile.get('ref_audio_path', 'N/A')}")
            print(f"    参考文本: {profile.get('ref_text', 'N/A')[:50]}..." if len(profile.get('ref_text', '')) > 50 else f"    参考文本: {profile.get('ref_text', 'N/A')}")
            print()

def check_recent_logs():
    """检查最近的日志文件（如果API服务器正在运行）"""
    print("\n📝 提示: API 服务器的实时日志会显示每次推理的详细信息")
    print("   包括:")
    print("   - 参考音频路径")
    print("   - 参考文本（原始和清理后）")
    print("   - 目标文本（原始和清理后）")
    print("   - 使用的模型路径")
    print("   - 语言设置")
    print("\n   查看日志的方法:")
    print("   - 如果使用 modules/tts_backend/scripts/start_api_v2.sh 启动，日志会输出到终端")
    print("   - 或者查看 API 服务器的输出窗口")

if __name__ == "__main__":
    voice_id = sys.argv[1] if len(sys.argv) > 1 else None
    check_voice_library(voice_id)
    check_recent_logs()

