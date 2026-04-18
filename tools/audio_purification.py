import shutil
from pathlib import Path


def purify_audio_file(src_path: str, dst_path: str, task_id: str = "", sentence_index: int = -1, **kwargs):
    """
    轻量兜底版音频提纯接口：
    - 保持与 train_api.py 调用签名兼容
    - 在未集成完整降噪模型时，直接复制输入音频到输出路径
    """
    src = Path(src_path)
    dst = Path(dst_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst)
