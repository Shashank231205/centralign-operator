"""Integration tests against real Postgres and Redis (run with: uv run poe test-integration).

Requires the services from docker-compose (or scripts/windows/infra.ps1) and an applied
migration. Settings come from the environment, exactly like production.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.config import get_settings
from app.core.rate_limit import BucketSpec, TokenBucketLimiter
from app.infrastructure.cache.redis import create_redis
from app.infrastructure.db.engine import Database
from app.main import create_app
from app.services.memory import PostgresCompanyMemory

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis() -> AsyncIterator[object]:
    client = create_redis(get_settings().redis)
    yield client
    await client.aclose()


async def test_token_bucket_allows_burst_then_limits(redis: object) -> None:
    limiter = TokenBucketLimiter(redis)  # type: ignore[arg-type]
    key = f"test:{uuid.uuid4()}"
    spec = BucketSpec(rate_per_second=0.1, capacity=2)
    decisions = [await limiter.acquire(key, spec) for _ in range(3)]
    assert [decision.allowed for decision in decisions] == [True, True, False]
    assert decisions[2].retry_after_seconds > 0


async def test_memory_deduplicates_and_recalls_by_text_search() -> None:
    database = Database(get_settings().database)
    memory = PostgresCompanyMemory(database)
    marker = uuid.uuid4().hex[:8]
    lesson = f"Ledgerly due date field requires DD/MM/YYYY {marker}"
    assert await memory.learn([lesson, lesson], str(uuid.uuid4())) == [lesson]
    recalled = await memory.recall(f"ledgerly due date {marker}", limit=5)
    assert any(marker in item for item in recalled)
    await database.dispose()


async def test_api_requires_key_and_accepts_tasks_idempotently() -> None:
    settings = get_settings()
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    key = settings.api.bootstrap_api_key.get_secret_value()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as client,
    ):
        assert (await client.post("/tasks", json={"request": "hello"})).status_code == 401
        headers = {"X-API-Key": key, "Idempotency-Key": f"it-{uuid.uuid4()}"}
        first = await client.post(
            "/tasks", json={"request": "Export overdue invoices"}, headers=headers
        )
        second = await client.post(
            "/tasks", json={"request": "Export overdue invoices"}, headers=headers
        )
        assert first.status_code == second.status_code == 202
        assert first.json()["run_id"] == second.json()["run_id"]
        assert second.json()["replayed"] is True
        detail = await client.get(f"/runs/{first.json()['run_id']}", headers={"X-API-Key": key})
        assert detail.status_code == 200
