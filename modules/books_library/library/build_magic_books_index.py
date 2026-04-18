import json
import os
import re
from typing import Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BOOK_ROOT = os.path.join(ROOT, "绘本集")
OUT_INDEX = os.path.join(ROOT, "library", "magic_books_index.json")
OUT_MISSING_MD = os.path.join(ROOT, "library", "magic_books_missing_images.md")


def build_tag_index() -> Dict[str, Dict[str, object]]:
    # 与 merge_picture_books.py 保持一致（后续如需统一可做成单一来源）
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


def parse_book_paras(txt_path: str) -> List[str]:
    paras: List[str] = []
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            m = re.match(r"^\s*\d+[\.、．]\s*(.*)$", s)
            paras.append((m.group(1) if m else s).strip())
    return paras


def build_missing_md(index: dict) -> None:
    lines: List[str] = []
    lines.append("# 绘本缺失段落配图提示汇总\n")
    lines.append("（说明：仅列出当前没有配图的段落，用于后续批量生图。）\n")

    for title, info in sorted(index.items(), key=lambda x: x[0]):
        folder = os.path.join(BOOK_ROOT, info.get("dir") or title)
        txt_path = os.path.join(folder, info.get("file") or f"{title}.txt")
        if not os.path.exists(txt_path):
            continue
        paras = parse_book_paras(txt_path)
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

    os.makedirs(os.path.dirname(OUT_MISSING_MD), exist_ok=True)
    with open(OUT_MISSING_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    tag_index = build_tag_index()
    out: Dict[str, Dict[str, object]] = {}

    if not os.path.isdir(BOOK_ROOT):
        raise SystemExit(f"not found: {BOOK_ROOT}")

    for name in sorted(os.listdir(BOOK_ROOT)):
        folder = os.path.join(BOOK_ROOT, name)
        if not os.path.isdir(folder):
            continue
        # 选同名 txt，找不到就退化为目录中第一个 txt
        txt = os.path.join(folder, f"{name}.txt")
        if not os.path.exists(txt):
            txts = [f for f in os.listdir(folder) if f.lower().endswith(".txt")]
            if not txts:
                continue
            txt = os.path.join(folder, txts[0])

        pages: Dict[str, List[str]] = {}
        for fn in os.listdir(folder):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            m = re.match(r"^第([1-4])段(?:_\d+)?\.(jpg|jpeg|png)$", fn, flags=re.IGNORECASE)
            if not m:
                continue
            k = m.group(1)
            pages.setdefault(k, []).append(fn)
        for k in list(pages.keys()):
            pages[k] = sorted(pages[k])

        meta = tag_index.get(name, {"tags": [], "icon": ""})
        out[name] = {
            "dir": name,
            "file": os.path.basename(txt),
            "tags": meta.get("tags") or [],
            "icon": meta.get("icon") or "",
            "pages": pages,
        }

    os.makedirs(os.path.dirname(OUT_INDEX), exist_ok=True)
    with open(OUT_INDEX, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    build_missing_md(out)


if __name__ == "__main__":
    main()

