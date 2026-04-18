#!/usr/bin/env python3
"""
将项目根目录打包为 zip，排除：
  - 整个 GPT_SoVITS/ 目录
  - 整个 frontend_trim10img_extracted/（大体积解压副本，不应打进源码包）
  - 根目录下两个超大 tar.gz（与 DEPLOY.md 说明一致）
  - Python 虚拟环境目录：venv/、.venv/（不打包本机 pip 安装的环境）

用法（在项目根目录执行）：
  python tools/pack_source_zip.py
  python tools/pack_source_zip.py -o C:\\path\\out.zip
"""
from __future__ import annotations

import argparse
import os
import sys
import zipfile
from pathlib import Path

# 与 DEPLOY.md「0.8」一致：根目录两个超大压缩包文件名
EXCLUDE_ROOT_FILES = frozenset(
    {
        "excluded_big_assets_bundle_20260402-154902.tar.gz",
        "frontend_trim10img_10speaker_5books_repack_20260402-155430.tar.gz",
    }
)
# 项目根下整目录排除（不进入、不打包）
EXCLUDE_TOP_LEVEL_DIRS = frozenset({"GPT_SoVITS", "frontend_trim10img_extracted"})
# 任意层级下名为 venv / .venv 的目录均不打包（避免把本地下载的虚拟环境打进源码包）
EXCLUDE_DIR_NAMES = frozenset({"venv", ".venv"})


def _rel_has_excluded_dir(rel: Path) -> bool:
    if any(p in EXCLUDE_DIR_NAMES for p in rel.parts):
        return True
    # 防止深层路径里出现同名目录时误打包
    if "frontend_trim10img_extracted" in rel.parts:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack project source to zip with exclusions.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="输出 zip 路径（默认：项目上一级目录，文件名：<项目文件夹名>-src-no-gptsovits-no-big-tarballs.zip）",
    )
    args = parser.parse_args()

    tools_dir = Path(__file__).resolve().parent
    project_root = tools_dir.parent
    if not project_root.is_dir():
        print("无法定位项目根目录", file=sys.stderr)
        return 1

    out_zip = args.output
    if out_zip is None:
        out_zip = project_root.parent / f"{project_root.name}-src-no-gptsovits-no-big-tarballs.zip"

    out_zip = out_zip.resolve()
    print(f"项目根: {project_root}")
    print(f"输出:   {out_zip}")
    print(
        "排除:   "
        + ", ".join(sorted(EXCLUDE_TOP_LEVEL_DIRS))
        + "/ 、"
        + str(sorted(EXCLUDE_DIR_NAMES))
        + " 、根目录文件 "
        + str(sorted(EXCLUDE_ROOT_FILES))
    )

    count = 0
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dirpath, dirnames, filenames in os.walk(project_root):
            # 不进入根级排除目录
            for d in list(dirnames):
                if d in EXCLUDE_TOP_LEVEL_DIRS:
                    dirnames.remove(d)
            # 不进入 venv / .venv
            for d in list(dirnames):
                if d in EXCLUDE_DIR_NAMES:
                    dirnames.remove(d)

            rel_dir = Path(dirpath).relative_to(project_root)
            for fn in filenames:
                fp = Path(dirpath) / fn
                rel = fp.relative_to(project_root)
                if _rel_has_excluded_dir(rel):
                    continue
                # 根目录排除两个 tar.gz
                if rel.parts[0:1] == (fn,) and fn in EXCLUDE_ROOT_FILES:
                    continue
                arcname = rel.as_posix()
                zf.write(fp, arcname)
                count += 1
                if count % 2000 == 0:
                    print(f"  ... 已加入 {count} 个文件")

    print(f"完成，共打包 {count} 个文件，大小约 {out_zip.stat().st_size / (1024 * 1024):.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
