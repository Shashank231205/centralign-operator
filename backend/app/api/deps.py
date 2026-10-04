"""FastAPI dependency providers. Routes depend on these, never on concrete infrastructure."""

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request

from app.container import Container
from app.core.errors import AuthenticationError, RateLimitedError
from app.core.rate_limit import BucketSpec
from app.core.security import hash_api_key
from app.infrastructure.repositories.api_keys import ApiKeyRepository

_KEY_CACHE_PREFIX = "operator:apikey:"
_BEARER = "bearer "


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def require_api_key(
    container: ContainerDep,
    x_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """Authenticate by API key (X-API-Key or Bearer) and apply the per-key rate limit."""
    raw = x_api_key or _bearer_token(authorization)
    if not raw:
        raise AuthenticationError("Missing API key")
    key_id = await _resolve_key(container, hash_api_key(raw))
    if key_id is None:
        raise AuthenticationError("Invalid API key")
    api = container.settings.api
    decision = await container.shared.limiter.acquire(
        f"api:{key_id}", BucketSpec.per_minute(api.requests_per_minute, api.burst)
    )
    if not decision.allowed:
        raise RateLimitedError(
            "Too many requests", retry_after_seconds=decision.retry_after_seconds
        )
    return key_id


ApiKeyDep = Annotated[uuid.UUID, Depends(require_api_key)]


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith(_BEARER):
        return authorization[len(_BEARER) :].strip()
    return None


async def _resolve_key(container: Container, key_hash: str) -> uuid.UUID | None:
    """Cache-aside: hashed key → key id in Redis, falling back to Postgres."""
    redis = container.redis
    if cached := await redis.get(_KEY_CACHE_PREFIX + key_hash):
        return uuid.UUID(str(cached))
    async with container.database.session() as session:
        key_id = await ApiKeyRepository(session).find_active(key_hash)
    if key_id is not None:
        await redis.set(
            _KEY_CACHE_PREFIX + key_hash,
            str(key_id),
            ex=container.settings.api.key_cache_ttl_seconds,
        )
    return key_id
