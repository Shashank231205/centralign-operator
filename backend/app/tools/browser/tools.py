"""Browser actions. Each one ends with a fresh, settled page observation.

Page-level outcomes (HTTP errors, validation messages) come back as observations so the model
can read and react to them; only tool-level problems (stale ref, policy) raise.
"""

import asyncio
from abc import abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, ClassVar
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, Field, model_validator

from app.core.errors import PolicyViolationError, ToolError, ToolInputError, ToolTimeoutError
from app.domain.enums import EvidenceKind, FailureKind, RiskLevel, ToolKind
from app.domain.models import ArtifactRef, Assessment, Observation
from app.tools.base import Tool, ToolContext, ensure_writable
from app.tools.browser.session import BrowserSession
from app.tools.browser.snapshot import PageSnapshot

_HTTP_SERVER_ERROR = 500
_HTTP_CLIENT_ERROR = 400


async def observe(
    session: BrowserSession, ctx: ToolContext, label: str, *, screenshot: bool = True
) -> Observation:
    snapshot = await session.snapshot()
    artifacts: list[ArtifactRef] = []
    if screenshot:
        artifacts.append(
            await ctx.evidence.save(
                ctx.run_id,
                f"{label}.png",
                await session.screenshot(),
                EvidenceKind.SCREENSHOT,
                f"{snapshot.title} ({snapshot.url})",
            )
        )
    ok, failure = _classify(snapshot)
    return Observation(
        ok=ok,
        summary=snapshot.render(ctx.observation_char_budget),
        data={"url": snapshot.url, "title": snapshot.title, "status": snapshot.status},
        error=_error_text(snapshot) if not ok else None,
        failure_kind=failure,
        artifacts=artifacts,
        location=snapshot.url,
    )


def _classify(snapshot: PageSnapshot) -> tuple[bool, FailureKind | None]:
    status = snapshot.status or 200
    if status >= _HTTP_SERVER_ERROR:
        return False, FailureKind.TRANSIENT
    if status >= _HTTP_CLIENT_ERROR:
        return False, FailureKind.STRUCTURAL
    return True, None


def _error_text(snapshot: PageSnapshot) -> str:
    detail = "; ".join(snapshot.alerts) or (snapshot.headings[0] if snapshot.headings else "")
    return f"HTTP {snapshot.status}: {detail}".strip()


@asynccontextmanager
async def translated_errors(action: str) -> AsyncIterator[None]:
    """Map Playwright exceptions to typed errors so the executor stays driver-agnostic."""
    try:
        yield
    except PlaywrightTimeoutError as exc:
        raise ToolTimeoutError(f"{action} timed out: {exc.message.splitlines()[0]}") from exc
    except PlaywrightError as exc:
        raise ToolError(f"{action} failed: {exc.message.splitlines()[0]}") from exc


async def _session_for(ctx: ToolContext, url: str | None = None) -> BrowserSession:
    session = await ctx.browser.session()
    host = urlparse(url or session.page.url).netloc
    if host:
        await ctx.throttle_host(host)
    session.reset_status()
    return session


class BrowserTool[ArgsT: BaseModel](Tool[ArgsT]):
    """Runs ``act`` with Playwright errors translated to typed tool errors."""

    kind: ClassVar[ToolKind] = ToolKind.BROWSER

    async def run(self, args: ArgsT, ctx: ToolContext) -> Observation:
        async with translated_errors(self.name):
            return await self.act(args, ctx)

    @abstractmethod
    async def act(self, args: ArgsT, ctx: ToolContext) -> Observation: ...


class OpenArgs(BaseModel):
    url: str = Field(description="Absolute URL inside an allowed company system")


class BrowserOpen(BrowserTool[OpenArgs]):
    name: ClassVar[str] = "browser_open"
    description: ClassVar[str] = "Navigate the browser to a URL and observe the page."
    args_model = OpenArgs

    async def assess(self, args: OpenArgs, ctx: ToolContext) -> Assessment:
        host = urlparse(args.url).netloc
        if host not in ctx.company.allowed_hosts:
            raise PolicyViolationError(f"Host '{host}' is not an approved company system")
        system = ctx.company.system_for_url(args.url)
        return Assessment(
            risk=RiskLevel.READ,
            system=system.name if system else None,
            description=f"open {args.url}",
        )

    async def act(self, args: OpenArgs, ctx: ToolContext) -> Observation:
        session = await _session_for(ctx, args.url)
        await session.page.goto(args.url, wait_until="domcontentloaded")
        return await observe(session, ctx, "open")


class RefArgs(BaseModel):
    ref: str = Field(description="Element ref from the latest page observation, e.g. e7")


class BrowserClick(BrowserTool[RefArgs]):
    name: ClassVar[str] = "browser_click"
    description: ClassVar[str] = (
        "Click a link or button by ref. Clicking a submit button sends that form."
    )
    args_model = RefArgs

    async def assess(self, args: RefArgs, ctx: ToolContext) -> Assessment:
        session = await ctx.browser.session()
        snapshot = session.last_snapshot
        element = snapshot.element(args.ref) if snapshot else None
        if snapshot is None or element is None:
            return Assessment(risk=RiskLevel.READ, description=f"click {args.ref}")
        form = snapshot.form_of(element)
        if not (element.submits and form and form.method == "POST"):
            return Assessment(risk=RiskLevel.READ, description=f"click {element.label!r}")
        system = ctx.company.system_for_url(form.action)
        # Sign-in forms carry credentials, not business data; they change nothing.
        risk = RiskLevel.READ if form.has_password else RiskLevel.WRITE
        system_name = system.name if system else None
        ensure_writable(ctx, system_name, risk)
        return Assessment(
            risk=risk,
            system=system_name,
            payload={**form.fields, "_method": "POST", "_action": urlparse(form.action).path},
            description=f"submit form via {element.label!r} to {form.action}",
        )

    async def act(self, args: RefArgs, ctx: ToolContext) -> Observation:
        session = await _session_for(ctx)
        locator = await session.require(args.ref)
        await locator.click()
        return await observe(session, ctx, "click")


