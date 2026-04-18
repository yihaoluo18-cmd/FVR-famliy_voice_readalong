#!/usr/bin/env python3
# Wrapper: modules/tts_backend/training/prepare_dataset.py
# Delegates to project-root prepare_dataset.py

import os
import runpy
import sys


def _project_root() -> str:
    # modules/tts_backend/training/prepare_dataset.py -> project root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


if __name__ == "__main__":
    root = _project_root()
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    # First try the encapsulated/deprecated location.
    target = os.path.join(root, "deprecated_unused", "prepare_dataset.py")
    if not os.path.isfile(target):
        target = os.path.join(root, "prepare_dataset.py")
    runpy.run_path(target, run_name="__main__")
