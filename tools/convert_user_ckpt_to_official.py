#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将本项目训练产物（如 user_models/unlogged/*/gpt_model.ckpt、sovits_model.pth、tmp_s2.json）
转换为 GPT-SoVITS 官方 inference_webui 可直接加载的“精简格式”权重。

背景：
- inference_webui.py 在 import 阶段会读取 gpt_ckpt["config"]["data"]["max_sec"] 等字段；
  而本项目的 gpt_model.ckpt 往往没有完整 config（尤其缺 data），导致 KeyError: 'data'。

本脚本策略：
1) GPT：
   - 若输入是 Lightning ckpt（含 state_dict），抽取 weight 并写入 config。
   - 若输入已是精简格式（含 weight），则直接补齐 config。
   - 如果 config 缺少 data，则从预训练 s1v3.ckpt 读取 config 并做 merge 兜底。
2) SoVITS：
   - 若输入是完整 checkpoint（含 model），抽取 weight 并用 my_save2 写入 v2Pro 头。
   - 若已是精简格式（含 weight），保持不动（可选：写到新位置）。

用法示例（在 test1/ 根目录）：
  venv/bin/python tools/convert_user_ckpt_to_official.py \
    --gpt_in user_models/unlogged/wx_clone_user/mother_xxx/gpt_model.ckpt \
    --sovits_in user_models/unlogged/wx_clone_user/mother_xxx/sovits_model.pth \
    --s2_config_in user_models/unlogged/wx_clone_user/<task_id>/tmp_s2.json \
    --gpt_out GPT_weights_v2Pro/voice_wx_clone_user_xxx-e15.ckpt \
    --sovits_out SoVITS_weights_v2Pro/voice_wx_clone_user_xxx_e6_s18.pth \
    --model_version v2Pro
