"""HTTP 适配器：不启动浏览器，直接用 httpx 取 HTML。

适用于服务端渲染页面（如 Mock 商城）；JS 渲染站点仍需 Playwright 适配器。
好处是 Worker 镜像可以不含 Chromium，资源占用低、吞吐高。
"""

from __future__ import annotations

from typing import Any

import httpx

from price_platform.common.errors import NetworkError, TimeoutError_, http_error
from price_platform.worker.adapters.base import BaseAdapter, PriceSnapshot
from price_platform.worker.selectors import SelectorSet


class HttpAdapter(BaseAdapter):
    name = "http"
    needs_browser = False

    async def collect(
        self,
        browser: Any,
        product: dict[str, Any],
        source: dict[str, Any],
        selectors: SelectorSet,
    ) -> PriceSnapshot:
        url = self.resolve_url(product, source)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 price-platform/1.0"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise TimeoutError_(f"timeout: {url}") from exc
        except httpx.HTTPError as exc:
            raise NetworkError(f"http error: {url} ({exc})") from exc

        if response.status_code >= 400:
            raise http_error(response.status_code, f"GET {url} -> {response.status_code}")

        snapshot = self.parse(response.text, selectors, http_status=response.status_code)
        snapshot.raw.setdefault("url", url)
        snapshot.raw.setdefault("mode", "http")
        return snapshot

