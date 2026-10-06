"""Versioned API routers for the AI Accelerator api service (FastAPI).

Business feature routers live here and attach to ``v1_router`` (see ``v1.py``),
so every business endpoint is served under ``/v1``. Operational endpoints
(``/ping``, ``/health``, ``/info``) stay unversioned in ``app/routes.py``.
"""

from __future__ import annotations

from app.routers.v1 import API_V1_PREFIX, v1_router

__all__ = ["API_V1_PREFIX", "v1_router"]
