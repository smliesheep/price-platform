"""商品创建时的轻量预览：不启动浏览器，用 httpx + selectolax 取标题/价格。"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlparse

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from price_platform.common.errors import ParseError
from price_platform.worker.adapters.base import parse_price_text
from price_platform.worker.selectors import SelectorSet


def guess_external_id(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    return tail or urlparse(url).netloc.replace(".", "-")


async def preview(url: str, selectors: SelectorSet, timeout: float = 6.0) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "price-platform/1.0 preview"})
    response.raise_for_status()
    tree = HTMLParser(response.text)

    title = None
    for selector in selectors.title:
        node = tree.css_first(selector)
        if node and node.text(strip=True):
            title = node.text(strip=True)
            break

    price: Decimal | None = None
    for selector in selectors.price:
        node = tree.css_first(selector)
        if node and node.text(strip=True):
            try:
                price = parse_price_text(node.text(), selectors.strip_chars)
            except ParseError:
                price = None
            break

    return {"title": title, "price": price, "http_status": response.status_code}

