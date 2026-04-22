import os


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GPT_SOVITS_DIR = os.path.join(ROOT_DIR, "GPT_SoVITS")
PRETRAIN_DIR = os.path.join(GPT_SOVITS_DIR, "pretrained_models")

# 兼容 wx_api / inference_webui 直接 `from config import xxx` 的用法
api_port = int(os.environ.get("API_PORT", "9880"))
infer_device = os.environ.get("INFER_DEVICE", "cuda")
is_half = os.environ.get("IS_HALF", "1") not in ("0", "false", "False")

cnhubert_path = os.path.join(PRETRAIN_DIR, "chinese-hubert-base")
bert_path = os.path.join(PRETRAIN_DIR, "chinese-roberta-wwm-ext-large")
_sovits_v2pro = os.path.join(PRETRAIN_DIR, "v2Pro", "s2Gv2Pro.pth")
pretrained_sovits_name = {
    # inference_webui 会索引 "v3"，这里统一回退到 v2Pro 预训练权重，保证 test1 可启动可推理。
    "v1": _sovits_v2pro,
    "v2": _sovits_v2pro,
    "v3": _sovits_v2pro,
    "v4": _sovits_v2pro,
    "v2Pro": _sovits_v2pro,
    "v2ProPlus": _sovits_v2pro,
}
pretrained_gpt_name = {
    "v1": os.path.join(PRETRAIN_DIR, "s1v3.ckpt"),
    "v2": os.path.join(PRETRAIN_DIR, "s1v3.ckpt"),
    "v3": os.path.join(PRETRAIN_DIR, "s1v3.ckpt"),
    "v4": os.path.join(PRETRAIN_DIR, "s1v3.ckpt"),
    "v2Pro": os.path.join(PRETRAIN_DIR, "s1v3.ckpt"),
    "v2ProPlus": os.path.join(PRETRAIN_DIR, "s1v3.ckpt"),
}
gpt_path = pretrained_gpt_name["v2Pro"]
sovits_path = pretrained_sovits_name["v2Pro"]
name2gpt_path = {"default": gpt_path}
name2sovits_path = {"default": sovits_path}


class Config:
    def __init__(self):
        self.api_port = api_port
        self.infer_device = infer_device
        self.is_half = is_half
        self.cnhubert_path = cnhubert_path
        self.bert_path = bert_path
        self.pretrained_sovits_name = pretrained_sovits_name
        self.gpt_path = gpt_path
        self.sovits_path = sovits_path
        self.name2gpt_path = name2gpt_path
        self.name2sovits_path = name2sovits_path


def get_weights_names():
    cfg = Config()
    return list(cfg.name2sovits_path.keys()), list(cfg.name2gpt_path.keys())


def change_choices():
    return get_weights_names()
