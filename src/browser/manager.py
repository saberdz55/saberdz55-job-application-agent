"""Playwright lifecycle and encrypted authenticated-state persistence."""

import json
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from src.utils.config import encrypt, decrypt
from src.utils.logger import get_logger

logger = get_logger("browser")


class BrowserManager:
    """Own one isolated browser context and optionally persist its auth state."""

    def __init__(self, state_path: Optional[Path] = None, headless: bool = False):
        self.state_path = state_path
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "BrowserManager":
        self._playwright = await async_playwright().start()
        # Do not spoof browser fingerprints or disable automation controls.
        # Reliability comes from deterministic waits and verified state, not evasion.
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        storage_state = self._load_state()
        context_kwargs = {
            "accept_downloads": False,
            "viewport": {"width": 1440, "height": 900},
        }
        if storage_state:
            logger.info("Loading saved encrypted browser session state.")
            context_kwargs["storage_state"] = storage_state
        else:
            logger.info("No saved session — starting a fresh browser context.")
        self._context = await self._browser.new_context(**context_kwargs)
        return self

    async def __aexit__(self, *args):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("BrowserManager context is not initialized")
        page = await self._context.new_page()
        page.set_default_timeout(15_000)
        page.set_default_navigation_timeout(60_000)
        return page

    async def save_state(self) -> None:
        if not self._context or not self.state_path:
            return
        state = await self._context.storage_state()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_bytes(encrypt(json.dumps(state, ensure_ascii=False)))
        logger.info("Encrypted browser session state updated.")

    def _load_state(self) -> Optional[dict]:
        if not self.state_path or not self.state_path.exists():
            return None
        try:
            return json.loads(decrypt(self.state_path.read_bytes()))
        except Exception as exc:
            raise RuntimeError(
                f"Unable to decrypt browser session {self.state_path.name}. "
                "Check ENCRYPTION_KEY instead of silently starting a new account."
            ) from exc

    def state_exists(self) -> bool:
        return bool(self.state_path and self.state_path.exists())
