"""
涂色小画家（Coloring）API 接口
包括：线稿获取、作品保存、AI评价等功能
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
import time
import uuid
from pydantic import BaseModel
from PIL import Image
import numpy as np
from scipy import ndimage
from fastapi.responses import FileResponse

router = APIRouter(prefix="/coloring", tags=["coloring"])

# 涂色数据存储路径
# 计算项目根目录（从 modules/coloring_artist/backend/coloring_api.py 往上 3 层）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
COLORING_DATA_DIR = PROJECT_ROOT / "assets" / "practice" / "coloring"
COLORING_INDEX_FILE = COLORING_DATA_DIR / "index.json"
COLORING_WORKS_DIR = PROJECT_ROOT / "output" / "coloring_works"
COLORING_WORKS_IMAGES_DIR = COLORING_WORKS_DIR / "images"
PAINT_BASEMENT_DIR = PROJECT_ROOT / "assets" / "paint_basement"
PAINT_BASEMENT_MASK_DIR = PROJECT_ROOT / "assets" / "paint_basement_masks"  # 手工区域掩码（可选）
PAINT_GEN_DIR = PROJECT_ROOT / "assets" / "paint_basement_generated"
PAINT_GEN_REGION_DIR = PAINT_GEN_DIR / "regionmap"
PAINT_GEN_OFFSETS_DIR = PAINT_GEN_DIR / "offsets"

os.makedirs(COLORING_WORKS_DIR, exist_ok=True)
os.makedirs(COLORING_WORKS_IMAGES_DIR, exist_ok=True)
os.makedirs(PAINT_GEN_REGION_DIR, exist_ok=True)
os.makedirs(PAINT_GEN_OFFSETS_DIR, exist_ok=True)


def load_coloring_index() -> Dict:
    """加载涂色索引"""
    if COLORING_INDEX_FILE.exists():
        try:
            with open(COLORING_INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 加载涂色索引失败: {e}")
    return {"version": 1, "total": 0, "items": []}


# 训练色库：从这里为“每张图”挑选专属 ≤4 色
TRAINING_PALETTE_BANK = [
    "#FF6B6B", "#FBBF24", "#34D399", "#60A5FA",  # 经典红黄绿蓝
    "#A78BFA", "#F472B6", "#FB923C", "#22C55E",
    "#38BDF8", "#F97316", "#E879F9", "#84CC16",
]


def _find_answer_image_for_lineart(lineart_path: Path) -> Optional[Path]:
    """
    查找与线稿同名的答案图（paint_basement_masks）。
    约定：题库与答案库同名一一对应，如 `16 西瓜.jpg`。
    """
    if not PAINT_BASEMENT_MASK_DIR.exists():
        return None
    exts = (".png", ".jpg", ".jpeg", ".webp")
    for ext in exts:
        cand = PAINT_BASEMENT_MASK_DIR / f"{lineart_path.stem}{ext}"
        if cand.exists():
            return cand
    return None


def _hex_to_rgb_tuple(h: str) -> tuple[int, int, int]:
    s = (h or "").lstrip("#")
    if len(s) == 3:
        s = "".join([c + c for c in s])
    if len(s) != 6:
        return (0, 0, 0)
    n = int(s, 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def _label_to_rgb(idx: int) -> tuple[int, int, int]:
    # 为 regionMap 生成稳定且可区分的颜色（避开白色）
    x = int(idx) & 0xFFFFFF
    r = (x & 255)
    g = ((x >> 8) & 255)
    b = ((x >> 16) & 255)
    if r > 245 and g > 245 and b > 245:
        r = (r + 60) % 256
        g = (g + 120) % 256
        b = (b + 180) % 256
    if r == 0 and g == 0 and b == 0:
        r = 80
        g = 160
        b = 240
    return (r, g, b)


def _pick_palette_for_image(image_path: Path) -> list[str]:
    """
    为“单张训练图片”生成专属 ≤4 色调色板（稳定、可复现、非全局固定）。
    说明：线稿本身无颜色信息，所以这里采用“可复现的确定性选色”（基于文件名/内容hash）。
    """
    import hashlib

    # 优先使用文件内容哈希（文件改动 -> palette 改动）
    try:
        h = hashlib.sha1(image_path.read_bytes()).hexdigest()
    except Exception:
        h = hashlib.sha1(str(image_path).encode("utf-8")).hexdigest()

    bank = TRAINING_PALETTE_BANK
    n = len(bank)
    # 从 hash 里抽取 4 个位置，保证不重复
    idxs = []
    for k in range(0, 16, 4):
        v = int(h[k : k + 4], 16)
        idxs.append(v % n)
    uniq = []
    for i in idxs:
        if i not in uniq:
            uniq.append(i)
        if len(uniq) >= 4:
            break
    # 补足到 4
    j = 0
    while len(uniq) < 4 and j < n:
        if j not in uniq:
            uniq.append(j)
        j += 1
    return [bank[i] for i in uniq[:4]]


def _pick_palette_from_answer_image(answer_path: Path, max_colors: int = 4) -> list[str]:
    """
    从答案图提取主色（优先用于前端推荐色）。
    过滤近白/近黑像素，按频次排序，返回最多 max_colors 个 HEX。
    """
    try:
        img = Image.open(answer_path).convert("RGB")
        arr = np.array(img)
        if arr.size == 0:
            return []
        flat = arr.reshape(-1, 3)

        # 排除背景白、线条黑，避免把边线当推荐色
        valid = (
            ~((flat[:, 0] > 245) & (flat[:, 1] > 245) & (flat[:, 2] > 245))
            & ~((flat[:, 0] < 25) & (flat[:, 1] < 25) & (flat[:, 2] < 25))
        )
        cand = flat[valid]
        if cand.size == 0:
            return []

        # 轻度量化，减少 jpg 压缩噪声导致的碎色
        q = ((cand // 16) * 16).astype(np.uint8)
        uniq, counts = np.unique(q, axis=0, return_counts=True)
        order = np.argsort(-counts)
        palette = []
        for idx in order:
            r, g, b = map(int, uniq[idx])
            hx = f"#{r:02X}{g:02X}{b:02X}"
            if hx not in palette:
                palette.append(hx)
            if len(palette) >= max_colors:
                break
        return palette
    except Exception:
        return []


def _postprocess_regions_for_known_images(
    lineart_path: Path, regions: list[dict], palette_4: list[str]
) -> tuple[list[dict], list[str]]:
    """
    针对少量“教具级”图片做手工语义配色：
    - 合并色系：同一大部位用同一 target_color
    - 降低颜色种类：保证整体调色板简单
    仅依赖文件名进行区分，便于后续扩展。
    """
    name = lineart_path.stem.lower()
    if not regions:
        return regions, palette_4

    # 统一收集实际使用到的 target_color，便于后续精简 palette_4
    def _collect_palette(rs: list[dict]) -> list[str]:
        used = []
        for r in rs:
            c = (r.get("target_color") or "").strip()
            if c and c not in used:
                used.append(c)
        # 至少保留 4 个槽位，避免前端 palette 过短影响 UI
        while len(used) < 4 and palette_4:
            for pc in palette_4:
                if pc not in used:
                    used.append(pc)
                if len(used) >= 4:
                    break
        return used[:4]

    # 1) 苹果：果身红色，叶子/叶根简单配两种辅色
    if "apple" in name:
        # 按面积排序，假定最大区域是果身，其余为叶子/叶根/背景小块
        ordered = sorted(regions, key=lambda r: int(r.get("area", 0)), reverse=True)
        if ordered:
            body_color = "#EF4444"  # 果身：红色
            ordered[0]["target_color"] = body_color
            ordered[0]["suggest_colors"] = [body_color]
            ordered[0]["name"] = "果身"
        if len(ordered) >= 2:
            leaf_color = "#22C55E"  # 叶子：绿色
            ordered[1]["target_color"] = leaf_color
            ordered[1]["suggest_colors"] = [leaf_color]
            ordered[1]["name"] = "叶子"
        if len(ordered) >= 3:
            stem_color = "#9A3412"  # 叶根/枝干：棕色
            ordered[2]["target_color"] = stem_color
            ordered[2]["suggest_colors"] = [stem_color]
            ordered[2]["name"] = "叶根"
        regions = ordered
        palette_4 = _collect_palette(regions)
        return regions, palette_4

    # 2) 小狗：身体+头统一为主色，其余部位合并为 1~2 个辅色，并赋予语义名称
    if "dog" in name:
        ordered = sorted(regions, key=lambda r: int(r.get("area", 0)), reverse=True)
        if not ordered:
            return regions, palette_4
        body_head_color = "#FBBF24"  # 身体+头：暖黄色
        accent_color = "#FB7185"  # 耳朵/尾巴/四肢：粉色
        extra_color = "#A78BFA"  # 额外装饰：淡紫

        # 最大两个区域：身体 + 头部（拆成两个部位，便于教学）
        ordered[0]["target_color"] = body_head_color
        ordered[0]["suggest_colors"] = [body_head_color]
        ordered[0]["name"] = "狗身体"
        if len(ordered) >= 2:
            ordered[1]["target_color"] = body_head_color
            ordered[1]["suggest_colors"] = [body_head_color]
            ordered[1]["name"] = "狗头部"

        # 其余区域按中心位置粗分耳朵/四肢/尾巴
        for idx in range(2, len(ordered)):
            r = ordered[idx]
            center = r.get("center") or {}
            ux = float(center.get("ux", 0.5))
            uy = float(center.get("uy", 0.5))
            area = int(r.get("area", 0))
            main_area = int(ordered[0].get("area", 0) or 1)

            role = "狗身体"
            color = body_head_color
            # 头顶附近 → 耳朵
            if uy < 0.35:
                role = "狗耳朵"
                color = accent_color
            # 下方 → 四肢
            elif uy > 0.7:
                role = "狗四肢"
                color = accent_color
            # 右侧中部 → 尾巴
            elif ux > 0.7 and 0.3 < uy < 0.8:
                role = "狗尾巴"
                color = extra_color
            else:
                # 其余小区域：作为装饰并入身体或耳朵
                if area < 0.08 * main_area:
                    role = "装饰"
                    color = extra_color

            r["name"] = role
            r["target_color"] = color
            r["suggest_colors"] = [color]

        regions = ordered
        palette_4 = _collect_palette(regions)
        return regions, palette_4

    return regions, palette_4


def _generate_regionmap_from_lineart(lineart_path: Path, out_region_path: Path, palette_4: list[str]) -> dict:
    """
    从黑白线稿自动生成 regionMap：
    - 线条阈值化 + 膨胀/闭合
    - 对“非线条区域”做连通域标记
    - 去掉外部背景，剩余区域为可填区域
    输出：regionMap PNG + regions metadata（含 colorKey/target_color/suggest_colors）
    """
    # 1) 优先尝试使用“手工区域掩码”（如果存在），完全信任这张图中的纯色块划分区域
    # 支持两种命名：<stem>_region.png 或 <stem>_mask.png，方便你手工制作时命名。
    manual_mask = None
    candidate_masks = [
        PAINT_BASEMENT_MASK_DIR / f"{lineart_path.stem}_region.png",
        PAINT_BASEMENT_MASK_DIR / f"{lineart_path.stem}_mask.png",
        PAINT_BASEMENT_MASK_DIR / f"{lineart_path.stem}_region.jpg",
        PAINT_BASEMENT_MASK_DIR / f"{lineart_path.stem}_mask.jpg",
    ]
    for cand in candidate_masks:
        if cand.exists():
            manual_mask = cand
            break

    if manual_mask is not None and manual_mask.exists():
        try:
            region_img = Image.open(manual_mask).convert("RGB")
            rgb = np.array(region_img)
            h, w, _ = rgb.shape
            # jpg/jpeg 掩码会有压缩杂色，先做一次“颜色量化/吸附”，避免生成大量碎片区域导致看起来偏移
            suffix = manual_mask.suffix.lower()
            if suffix in (".jpg", ".jpeg"):
                flat0 = rgb.reshape(-1, 3)

                def _is_bg_arr(arr: np.ndarray) -> np.ndarray:
                    return (arr[:, 0] > 245) & (arr[:, 1] > 245) & (arr[:, 2] > 245)

                def _is_line_arr(arr: np.ndarray) -> np.ndarray:
                    return (arr[:, 0] < 25) & (arr[:, 1] < 25) & (arr[:, 2] < 25)

                # 仅统计“非背景/非线条”颜色，挑出现频最高的若干主色
                keep = ~( _is_bg_arr(flat0) | _is_line_arr(flat0) )
                cand = flat0[keep]
                if cand.size > 0:
                    uniq_c, counts = np.unique(cand, axis=0, return_counts=True)
                    # 取 topK 主色
                    top_k = int(min(16, uniq_c.shape[0]))
                    top_idx = np.argsort(-counts)[:top_k]
                    centers = uniq_c[top_idx].astype(np.int16)  # (K,3)

                    # 将每个像素吸附到最近主色（背景/线条保持原样）
                    out = flat0.astype(np.int16)
                    idxs = np.where(keep)[0]
                    # 分块避免内存暴涨
                    chunk = 200000
                    for s in range(0, idxs.size, chunk):
                        j = idxs[s : s + chunk]
                        px = out[j]  # (N,3)
                        # (N,K,3) -> (N,K)
                        d2 = ((px[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
                        nn = d2.argmin(axis=1)
                        out[j] = centers[nn]
                    rgb = out.astype(np.uint8).reshape(h, w, 3)

            # 展平后找出所有颜色（量化后 uniq 更少更稳定）
            flat = rgb.reshape(-1, 3)
            uniq_colors, inverse = np.unique(flat, axis=0, return_inverse=True)
            regions: list[dict] = []
            region_color_map: dict[str, int] = {}
            region_offsets: dict[str, list[int]] = {}

            # 过滤掉接近白色的背景块
            def _is_bg(c):
                r, g, b = map(int, c)
                return r > 245 and g > 245 and b > 245

            def _is_line(c):
                r, g, b = map(int, c)
                return r < 25 and g < 25 and b < 25

            region_idx = 0
            for k, color in enumerate(uniq_colors):
                if _is_bg(color) or _is_line(color):
                    continue
                mask_idx = inverse == k
                if not mask_idx.any():
                    continue
                ys, xs = np.where(mask_idx.reshape(h, w))
                if ys.size == 0:
                    continue
                area = int(ys.size)
                region_idx += 1
                r, g, b = map(int, color)
                color_key = f"rgb({r},{g},{b})"
                target_color = palette_4[(region_idx - 1) % len(palette_4)]

                offs = (ys * w + xs) * 4
                region_offsets[color_key] = offs.astype(np.uint32).tolist()
                regions.append(
                    {
                        "id": f"region_{region_idx:03d}",
                        "name": f"区域{region_idx}",
                        "suggest_colors": [target_color],
                        "target_color": target_color,
                        "color_key": color_key,
                        "area": area,
                        "center": {
                            "ux": float(xs.mean() / max(1, w)),
                            "uy": float(ys.mean() / max(1, h)),
                        },
                        "bbox": {
                            "x0": float(xs.min() / max(1, w)),
                            "y0": float(ys.min() / max(1, h)),
                            "x1": float((xs.max() + 1) / max(1, w)),
                            "y1": float((ys.max() + 1) / max(1, h)),
                        },
                    }
                )
                region_color_map[color_key] = region_idx - 1

            # 将手工掩码自身拷贝为 regionMap 输出
            Image.open(manual_mask).convert("RGB").save(out_region_path)

            # 进一步做语义配色和色系合并（dog/apple 专用）
            regions, palette_4 = _postprocess_regions_for_known_images(lineart_path, regions, palette_4)

            return {
                "regions": regions,
                "region_color_map": region_color_map,
                "region_offsets": region_offsets,
                "palette_override": palette_4,
            }
        except Exception as e:
            print(f"[coloring] 使用手工掩码 {manual_mask} 失败，回退自动分割: {e}")

    # 2) 否则回退到基于线稿的自动连通域分割
    img = Image.open(lineart_path).convert("L")
    gray = np.array(img)
    # 线条阈值（线条=1）
    line = gray < 200
    # 不做 binary_dilation，让区域轮廓尽可能与原图一致
    fill = ~line  # 可填区域 = 非线条
    # 连通域标记
    labels, num = ndimage.label(fill)
    if num <= 1:
        # 没有可分割区域，直接输出全白 regionMap
        out = Image.new("RGBA", img.size, (255, 255, 255, 255))
        out.save(out_region_path)
        return {"regions": [], "region_color_map": {}}

    bg_label = int(labels[0, 0])
    # 统计面积
    areas = np.bincount(labels.reshape(-1))
    regions = []
    region_color_map = {}

    h, w = labels.shape
    total = h * w
    min_area = max(80, int(total * 0.002))  # 过滤噪点小块

    # regionMap 初始白底
    out_rgb = np.full((h, w, 3), 255, dtype=np.uint8)

    region_idx = 0
    region_offsets: dict[str, list[int]] = {}
    for lab in range(1, num + 1):
        if lab == bg_label:
            continue
        area = int(areas[lab]) if lab < len(areas) else 0
        if area < min_area:
            continue
        region_idx += 1
        rgb = _label_to_rgb(region_idx)
        mask = labels == lab
        out_rgb[mask] = rgb

        # 基本几何信息（用于后续语义标注 & 持久化，避免下次重复计算）
        ys, xs = np.where(mask)
        if ys.size == 0 or xs.size == 0:
            continue
        cx = float(xs.mean())
        cy = float(ys.mean())
        x0 = int(xs.min())
        x1 = int(xs.max())
        y0 = int(ys.min())
        y1 = int(ys.max())
        # 归一化到 0~1，便于前后端统一使用
        center_norm = {
            "ux": float(cx / max(1, w)),
            "uy": float(cy / max(1, h)),
        }
        bbox_norm = {
            "x0": float(x0 / max(1, w)),
            "y0": float(y0 / max(1, h)),
            "x1": float((x1 + 1) / max(1, w)),
            "y1": float((y1 + 1) / max(1, h)),
        }

        color_key = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
        target_color = palette_4[(region_idx - 1) % len(palette_4)]
        # 生成 offsets（RGBA 偏移，步长 4），用于前端快速预览/填色
        # 注意：这里 offsets 是“像素数组偏移”，与前端 regionMapImageData 的索引一致
        offs = (ys * w + xs) * 4
        region_offsets[color_key] = offs.astype(np.uint32).tolist()
        regions.append(
            {
                "id": f"region_{region_idx:03d}",
                "name": f"区域{region_idx}",
                "suggest_colors": [target_color],  # 训练：每个区域给一个“标准色”
                "target_color": target_color,
                "color_key": color_key,
                "area": area,
                "center": center_norm,
                "bbox": bbox_norm,
            }
        )
        region_color_map[color_key] = region_idx - 1

    # 针对部分已知图片（如 dog/apple）做语义级配色与色系合并
    regions, palette_4 = _postprocess_regions_for_known_images(lineart_path, regions, palette_4)

    out_img = Image.fromarray(out_rgb, mode="RGB")
    out_img.save(out_region_path)
    return {
        "regions": regions,
        "region_color_map": region_color_map,
        "region_offsets": region_offsets,
        "palette_override": palette_4,
    }


def _write_offsets_file(offsets_map: dict, out_path: Path) -> None:
    """
    写入二进制 offsets 文件（无需解压库，前端可直接解析 ArrayBuffer）：
    格式：
      - magic 'OFST1' (5 bytes)
      - uint32 nKeys
      - for each:
          uint16 keyLen
          key utf8 bytes
          uint32 count
          count * uint32 offsets
    """
    import struct

    items = list(offsets_map.items())
    with open(out_path, "wb") as f:
        f.write(b"OFST1")
        f.write(struct.pack("<I", len(items)))
        for key, offsets in items:
            kb = str(key).encode("utf-8")
            f.write(struct.pack("<H", len(kb)))
            f.write(kb)
            arr = np.asarray(offsets, dtype=np.uint32)
            f.write(struct.pack("<I", int(arr.size)))
            f.write(arr.tobytes(order="C"))


def _load_paint_basement_items() -> list[dict]:
    """
    扫描 paint_basement 下的图片，生成涂色训练任务：
    - lineart_url 指向 /paint_basement_static
    - regionmap_url 指向 /paint_basement_gen_static/regionmap
    - regions 自动生成（可填闭合区域）
    - palette 限制为 4 色
    """
    if not PAINT_BASEMENT_DIR.exists():
        return []

    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in sorted(PAINT_BASEMENT_DIR.iterdir()) if p.is_file() and p.suffix.lower() in exts]
    items = []
    for p in files:
        sketch_id = f"basement_{p.stem}"
        region_out = PAINT_GEN_REGION_DIR / f"{p.stem}_region.png"
        meta_out = PAINT_GEN_DIR / f"{p.stem}_meta.json"
        offsets_out = PAINT_GEN_OFFSETS_DIR / f"{p.stem}.ofst"

        # 注意：不要在每次 get_sketches 请求时都提取答案图主色（会明显阻塞接口）。
        # 仅在 need_regen 分支中计算并写入 meta；平时直接读取已缓存的 meta.palette。
        palette_4: list[str] = []

        need_regen = True
        if region_out.exists() and meta_out.exists() and offsets_out.exists():
            try:
                # 源图或手工掩码有更新，都应触发重新生成
                base_mtime = max(region_out.stat().st_mtime, meta_out.stat().st_mtime, offsets_out.stat().st_mtime)
                need_regen = p.stat().st_mtime > base_mtime

                # 掩码任一候选文件比生成物更新，也需要重建
                mask_candidates = [
                    PAINT_BASEMENT_MASK_DIR / f"{p.stem}_region.png",
                    PAINT_BASEMENT_MASK_DIR / f"{p.stem}_mask.png",
                    PAINT_BASEMENT_MASK_DIR / f"{p.stem}_region.jpg",
                    PAINT_BASEMENT_MASK_DIR / f"{p.stem}_mask.jpg",
                    PAINT_BASEMENT_MASK_DIR / f"{p.stem}_region.jpeg",
                    PAINT_BASEMENT_MASK_DIR / f"{p.stem}_mask.jpeg",
                ]
                ans_same_name = _find_answer_image_for_lineart(p)
                if ans_same_name is not None:
                    mask_candidates.append(ans_same_name)
                for mc in mask_candidates:
                    if mc.exists() and mc.stat().st_mtime > base_mtime:
                        need_regen = True
                        break

                # 兼容历史 meta：若未标记 palette 来源为答案图，则执行一次升级重建
                try:
                    saved_meta = json.loads(meta_out.read_text(encoding="utf-8")) or {}
                    palette_source = str(saved_meta.get("palette_source") or "")
                    if palette_source != "answer_image":
                        need_regen = True
                except Exception:
                    need_regen = True
            except Exception:
                need_regen = True

        meta = {"regions": [], "region_color_map": {}, "palette_override": None}
        if need_regen:
            # 仅重建时：优先从答案图提色；失败再回退到训练色
            answer_img = _find_answer_image_for_lineart(p)
            palette_4 = _pick_palette_from_answer_image(answer_img, max_colors=4) if answer_img else []
            if not palette_4:
                palette_4 = _pick_palette_for_image(p)
            try:
                meta = _generate_regionmap_from_lineart(p, region_out, palette_4)
            except Exception as e:
                # 失败时至少保证 regionmap_url 可访问（白图）
                Image.new("RGB", (512, 512), (255, 255, 255)).save(region_out)
                meta = {"regions": [], "region_color_map": {}, "palette_override": None}
            # 写入 meta（持久化“专属 palette + 区域标准色”）
            try:
                # 若 _generate_regionmap_from_lineart 给出更精简的调色板，则优先使用
                palette_for_save = list(meta.get("palette_override") or palette_4)[:4] or palette_4
                with open(meta_out, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "sketch_id": sketch_id,
                            "source": str(p.name),
                            "palette": palette_for_save,
                            "palette_source": "answer_image",
                            "regions": [
                                {
                                    k: v
                                    for k, v in r.items()
                                    if k
                                    in (
                                        "id",
                                        "name",
                                        "target_color",
                                        "suggest_colors",
                                        "color_key",
                                        "area",
                                        "center",
                                        "bbox",
                                    )
                                }
                                for r in meta.get("regions", [])
                            ],
                            "updated_at": datetime.now().isoformat(),
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            except Exception:
                pass
            # 写入 offsets（二进制，供前端直接读取）
            try:
                _write_offsets_file(meta.get("region_offsets", {}) or {}, offsets_out)
            except Exception:
                pass
        else:
            try:
                with open(meta_out, "r", encoding="utf-8") as f:
                    saved = json.load(f) or {}
                # 直接用已保存的区域/标准色（保证“专属标准色”稳定）
                saved_regions = saved.get("regions", []) or []
                loaded_palette = list(saved.get("palette", palette_4))[:4] or palette_4
                # 如果旧 meta 中还没有语义名称/部位信息，运行一次后处理逻辑填充 name/target_color 等，
                # 避免已经存在的 meta 文件导致“始终只有 区域1/区域2，没有 狗耳朵/果身 等选项”。
                processed_regions, palette_override = _postprocess_regions_for_known_images(
                    p, list(saved_regions), loaded_palette
                )
                meta = {
                    "regions": processed_regions,
                    "region_color_map": {},
                    "palette_override": palette_override,
                }
                palette_4 = palette_override or loaded_palette
            except Exception:
                # 读失败就重建
                if not palette_4:
                    answer_img = _find_answer_image_for_lineart(p)
                    palette_4 = _pick_palette_from_answer_image(answer_img, max_colors=4) if answer_img else []
                    if not palette_4:
                        palette_4 = _pick_palette_for_image(p)
                try:
                    meta = _generate_regionmap_from_lineart(p, region_out, palette_4)
                except Exception:
                    meta = {"regions": [], "region_color_map": {}, "palette_override": None}

        items.append(
            {
                "id": sketch_id,
                "title": p.stem,
                "desc": "填色训练（paint_basement）",
                "lineart_url": f"/paint_basement_static/{p.name}",
                "regionmap_url": f"/paint_basement_gen_static/regionmap/{p.stem}_region.png",
                "offsets_url": f"/paint_basement_gen_static/offsets/{p.stem}.ofst",
                # palette: 若 meta 中包含语义级 palette_override，则优先使用
                "regions": [
                    {
                        k: v
                        for k, v in r.items()
                        if k
                        in (
                            "id",
                            "name",
                            "suggest_colors",
                            "target_color",
                            "color_key",
                            "area",
                            "center",
                            "bbox",
                        )
                    }
                    for r in meta.get("regions", [])
                ],
                "palette": list(meta.get("palette_override") or palette_4)[:4] or palette_4,
                "age_range": "3-6",
            }
        )
    return items


@router.get("/get_sketches")
async def get_sketches(request: Request, limit: int = 30, skip: int = 0, debug: int = 0):
    """
    获取涂色线稿列表
    
    Args:
        limit: 返回的最大数量
        skip: 跳过的数量（用于分页）
    
    Returns:
        {
            "ok": true,
            "total": 30,
            "items": [
                {
                    "id": "color_001",
                    "title": "可爱的小兔子",
                    "lineart_url": "...",
                    "regionmap_url": "...",
                    "regions": [...],
                    "age_range": "3-6"
                }
            ]
        }
    """
    trace_id = uuid.uuid4().hex[:12]
    t0 = time.time()
    try:
        index_data = load_coloring_index()
        # 主题：paint_basement 作为“涂色题目”主数据源
        # 前端默认 get_sketches(limit=30) 直接取前 30 条并按题号展示。
        # 若把 practice/coloring/index.json 放在 paint_basement 前面，会挤掉题号 5~9 等条目。
        try:
            basement_items = _load_paint_basement_items()
        except Exception:
            basement_items = []

        # basement 放在最前面，确保前 30 条严格对应题号 1~30
        items = basement_items + list(index_data.get("items", []) or [])
        
        # 分页处理
        paginated = items[skip:skip + limit]

        out = {
            "ok": True,
            "total": len(items),
            "count": len(paginated),
            "items": paginated
        }

        if debug:
            practice_dir = COLORING_DATA_DIR  # practice/coloring
            per_item = []
            for it in paginated:
                lineart_url = str(it.get("lineart_url") or "")
                regionmap_url = str(it.get("regionmap_url") or "")

                def resolve_practice_static(u: str) -> str:
                    # /practice_static/... -> <PROJECT_ROOT>/assets/practice/...
                    if u.startswith("/practice_static/"):
                        rel = u[len("/practice_static/"):]
                        return str((PROJECT_ROOT / "assets" / "practice" / rel).resolve())
                    return ""

                la_path = resolve_practice_static(lineart_url)
                rm_path = resolve_practice_static(regionmap_url)
                per_item.append({
                    "id": it.get("id"),
                    "lineart_url": lineart_url,
                    "regionmap_url": regionmap_url,
                    "lineart_abs": la_path,
                    "regionmap_abs": rm_path,
                    "lineart_exists": bool(la_path and os.path.exists(la_path)),
                    "regionmap_exists": bool(rm_path and os.path.exists(rm_path)),
                    "lineart_size": os.path.getsize(la_path) if la_path and os.path.exists(la_path) else None,
                    "regionmap_size": os.path.getsize(rm_path) if rm_path and os.path.exists(rm_path) else None,
                })

            out["debug"] = {
                "trace_id": trace_id,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "client": {
                    "host": getattr(request.client, "host", None),
                    "user_agent": request.headers.get("user-agent"),
                },
                "project_root": str(PROJECT_ROOT.resolve()),
                "coloring_data_dir": str(COLORING_DATA_DIR.resolve()),
                "index_file": str(COLORING_INDEX_FILE.resolve()),
                "index_exists": COLORING_INDEX_FILE.exists(),
                "items_sample": per_item[: min(10, len(per_item))],
            }
            print(f"[coloring/get_sketches][{trace_id}] ok total={len(items)} count={len(paginated)} elapsed_ms={out['debug']['elapsed_ms']}")

        return out
    except Exception as e:
        print(f"[coloring/get_sketches][{trace_id}] ❌ failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_sketch/{sketch_id}")
async def get_sketch(sketch_id: str):
    """
    获取单个涂色线稿的详细信息
    
    Args:
        sketch_id: 线稿ID，如 "color_001"
    
    Returns:
        详细的线稿信息
    """
    try:
        index_data = load_coloring_index()
        items = index_data.get("items", [])
        
        for item in items:
            if item["id"] == sketch_id:
                return {
                    "ok": True,
                    "data": item
                }
        
        raise HTTPException(status_code=404, detail=f"线稿 {sketch_id} 未找到")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 获取线稿详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save_work")
async def save_coloring_work(
    request: Request,
    sketch_id: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
    user_id: Optional[str] = Form(default="guest"),
    evaluation: Optional[str] = Form(None)
):
    """
    保存用户的涂色作品
    
    Args:
        sketch_id: 线稿ID
        title: 线稿名称
        user_id: 用户ID
        evaluation: AI评价结果（JSON字符串）
    
    Returns:
        {
            "ok": true,
            "work_id": "work_20240318_123456",
            "saved_path": "..."
        }
    """
    try:
        # 兼容小程序 JSON 提交（避免 Form 参数校验导致 422）
        if not sketch_id or not title:
            try:
                body = await request.json()
            except Exception:
                body = {}
            sketch_id = sketch_id or str(body.get("sketch_id") or "").strip()
            title = title or str(body.get("title") or "").strip()
            user_id = (user_id or str(body.get("user_id") or "").strip() or "guest")
            if evaluation is None and body.get("evaluation") is not None:
                ev = body.get("evaluation")
                evaluation = ev if isinstance(ev, str) else json.dumps(ev, ensure_ascii=False)

        if not sketch_id:
            raise HTTPException(status_code=400, detail="缺少 sketch_id")
        if not title:
            title = sketch_id
        if not user_id:
            user_id = "guest"

        # 生成作品ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        work_id = f"work_{timestamp}_{sketch_id}"
        
        # 创建作品记录
        work_record = {
            "work_id": work_id,
            "sketch_id": sketch_id,
            "title": title,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "evaluation": None
        }
        
        # 保存评价信息
        if evaluation:
            try:
                work_record["evaluation"] = json.loads(evaluation)
            except:
                work_record["evaluation"] = {"raw": evaluation}
        
        # 保存到文件
        work_file = COLORING_WORKS_DIR / f"{work_id}.json"
        with open(work_file, "w", encoding="utf-8") as f:
            json.dump(work_record, f, ensure_ascii=False, indent=2)
        
        return {
            "ok": True,
            "work_id": work_id,
            "saved_path": str(work_file),
            "message": "涂色作品已保存"
        }
    except Exception as e:
        print(f"❌ 保存涂色作品失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload_work")
async def upload_coloring_work(
    file: UploadFile = File(...),
    sketch_id: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
    user_id: Optional[str] = Form(default="guest"),
    evaluation: Optional[str] = Form(None),
):
    """
    上传并持久化一幅涂色作品（PNG/JPG），并写入作品记录 JSON。
    返回 works 记录（含 image_url）供前端直接展示。
    """
    try:
        img_bytes = await file.read()
        if not img_bytes:
            raise HTTPException(status_code=400, detail="empty file")

        sketch_id = (sketch_id or "").strip() or "coloring_task"
        title = (title or "").strip() or sketch_id
        user_id = (user_id or "").strip() or "guest"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        work_id = f"work_{timestamp}_{sketch_id}"

        # 保存图片
        ext = (Path(str(file.filename or "")).suffix or "").lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            ext = ".png"
        image_name = f"{work_id}{ext}"
        image_path = COLORING_WORKS_IMAGES_DIR / image_name
        with open(image_path, "wb") as f:
            f.write(img_bytes)

        work_record = {
            "work_id": work_id,
            "sketch_id": sketch_id,
            "title": title,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "evaluation": None,
            "image_name": image_name,
            "image_url": f"/coloring/work_image/{work_id}",
        }
        if evaluation:
            try:
                work_record["evaluation"] = json.loads(evaluation)
            except Exception:
                work_record["evaluation"] = {"raw": evaluation}

        work_file = COLORING_WORKS_DIR / f"{work_id}.json"
        with open(work_file, "w", encoding="utf-8") as f:
            json.dump(work_record, f, ensure_ascii=False, indent=2)

        return {
            "ok": True,
            "work": work_record,
            "work_id": work_id,
            "message": "涂色作品已上传并保存",
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 上传涂色作品失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/work_image/{work_id}")
async def get_coloring_work_image(work_id: str):
    """读取作品图片文件（供小程序 <image> 直接加载）。"""
    try:
        work_file = COLORING_WORKS_DIR / f"{work_id}.json"
        if not work_file.exists():
            raise HTTPException(status_code=404, detail="work not found")
        with open(work_file, "r", encoding="utf-8") as f:
            work = json.load(f)
        image_name = str(work.get("image_name") or "")
        if not image_name:
            raise HTTPException(status_code=404, detail="image not found")
        image_path = COLORING_WORKS_IMAGES_DIR / image_name
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="image file missing")
        # 简单 mime 推断
        suf = image_path.suffix.lower()
        media = "image/png"
        if suf in {".jpg", ".jpeg"}:
            media = "image/jpeg"
        elif suf == ".webp":
            media = "image/webp"
        return FileResponse(str(image_path), media_type=media)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_user_works/{user_id}")
async def get_user_coloring_works(user_id: str, limit: int = 50):
    """
    获取用户的所有涂色作品
    
    Args:
        user_id: 用户ID
        limit: 最多返回的作品数
    
    Returns:
        {
            "ok": true,
            "works": [...]
        }
    """
    try:
        works = []
        for work_file in COLORING_WORKS_DIR.glob("*.json"):
            try:
                with open(work_file, "r", encoding="utf-8") as f:
                    work = json.load(f)
                    if work.get("user_id") == user_id:
                        works.append(work)
            except:
                continue
        
        # 按创建时间倒序排列
        works.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        works = works[:limit]

        # 补齐 image_url（兼容旧记录）
        for w in works:
            if not w.get("image_url") and w.get("work_id") and w.get("image_name"):
                w["image_url"] = f"/coloring/work_image/{w['work_id']}"
        
        return {
            "ok": True,
            "total": len(works),
            "works": works
        }
    except Exception as e:
        print(f"❌ 获取用户作品失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete_work/{work_id}")
async def delete_coloring_work(work_id: str):
    """
    删除涂色作品
    
    Args:
        work_id: 作品ID
    
    Returns:
        {
            "ok": true,
            "message": "作品已删除"
        }
    """
    try:
        work_file = COLORING_WORKS_DIR / f"{work_id}.json"
        if work_file.exists():
            # 同步删除图片文件（如果有）
            try:
                with open(work_file, "r", encoding="utf-8") as f:
                    work = json.load(f)
                image_name = str(work.get("image_name") or "")
                if image_name:
                    image_path = COLORING_WORKS_IMAGES_DIR / image_name
                    if image_path.exists():
                        image_path.unlink()
            except Exception:
                pass
            work_file.unlink()
            return {
                "ok": True,
                "message": f"作品 {work_id} 已删除"
            }
        else:
            raise HTTPException(status_code=404, detail=f"作品 {work_id} 不存在")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 删除作品失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch_regenerate_sketches")
async def batch_regenerate_sketches(start_id: int = 1, end_id: int = 30):
    """
    批量重新生成涂色线稿（管理员用）
    
    这会调用 practice/generate_coloring_lineart.py 脚本
    
    Args:
        start_id: 开始ID（如 1 表示 color_001）
        end_id: 结束ID（如 30 表示 color_030）
    
    Returns:
        {
            "ok": true,
            "message": "开始生成线稿，请稍候..."
        }
    """
    try:
        import subprocess
        
        script_path = Path(__file__).parent.parent / "practice" / "generate_coloring_lineart.py"
        
        # 后台运行生成脚本
        subprocess.Popen(
            ["python", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        return {
            "ok": True,
            "message": f"开始生成线稿 color_{start_id:03d} 到 color_{end_id:03d}，这可能需要几分钟，请稍候..."
        }
    except Exception as e:
        print(f"❌ 批量生成线稿失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate_index")
async def regenerate_coloring_index():
    """
    重新生成涂色线稿索引
    这会在线稿文件夹中扫描所有 PNG 并更新索引
    """
    try:
        from practice.coloring_prompts import load_coloring_prompts
        
        lineart_dir = COLORING_DATA_DIR / "lineart"
        regionmap_dir = COLORING_DATA_DIR / "regionmap"
        
        # 加载提示词
        prompts_file = Path(__file__).parent.parent / "practice" / "coloring_prompts.json"
        with open(prompts_file, "r", encoding="utf-8") as f:
            prompts_data = json.load(f)
        
        prompts_map = {item["id"]: item for item in prompts_data.get("items", [])}
        
        # 扫描线稿文件
        index_items = []
        for lineart_file in sorted(lineart_dir.glob("color_*.png")):
            task_id = lineart_file.stem
            
            if task_id in prompts_map:
                prompt_item = prompts_map[task_id]
                
                index_item = {
                    "id": task_id,
                    "title": prompt_item["title"],
                    "desc": prompt_item["desc"],
                    "lineart_url": f"/practice_static/coloring/lineart/{task_id}.png",
                    "regionmap_url": f"/practice_static/coloring/regionmap/{task_id}_region.png",
                    "regions": prompt_item["regions"],
                    "color_count": prompt_item["color_count"],
                    "age_range": prompt_item.get("age_range", "3-6"),
                    "generated_at": datetime.now().isoformat()
                }
                index_items.append(index_item)
        
        # 保存索引
        index_data = {
            "version": 1,
            "total": len(index_items),
            "generated_at": datetime.now().isoformat(),
            "items": index_items
        }
        
        with open(COLORING_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        
        return {
            "ok": True,
            "message": f"索引已更新，共 {len(index_items)} 项"
        }
    except Exception as e:
        print(f"❌ 重新生成索引失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 健康检查
@router.get("/health")
async def coloring_health():
    """涂色模块健康检查"""
    index_data = load_coloring_index()
    return {
        "ok": True,
        "module": "coloring",
        "status": "healthy",
        "sketches_available": len(index_data.get("items", []))
    }
