# GPT-SoVITS-v2Pro 自动化训练和推理流程

## 📋 概述

本目录包含完整的自动化训练和推理脚本，可以一键完成从数据准备到模型训练再到语音合成的完整流程。

## 🚀 快速开始

### 1. 准备数据集

将你的音频文件和对应的文本文件放在 `dataset` 目录下，格式如下：

```
dataset/
├── sentence_0.wav
├── sentence_0.txt
├── sentence_1.wav
├── sentence_1.txt
├── ...
```

**要求**：
- 音频文件命名格式：`sentence_X.wav`（X为数字）
- 文本文件命名格式：`sentence_X.txt`（与音频文件对应）
- 文本文件内容为对应的音频文本，UTF-8编码

### 2. 运行完整训练流程

#### 方式一：使用Shell脚本（推荐）

```bash
# 使用默认配置
./run_full_pipeline.sh

# 或使用自定义配置
export EXP_NAME="my_voice"
export DATASET_DIR="dataset"
export GPU="0"
export S2_EPOCHS=8
export S1_EPOCHS=20
./run_full_pipeline.sh
```

#### 方式二：使用Python脚本

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行完整流程
python modules/tts_backend/training/auto_train_infer.py \
    --dataset_dir dataset \
    --exp_name my_voice \
    --gpu 0 \
    --batch_size 12 \
    --s2_epochs 8 \
    --s1_epochs 20 \
    --lang ZH
```

### 3. 进行推理

训练完成后，可以使用以下方式进行推理：

#### 方式一：使用WebUI（推荐）

```bash
./go-webui.sh
```

然后在Web界面中：
1. 选择训练好的GPT模型和SoVITS模型
2. 上传参考音频（可以使用数据集中的音频）
3. 输入参考文本和目标文本
4. 点击合成

#### 方式二：使用API

```bash
./modules/tts_backend/scripts/start_api_v2.sh
```

然后通过API接口调用推理功能。

#### 方式三：使用命令行脚本

```bash
python modules/tts_backend/inference/simple_inference.py \
    --exp_name my_voice \
    --text "要合成的文本" \
    --ref_index 0 \
    --output output.wav
```

## 📁 脚本说明

### 1. `prepare_dataset.py`
数据准备脚本，将dataset文件夹中的音频和文本文件转换为训练所需的格式。

**用法**：
```bash
python modules/tts_backend/training/prepare_dataset.py <dataset_dir> <output_file> [exp_name] [lang]
```

**示例**：
```bash
python modules/tts_backend/training/prepare_dataset.py dataset output/my_dataset.list my_dataset ZH
```

### 2. `auto_train_infer.py`
自动化训练脚本，包含完整的数据预处理和模型训练流程。

**主要功能**：
- 数据准备
- 数据预处理（4个步骤）
  - 1a: 文本处理与BERT特征提取
  - 1b: Hubert特征提取与音频重采样
  - 1b2: 说话人特征提取
  - 1c: 语义特征提取
- SoVITS模型训练
- GPT模型训练

**参数说明**：
- `--dataset_dir`: 数据集目录（默认：dataset）
- `--exp_name`: 实验名称（默认：my_voice）
- `--gpu`: GPU编号，多个用-连接（默认：0）
- `--batch_size`: SoVITS训练batch size（默认：12）
- `--s2_epochs`: SoVITS训练epoch数（默认：8）
- `--s1_epochs`: GPT训练epoch数（默认：20）
- `--lang`: 语言代码（默认：ZH）
- `--skip_prepare`: 跳过数据准备步骤
- `--skip_preprocess`: 跳过数据预处理步骤
- `--skip_train`: 跳过训练步骤

### 3. `simple_inference.py`
简化的推理脚本（需要进一步完善）。

**用法**：
```bash
python modules/tts_backend/inference/simple_inference.py \
    --exp_name my_voice \
    --text "要合成的文本" \
    [--ref_audio path/to/ref.wav] \
    [--ref_text "参考文本"] \
    [--ref_index 0] \
    [--output output.wav]
