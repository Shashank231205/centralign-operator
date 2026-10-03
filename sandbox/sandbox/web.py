"""Plumbing shared by both mock apps: cookie sessions, login guard, templates, DB sessions.

Per-app state (chaos engine, templates, DB sessionmaker) lives on ``app.state`` so routes can
be declared at module level with plain FastAPI dependencies.
"""

import hmac
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from sandbox.chaos import ChaosEngine, ChaosMiddleware
from sandbox.config import SandboxSettings

SESSION_USER_KEY = "user"
SESSION_HITS_KEY = "hits"


class LoginRequiredError(Exception):
    def __init__(self, next_path: str) -> None:
        super().__init__(next_path)
        self.next_path = next_path


def credentials_match(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode(), expected.encode())


def safe_next(path: str, default: str) -> str:
    """Only allow same-origin relative redirects (blocks //host and scheme URLs)."""
    return path if path.startswith("/") and not path.startswith("//") else default


def chaos_of(request: Request) -> ChaosEngine:
    engine: ChaosEngine = request.app.state.chaos
    return engine


def templates_of(request: Request) -> Jinja2Templates:
    templates: Jinja2Templates = request.app.state.templates
    return templates


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with sessions() as session:
        yield session


def require_user(request: Request) -> str:
    """Return the signed-in user or redirect to /login.

    Under chaos the session silently expires after N requests, like a real SSO timeout.
    """
    user = request.session.get(SESSION_USER_KEY)
    if not user:
        raise LoginRequiredError(request.url.path)
    hits = int(request.session.get(SESSION_HITS_KEY, 0)) + 1
    limit = chaos_of(request).session_max_requests
    if limit is not None and hits > limit:
        request.session.clear()
        raise LoginRequiredError(request.url.path)
    request.session[SESSION_HITS_KEY] = hits
    return str(user)


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[str, Depends(require_user)]


def sign_in(request: Request, username: str) -> None:
    request.session.clear()
    request.session[SESSION_USER_KEY] = username
    request.session[SESSION_HITS_KEY] = 0


def render(request: Request, template: str, status_code: int = 200, **context: Any) -> Response:
    return templates_of(request).TemplateResponse(
        request, template, context, status_code=status_code
    )


async def _redirect_to_login(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, LoginRequiredError)
    return RedirectResponse(f"/login?next={quote(exc.next_path)}", status_code=303)


def build_app(
    *, title: str, settings: SandboxSettings, cookie_name: str, package_dir: Path, db_file: str
) -> FastAPI:
    chaos = ChaosEngine(settings.chaos)
    app = FastAPI(title=title, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.chaos = chaos
    app.state.settings = settings
    app.state.templates = _templates(package_dir, chaos)
    app.state.sessions = sqlite_sessions(settings.sandbox.data_dir / db_file)
    app.add_middleware(ChaosMiddleware, engine=chaos)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.sandbox.session_secret.get_secret_value(),
        session_cookie=cookie_name,
        same_site="lax",
    )
    app.add_exception_handler(LoginRequiredError, _redirect_to_login)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _templates(package_dir: Path, chaos: ChaosEngine) -> Jinja2Templates:
    templates = Jinja2Templates(
        directory=[package_dir / "templates", Path(__file__).parent / "templates"]
    )
    templates.env.globals["label"] = chaos.label
    templates.env.globals["render_delay_ms"] = chaos.render_delay_ms
    templates.env.filters["money"] = money
    return templates


def sqlite_sessions(path: Path) -> async_sessionmaker[AsyncSession]:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    return async_sessionmaker(engine, expire_on_commit=False)


def money(value: Any) -> str:
    return f"{float(value):,.2f}"
