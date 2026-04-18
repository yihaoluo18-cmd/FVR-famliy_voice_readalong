#!/usr/bin/env python3
# Wrapper: modules/tts_backend/inference/simple_inference.py
# Delegates to project-root simple_inference.py

import os
import runpy
import sys


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


if __name__ == "__main__":
    root = _project_root()
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    target = os.path.join(root, "deprecated_unused", "simple_inference.py")
    if not os.path.isfile(target):
        target = os.path.join(root, "simple_inference.py")
    runpy.run_path(target, run_name="__main__")
