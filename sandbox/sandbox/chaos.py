"""Seeded failure injection so the operator's recovery paths are exercised, not assumed.

Faults: random 5xx before handling, slow responses, delayed form rendering (client side),
session expiry after N requests, alternative button labels, and an "acknowledgement lost"
trap where a create is committed but the client receives a 502.
"""

import asyncio
import random
from dataclasses import dataclass, field

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from sandbox.config import ChaosSettings

_EXEMPT_PREFIXES = ("/static", "/health", "/favicon")
_LABEL_VARIANTS: dict[str, tuple[str, ...]] = {
    "save_invoice": ("Save invoice", "Record invoice", "Submit"),
    "save_vendor": ("Save vendor", "Create vendor", "Add supplier"),
    "sign_in": ("Sign in", "Log in", "Continue"),
    "download_pdf": ("Download PDF", "Get invoice PDF", "Download"),
}


@dataclass
class ChaosEngine:
    settings: ChaosSettings
    _rng: random.Random = field(init=False)
    _ack_trap_armed: bool = field(init=False)
    _label_variant: int = field(init=False)

    def __post_init__(self) -> None:
        # Deterministic on purpose: a fixed seed replays the same faults in tests.
        self._rng = random.Random(self.settings.seed)  # noqa: S311
        self._ack_trap_armed = self.settings.duplicate_trap
        variant = self._rng.randrange(len(_LABEL_VARIANTS["save_invoice"]))
        self._label_variant = variant if self.settings.enabled and self.settings.alt_labels else 0

    def label(self, key: str) -> str:
        return _LABEL_VARIANTS[key][self._label_variant]

    @property
    def render_delay_ms(self) -> int:
        return self.settings.render_delay_ms if self.settings.enabled else 0

    @property
    def session_max_requests(self) -> int | None:
        return self.settings.session_max_requests if self.settings.enabled else None

    def should_fail(self) -> bool:
        return self.settings.enabled and self._rng.random() < self.settings.error_rate

    def slow_delay_seconds(self) -> float:
        if self.settings.enabled and self._rng.random() < self.settings.slow_rate:
            return self.settings.slow_ms / 1000
        return 0.0

    def consume_ack_trap(self) -> bool:
        """True exactly once when the duplicate trap is on: drop the success acknowledgement."""
        if self._ack_trap_armed:
            self._ack_trap_armed = False
            return True
        return False


class ChaosMiddleware:
    def __init__(self, app: ASGIApp, engine: ChaosEngine) -> None:
        self._app = app
        self._engine = engine

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(_EXEMPT_PREFIXES):
            await self._app(scope, receive, send)
            return
        if delay := self._engine.slow_delay_seconds():
            await asyncio.sleep(delay)
        if self._engine.should_fail():
            await _unavailable(Request(scope))(scope, receive, send)
            return
        await self._app(scope, receive, send)


def _unavailable(request: Request) -> Response:
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Service temporarily unavailable"}, status_code=503)
    return HTMLResponse(
        "<html><body><h1>503 Service Unavailable</h1>"
        "<p>The server is temporarily busy. Please try again.</p></body></html>",
        status_code=503,
    )
