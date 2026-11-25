"""Mock 商城：演示与压测用的目标站点。

- 20 个商品，价格随时间波动，可注入 5xx / 延迟 / 404
- 页面结构对应 configs/selectors/mock/v1.yaml
- /admin/config 供演示时现场切换故障，方便讲解重试与 DLQ
"""

from __future__ import annotations

import asyncio
import math
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="mock-shop", version="1.0.0")

START_TS = time.time()


@dataclass
class FaultConfig:
    fail_rate: float = float(os.getenv("FAIL_RATE", "0"))
    delay_ms: int = int(os.getenv("DELAY_MS", "0"))
    mode: str = os.getenv("FAIL_MODE", "none")  # none | 500 | 404 | timeout
    out_of_stock_ids: set[int] = field(default_factory=set)


fault = FaultConfig()


CATALOG: list[dict] = [
    {"id": 1001, "title": "Mock 无线降噪耳机 Pro", "category": "耳机", "base": 249.00},
    {"id": 1002, "title": "Mock 机械键盘 87 键", "category": "键盘", "base": 399.00},
    {"id": 1003, "title": "Mock 4K 显示器 27 英寸", "category": "显示器", "base": 1499.00},
    {"id": 1004, "title": "Mock 便携充电宝 20000mAh", "category": "配件", "base": 129.00},
    {"id": 1005, "title": "Mock 智能手环 5 代", "category": "穿戴", "base": 199.00},
    {"id": 1006, "title": "Mock 空气净化器 Mini", "category": "家电", "base": 899.00},
    {"id": 1007, "title": "Mock 电动牙刷 S1", "category": "个护", "base": 159.00},
    {"id": 1008, "title": "Mock 蓝牙音箱 X2", "category": "音频", "base": 329.00},
    {"id": 1009, "title": "Mock 路由器 AX3000", "category": "网络", "base": 459.00},
    {"id": 1010, "title": "Mock 移动固态硬盘 1TB", "category": "存储", "base": 599.00},
    {"id": 1011, "title": "Mock 摄像头 2K", "category": "配件", "base": 219.00},
    {"id": 1012, "title": "Mock 咖啡机 半自动", "category": "家电", "base": 1299.00},
    {"id": 1013, "title": "Mock 台灯 护眼版", "category": "家居", "base": 189.00},
    {"id": 1014, "title": "Mock 电纸书 7 英寸", "category": "数码", "base": 799.00},
    {"id": 1015, "title": "Mock 人体工学椅", "category": "家居", "base": 1599.00},
    {"id": 1016, "title": "Mock 桌面麦克风", "category": "音频", "base": 349.00},
    {"id": 1017, "title": "Mock 智能插座 4 件套", "category": "家居", "base": 99.00},
    {"id": 1018, "title": "Mock 游戏手柄 无线", "category": "娱乐", "base": 279.00},
    {"id": 1019, "title": "Mock 迷你主机 N100", "category": "数码", "base": 1099.00},
    {"id": 1020, "title": "Mock 降噪耳塞", "category": "耳机", "base": 79.00},
]
BY_ID = {p["id"]: p for p in CATALOG}


def current_price(product: dict) -> float:
    """价格随时间波动：±8%，周期约 20 分钟，20 个商品相位错开。"""
    minutes = (time.time() - START_TS) / 60.0
    factor = 1 + 0.08 * math.sin((minutes + product["id"] * 1.7) / 3.2)
    return round(product["base"] * factor, 2)


def in_stock(product: dict) -> bool:
    return product["id"] not in fault.out_of_stock_ids


async def apply_fault(request: Request) -> None:
    """在响应前模拟网络/服务故障。"""
    if fault.delay_ms > 0:
        await asyncio.sleep(fault.delay_ms / 1000.0)
    if fault.mode == "500":
        raise HTTPException(status_code=500, detail="injected 500")
    if fault.mode == "404":
        raise HTTPException(status_code=404, detail="injected 404")
    if fault.mode == "timeout":
        await asyncio.sleep(3600)
    if fault.fail_rate > 0 and random.random() < fault.fail_rate:
        raise HTTPException(status_code=500, detail="random 500")


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/api/products")
async def list_products() -> JSONResponse:
    items = [
        {
            "id": p["id"],
            "title": p["title"],
            "category": p["category"],
            "price": current_price(p),
            "in_stock": in_stock(p),
            "url": f"/p/{p['id']}",
        }
        for p in CATALOG
    ]
    return JSONResponse({"items": items, "total": len(items)})


@app.get("/api/price/{pid}")
async def price(pid: int) -> JSONResponse:
    product = BY_ID.get(pid)
    if not product:
        raise HTTPException(status_code=404, detail="not found")
    return JSONResponse(
        {
            "id": pid,
            "price": current_price(product),
            "in_stock": in_stock(product),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )


@app.get("/p/{pid}", response_class=HTMLResponse)
async def product_page(pid: int, request: Request) -> HTMLResponse:
    await apply_fault(request)
    product = BY_ID.get(pid)
    if not product:
        raise HTTPException(status_code=404, detail="product not found")

    price_value = current_price(product)
    stock = in_stock(product)
    stock_text = "现货" if stock else "缺货"
    stock_class = "stock-status in-stock" if stock else "stock-status out-of-stock"
    ld_json = (
        '{"@context":"https://schema.org/","@type":"Product",'
        f'"name":"{product["title"]}","offers":{{"@type":"Offer","price":"{price_value}",'
        '"priceCurrency":"CNY","availability":"https://schema.org/'
        + ("InStock" if stock else "OutOfStock")
        + '"}},"sku":"' + str(pid) + '"}'
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{product["title"]} - Mock 商城</title>
<script type="application/ld+json">{ld_json}</script>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 40px; color: #111; }}
  .product-title {{ font-size: 24px; margin-bottom: 8px; }}
  .product-price {{ color: #e11d48; font-size: 28px; font-weight: 700; }}
  .product-price .amount::before {{ content: "¥"; font-size: 18px; }}
  .stock-status {{ margin-top: 8px; font-size: 14px; }}
  .in-stock {{ color: #16a34a; }}
  .out-of-stock {{ color: #9ca3af; }}
  .meta {{ margin-top: 24px; color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
  <h1 class="product-title">{product["title"]}</h1>
  <div class="product-price"><span class="amount">{price_value:.2f}</span></div>
  <div class="{stock_class}">{stock_text}</div>
  <div class="meta">商品编号 {pid} · 分类 {product["category"]} · 数据为演示用途</div>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/admin/config")
async def get_config() -> dict:
    return {
        "fail_rate": fault.fail_rate,
        "delay_ms": fault.delay_ms,
        "mode": fault.mode,
        "out_of_stock_ids": sorted(fault.out_of_stock_ids),
    }


@app.post("/admin/config")
async def set_config(payload: dict) -> dict:
    if "fail_rate" in payload:
        fault.fail_rate = max(0.0, min(1.0, float(payload["fail_rate"])))
    if "delay_ms" in payload:
        fault.delay_ms = max(0, int(payload["delay_ms"]))
    if "mode" in payload:
        if payload["mode"] not in {"none", "500", "404", "timeout"}:
            raise HTTPException(status_code=400, detail="bad mode")
        fault.mode = payload["mode"]
    if "out_of_stock_ids" in payload:
        fault.out_of_stock_ids = {int(x) for x in payload["out_of_stock_ids"]}
    return await get_config()


@app.post("/admin/reset")
async def reset() -> dict:
    fault.fail_rate = 0.0
    fault.delay_ms = 0
    fault.mode = "none"
    fault.out_of_stock_ids = set()
    return {"ok": True}
