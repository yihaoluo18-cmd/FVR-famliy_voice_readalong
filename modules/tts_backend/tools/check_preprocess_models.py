#!/usr/bin/env python3
"""
检查音频预处理模型是否可用
"""

import os
import sys

now_dir = os.path.dirname(os.path.abspath(__file__))

def check_denoise_model():
    """检查降噪模型"""
    print("\n" + "="*60)
    print("📦 检查降噪模型")
    print("="*60)
    
    # 检查本地模型
    local_path = os.path.join(now_dir, "tools", "denoise-model", "speech_frcrn_ans_cirm_16k")
    if os.path.exists(local_path):
        print(f"✓ 本地降噪模型存在: {local_path}")
        return True
    else:
        print(f"✗ 本地降噪模型不存在: {local_path}")
        print("  → 将使用 ModelScope 在线模型: damo/speech_frcrn_ans_cirm_16k")
        print("  → 首次使用时会自动下载")
        
        # 尝试导入 ModelScope
        try:
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks
            print("  ✓ ModelScope 库可用，将使用在线模型")
            return True
        except ImportError:
            print("  ✗ ModelScope 库未安装，请运行: pip install modelscope")
            return False


def check_uvr5_models():
    """检查UVR5去混响模型"""
    print("\n" + "="*60)
    print("📦 检查UVR5去混响模型")
    print("="*60)
    
    weight_uvr5_root = os.path.join(now_dir, "tools", "uvr5", "uvr5_weights")
    
    if not os.path.exists(weight_uvr5_root):
        print(f"✗ UVR5模型目录不存在: {weight_uvr5_root}")
        return False
    
    models_found = []
    models_missing = []
    
    # 检查常见模型
    common_models = [
        "VR-DeEchoNormal.pth",
        "VR-DeEchoAggressive.pth",
        "VR-DeEchoDeReverb.pth",
        "HP2_all_vocals.pth",
        "HP5_only_main_vocal.pth",
        "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
    ]
    
    onnx_dereverb_path = os.path.join(weight_uvr5_root, "onnx_dereverb_By_FoxJoy")
    
    for model_file in common_models:
        model_path = os.path.join(weight_uvr5_root, model_file)
        if os.path.exists(model_path):
            size_mb = os.path.getsize(model_path) / (1024 * 1024)
            models_found.append((model_file, size_mb))
        else:
            models_missing.append(model_file)
    
    if os.path.exists(onnx_dereverb_path):
        models_found.append(("onnx_dereverb_By_FoxJoy/", "目录"))
    
    if models_found:
        print("✓ 找到以下模型:")
        for model, size in models_found:
            print(f"  - {model} ({size} MB)" if isinstance(size, float) else f"  - {model} ({size})")
    
    if models_missing:
        print("\n⚠ 以下模型未找到（可选）:")
        for model in models_missing:
            print(f"  - {model}")
    
    # 列出所有模型文件
    all_models = []
    if os.path.exists(weight_uvr5_root):
        for name in os.listdir(weight_uvr5_root):
            if name.endswith(".pth") or name.endswith(".ckpt"):
                all_models.append(name)
            elif name == "onnx_dereverb_By_FoxJoy" and os.path.isdir(os.path.join(weight_uvr5_root, name)):
                all_models.append(name)
    
    if all_models:
        print(f"\n📋 所有可用模型 ({len(all_models)} 个):")
        for model in sorted(all_models):
            print(f"  - {model}")
    
    return len(models_found) > 0


def check_dependencies():
    """检查依赖库"""
    print("\n" + "="*60)
    print("📦 检查依赖库")
    print("="*60)
    
    dependencies = {
        "modelscope": "ModelScope (降噪模型)",
        "torch": "PyTorch",
        "librosa": "librosa (音频处理)",
    }
    
    all_ok = True
    for lib, desc in dependencies.items():
        try:
            __import__(lib)
            print(f"✓ {desc} 已安装")
        except ImportError:
            print(f"✗ {desc} 未安装")
            all_ok = False
    
    # 检查 ffmpeg（系统命令）
    try:
        import subprocess
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=2)
        if result.returncode == 0:
            print(f"✓ ffmpeg (系统命令) 可用")
        else:
            print(f"⚠ ffmpeg (系统命令) 可能不可用")
            all_ok = False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            import ffmpeg
            print(f"✓ ffmpeg-python 已安装")
        except ImportError:
            print(f"⚠ ffmpeg (系统命令或Python库) 未找到，但可能不影响基本功能")
    
    return all_ok


def main():
    print("\n" + "="*60)
    print("🔍 音频预处理模型检查工具")
    print("="*60)
    
    denoise_ok = check_denoise_model()
    uvr5_ok = check_uvr5_models()
    deps_ok = check_dependencies()
    
    print("\n" + "="*60)
    print("📊 检查结果总结")
    print("="*60)
    
    # 重新检查降噪功能（因为依赖检查已经确认）
    denoise_available = denoise_ok  # 使用之前检查的结果
    if denoise_available:
        print("✓ 降噪功能: 可用（使用 ModelScope 在线模型，首次使用时会自动下载）")
    else:
        print("✗ 降噪功能: 不可用（需要安装 ModelScope）")
    
    if uvr5_ok:
        print("✓ 去混响功能: 可用")
    else:
        print("✗ 去混响功能: 不可用（模型文件缺失）")
    
    if deps_ok:
        print("✓ 依赖库: 完整")
    else:
        print("⚠ 依赖库: 部分缺失")
    
    if denoise_available and uvr5_ok and deps_ok:
        print("\n✅ 所有功能可用！")
        return 0
    elif uvr5_ok and deps_ok:
        print("\n✅ 去混响功能可用！降噪功能将使用在线模型（首次使用时会自动下载）")
        return 0
    else:
        print("\n⚠️  部分功能不可用，请根据上述提示进行修复")
        return 1


if __name__ == "__main__":
    sys.exit(main())