"""

from __future__ import annotations

import argparse
import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Tuple

import torch


def _load_ckpt(path: Path) -> Dict[str, Any]:
    return torch.load(str(path), map_location="cpu", weights_only=False)


def _load_pretrained_gpt_config(pretrained_s1: Path) -> Dict[str, Any]:
    d = _load_ckpt(pretrained_s1)
    cfg = d.get("config")
    return cfg if isinstance(cfg, dict) else {}


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in (src or {}).items():
        if k not in dst:
            dst[k] = v
            continue
        if isinstance(dst.get(k), dict) and isinstance(v, dict):
            _deep_merge(dst[k], v)
    return dst


def convert_gpt_ckpt(
    gpt_in: Path,
    gpt_out: Path,
    model_version: str,
    pretrained_s1: Path,
) -> Tuple[Path, str]:
    ckpt = _load_ckpt(gpt_in)

    converted = OrderedDict()
    converted["weight"] = OrderedDict()

    if isinstance(ckpt, dict) and "state_dict" in ckpt and "weight" not in ckpt:
        state_dict = ckpt["state_dict"] or {}
        for key, value in state_dict.items():
            # inference_webui 的 Text2SemanticLightningModule(state_dict) 期望 key 带 "model." 前缀
            # 因此这里不要去掉该前缀。
            new_key = key
            if hasattr(value, "dtype") and value.dtype == torch.float32:
                converted["weight"][new_key] = value.half()
            else:
                converted["weight"][new_key] = value
        hp = ckpt.get("hyper_parameters")
        converted["config"] = hp if isinstance(hp, dict) else {}
        epoch = int(ckpt.get("epoch", 0) or 0)
        converted["info"] = f"GPT-e{epoch + 1}"
    else:
        # 可能是本项目的精简包：通常包含 weight，但 config 不完整
        w = ckpt.get("weight") if isinstance(ckpt, dict) else None
        if not isinstance(w, dict):
            raise RuntimeError(f"输入 GPT ckpt 不含 weight/state_dict，无法转换: keys={list(ckpt.keys())[:10]}")
        for k, v in w.items():
            key = str(k)
            if not key.startswith("model."):
                key = "model." + key
            if hasattr(v, "dtype") and v.dtype == torch.float32:
                converted["weight"][key] = v.half()
            else:
                converted["weight"][key] = v
        cfg = ckpt.get("config")
        converted["config"] = cfg if isinstance(cfg, dict) else {}
        converted["info"] = str(ckpt.get("info") or "GPT-converted")

    # 兜底：补齐 config.data（inference_webui import 期望）
    cfg = converted.get("config")
    if not isinstance(cfg, dict):
        cfg = {}
    if not isinstance(cfg.get("data"), dict) or "max_sec" not in (cfg.get("data") or {}):
        base_cfg = _load_pretrained_gpt_config(pretrained_s1)
        if isinstance(base_cfg, dict):
            _deep_merge(cfg, base_cfg)
    converted["config"] = cfg

    # 保存为官方兼容格式：ckpt 仍用 torch.save（后缀 .ckpt），内容为 {weight, config, info}
    gpt_out.parent.mkdir(parents=True, exist_ok=True)
    tmp = gpt_out.with_suffix(gpt_out.suffix + ".tmp")
    torch.save(converted, str(tmp))
    tmp.replace(gpt_out)
    return gpt_out, "ok"


def convert_sovits_ckpt(
    sovits_in: Path,
    sovits_out: Path,
    model_version: str,
    s2_config_in: Path | None,
) -> Tuple[Path, str]:
    # SoVITS v2Pro/Plus “精简格式”可能不是标准 pickle（带自定义头），直接 torch.load 会报 UnpicklingError。
    # 这里优先用官方 process_ckpt.load_sovits_new 做兼容读取；失败再退回 torch.load。
    ckpt = None
    try:
        from GPT_SoVITS.process_ckpt import load_sovits_new

        ckpt = load_sovits_new(str(sovits_in))
    except Exception:
        ckpt = _load_ckpt(sovits_in)
    if isinstance(ckpt, dict) and "model" in ckpt and "weight" not in ckpt:
        converted = OrderedDict()
        converted["weight"] = OrderedDict()
        model_state = ckpt.get("model") or {}
        for k, v in model_state.items():
            if "enc_q" in str(k):
                continue
            if hasattr(v, "dtype") and v.dtype == torch.float32:
                converted["weight"][k] = v.half()
            else:
                converted["weight"][k] = v

        cfg = {}
        if s2_config_in and s2_config_in.exists():
            cfg = json.loads(s2_config_in.read_text(encoding="utf-8"))
        converted["config"] = cfg if isinstance(cfg, dict) else {}
        iteration = int(ckpt.get("iteration", 0) or 0)
        epoch = int(ckpt.get("epoch", 0) or 0)
        converted["info"] = f"{epoch}epoch_{iteration}iteration"

        from GPT_SoVITS.process_ckpt import my_save2

        sovits_out.parent.mkdir(parents=True, exist_ok=True)
        my_save2(converted, str(sovits_out), model_version)
        return sovits_out, "ok(full->slim)"

    # 已是精简格式：直接拷贝到目标
    sovits_out.parent.mkdir(parents=True, exist_ok=True)
    if sovits_in.resolve() != sovits_out.resolve():
        sovits_out.write_bytes(sovits_in.read_bytes())
    return sovits_out, "ok(already_slim)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpt_in", required=True)
    ap.add_argument("--sovits_in", required=True)
    ap.add_argument("--gpt_out", required=True)
    ap.add_argument("--sovits_out", required=True)
    ap.add_argument("--s2_config_in", default="")
    ap.add_argument("--model_version", default="v2Pro")
    ap.add_argument(
        "--pretrained_s1",
        default="GPT_SoVITS/pretrained_models/s1v3.ckpt",
        help="用于补齐 GPT config 的预训练 s1 权重（含 config.data）",
    )
    args = ap.parse_args()

    gpt_in = Path(args.gpt_in)
    sovits_in = Path(args.sovits_in)
    gpt_out = Path(args.gpt_out)
    sovits_out = Path(args.sovits_out)
    s2_cfg = Path(args.s2_config_in) if str(args.s2_config_in).strip() else None
    pretrained_s1 = Path(args.pretrained_s1)

    if not gpt_in.exists():
        raise SystemExit(f"GPT 输入不存在: {gpt_in}")
    if not sovits_in.exists():
        raise SystemExit(f"SoVITS 输入不存在: {sovits_in}")
    if not pretrained_s1.exists():
        raise SystemExit(f"预训练 s1 不存在（用于补齐 config）：{pretrained_s1}")

    gpt_out_path, gpt_tag = convert_gpt_ckpt(gpt_in, gpt_out, args.model_version, pretrained_s1)
    sovits_out_path, sovits_tag = convert_sovits_ckpt(sovits_in, sovits_out, args.model_version, s2_cfg)

    print("[OK] GPT:", gpt_out_path, gpt_tag)
    print("[OK] SoVITS:", sovits_out_path, sovits_tag)


if __name__ == "__main__":
    main()

