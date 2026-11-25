"""站点适配器：打开页面 → 等元素 → 取 HTML → 解析价格。

真实执行由 Playwright 驱动；解析用 selectolax，两者解耦，便于单测。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from price_platform.common.errors import (
    NetworkError,
    NotFoundError,
    ParseError,
    ScrapeError,
    TimeoutError_,
    http_error,
)
from price_platform.common.settings import Settings
from price_platform.worker.selectors import SelectorSet

PRICE_RE = re.compile(r"\d+(?:\.\d{1,2})?")


@dataclass(slots=True)
class PriceSnapshot:
    price: Decimal
    currency: str = "CNY"
    in_stock: bool | None = None
    http_status: int = 200
    raw: dict[str, Any] = field(default_factory=dict)


def parse_price_text(text: str, strip_chars: str) -> Decimal:
    cleaned = text
    for ch in strip_chars:
        if ch:
            cleaned = cleaned.replace(ch, "")
    match = PRICE_RE.search(cleaned.replace(",", ""))
    if not match:
        raise ParseError(f"no price in text: {text!r}")
    try:
        value = Decimal(match.group(0))
    except InvalidOperation as exc:
        raise ParseError(f"bad price: {text!r}") from exc
    if not (Decimal("0") < value < Decimal("1000000")):
        raise ParseError(f"price out of range: {value}")
    return value.quantize(Decimal("0.01"))


def _first_text(tree: HTMLParser, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        node = tree.css_first(selector)
        if node is not None:
            text = (node.text() or "").strip()
            if text:
                return text
    return None


def _json_ld_price(tree: HTMLParser) -> Decimal | None:
    for node in tree.css("script[type='application/ld+json']"):
        try:
            data = json.loads(node.text() or "{}")
        except json.JSONDecodeError:
            continue
        offers = data.get("offers") if isinstance(data, dict) else None
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if isinstance(offers, dict) and offers.get("price") is not None:
            try:
                return Decimal(str(offers["price"])).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                continue
    return None


class BaseAdapter(ABC):
    name: str = "base"
    needs_browser: bool = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve_url(self, product: dict[str, Any], source: dict[str, Any]) -> str:
        url = str(product.get("url") or "")
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return urljoin(str(source.get("base_url") or ""), url)

    async def collect(
        self,
        browser: Any,
        product: dict[str, Any],
        source: dict[str, Any],
        selectors: SelectorSet,
    ) -> PriceSnapshot:
        url = self.resolve_url(product, source)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 price-platform/1.0"
            ),
            ignore_https_errors=True,
        )
        page = await context.new_page()
        try:
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:  # noqa: BLE001 - Playwright 异常统一分类
                raise _classify_navigation(exc, url) from exc

            status = response.status if response is not None else 0
            if status >= 400:
                raise http_error(status, f"GET {url} -> {status}")

            try:
                await page.wait_for_selector(selectors.price[0], timeout=15_000)
            except Exception as exc:  # noqa: BLE001
                raise ParseError(f"price selector not found: {selectors.price[0]}") from exc

            html = await page.content()
            title = (await page.title()) if page else ""
        finally:
            try:
                await context.close()
            except Exception:  # noqa: BLE001
                pass

        snapshot = self.parse(html, selectors, http_status=status)
        snapshot.raw.setdefault("url", url)
        snapshot.raw.setdefault("page_title", title)
        return snapshot

    def parse(self, html: str, selectors: SelectorSet, *, http_status: int = 200) -> PriceSnapshot:
        tree = HTMLParser(html)

        price_text = _first_text(tree, selectors.price)
        price: Decimal | None = None
        if price_text:
            price = parse_price_text(price_text, selectors.strip_chars)
        else:
            price = _json_ld_price(tree)
            if price is None:
                raise ParseError(f"no price matched selectors: {selectors.price}")

        title = _first_text(tree, selectors.title) or ""
        stock_text = _first_text(tree, selectors.stock)
        in_stock: bool | None = None
        if stock_text:
            if selectors.out_of_stock_text in stock_text:
                in_stock = False
            elif selectors.in_stock_text in stock_text:
                in_stock = True

        return PriceSnapshot(
            price=price,
            currency=selectors.currency,
            in_stock=in_stock,
            http_status=http_status,
            raw={
                "price_text": price_text,
                "title": title,
                "stock_text": stock_text,
                "selector_version": selectors.version,
            },
        )


class GenericAdapter(BaseAdapter):
    name = "generic"


class MockAdapter(GenericAdapter):
    name = "mock"

    def resolve_url(self, product: dict[str, Any], source: dict[str, Any]) -> str:
        url = str(product.get("url") or "")
        if url.startswith("http"):
            return url
        base = self.settings.mock_shop_url.rstrip("/")
        return f"{base}/{url.lstrip('/')}"


class HttpAdapter(BaseAdapter):
    """不启动浏览器的轻量适配器（用于 Mock JSON 接口或纯静态页）。"""

    name = "http"

    async def collect(self, browser, product, source, selectors) -> PriceSnapshot:  # type: ignore[override]
        raise NotImplementedError("http adapter is reserved for future use")


def _classify_navigation(exc: BaseException, url: str) -> ScrapeError:
    text = f"{type(exc).__name__} {exc}".lower()
    if "timeout" in text:
        return TimeoutError_(f"goto timeout: {url}")
    if "net::err_aborted" in text or "err_aborted" in text:
        return NetworkError(f"navigation aborted: {url}")
    if "err_name_not_resolved" in text or "err_connection" in text or "err_network" in text:
        return NetworkError(f"network error: {url}")
    if "404" in text:
        return NotFoundError(f"not found: {url}")
    return NetworkError(f"navigation failed: {url} ({type(exc).__name__})")


