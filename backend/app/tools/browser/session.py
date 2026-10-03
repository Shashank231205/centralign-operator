"""Playwright lifecycle: one Chromium per worker process, one isolated context per run.

Network requests to hosts outside the company allowlist are aborted at the browser layer, so
even a link inside a hostile page cannot make the operator leave approved systems.
"""

import asyncio
import logging
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Request,
    Response,
    Route,
    async_playwright,
)

from app.core.config import BrowserSettings
from app.core.errors import ToolInputError
from app.tools.browser.snapshot import SNAPSHOT_SCRIPT, PageSnapshot

logger = logging.getLogger(__name__)

_LOCAL_SCHEMES = ("about", "data", "blob")
_SETTLE_STABLE_POLLS = 2


class BrowserSession:
    def __init__(self, context: BrowserContext, page: Page, settings: BrowserSettings) -> None:
        self.context = context
        self.page = page
        self._settings = settings
        self.last_snapshot: PageSnapshot | None = None
        self._main_status: int | None = None
        page.on("response", self._track_main_frame)
        page.set_default_timeout(settings.navigation_timeout_seconds * 1000)

    def _track_main_frame(self, response: Response) -> None:
        if response.request.is_navigation_request() and response.frame == self.page.main_frame:
            self._main_status = response.status

    def reset_status(self) -> None:
        self._main_status = None

    def locator(self, ref: str) -> Locator:
        return self.page.locator(f'[data-op-ref="{ref}"]')

    async def require(self, ref: str) -> Locator:
        locator = self.locator(ref)
        if await locator.count() == 0:
            raise ToolInputError(
                f"Element {ref} is not on the current page; use refs from the latest observation"
            )
        return locator

    async def snapshot(self) -> PageSnapshot:
        """Wait for the page to settle (element count stable), then capture it."""
        deadline = asyncio.get_running_loop().time() + self._settings.settle_timeout_seconds
        previous, stable = -1, 0
        snapshot = await self._capture()
        while asyncio.get_running_loop().time() < deadline:
            count = len(snapshot.elements)
            stable = stable + 1 if count == previous and count > 0 else 0
            if stable >= _SETTLE_STABLE_POLLS:
                break
            previous = count
            await asyncio.sleep(self._settings.settle_interval_ms / 1000)
            snapshot = await self._capture()
        snapshot.status = self._main_status
        self.last_snapshot = snapshot
        return snapshot

    async def _capture(self) -> PageSnapshot:
        await self.page.wait_for_load_state("domcontentloaded")
        raw = await self.page.evaluate(SNAPSHOT_SCRIPT, self._settings.max_snapshot_elements)
        return PageSnapshot.model_validate(raw)

    async def screenshot(self) -> bytes:
        return await self.page.screenshot(full_page=True)

    async def close(self) -> None:
        await self.context.close()


class BrowserManager:
    def __init__(self, settings: BrowserSettings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._settings.headless)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_session(self, allowed_hosts: set[str]) -> BrowserSession:
        if self._browser is None:
            raise RuntimeError("BrowserManager.start() must be called first")
        context = await self._browser.new_context(
            viewport={
                "width": self._settings.viewport_width,
                "height": self._settings.viewport_height,
            },
            accept_downloads=True,
        )

        async def enforce_allowlist(route: Route, request: Request) -> None:
            parsed = urlparse(request.url)
            if parsed.scheme in _LOCAL_SCHEMES or parsed.netloc in allowed_hosts:
                await route.continue_()
                return
            logger.warning("blocked request to non-allowlisted host", extra={"host": parsed.netloc})
            await route.abort("blockedbyclient")

        await context.route("**/*", enforce_allowlist)
        return BrowserSession(context, await context.new_page(), self._settings)


class RunBrowser:
    """Lazily opens the run's browser session on first use and closes it at the end."""

    def __init__(self, manager: BrowserManager, allowed_hosts: set[str]) -> None:
        self._manager = manager
        self._allowed_hosts = allowed_hosts
        self._session: BrowserSession | None = None

    async def session(self) -> BrowserSession:
        if self._session is None:
            self._session = await self._manager.new_session(self._allowed_hosts)
        return self._session

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
