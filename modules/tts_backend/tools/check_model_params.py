#!/usr/bin/env python3
"""
检测已训练模型的训练参数
使用方法: python check_model_params.py <模型名称>
"""

import os
import json
import yaml
from pathlib import Path
import sys

BASE_DIR = Path(__file__).parent

def load_yaml(file_path):
    """加载YAML文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 由于YAML包含pathlib对象，直接使用正则表达式提取关键信息
        import re
        result = {"config": {}}
        
        # 提取train配置
        train_config = {}
        batch_match = re.search(r'batch_size:\s*(\d+)', content)
        epochs_match = re.search(r'epochs:\s*(\d+)', content)
        precision_match = re.search(r'precision:\s*([^\n]+)', content)
        save_every_match = re.search(r'save_every_n_epoch:\s*(\d+)', content)
        
        if batch_match:
            train_config["batch_size"] = int(batch_match.group(1))
        if epochs_match:
            train_config["epochs"] = int(epochs_match.group(1))
        if precision_match:
            train_config["precision"] = precision_match.group(1).strip()
        if save_every_match:
            train_config["save_every_n_epoch"] = int(save_every_match.group(1))
        
        result["config"]["train"] = train_config
        
        # 提取optimizer配置
        optimizer_config = {}
        lr_init_match = re.search(r'lr_init:\s*([\d.e-]+)', content)
        lr_match = re.search(r'\blr:\s*([\d.e-]+)', content)
        warmup_match = re.search(r'warmup_steps:\s*(\d+)', content)
        decay_match = re.search(r'decay_steps:\s*(\d+)', content)
        
        if lr_init_match:
            optimizer_config["lr_init"] = float(lr_init_match.group(1))
        if lr_match:
            optimizer_config["lr"] = float(lr_match.group(1))
        if warmup_match:
            optimizer_config["warmup_steps"] = int(warmup_match.group(1))
        if decay_match:
            optimizer_config["decay_steps"] = int(decay_match.group(1))
        
        result["config"]["optimizer"] = optimizer_config
        
        return result
    except Exception as e:
        print(f"  ⚠️ 无法读取YAML文件: {e}")
        return None

def load_json(file_path):
    """加载JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️ 无法读取JSON文件: {e}")
        return None

