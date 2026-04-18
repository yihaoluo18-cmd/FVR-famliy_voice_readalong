#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPT-SoVITS-v2Pro 自动化训练和推理脚本
完整流程：数据准备 -> 数据预处理 -> 模型训练 -> 推理
"""

import os
import sys
import json
import yaml
import subprocess
import argparse
from pathlib import Path
from multiprocessing import cpu_count
from typing import Optional

# 设置项目根目录
now_dir = os.getcwd()
sys.path.insert(0, now_dir)

# 默认配置
DEFAULT_CONFIG = {
    "version": "v2Pro",
    "exp_name": "my_voice",
    "dataset_dir": "dataset",
    "gpu_numbers": "0",
    "batch_size": 12,  # SoVITS默认batch_size
    "s2_epochs": 8,  # SoVITS训练epoch数
    "s2_save_every_epoch": 4,  # SoVITS每N个epoch保存一次
    "s1_epochs": 20,  # GPT训练epoch数
    "s1_save_every_epoch": 5,  # GPT每N个epoch保存一次（官方webui默认5）
    "lang": "ZH",
    "is_half": True,
}


def select_free_gpu() -> Optional[str]:
    """
    自动选择一块空闲 GPU（显存剩余最多的那块）
    返回 GPU 编号字符串，如 "0"；如果检测失败则返回 None
    """
    try:
        import subprocess

        cmd = [
            "nvidia-smi",
            "--query-gpu=index,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, encoding="utf-8")
        best_idx = None
        best_free = -1
        for line in out.strip().splitlines():
            # 形如: 0, 24564, 200, 24364
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 4:
                continue
            idx, total, used, free = parts
            free_mb = int(free)
            if free_mb > best_free:
                best_free = free_mb
                best_idx = idx
        if best_idx is not None:
            print(f"自动选择空闲 GPU: {best_idx} (剩余显存约 {best_free} MiB)")
        return best_idx
    except Exception as e:
        print(f"自动选择 GPU 失败，将回退到手动配置。原因: {e}")
        return None


# 预训练模型路径
PRETRAINED_MODELS = {
    "bert": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
    "cnhubert": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
    "s2G": "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth",
    "s2D": "GPT_SoVITS/pretrained_models/v2Pro/s2Dv2Pro.pth",
    "sv": "GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt",
}

# 输出目录
exp_root = "logs"


def check_pretrained_models():
    """检查预训练模型是否存在"""
    missing = []
    for name, path in PRETRAINED_MODELS.items():
        if not os.path.exists(path):
            missing.append(f"{name}: {path}")
    
    if missing:
        print("警告: 以下预训练模型不存在:")
        for m in missing:
            print(f"  - {m}")
        return False
    return True


def prepare_dataset_list(dataset_dir, output_file, exp_name, lang):
    """准备训练数据列表"""
    print("\n" + "="*60)
    print("步骤 1: 准备训练数据列表")
    print("="*60)
    
    cmd = [
        sys.executable, "-s", "prepare_dataset.py",
        dataset_dir, output_file, exp_name, lang
    ]
    
    result = subprocess.run(cmd, cwd=now_dir)
    if result.returncode != 0:
        print("错误: 数据准备失败")
        return False
    
    print("✓ 数据准备完成")
    return True


def run_preprocessing_step(step_name, script_name, env_vars, all_parts=1):
    """运行预处理步骤"""
    print(f"\n运行预处理步骤: {step_name}")
    
    processes = []
    for i_part in range(all_parts):
        env = os.environ.copy()
        env.update(env_vars)
        env["i_part"] = str(i_part)
        env["all_parts"] = str(all_parts)
        
        cmd = [sys.executable, "-s", script_name]
        p = subprocess.Popen(cmd, env=env, cwd=now_dir)
        processes.append(p)
    
    # 等待所有进程完成
    for p in processes:
        p.wait()
        if p.returncode != 0:
            print(f"错误: {step_name} 失败")
            return False
    
    print(f"✓ {step_name} 完成")
    return True


def preprocess_data(inp_text, inp_wav_dir, exp_name, gpu_numbers, config):
    """执行数据预处理（4个步骤）"""
    print("\n" + "="*60)
    print("步骤 2: 数据预处理")
    print("="*60)
    
    opt_dir = os.path.join(exp_root, exp_name)
    os.makedirs(opt_dir, exist_ok=True)
    
    # 样本数量
    with open(inp_text, "r", encoding="utf8") as f:
        num_items = len([l for l in f.read().strip("\n").split("\n") if l.strip()])
    
    # 并行策略：参考官方webui.py的实现
    # 官方使用: all_parts = len(gpu_names.split("-"))
    # 例如: gpu="0" -> 1个进程, gpu="0-1" -> 2个进程
    # 这样每个GPU一个进程，避免多进程争抢同一GPU显存
    gpu_names = gpu_numbers.split("-")
    all_parts = len(gpu_names)
    
    # 对于小数据集（<50条），单进程更快（避免模型加载开销）
    # 对于大数据集，多进程并行处理
    if num_items < 50:
        all_parts = 1
        print(f"数据集较小（{num_items}条），使用单进程处理")
    else:
        print(f"数据集较大（{num_items}条），使用{all_parts}个进程并行处理")
    
    # 步骤1a: 文本处理与BERT特征提取
    env_vars_1a = {
        "inp_text": inp_text,
        "inp_wav_dir": inp_wav_dir,
        "exp_name": exp_name,
        "opt_dir": opt_dir,
        "bert_pretrained_dir": PRETRAINED_MODELS["bert"],
        "is_half": str(config["is_half"]),
        "_CUDA_VISIBLE_DEVICES": gpu_numbers,
    }
    
    if not run_preprocessing_step("1a: 文本处理与BERT特征提取", 
                                  "GPT_SoVITS/prepare_datasets/1-get-text.py",
                                  env_vars_1a, all_parts):
        return False
    
    # 合并文本文件
    opt = []
    for i_part in range(all_parts):
        txt_path = os.path.join(opt_dir, f"2-name2text-{i_part}.txt")
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf8") as f:
                opt += f.read().strip("\n").split("\n")
            os.remove(txt_path)
    
    path_text = os.path.join(opt_dir, "2-name2text.txt")
    with open(path_text, "w", encoding="utf8") as f:
        f.write("\n".join(opt) + "\n")
    
    # 步骤1b: Hubert特征提取与音频重采样
    env_vars_1b = {
        "inp_text": inp_text,
        "inp_wav_dir": inp_wav_dir,
        "exp_name": exp_name,
        "opt_dir": opt_dir,
        "cnhubert_base_dir": PRETRAINED_MODELS["cnhubert"],
        "is_half": str(config["is_half"]),
        "_CUDA_VISIBLE_DEVICES": gpu_numbers,
    }
    
    if not run_preprocessing_step("1b: Hubert特征提取与音频重采样",
                                  "GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py",
                                  env_vars_1b, all_parts):
        return False
    
    # 步骤1b2: 说话人特征提取
    env_vars_1b2 = {
        "inp_text": inp_text,
        "inp_wav_dir": inp_wav_dir,
        "exp_name": exp_name,
        "opt_dir": opt_dir,
        "sv_path": PRETRAINED_MODELS["sv"],
        "is_half": str(config["is_half"]),
        "_CUDA_VISIBLE_DEVICES": gpu_numbers,
    }
    
    if not run_preprocessing_step("1b2: 说话人特征提取",
                                  "GPT_SoVITS/prepare_datasets/2-get-sv.py",
                                  env_vars_1b2, all_parts):
        return False
    
    # 步骤1c: 语义特征提取
    config_file = f"GPT_SoVITS/configs/s2{config['version']}.json"
    if not os.path.exists(config_file):
        config_file = "GPT_SoVITS/configs/s2v2Pro.json"
    
    env_vars_1c = {
        "inp_text": inp_text,
        "exp_name": exp_name,
        "opt_dir": opt_dir,
        "pretrained_s2G": PRETRAINED_MODELS["s2G"],
        "s2config_path": config_file,
        "is_half": str(config["is_half"]),
        "_CUDA_VISIBLE_DEVICES": gpu_numbers,
    }
    
    if not run_preprocessing_step("1c: 语义特征提取",
                                  "GPT_SoVITS/prepare_datasets/3-get-semantic.py",
                                  env_vars_1c, all_parts):
        return False
    
    # 合并语义文件
    opt = ["item_name\tsemantic_audio"]
    path_semantic = os.path.join(opt_dir, "6-name2semantic.tsv")
    for i_part in range(all_parts):
        semantic_path = os.path.join(opt_dir, f"6-name2semantic-{i_part}.tsv")
        if os.path.exists(semantic_path):
            with open(semantic_path, "r", encoding="utf8") as f:
                opt += f.read().strip("\n").split("\n")
            os.remove(semantic_path)
    
    with open(path_semantic, "w", encoding="utf8") as f:
        f.write("\n".join(opt) + "\n")
    
    print("\n✓ 数据预处理全部完成")
    return True


def train_sovits(exp_name, gpu_numbers, config):
    """训练SoVITS模型"""
    print("\n" + "="*60)
    print("步骤 3: 训练SoVITS模型")
    print("="*60)
    
    opt_dir = os.path.join(exp_root, exp_name)
    config_file = f"GPT_SoVITS/configs/s2{config['version']}.json"
    if not os.path.exists(config_file):
        config_file = "GPT_SoVITS/configs/s2v2Pro.json"
    
    # 读取配置文件
    with open(config_file, 'r', encoding='utf-8') as f:
        s2_config = json.load(f)
    
    # 更新配置
    s2_dir = opt_dir
    os.makedirs(os.path.join(s2_dir, f"logs_s2_{config['version']}"), exist_ok=True)
    
    s2_config["train"]["epochs"] = config["s2_epochs"]
    s2_config["train"]["batch_size"] = config["batch_size"]
    s2_config["train"]["save_every_epoch"] = config["s2_save_every_epoch"]
    # 和官网 webui 一致：写入 gpu_numbers，用于 s2_train.py 中设置 CUDA_VISIBLE_DEVICES
    s2_config["train"]["gpu_numbers"] = gpu_numbers
    # 和官网 webui 一致：设置保存选项（默认值：仅保存最新权重，每次保存时保存到weights文件夹）
    s2_config["train"]["if_save_latest"] = True
    s2_config["train"]["if_save_every_weights"] = True
    s2_config["data"]["exp_dir"] = s2_dir
    s2_config["s2_ckpt_dir"] = s2_dir
    s2_config["save_weight_dir"] = f"SoVITS_weights_{config['version']}"
    s2_config["name"] = exp_name
    s2_config["version"] = config["version"]
    s2_config["model"]["version"] = config["version"]
    s2_config["train"]["pretrained_s2G"] = PRETRAINED_MODELS["s2G"]
    s2_config["train"]["pretrained_s2D"] = PRETRAINED_MODELS["s2D"]
    
    # 保存临时配置文件
    tmp_config_path = os.path.join("TEMP", "tmp_s2.json")
    os.makedirs("TEMP", exist_ok=True)
    with open(tmp_config_path, "w", encoding='utf-8') as f:
        json.dump(s2_config, f, ensure_ascii=False, indent=2)
    
    # 设置GPU
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_numbers.replace("-", ",")
    
    # 运行训练
    cmd = [
        sys.executable, "-s", "GPT_SoVITS/s2_train.py",
        "--config", tmp_config_path
    ]
    
    print(f"开始训练SoVITS模型 (epochs={config['s2_epochs']}, batch_size={config['batch_size']})...")
    result = subprocess.run(cmd, cwd=now_dir)
    
    if result.returncode != 0:
        print("错误: SoVITS训练失败")
        return False
    
    print("✓ SoVITS模型训练完成")
    return True


def train_gpt(exp_name, gpu_numbers, config):
    """训练GPT模型"""
    print("\n" + "="*60)
    print("步骤 4: 训练GPT模型")
    print("="*60)
    
    opt_dir = os.path.join(exp_root, exp_name)
    config_file = "GPT_SoVITS/configs/s1longer-v2.yaml"
    
    # 读取配置文件
    with open(config_file, 'r', encoding='utf-8') as f:
        s1_config = yaml.load(f, Loader=yaml.FullLoader)
    
    # 更新配置
    s1_dir = opt_dir
    output_dir = os.path.join(s1_dir, f"logs_s1_{config['version']}")
    os.makedirs(output_dir, exist_ok=True)
    
    s1_config["train"]["epochs"] = config["s1_epochs"]
    s1_config["train"]["exp_name"] = exp_name
    # 和官网 webui 一致：checkpoint 相关配置
    s1_config["train"]["if_save_latest"] = True
    s1_config["train"]["if_save_every_weights"] = True
    s1_config["train"]["save_every_n_epoch"] = config.get("s1_save_every_epoch", 5)
    s1_config["train_semantic_path"] = os.path.join(s1_dir, "6-name2semantic.tsv")
    s1_config["train_phoneme_path"] = os.path.join(s1_dir, "2-name2text.txt")
    s1_config["output_dir"] = output_dir
    s1_config["train"]["half_weights_save_dir"] = f"GPT_weights_{config['version']}"
    
    # 保存临时配置文件
    tmp_config_path = os.path.join("TEMP", "tmp_s1.yaml")
    os.makedirs("TEMP", exist_ok=True)
    with open(tmp_config_path, "w", encoding='utf-8') as f:
        yaml.dump(s1_config, f, allow_unicode=True, default_flow_style=False)
    
    # 设置GPU
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_numbers.replace("-", ",")
    
    # 运行训练
    cmd = [
        sys.executable, "-s", "GPT_SoVITS/s1_train.py",
        "--config_file", tmp_config_path
    ]
    
    print(f"开始训练GPT模型 (epochs={config['s1_epochs']})...")
    result = subprocess.run(cmd, cwd=now_dir)
    
    if result.returncode != 0:
        print("错误: GPT训练失败")
        return False
    
    print("✓ GPT模型训练完成")
    return True


def find_latest_model(exp_name, model_type, config):
    """查找最新的模型文件"""
    if model_type == "sovits":
        weight_dir = f"SoVITS_weights_{config['version']}"
        pattern = f"{exp_name}_e*.pth"
    else:  # gpt
        weight_dir = f"GPT_weights_{config['version']}"
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


def main():
    parser = argparse.ArgumentParser(description="GPT-SoVITS-v2Pro 自动化训练和推理脚本")
    parser.add_argument("--dataset_dir", type=str, default="dataset",
                       help="数据集目录（包含sentence_X.wav和sentence_X.txt）")
    parser.add_argument("--exp_name", type=str, default="my_voice",
                       help="实验名称")
    parser.add_argument(
        "--gpu",
        type=str,
        default="0",
        help="GPU编号，多个用-连接，如0-1；或使用 'auto' 自动选择空闲GPU",
    )
    parser.add_argument("--batch_size", type=int, default=12,
                       help="SoVITS训练batch size")
    parser.add_argument("--s2_epochs", type=int, default=8,
                       help="SoVITS训练epoch数")
    parser.add_argument("--s1_epochs", type=int, default=20,
                       help="GPT训练epoch数")
    parser.add_argument("--lang", type=str, default="ZH",
                       help="语言代码（ZH/EN/JA等）")
    parser.add_argument("--skip_prepare", action="store_true",
                       help="跳过数据准备步骤")
    parser.add_argument("--skip_preprocess", action="store_true",
                       help="跳过数据预处理步骤")
    parser.add_argument("--skip_train", action="store_true",
                       help="跳过训练步骤")
    parser.add_argument("--only_infer", action="store_true",
                       help="仅进行推理（需要先完成训练）")
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()

    # 处理 GPU 选择逻辑
    gpu_arg = args.gpu.strip()
    if gpu_arg.lower() == "auto":
        auto_gpu = select_free_gpu()
        if auto_gpu is None:
            # 回退到 0 号 GPU
            gpu_numbers = "0"
        else:
            gpu_numbers = auto_gpu
    else:
        gpu_numbers = gpu_arg

    config.update(
        {
            "exp_name": args.exp_name,
            "dataset_dir": args.dataset_dir,
            "gpu_numbers": gpu_numbers,
            "batch_size": args.batch_size,
            "s2_epochs": args.s2_epochs,
            "s1_epochs": args.s1_epochs,
            "lang": args.lang,
        }
    )
    
    print("="*60)
    print("GPT-SoVITS-v2Pro 自动化训练和推理脚本")
    print("="*60)
    print(f"实验名称: {config['exp_name']}")
    print(f"数据集目录: {config['dataset_dir']}")
    print(f"GPU: {config['gpu_numbers']}")
    print(f"SoVITS epochs: {config['s2_epochs']}")
    print(f"GPT epochs: {config['s1_epochs']}")
    print("="*60)
    
    # 检查预训练模型
    if not check_pretrained_models():
        print("\n警告: 部分预训练模型不存在，训练可能会失败")
        response = input("是否继续? (y/n): ")
        if response.lower() != 'y':
            return
    
    # 如果只是推理，跳过训练步骤
    if args.only_infer:
        print("\n仅进行推理模式")
        # 推理部分将在单独的脚本中实现
        print("请使用 inference.py 脚本进行推理")
        return
    
    # 步骤1: 准备数据
    if not args.skip_prepare:
        inp_text = os.path.join("output", f"{config['exp_name']}.list")
        if not prepare_dataset_list(config['dataset_dir'], inp_text, 
                                    config['exp_name'], config['lang']):
            return
    else:
        inp_text = os.path.join("output", f"{config['exp_name']}.list")
        if not os.path.exists(inp_text):
            print(f"错误: 数据列表文件不存在: {inp_text}")
            return
    
    inp_wav_dir = config['dataset_dir']
    
    # 步骤2: 数据预处理
    if not args.skip_preprocess:
        if not preprocess_data(inp_text, inp_wav_dir, config['exp_name'], 
                              config['gpu_numbers'], config):
            return
    
    # 步骤3和4: 训练模型
    if not args.skip_train:
        if not train_sovits(config['exp_name'], config['gpu_numbers'], config):
            return
        
        if not train_gpt(config['exp_name'], config['gpu_numbers'], config):
            return
    
    # 查找训练好的模型
    sovits_model = find_latest_model(config['exp_name'], "sovits", config)
    gpt_model = find_latest_model(config['exp_name'], "gpt", config)
    
    print("\n" + "="*60)
    print("训练完成!")
    print("="*60)
    if sovits_model:
        print(f"SoVITS模型: {sovits_model}")
    if gpt_model:
        print(f"GPT模型: {gpt_model}")
    print("\n现在可以使用 inference.py 脚本进行推理了")


if __name__ == "__main__":
    main()

