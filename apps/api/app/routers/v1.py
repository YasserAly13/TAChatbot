"""The ``/v1`` versioned API surface (MANDATORY — ADR-0001 / rule 05).

Every business endpoint MUST be served under ``/v1``. Add a feature router and
attach it here so it inherits the prefix::

    # app/routers/projects.py
    from fastapi import APIRouter
    router = APIRouter(prefix="/projects", tags=["projects"])

    @router.get("")
    async def list_projects() -> list[dict]:
        ...

    # app/routers/v1.py
    from app.routers import projects
    v1_router.include_router(projects.router)   # -> GET /v1/projects

Operational endpoints (``/ping``, ``/health``, ``/info``) are the only exemption
and stay unversioned in ``app/routes.py``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ErrorBody
from app.routers import conversations

API_V1_PREFIX = "/v1"

# Business feature routers attach to this router (see module docstring). It is
# included by app/main.py.
v1_router = APIRouter(
    prefix=API_V1_PREFIX,
    # The error contract (app/errors.py) — documented once here, inherited by every
    # feature router; add per-route 404/409 with `responses={404: {"model": ErrorBody}}`.
    responses={
        422: {"model": ErrorBody, "description": "Validation failed (`validation_error`)"},
        500: {"model": ErrorBody, "description": "Unhandled error (`internal_error`)"},
    },
)

# /v1/conversations — create and list (roadmap api 2.1)
v1_router.include_router(conversations.router)
