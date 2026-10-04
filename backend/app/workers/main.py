"""arq worker: executes runs from the queue.

A Redis lock guarantees one executor per run. The runtime checkpoints after every step, so a
killed worker (deploy, crash, SIGTERM) loses at most one step and arq's retry resumes the run
from its checkpoint. If every LLM backend is down, the job is deferred rather than failed.
"""

import logging
import uuid
from typing import Any, ClassVar

from arq import Retry

from app.container import WorkerContainer
from app.core.config import get_settings
from app.core.errors import LLMUnavailableError
from app.core.logging import configure_logging, run_id_var
from app.infrastructure.cache.coordination import RunLock
from app.infrastructure.queue.jobs import arq_settings
from app.infrastructure.repositories.runs import RunRepository

logger = logging.getLogger(__name__)
CONTAINER_KEY = "container"

_settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(_settings.log_level)
    container = WorkerContainer.build(_settings)
    await container.start()
    ctx[CONTAINER_KEY] = container
    logger.info("worker started", extra={"queue": _settings.redis.queue_name})


async def shutdown(ctx: dict[str, Any]) -> None:
    container: WorkerContainer | None = ctx.get(CONTAINER_KEY)
    if container:
        await container.close()


async def execute_run(ctx: dict[str, Any], run_id: str) -> str:
    container: WorkerContainer = ctx[CONTAINER_KEY]
    run_uuid = uuid.UUID(run_id)
    lock = RunLock(container.shared.redis, run_uuid, _settings.redis.run_lock_ttl_seconds)
    if not await lock.acquire():
        logger.info("run is held by another worker", extra={"run_id": run_id})
        return "locked"
    token = run_id_var.set(run_id)
    try:
        return await _advance(container, run_uuid)
    finally:
        run_id_var.reset(token)
        await lock.release()


async def _advance(container: WorkerContainer, run_id: uuid.UUID) -> str:
    async with container.shared.database.session() as session:
        state = await RunRepository(session).get_state(run_id)
    if state is None or state.status.is_terminal or state.status.is_paused:
        return state.status if state else "missing"
    browser = container.run_browser()
    try:
        await container.runtime.advance(
            state, container.tool_context(run_id, browser), container.shared.recorder
        )
    except LLMUnavailableError as exc:
        await container.shared.recorder.checkpoint(state)
        logger.warning("llm unavailable; deferring run", extra={"error": exc.message})
        raise Retry(defer=_settings.agent.llm_unavailable_retry_seconds) from exc
    finally:
        await browser.close()
    return state.status


class WorkerSettings:
    functions: ClassVar[list[Any]] = [execute_run]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = arq_settings(_settings.redis)
    queue_name = _settings.redis.queue_name
    job_timeout = _settings.agent.max_duration_seconds + _settings.agent.worker_grace_seconds
    max_tries = _settings.agent.worker_max_tries
    max_jobs = _settings.agent.worker_concurrency
    keep_result = _settings.agent.job_result_ttl_seconds
