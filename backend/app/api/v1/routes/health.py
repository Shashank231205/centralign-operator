import asyncio
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_container
from app.container import Container

router = APIRouter(prefix="/health", tags=["health"])

READINESS_TIMEOUT_SECONDS = 2.0


@router.get("/live")
async def live() -> dict[str, str]:
    """Process is up. Never touches dependencies so orchestrators don't restart on DB blips."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(container: Annotated[Container, Depends(get_container)]) -> JSONResponse:
    checks = {
        "database": await _check(container.database.ping()),
        "redis": await _check(container.redis.ping()),
    }
    healthy = all(status == "ok" for status in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )


async def _check(probe: Awaitable[object]) -> str:
    try:
        await asyncio.wait_for(probe, timeout=READINESS_TIMEOUT_SECONDS)
    # OSError covers TimeoutError and refused connections.
    except (OSError, SQLAlchemyError, RedisError) as exc:
        return f"error: {type(exc).__name__}"
    return "ok"
