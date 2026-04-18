"""
Compatibility stub for coloring API.

The real implementation is under:
  modules/coloring_artist/backend/coloring_api.py

This file keeps existing imports working, e.g.:
  from coloring_api import router
"""

from modules.coloring_artist.backend.coloring_api import router  # noqa: F401

__all__ = ["router"]

