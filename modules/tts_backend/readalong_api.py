"""
Compatibility stub for readalong API.

The real implementation has been moved to:
  modules/speaker_game/readalong_api.py

This file keeps existing launch/import paths working (e.g. uvicorn readalong_api:app
or older scripts pointing to modules.tts_backend.readalong_api:app).
"""

from modules.speaker_game.readalong_api import app  # noqa: F401

__all__ = ["app"]
