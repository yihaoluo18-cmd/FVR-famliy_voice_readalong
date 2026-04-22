import os
import runpy
import sys
from pathlib import Path


def main() -> int:
    raw = str(os.environ.get("PREP_PIPELINE_SCRIPTS", "")).strip()
    scripts = [x.strip() for x in raw.split(";") if x.strip()]
    if not scripts:
        print("[prepare_pipeline_part] no scripts configured")
        return 2

    for idx, script in enumerate(scripts, start=1):
        p = Path(script)
        if not p.exists():
            print(f"[prepare_pipeline_part] missing script: {p}")
            return 3
        print(f"[prepare_pipeline_part] ({idx}/{len(scripts)}) run: {p}")
        # 每个脚本以独立 __main__ 上下文执行，但复用同一 Python 进程。
        runpy.run_path(str(p), run_name="__main__")
    print("[prepare_pipeline_part] done")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[prepare_pipeline_part] fatal: {e}")
        raise
