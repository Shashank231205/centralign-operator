"""Composition roots. Concrete infrastructure is built once per process and injected; nothing
else constructs clients. The API process needs no browser or LLM; workers get both."""

import time
import uuid
from dataclasses import dataclass, field

import httpx
from redis.asyncio import Redis

from app.agent.executor.executor import Executor
from app.agent.observer.observer import Observer
from app.agent.prompts.library import DEFAULT_PROMPTS_DIR, PromptLibrary
from app.agent.runtime.budget import BudgetGuard
from app.agent.runtime.orchestrator import AgentRuntime
from app.agent.stages import Stages
from app.agent.understanding.context import ContextLoader
from app.agent.verifier.verifier import Verifier
from app.core.config import Settings, environment_variables
from app.core.rate_limit import BucketSpec, TokenBucketLimiter
from app.core.resilience import BreakerRegistry, RetryPolicy
from app.core.security import hash_api_key
from app.infrastructure.cache.coordination import CancelFlags, EventBus, IdempotencyCache
from app.infrastructure.cache.redis import create_redis
from app.infrastructure.db.engine import Database
from app.infrastructure.http import create_http_client
from app.infrastructure.queue.jobs import RunQueue
from app.infrastructure.repositories.api_keys import ApiKeyRepository
from app.infrastructure.storage.local import LocalEvidenceStore
from app.llm.cache import LLMResponseCache
from app.llm.providers.openai_compatible import OpenAICompatibleProvider
from app.llm.router import LLMRouter
from app.llm.structured import StructuredLLM
from app.services.approvals import ApprovalService
from app.services.memory import PostgresCompanyMemory
from app.services.recorder import DbRunRecorder
from app.services.runs import RunService
from app.services.tasks import TaskService
from app.tools.base import CredentialStore, ToolContext, Workspace
from app.tools.browser.session import BrowserManager, RunBrowser
from app.tools.catalog import default_registry

BOOTSTRAP_KEY_NAME = "bootstrap"


@dataclass(slots=True)
class Shared:
    """Infrastructure common to API and worker processes."""

    settings: Settings
    database: Database
    redis: Redis
    bus: EventBus
    cancel_flags: CancelFlags
    recorder: DbRunRecorder
    memory: PostgresCompanyMemory
    evidence: LocalEvidenceStore
    limiter: TokenBucketLimiter

    @classmethod
    def build(cls, settings: Settings) -> "Shared":
        database = Database(settings.database)
        redis = create_redis(settings.redis)
        bus = EventBus(redis, settings.redis.events_channel_prefix)
        cancel_flags = CancelFlags(redis, settings.agent.max_duration_seconds * 4)
        return cls(
            settings=settings,
            database=database,
            redis=redis,
            bus=bus,
            cancel_flags=cancel_flags,
            recorder=DbRunRecorder(database, bus, cancel_flags),
            memory=PostgresCompanyMemory(database),
            evidence=LocalEvidenceStore(settings.paths.evidence_dir),
            limiter=TokenBucketLimiter(redis),
        )

    async def ping(self) -> None:
        await self.database.ping()
        await self.redis.ping()

    async def close(self) -> None:
        await self.redis.aclose()
        await self.database.dispose()


@dataclass(slots=True)
class Container:
    """API process."""

    shared: Shared
    queue: RunQueue
    tasks: TaskService
    runs: RunService
    approvals: ApprovalService

    @property
    def settings(self) -> Settings:
        return self.shared.settings

    @property
    def database(self) -> Database:
        return self.shared.database

    @property
    def redis(self) -> Redis:
        return self.shared.redis

    @classmethod
    async def create(cls, settings: Settings) -> "Container":
        shared = Shared.build(settings)
        queue = await RunQueue.connect(settings.redis)
        idempotency = IdempotencyCache(shared.redis, settings.api.idempotency_ttl_seconds)
        return cls(
            shared=shared,
            queue=queue,
            tasks=TaskService(shared.database, queue, idempotency),
            runs=RunService(
                shared.database,
                queue,
                shared.bus,
                shared.cancel_flags,
                shared.recorder,
                shared.evidence,
            ),
            approvals=ApprovalService(shared.database, queue, shared.recorder, shared.memory),
        )

    async def start(self) -> None:
        """Fail fast on unreachable dependencies; register the bootstrap API key (hashed)."""
        await self.shared.ping()
        key_hash = hash_api_key(self.settings.api.bootstrap_api_key.get_secret_value())
        async with self.database.session() as session:
            await ApiKeyRepository(session).ensure(BOOTSTRAP_KEY_NAME, key_hash)

    async def close(self) -> None:
        await self.queue.close()
        await self.shared.close()


