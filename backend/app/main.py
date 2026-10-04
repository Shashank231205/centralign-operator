"""FastAPI app factory: lifespan, middleware and router mounting only."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import install_middleware
from app.api.v1.router import api_router
from app.container import Container
from app.core.config import API_PREFIX, Settings, get_settings
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = await Container.create(settings)
        await container.start()
        app.state.container = container
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(title="Autonomous Company Operator", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key"],
    )
    install_middleware(app)
    app.include_router(api_router, prefix=API_PREFIX)
    return app
