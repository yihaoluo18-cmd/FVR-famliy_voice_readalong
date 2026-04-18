import json
import os
import re
from typing import List, Dict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BOOK_ROOT = os.path.join(ROOT, "绘本集")
INDEX_JSON = os.path.join(ROOT, "library", "magic_books_index.json")
MISSING_MD = os.path.join(ROOT, "library", "magic_books_missing_images.md")


def merge_paragraphs(lines: List[str]) -> List[str]:
    """
    按约定规则将一行一段的绘本文本合并为 3-4 段：
    - 行首可能是 "1." "2." 这样的编号，需去除编号后再合并。
    - <=4 段：保持不变
    - 5-6 段：合并为 3 段（1-2，3-4，5+）
    - >=7 段：合并为 4 段（1-2，3-4，5-6，7+）
    """
    paras: List[str] = []
    for raw in lines:
        s = str(raw).strip()
        if not s:
            continue
        m = re.match(r"^\\s*\\d+[\\.、．]\\s*(.*)$", s)
        if m:
            s = m.group(1).strip()
        paras.append(s)

    n = len(paras)
    if n <= 4:
        merged = paras
    elif n <= 6:
        merged = [
            " ".join(paras[0:2]),
            " ".join(paras[2:4]) if n >= 4 else "",
            " ".join(paras[4:]) if n > 4 else "",
        ]
        merged = [p.strip() for p in merged if p.strip()]
    else:
        merged = [
            " ".join(paras[0:2]),
            " ".join(paras[2:4]),
            " ".join(paras[4:6]),
            " ".join(paras[6:]),
        ]
        merged = [p.strip() for p in merged if p.strip()]

    out: List[str] = []
    for i, p in enumerate(merged, start=1):
        out.append(f"{i}.{p}")
    return out


def build_tag_index() -> Dict[str, Dict[str, object]]:
    return {
        "蝴蝶的生命周期": {"tags": ["自然与生命"], "icon": "nature"},
        "谢谢你，小帮手": {"tags": ["家人最懂我", "好好说话好朋友"], "icon": "family"},
        "根本就不脏嘛": {"tags": ["我会照顾自己"], "icon": "selfcare"},
        "菲菲生气了": {"tags": ["情绪小侦探", "家人最懂我"], "icon": "emotion"},
        "肚子里有个火车站": {"tags": ["自然与生命", "我会照顾自己"], "icon": "body"},
        "生气王子": {"tags": ["情绪小侦探"], "icon": "emotion"},
        "红绿灯眨眼睛": {"tags": ["安全小勇士"], "icon": "safety"},
        "生气汤": {"tags": ["情绪小侦探"], "icon": "emotion"},
        "生命的故事": {"tags": ["自然与生命"], "icon": "nature"},
        "猜猜我有多爱你": {"tags": ["家人最懂我"], "icon": "family"},
        "牙齿大街的新鲜事": {"tags": ["我会照顾自己"], "icon": "selfcare"},
        "我妈妈": {"tags": ["家人最懂我"], "icon": "family"},
        "有个性的羊": {"tags": ["我在长大"], "icon": "self"},
        "我会自己穿衣服": {"tags": ["我会照顾自己"], "icon": "selfcare"},
        "我们都是好朋友": {"tags": ["好好说话好朋友"], "icon": "friends"},
        "我不想生气": {"tags": ["情绪小侦探"], "icon": "emotion"},
        "我不挑食": {"tags": ["我会照顾自己"], "icon": "selfcare"},
        "小黑鱼": {"tags": ["我在长大", "好好说话好朋友"], "icon": "self"},
        "小小的我": {"tags": ["我在长大"], "icon": "self"},
        "小熊宝宝": {"tags": ["我会照顾自己", "家人最懂我"], "icon": "selfcare"},
        "彩虹鱼": {"tags": ["好好说话好朋友"], "icon": "friends"},
        "对不起，没关系": {"tags": ["好好说话好朋友"], "icon": "friends"},
        "好脏的哈利": {"tags": ["我会照顾自己"], "icon": "selfcare"},
        "大嗓门妈妈": {"tags": ["家人最懂我", "情绪小侦探"], "icon": "family"},
        "学会倾听": {"tags": ["好好说话好朋友"], "icon": "friends"},
        "大卫，不可以": {"tags": ["家人最懂我", "我在长大"], "icon": "family"},
        "好朋友": {"tags": ["好好说话好朋友"], "icon": "friends"},
        "勇敢说“不”": {"tags": ["安全小勇士", "好好说话好朋友"], "icon": "safety"},
        "你很快就会长高": {"tags": ["我在长大"], "icon": "growth"},
        "分享是快乐的": {"tags": ["好好说话好朋友"], "icon": "friends"},
        "不要随便发脾气": {"tags": ["情绪小侦探"], "icon": "emotion"},
        "云朵面包": {"tags": ["魔法想象屋", "家人最懂我"], "icon": "magic"},
        "不可思议的旅程": {"tags": ["魔法想象屋"], "icon": "magic"},
    }


