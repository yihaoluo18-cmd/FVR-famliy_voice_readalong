#!/usr/bin/env python3
"""
Generate GitHub Release zip bundles:
  - assets_release.zip  from <deploy_root>/仓库/assets
  - fvr_deploy_output.zip from <deploy_root>/test/FVR_deploy_run/output

<deploy_root> = parent of the FVR_github repo directory (this script lives in FVR_github/scripts/).
Override with env FVR_DEPLOY_ROOT.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    deploy_root = Path(os.environ.get("FVR_DEPLOY_ROOT", repo_root.parent)).resolve()

    assets_dir = deploy_root / "仓库" / "assets"
    output_dir = deploy_root / "test" / "FVR_deploy_run" / "output"
    release_dir = deploy_root / "release_packages"
    release_dir.mkdir(parents=True, exist_ok=True)

    if not assets_dir.is_dir():
        print(f"[error] 未找到资源目录: {assets_dir}", file=sys.stderr)
        print("  设置 FVR_DEPLOY_ROOT 指向包含「仓库/assets」的部署根目录。", file=sys.stderr)
        return 1
    if not output_dir.is_dir():
        print(f"[error] 未找到 output 目录: {output_dir}", file=sys.stderr)
        return 1

    assets_zip = release_dir / "assets_release"
    output_zip = release_dir / "fvr_deploy_output"

    # Zip root: contents of assets/ at archive root (images/, paint_basement_generated/, ...)
    shutil.make_archive(str(assets_zip), "zip", root_dir=str(assets_dir))
    # Zip contains output/... for extract-at-project-root layout
    shutil.make_archive(str(output_zip), "zip", root_dir=str(output_dir.parent), base_dir="output")

    print(f"OK: {assets_zip}.zip")
    print(f"OK: {output_zip}.zip")
    print(f"部署根目录: {deploy_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
