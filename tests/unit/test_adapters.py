from __future__ import annotations

from decimal import Decimal

import pytest

from price_platform.common.errors import ParseError
from price_platform.common.settings import settings
from price_platform.worker.adapters.base import GenericAdapter, parse_price_text
from price_platform.worker.selectors import SelectorSet

HTML_OK = """
<html><head><title>测试商品</title></head><body>
  <h1 class="product-title">Mock 无线降噪耳机 Pro</h1>
  <div class="product-price"><span class="amount">249.00</span></div>
  <div class="stock-status in-stock">现货</div>
</body></html>
"""

HTML_OUT_OF_STOCK = """
<html><body>
  <h1 class="product-title">Mock 耳机</h1>
  <div class="product-price"><span class="amount">199.00</span></div>
  <div class="stock-status out-of-stock">缺货</div>
</body></html>
"""

HTML_JSONLD = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org/","@type":"Product","name":"x",
 "offers":{"@type":"Offer","price":"88.50","priceCurrency":"CNY"}}
</script></head><body><h1 class="product-title">x</h1></body></html>
"""

HTML_BAD_PRICE = """
<html><body><h1 class="product-title">x</h1>
<div class="product-price"><span class="amount">¥--</span></div></body></html>
"""

SELECTORS = SelectorSet(
    version="v1",
    timeout_sec=300,
    title=("h1.product-title",),
    price=(".product-price .amount",),
    stock=(".stock-status",),
    currency="CNY",
    in_stock_text="现货",
    out_of_stock_text="缺货",
    strip_chars="¥￥, ",
)


@pytest.fixture()
def adapter() -> GenericAdapter:
    return GenericAdapter(settings)


def test_parse_normal(adapter: GenericAdapter) -> None:
    snapshot = adapter.parse(HTML_OK, SELECTORS)
    assert snapshot.price == Decimal("249.00")
    assert snapshot.in_stock is True
    assert snapshot.raw["title"] == "Mock 无线降噪耳机 Pro"


def test_parse_out_of_stock(adapter: GenericAdapter) -> None:
    snapshot = adapter.parse(HTML_OUT_OF_STOCK, SELECTORS)
    assert snapshot.in_stock is False


def test_parse_falls_back_to_json_ld(adapter: GenericAdapter) -> None:
    snapshot = adapter.parse(HTML_JSONLD, SELECTORS)
    assert snapshot.price == Decimal("88.50")


def test_parse_bad_price(adapter: GenericAdapter) -> None:
    with pytest.raises(ParseError):
        adapter.parse(HTML_BAD_PRICE, SELECTORS)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("249.00", Decimal("249.00")),
        ("¥1,299.00", Decimal("1299.00")),
        ("  ￥ 88.5 ", Decimal("88.50")),
    ],
)
def test_parse_price_text(text: str, expected: Decimal) -> None:
    assert parse_price_text(text, "¥￥, ") == expected


@pytest.mark.parametrize("text", ["¥--", "0.00", "10000000", ""])
def test_parse_price_text_invalid(text: str) -> None:
    with pytest.raises(ParseError):
        parse_price_text(text, "¥￥, ")
