"""截取 Grafana 看板，用于 README 展示。

前置：kubectl -n observability port-forward svc/grafana 13000:3000
用法：python scripts/capture_grafana.py --url http://127.0.0.1:13000 --out docs/img/grafana.png
"""

from __future__ import annotations

import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:13000")
    parser.add_argument("--out", default="docs/img/grafana.png")
    parser.add_argument("--uid", default="price-platform")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=2).new_page()
        page.goto(f"{args.url}/d/{args.uid}?orgId=1&kiosk", wait_until="domcontentloaded", timeout=60_000)
        time.sleep(12)
        page.screenshot(path=args.out, full_page=False)
        print(f"saved {args.out}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