def parse_paras(path: str) -> list[str]:
    paras: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            m = re.match(r"^\\s*\\d+[\\.、．]\\s*(.*)$", s)
            if m:
                s = m.group(1).strip()
            paras.append(s)
    return paras


def build_missing_md(index_data: Dict[str, Dict[str, object]]) -> None:
    lines: list[str] = []
    lines.append("# 绘本缺失段落配图提示汇总\n")
    lines.append("（说明：仅列出当前没有配图的段落，用于后续批量生图。）\n")

    for title, info in sorted(index_data.items(), key=lambda x: x[0]):
        dir_rel = info.get("dir") or title
        txt_file = info.get("file") or f"{title}.txt"
        txt_path = os.path.join(BOOK_ROOT, dir_rel, txt_file)
        if not os.path.exists(txt_path):
            continue
        paras = parse_paras(txt_path)
        if not paras:
            continue
        n = len(paras)
        pages = info.get("pages") or {}
        has_imgs = {int(k) for k in pages.keys() if str(k).isdigit()}
        missing = [k for k in range(1, n + 1) if k not in has_imgs]
        if not missing:
            continue

        lines.append(f"\n## {title}\n")
        for k in missing:
            text = paras[k - 1]
            short = text[:120]
            prompt = (
                f"绘本《{title}》第{k}段：{short}。"
                " 请生成一幅儿童绘本插画，风格与本书已有配图一致，角色表情清晰，色彩明亮，画面简洁温暖，无文字。"
            )
            lines.append(f"- **缺失段落**：第{k}段")
            lines.append(f"  - **原文**：{short}")
            lines.append(f"  - **生图提示词**：{prompt}\n")

    with open(MISSING_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    os.makedirs(os.path.dirname(INDEX_JSON), exist_ok=True)
    tag_index = build_tag_index()
    index_data: Dict[str, Dict[str, object]] = {}

    for root, _, files in os.walk(BOOK_ROOT):
        for fn in files:
            if not fn.lower().endswith(".txt"):
                continue
            txt_path = os.path.join(root, fn)
            title = os.path.splitext(fn)[0]
            rel_dir = os.path.relpath(root, BOOK_ROOT)

            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    raw_lines = f.readlines()
            except UnicodeDecodeError:
                with open(txt_path, "r", encoding="gb18030", errors="ignore") as f:
                    raw_lines = f.readlines()

            merged_lines = merge_paragraphs(raw_lines)
            with open(txt_path, "w", encoding="utf-8") as f:
                for line in merged_lines:
                    f.write(line.rstrip() + "\n")

            info = tag_index.get(title, {"tags": [], "icon": ""})
            index_data[title] = {
                "dir": rel_dir.replace("\\", "/"),
                "file": fn,
                "tags": info.get("tags") or [],
                "icon": info.get("icon") or "",
            }

    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    # pages 信息和图片重命名由单独脚本负责；这里只负责文本+基础索引
    build_missing_md(index_data)


if __name__ == "__main__":
    main()

