"""浏览器生命周期：进程内单 Chromium，任务级 BrowserContext 隔离。"""

from __future__ import annotations

import asyncio
from typing import Any

from price_platform.common.logging import get_logger
from price_platform.common.metrics import BROWSER_RESTARTS
from price_platform.common.settings import Settings

log = get_logger("worker")


class BrowserManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright: Any = None
        self._browser: Any = None
        self._lock = asyncio.Lock()

    @property
    def browser(self) -> Any:
        return self._browser

    async def start(self) -> None:
        from playwright.async_api import async_playwright  # 延迟导入：API 镜像不装 playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._launch()
        log.info("browser_started", version=self._browser.version)

    async def _launch(self) -> Any:
        return await self._playwright.chromium.launch(
            headless=self.settings.browser_headless,
            channel=self.settings.browser_channel or None,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-background-networking",
            ],
        )

    async def ensure(self) -> Any:
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                log.warning("browser_restarting")
                BROWSER_RESTARTS.inc()
                if self._playwright is None:
                    await self.start()
                else:
                    self._browser = await self._launch()
            return self._browser

    async def close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None