@dataclass(slots=True)
class WorkerContainer:
    """Worker process: everything needed to execute runs."""

    shared: Shared
    http: httpx.AsyncClient
    breakers: BreakerRegistry
    context_loader: ContextLoader
    credentials: CredentialStore
    browser: BrowserManager
    runtime: AgentRuntime
    browsers: dict[uuid.UUID, tuple[RunBrowser, float]] = field(default_factory=dict)

    @property
    def settings(self) -> Settings:
        return self.shared.settings

    @classmethod
    def build(cls, settings: Settings) -> "WorkerContainer":
        shared = Shared.build(settings)
        http = create_http_client()
        breakers = BreakerRegistry(settings.resilience)
        registry = default_registry()
        retry = RetryPolicy.from_settings(settings.resilience)
        llm = _structured_llm(settings, shared, http, breakers)
        runtime = AgentRuntime(
            stages=Stages(llm, PromptLibrary(DEFAULT_PROMPTS_DIR), registry, settings.agent),
            executor=Executor(registry, retry, settings.agent.action_timeout_seconds),
            verifier=Verifier(settings.agent, retry),
            observer=Observer(settings.agent),
            budget=BudgetGuard(settings.agent),
            memory=shared.memory,
            settings=settings.agent,
        )
        return cls(
            shared=shared,
            http=http,
            breakers=breakers,
            context_loader=ContextLoader(
                settings.paths.company_context_dir, environment_variables()
            ),
            credentials=CredentialStore(settings.credentials),
            browser=BrowserManager(settings.browser),
            runtime=runtime,
        )

    async def start(self) -> None:
        await self.shared.ping()
        self.context_loader.load()
        await self.browser.start()

    async def close(self) -> None:
        for browser, _ in self.browsers.values():
            await browser.close()
        await self.browser.stop()
        await self.http.aclose()
        await self.shared.close()

    def run_browser(self, run_id: uuid.UUID) -> RunBrowser:
        """Reuse the run's browser if it paused recently on this worker, else start fresh."""
        cached = self.browsers.pop(run_id, None)
        if cached is not None:
            return cached[0]
        return RunBrowser(self.browser, self.context_loader.load().allowed_hosts)

    async def release_browser(self, run_id: uuid.UUID, browser: RunBrowser, keep: bool) -> None:
        if keep:
            self.browsers[run_id] = (browser, time.monotonic())
        else:
            await browser.close()
        await self._close_idle_browsers()

    async def _close_idle_browsers(self) -> None:
        cutoff = time.monotonic() - self.settings.browser.session_idle_seconds
        for run_id, (browser, parked_at) in list(self.browsers.items()):
            if parked_at < cutoff:
                del self.browsers[run_id]
                await browser.close()

    def tool_context(self, run_id: uuid.UUID, browser: RunBrowser) -> ToolContext:
        resilience = self.settings.resilience
        return ToolContext(
            run_id=run_id,
            company=self.context_loader.load(),
            workspace=Workspace(self.settings.paths.workspace_dir / str(run_id)),
            evidence=self.shared.evidence,
            credentials=self.credentials,
            http=self.http,
            browser=browser,
            limiter=self.shared.limiter,
            host_bucket=BucketSpec(resilience.host_requests_per_second, resilience.host_burst),
            host_rate_wait_seconds=resilience.host_rate_wait_seconds,
            breakers=self.breakers,
            observation_char_budget=self.settings.agent.observation_char_budget,
        )


def _structured_llm(
    settings: Settings, shared: Shared, http: httpx.AsyncClient, breakers: BreakerRegistry
) -> StructuredLLM:
    providers = {
        name: OpenAICompatibleProvider(name, settings.llm.backends[name], http)
        for name in settings.llm.providers
    }
    router = LLMRouter.build(providers, settings.llm, settings.resilience, shared.limiter, breakers)
    cache = LLMResponseCache(shared.redis, settings.llm.cache_ttl_seconds)
    return StructuredLLM(router, settings.llm, cache, router.fingerprint)
