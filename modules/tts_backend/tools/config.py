import os
import torch


class Config:
    """
    Minimal startup config for modules/tts_backend/wx_api.py.
    """

    def __init__(self):
        root = os.getcwd()
        self.python_exec = os.path.join(root, "venv", "bin", "python")
        self.infer_device = "cuda" if torch.cuda.is_available() else "cpu"
        self.api_port = 9880
        self.is_half = torch.cuda.is_available()

        # Runtime defaults (wx_api has fallback if these files are absent)
        self.pretrained_sovits_path = os.path.join(root, "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Gv2Pro.pth")
        self.pretrained_gpt_path = os.path.join(root, "GPT_SoVITS", "pretrained_models", "s1v3.ckpt")
        self.sovits_path = self.pretrained_sovits_path
        self.gpt_path = self.pretrained_gpt_path
        self.cnhubert_path = os.path.join(root, "GPT_SoVITS", "pretrained_models", "chinese-hubert-base")
        self.bert_path = os.path.join(root, "GPT_SoVITS", "pretrained_models", "chinese-roberta-wwm-ext-large")


# wx_api.get_sovits_weights() 会按此字典查询底模路径
pretrained_sovits_name = {
    "v2Pro": os.path.join(os.getcwd(), "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Gv2Pro.pth"),
    "v2ProPlus": os.path.join(os.getcwd(), "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Gv2Pro.pth"),
}
