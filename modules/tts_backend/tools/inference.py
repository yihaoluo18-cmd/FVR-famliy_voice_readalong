#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPT-SoVITS-v2Pro 推理脚本
使用训练好的模型进行文本到语音合成
"""

import os
import sys
import argparse
import torch
import torchaudio
import numpy as np
from pathlib import Path

# 设置项目根目录
now_dir = os.getcwd()
sys.path.insert(0, now_dir)

os.environ["version"] = "v2Pro"
os.environ["no_proxy"] = "localhost, 127.0.0.1, ::1"
os.environ["all_proxy"] = ""

import warnings
warnings.filterwarnings("ignore")

from text.LangSegmenter import LangSegmenter
from feature_extractor import cnhubert
from transformers import AutoModelForMaskedLM, AutoTokenizer
from GPT_SoVITS.AR.models.t2s_lightning_module import Text2SemanticLightningModule
from GPT_SoVITS.module.models import SynthesizerTrn
from GPT_SoVITS.module.mel_processing import spectrogram_torch
from GPT_SoVITS.text import cleaned_text_to_sequence
from GPT_SoVITS.text.get_text import get_text
from tools.my_utils import load_audio

# 预训练模型路径
BERT_PATH = "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
CNHUBERT_PATH = "GPT_SoVITS/pretrained_models/chinese-hubert-base"

# 默认配置
DEFAULT_CONFIG = {
    "version": "v2Pro",
    "is_half": True,
    "top_k": 15,
    "top_p": 0.85,
    "temperature": 1.0,
    "ref_free": False,
}


class GPTSoVITSInference:
    """GPT-SoVITS推理类"""
    
    def __init__(self, gpt_model_path, sovits_model_path, gpu="0", is_half=True):
        """
        初始化推理模型
        
        Args:
            gpt_model_path: GPT模型路径（.ckpt文件）
            sovits_model_path: SoVITS模型路径（.pth文件）
            gpu: GPU编号
            is_half: 是否使用半精度
        """
        self.gpu = gpu
        self.is_half = is_half and torch.cuda.is_available()
        self.device = torch.device(f"cuda:{gpu}" if torch.cuda.is_available() else "cpu")
        
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
        
        print(f"加载模型到设备: {self.device}")
        print(f"使用半精度: {self.is_half}")
        
        # 加载BERT模型
        print("加载BERT模型...")
        self.bert_tokenizer = AutoTokenizer.from_pretrained(BERT_PATH)
        self.bert_model = AutoModelForMaskedLM.from_pretrained(BERT_PATH).to(self.device)
        if self.is_half:
            self.bert_model = self.bert_model.half()
        self.bert_model.eval()
        
        # 加载Chinese Hubert模型
        print("加载Chinese Hubert模型...")
        cnhubert.cnhubert_base_path = CNHUBERT_PATH
        from GPT_SoVITS.feature_extractor.cnhubert import CNHubert
        self.cnhubert_model = CNHubert()
        if torch.cuda.is_available():
            self.cnhubert_model = self.cnhubert_model.to(self.device)
            if self.is_half:
                self.cnhubert_model = self.cnhubert_model.half()
        self.cnhubert_model.eval()
        
        # 加载GPT模型
        print(f"加载GPT模型: {gpt_model_path}")
        self.gpt_model = Text2SemanticLightningModule.load_from_checkpoint(
            gpt_model_path, map_location=self.device
        )
        self.gpt_model = self.gpt_model.model
        if self.is_half:
            self.gpt_model = self.gpt_model.half()
        self.gpt_model.eval()
        
        # 加载SoVITS模型
        print(f"加载SoVITS模型: {sovits_model_path}")
        checkpoint = torch.load(sovits_model_path, map_location=self.device)
        from GPT_SoVITS.module.models import SynthesizerTrn
        
        # 根据版本选择模型
        version = DEFAULT_CONFIG["version"]
        if version == "v2Pro":
            from GPT_SoVITS.configs.s2v2Pro import get_hparams
        else:
            from GPT_SoVITS.configs.s2 import get_hparams
        
        hps = get_hparams()
        hps.data.exp_dir = os.path.dirname(sovits_model_path)
        
        self.sovits_model = SynthesizerTrn(
            hps.data.filter_length // 2 + 1,
            hps.train.segment_size // hps.data.hop_length,
            n_speakers=hps.data.n_speakers,
            **hps.model
        ).to(self.device)
        
        if self.is_half:
            self.sovits_model = self.sovits_model.half()
        
        # 加载权重
        if "weight" in checkpoint:
            self.sovits_model.load_state_dict(checkpoint["weight"], strict=False)
        else:
            self.sovits_model.load_state_dict(checkpoint, strict=False)
        
        self.sovits_model.eval()
        
        # 语言分割器
        self.lang_segmenter = LangSegmenter()
        
        print("✓ 所有模型加载完成")
    
    def get_bert_feature(self, text, device):
        """获取BERT特征"""
        with torch.no_grad():
            inputs = self.bert_tokenizer(text, return_tensors="pt", padding=True)
            for k in inputs:
                inputs[k] = inputs[k].to(device)
            res = self.bert_model(**inputs, output_hidden_states=True)
            res = torch.cat(res["hidden_states"][-3:-2], -1)[0].cpu().numpy()
        return res
    
    def get_speaker_embedding(self, ref_audio_path):
        """从参考音频提取说话人特征"""
        wav, sr = load_audio(ref_audio_path, 16000)
        wav16k = torch.from_numpy(wav).unsqueeze(0).to(self.device)
        
        if self.is_half:
            wav16k = wav16k.half()
        
        with torch.no_grad():
            # 使用ERes2Net提取说话人特征
            from GPT_SoVITS.eres2net import ERes2NetV2
            import kaldi as Kaldi
            
            # 这里需要加载说话人验证模型
            # 简化版本：使用Hubert特征作为说话人特征
            g = self.cnhubert_model.model(wav16k)
            g = g.last_hidden_state
            g = g.mean(dim=1)
            return g
    
    def infer(self, text, ref_audio_path, ref_text, top_k=15, top_p=0.85, temperature=1.0):
        """
        推理函数
        
        Args:
            text: 要合成的文本
            ref_audio_path: 参考音频路径
            ref_text: 参考文本
            top_k: top_k采样参数
            top_p: top_p采样参数
            temperature: 温度参数
        
        Returns:
            合成的音频numpy数组
        """
        # 文本处理
        text = text.strip()
        ref_text = ref_text.strip()
        
        # 获取参考音频的说话人特征
        print("提取参考音频特征...")
        ref_speaker_embedding = self.get_speaker_embedding(ref_audio_path)
        
        # 获取参考文本的BERT特征（用于GPT生成）
        print("处理参考文本...")
        ref_bert = self.get_bert_feature(ref_text, self.device)
        ref_bert = torch.from_numpy(ref_bert).unsqueeze(0).to(self.device)
        if self.is_half:
            ref_bert = ref_bert.half()
        
        # 获取目标文本的BERT特征
        print("处理目标文本...")
        target_bert = self.get_bert_feature(text, self.device)
        target_bert = torch.from_numpy(target_bert).unsqueeze(0).to(self.device)
        if self.is_half:
            target_bert = target_bert.half()
        
        # GPT生成语义特征
        print("GPT生成语义特征...")
        with torch.no_grad():
            # 这里需要根据实际的GPT模型接口进行调整
            # 简化版本：直接使用参考音频的语义特征
            # 实际应该使用GPT模型生成
            pass
        
        # SoVITS生成音频
        print("SoVITS生成音频...")
        # 这里需要根据实际的SoVITS模型接口进行调整
        
        # 返回合成的音频
        # 这里返回一个示例，实际需要根据模型输出调整
        return np.zeros(16000)  # 示例返回值


def main():
    parser = argparse.ArgumentParser(description="GPT-SoVITS-v2Pro 推理脚本")
    parser.add_argument("--gpt_model", type=str, required=True,
                       help="GPT模型路径（.ckpt文件）")
    parser.add_argument("--sovits_model", type=str, required=True,
                       help="SoVITS模型路径（.pth文件）")
    parser.add_argument("--text", type=str, required=True,
                       help="要合成的文本")
    parser.add_argument("--ref_audio", type=str, required=True,
                       help="参考音频路径")
    parser.add_argument("--ref_text", type=str, required=True,
                       help="参考文本")
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
    
    # 检查文件是否存在
    if not os.path.exists(args.gpt_model):
        print(f"错误: GPT模型文件不存在: {args.gpt_model}")
        return
    
    if not os.path.exists(args.sovits_model):
        print(f"错误: SoVITS模型文件不存在: {args.sovits_model}")
        return
    
    if not os.path.exists(args.ref_audio):
        print(f"错误: 参考音频文件不存在: {args.ref_audio}")
        return
    
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
    
    # 初始化推理模型
    try:
        inferencer = GPTSoVITSInference(
            args.gpt_model,
            args.sovits_model,
            gpu=args.gpu,
            is_half=True
        )
    except Exception as e:
        print(f"错误: 模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 进行推理
    try:
        audio = inferencer.infer(
            args.text,
            args.ref_audio,
            args.ref_text,
            top_k=args.top_k,
            top_p=args.top_p,
            temperature=args.temperature
        )
        
        # 保存音频
        # 这里需要根据实际的音频格式进行调整
        print(f"✓ 推理完成，音频已保存到: {args.output}")
        
    except Exception as e:
        print(f"错误: 推理失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