class FillArgs(BaseModel):
    ref: str = Field(description="Input or textarea ref")
    value: str | None = Field(default=None, description="Text to type")
    secret: str | None = Field(
        default=None,
        description="Credential reference instead of a value, e.g. 'internal_erp.password'",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> "FillArgs":
        if (self.value is None) == (self.secret is None):
            raise ValueError("Provide exactly one of 'value' or 'secret'")
        return self


class BrowserFill(BrowserTool[FillArgs]):
    name: ClassVar[str] = "browser_fill"
    description: ClassVar[str] = (
        "Replace the text in an input. Use 'secret' for usernames/passwords; "
        "never type credentials yourself."
    )
    args_model = FillArgs

    async def act(self, args: FillArgs, ctx: ToolContext) -> Observation:
        session = await _session_for(ctx)
        locator = await session.require(args.ref)
        text = ctx.credentials.resolve(args.secret) if args.secret else (args.value or "")
        await locator.fill(text)
        return await observe(session, ctx, "fill", screenshot=False)


class SelectArgs(BaseModel):
    ref: str = Field(description="Select element ref")
    option: str = Field(description="Visible option text to choose")


class BrowserSelect(BrowserTool[SelectArgs]):
    name: ClassVar[str] = "browser_select"
    description: ClassVar[str] = "Choose an option in a dropdown by its visible text."
    args_model = SelectArgs

    async def act(self, args: SelectArgs, ctx: ToolContext) -> Observation:
        session = await _session_for(ctx)
        locator = await session.require(args.ref)
        try:
            await locator.select_option(label=args.option)
        except PlaywrightTimeoutError as exc:
            raise ToolInputError(f"Option {args.option!r} not found in {args.ref}") from exc
        return await observe(session, ctx, "select", screenshot=False)


class FieldValue(BaseModel):
    ref: str = Field(description="Field ref from the latest observation")
    value: str | None = Field(default=None, description="Text, or visible option text for a select")
    secret: str | None = Field(default=None, description="Credential reference instead of a value")

    @model_validator(mode="after")
    def _exactly_one(self) -> "FieldValue":
        if (self.value is None) == (self.secret is None):
            raise ValueError("Each field needs exactly one of 'value' or 'secret'")
        return self


class FillFormArgs(BaseModel):
    fields: list[FieldValue] = Field(min_length=1, description="Every field to set, in order")


class BrowserFillForm(BrowserTool[FillFormArgs]):
    name: ClassVar[str] = "browser_fill_form"
    description: ClassVar[str] = (
        "Fill several fields in one action (text inputs, textareas and dropdowns by visible "
        "option text). Prefer this over one-field-at-a-time filling. Does not submit."
    )
    args_model = FillFormArgs

    async def act(self, args: FillFormArgs, ctx: ToolContext) -> Observation:
        session = await _session_for(ctx)
        snapshot = session.last_snapshot
        for field in args.fields:
            locator = await session.require(field.ref)
            text = ctx.credentials.resolve(field.secret) if field.secret else (field.value or "")
            element = snapshot.element(field.ref) if snapshot else None
            if element is not None and element.tag == "select":
                try:
                    await locator.select_option(label=text)
                except PlaywrightTimeoutError as exc:
                    raise ToolInputError(f"Option {text!r} not found in {field.ref}") from exc
            else:
                await locator.fill(text)
        return await observe(session, ctx, "fill_form", screenshot=False)


class BrowserDownload(BrowserTool[RefArgs]):
    name: ClassVar[str] = "browser_download"
    description: ClassVar[str] = (
        "Click a link that downloads a file; the file is saved to the run workspace."
    )
    args_model = RefArgs

    async def act(self, args: RefArgs, ctx: ToolContext) -> Observation:
        session = await _session_for(ctx)
        locator = await session.require(args.ref)
        async with session.page.expect_download() as download_info:
            await locator.click()
        download = await download_info.value
        target = ctx.workspace.resolve(f"downloads/{download.suggested_filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(target)
        relative = ctx.workspace.relative(target)
        content = await asyncio.to_thread(target.read_bytes)
        artifact = await ctx.evidence.save(
            ctx.run_id,
            target.name,
            content,
            EvidenceKind.FILE,
            f"Downloaded from {download.url}",
        )
        return Observation(
            ok=True,
            summary=f"Downloaded '{relative}' ({len(content)} bytes). Use file_read to read it.",
            data={"path": relative, "source_url": download.url},
            artifacts=[artifact],
            location=session.page.url,
        )


class NoArgs(BaseModel):
    pass


class BrowserSnapshot(BrowserTool[NoArgs]):
    name: ClassVar[str] = "browser_snapshot"
    description: ClassVar[str] = "Re-observe the current page without acting (e.g. after waiting)."
    args_model = NoArgs

    async def act(self, args: NoArgs, ctx: ToolContext) -> Observation:  # noqa: ARG002
        session = await ctx.browser.session()
        return await observe(session, ctx, "snapshot")


def browser_tools() -> list[Tool[Any]]:
    return [
        BrowserOpen(),
        BrowserClick(),
        BrowserFill(),
        BrowserFillForm(),
        BrowserSelect(),
        BrowserDownload(),
        BrowserSnapshot(),
    ]
