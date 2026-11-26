"""用本机 Edge 截取前端页面，产出 README 用的截图。

前置：集群/本地栈已启动，API 可访问。
用法：python scripts/capture_screens.py --base http://127.0.0.1:8080 --out docs/img
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

TOKEN_KEY = "price_monitor_token"
USERNAME_KEY = "price_monitor_username"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--out", default="docs/img")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    response = httpx.post(
        f"{args.base}/api/v1/auth/login",
        json={"username": args.user, "password": args.password},
        timeout=15,
    )
    response.raise_for_status()
    token = response.json()["data"]["access_token"]

    from playwright.sync_api import sync_playwright

    pages = [
        ("login", "/login", False),
        ("overview", "/overview", True),
        ("products", "/products", True),
        ("product-detail", "/products/1", True),
        ("runs", "/runs", True),
        ("system", "/system", True),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = context.new_page()

        for name, path, need_auth in pages:
            page.goto(f"{args.base}/login", wait_until="domcontentloaded")
            if need_auth:
                page.evaluate(
                    "([k, v, u]) => { localStorage.setItem(k, v); localStorage.setItem(u[0], u[1]); }",
                    [TOKEN_KEY, token, [USERNAME_KEY, args.user]],
                )
            else:
                page.evaluate("() => localStorage.clear()")
            page.goto(f"{args.base}{path}", wait_until="networkidle")
            time.sleep(2.5)
            target = out / f"{name}.png"
            page.screenshot(path=str(target), full_page=False)
            print(f"saved {target}")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
