#!/usr/bin/env python3
# Wrapper script to keep the TTS backend generation code under modules/.
# It delegates to the original implementation under the project root.

import os
import runpy
import sys


def _project_root() -> str:
    # modules/tts_backend/practice/generate_speaker_images.py -> project root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


if __name__ == "__main__":
    root = _project_root()
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    runpy.run_path(os.path.join(root, "practice", "generate_speaker_images.py"), run_name="__main__")