def check_model_params(model_name):
    """检测指定模型的训练参数"""
    exp_dir = BASE_DIR / "logs" / model_name
    
    if not exp_dir.exists():
        print(f"❌ 错误: 模型目录不存在: {exp_dir}")
        return
    
    print(f"\n{'='*60}")
    print(f"📊 检测模型: {model_name}")
    print(f"📁 模型目录: {exp_dir}")
    print(f"{'='*60}\n")
    
    # 检查S1训练参数 (GPT模型)
    s1_config_path = exp_dir / "logs_s1_v2Pro" / "logs_s1_v2Pro" / "version_0" / "hparams.yaml"
    if not s1_config_path.exists():
        # 尝试查找其他版本目录
        s1_base_dir = exp_dir / "logs_s1_v2Pro" / "logs_s1_v2Pro"
        if s1_base_dir.exists():
            version_dirs = [d for d in s1_base_dir.iterdir() if d.is_dir() and d.name.startswith("version_")]
            if version_dirs:
                s1_config_path = version_dirs[0] / "hparams.yaml"
    
    if s1_config_path.exists():
        print("🔵 S1训练参数 (GPT模型):")
        hparams = load_yaml(s1_config_path)
        if hparams and "config" in hparams:
            config = hparams["config"]
            train_config = config.get("train", {})
            optimizer_config = config.get("optimizer", {})
            
            batch_size = train_config.get('batch_size', 'N/A')
            epochs = train_config.get('epochs', 'N/A')
            lr_init = optimizer_config.get('lr_init', 'N/A')
            if isinstance(lr_init, (int, float)):
                lr_init = f"{lr_init:.2e}"
            
            print(f"  批次大小 (batch_size): {batch_size} (官方值: 4)")
            print(f"  训练轮数 (epochs): {epochs} (官方值: 15)")
            print(f"  初始学习率 (lr_init): {lr_init}")
            print(f"  学习率 (lr): {optimizer_config.get('lr', 'N/A')}")
            print(f"  预热步数 (warmup_steps): {optimizer_config.get('warmup_steps', 'N/A')}")
            print(f"  衰减步数 (decay_steps): {optimizer_config.get('decay_steps', 'N/A')}")
            print(f"  精度 (precision): {train_config.get('precision', 'N/A')} (官方值: 16-mixed)")
            print(f"  每N轮保存 (save_every_n_epoch): {train_config.get('save_every_n_epoch', 'N/A')} (官方值: 5)")
            
            # 检查是否与官方值一致
            if batch_size != 'N/A' and batch_size != 4:
                print(f"  ⚠️  警告: batch_size={batch_size} 不是官方值 4")
            if epochs != 'N/A' and epochs != 15:
                print(f"  ⚠️  警告: epochs={epochs} 不是官方值 15")
        else:
            print("  ⚠️  配置文件格式不正确")
        print()
    else:
        print("🔵 S1训练参数: ❌ 未找到配置文件")
        print()
    
    # 检查S2训练参数 (SoVITS模型)
    s2_config_path = exp_dir / "config.json"
    if s2_config_path.exists():
        print("🟢 S2训练参数 (SoVITS模型):")
        config = load_json(s2_config_path)
        if config and "train" in config:
            train_config = config["train"]
            
            print(f"  批次大小 (batch_size): {train_config.get('batch_size', 'N/A')} (官方值: 4)")
            print(f"  训练轮数 (epochs): {train_config.get('epochs', 'N/A')} (官方值: 8)")
            print(f"  学习率 (learning_rate): {train_config.get('learning_rate', 'N/A')}")
            print(f"  每N轮保存 (save_every_epoch): {train_config.get('save_every_epoch', 'N/A')} (官方值: 4)")
            print(f"  FP16运行 (fp16_run): {train_config.get('fp16_run', 'N/A')} (官方值: True)")
            print(f"  片段大小 (segment_size): {train_config.get('segment_size', 'N/A')} (官方值: 20480)")
            
            # 检查是否与官方值一致
            batch_size = train_config.get('batch_size')
            epochs = train_config.get('epochs')
            if batch_size != 4:
                print(f"  ⚠️  警告: batch_size={batch_size} 不是官方值 4")
            if epochs != 8:
                print(f"  ⚠️  警告: epochs={epochs} 不是官方值 8")
        else:
            print("  ⚠️  配置文件格式不正确")
        print()
    else:
        print("🟢 S2训练参数: ❌ 未找到配置文件")
        print()
    
    # 检查模型文件
    print("📦 模型文件:")
    
    # S1模型文件 - 搜索多个可能的位置
    s1_model_file = None
    s1_dirs = [
        BASE_DIR / "GPT_weights_v2Pro",
        BASE_DIR / "GPT_weights_v2",
        BASE_DIR / "GPT_weights",
    ]
    for s1_dir in s1_dirs:
        if s1_dir.exists():
            candidate = s1_dir / f"{model_name}.ckpt"
            if candidate.exists():
                s1_model_file = candidate
                break
    
    if s1_model_file:
        size_mb = s1_model_file.stat().st_size / (1024 * 1024)
        print(f"  S1模型 (GPT): {s1_model_file.relative_to(BASE_DIR)} ({size_mb:.2f} MB)")
    else:
        print(f"  S1模型 (GPT): ❌ 未找到 (搜索路径: {[str(d.relative_to(BASE_DIR)) for d in s1_dirs]})")
    
    # S2模型文件 - 搜索多个可能的位置
    s2_model_file = None
    s2_dirs = [
        BASE_DIR / "SoVITS_weights_v2Pro",
        BASE_DIR / "SoVITS_weights_v2",
        BASE_DIR / "SoVITS_weights",
    ]
    for s2_dir in s2_dirs:
        if s2_dir.exists():
            candidate = s2_dir / f"{model_name}.pth"
            if candidate.exists():
                s2_model_file = candidate
                break
    
    if s2_model_file:
        size_mb = s2_model_file.stat().st_size / (1024 * 1024)
        print(f"  S2模型 (SoVITS): {s2_model_file.relative_to(BASE_DIR)} ({size_mb:.2f} MB)")
    else:
        print(f"  S2模型 (SoVITS): ❌ 未找到 (搜索路径: {[str(d.relative_to(BASE_DIR)) for d in s2_dirs]})")
    
    print()

def list_all_models():
    """列出所有已训练的模型"""
    logs_dir = BASE_DIR / "logs"
    if not logs_dir.exists():
        print("❌ logs目录不存在")
        return []
    
    models = []
    for entry in logs_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            # 检查是否有配置文件
            has_s1 = (entry / "logs_s1_v2Pro").exists()
            has_s2 = (entry / "config.json").exists()
            if has_s1 or has_s2:
                models.append(entry.name)
    
    return sorted(models)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        model_name = sys.argv[1]
        check_model_params(model_name)
    else:
        print("📋 可用的模型列表:\n")
        models = list_all_models()
        if models:
            for i, model in enumerate(models, 1):
                print(f"  {i}. {model}")
            print(f"\n使用方法: python check_model_params.py <模型名称>")
            print(f"例如: python check_model_params.py {models[0]}")
        else:
            print("  ❌ 未找到已训练的模型")