```

### 4. `run_full_pipeline.sh`
一键运行完整流程的Shell脚本。

## 📊 训练流程详解

### 步骤1: 数据准备
- 扫描dataset目录中的音频和文本文件
- 生成训练数据列表文件（格式：`音频路径|实验名|语言|文本`）

### 步骤2: 数据预处理
1. **文本处理与BERT特征提取** (`1-get-text.py`)
   - 文本清洗和规范化
   - 使用BERT模型提取文本特征
   - 输出：`2-name2text.txt`, `3-bert/`

2. **Hubert特征提取与音频重采样** (`2-get-hubert-wav32k.py`)
   - 将音频重采样到32kHz
   - 使用Chinese Hubert模型提取音频特征
   - 输出：`4-wav32k/`, `6-hubert/`

3. **说话人特征提取** (`2-get-sv.py`)
   - 提取说话人身份特征
   - 输出：`7-sv_cn/`

4. **语义特征提取** (`3-get-semantic.py`)
   - 使用预训练的SoVITS模型提取语义特征
   - 输出：`6-name2semantic.tsv`

### 步骤3: SoVITS模型训练
- 训练声码器（Vocoder）部分
- 学习将语义特征转换为音频波形
- 使用对抗训练（GAN）提升音质
- 输出：`SoVITS_weights_v2Pro/{exp_name}_e{epoch}_s{step}.pth`

### 步骤4: GPT模型训练
- 训练文本到语义的生成模型
- 学习从文本特征生成语义特征
- 使用自回归（AR）架构
- 输出：`GPT_weights_v2Pro/{exp_name}-e{epoch}.ckpt`

## 🔧 配置说明

### 默认训练参数

**SoVITS训练**：
- epochs: 8
- batch_size: 12
- learning_rate: 0.0001
- save_every_epoch: 4

**GPT训练**：
- epochs: 20
- batch_size: 8
- learning_rate: 0.01 (warmup后)

这些参数与官方默认参数保持一致。

### 预训练模型路径

脚本会自动查找以下预训练模型：
- BERT: `GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large`
- Chinese Hubert: `GPT_SoVITS/pretrained_models/chinese-hubert-base`
- SoVITS预训练: `GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth` 和 `s2Dv2Pro.pth`
- 说话人验证: `GPT_SoVITS/pretrained_models/sv/ERes2NetV2_Base_16k.pth`

## 📝 输出文件结构

训练完成后，会生成以下文件：

```
logs/{exp_name}/
├── 2-name2text.txt          # 文本映射
├── 3-bert/                   # BERT特征
├── 4-wav32k/                 # 32kHz音频
├── 5-wav32k/                 # 32kHz音频（确认）
├── 6-hubert/                 # Hubert特征
├── 6-name2semantic.tsv       # 语义特征
├── 7-sv_cn/                  # 说话人特征
└── logs_s2_v2Pro/           # SoVITS训练日志

SoVITS_weights_v2Pro/
└── {exp_name}_e{epoch}_s{step}.pth  # SoVITS模型权重

GPT_weights_v2Pro/
└── {exp_name}-e{epoch}.ckpt        # GPT模型权重
```

## 🎯 推理使用

### 使用训练好的模型进行推理

训练完成后，模型会自动保存在对应的权重目录中。推理时：

1. **选择参考音频**：可以使用数据集中的任意音频作为参考
2. **输入目标文本**：要合成的文本
3. **选择模型**：选择训练好的GPT和SoVITS模型

### 推荐推理方式

由于推理接口较复杂，推荐使用WebUI或API方式进行推理：

1. **WebUI方式**（最简单）：
   ```bash
   ./go-webui.sh
   ```
   然后在Web界面中选择模型和输入文本即可。

2. **API方式**（适合集成）：
   ```bash
   ./modules/tts_backend/scripts/start_api_v2.sh
   ```
   然后通过HTTP API调用推理功能。

## ⚠️ 注意事项

1. **数据质量**：音频质量直接影响训练效果，建议使用干净、清晰的音频
2. **文本对齐**：文本必须与音频内容完全对应
3. **GPU内存**：训练需要足够的GPU内存，如果内存不足可以减小batch_size
4. **训练时间**：完整训练流程可能需要数小时，请耐心等待
5. **模型版本**：确保使用匹配的模型版本（v2Pro）

## 🐛 常见问题

### Q: 训练过程中出现内存不足错误
A: 减小batch_size参数，例如：`--batch_size 6`

### Q: 找不到预训练模型
A: 确保已下载所有预训练模型，或使用install.sh脚本安装

### Q: 推理时找不到模型
A: 检查模型文件是否在正确的目录中，或使用绝对路径指定模型

### Q: 训练中断后如何继续
A: 可以使用 `--skip_prepare` 和 `--skip_preprocess` 跳过已完成的步骤

## 📚 更多信息

- 官方文档：查看项目README.md
- 训练参数：参考 `GPT_SoVITS/configs/` 目录下的配置文件
- 推理接口：参考 `GPT_SoVITS/inference_webui.py`

