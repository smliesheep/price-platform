"""选择器集合：从 ConfigMap 挂载目录加载，按 (adapter, version) 取用，支持热更新。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class SelectorSet:
    version: str
    timeout_sec: int
    title: tuple[str, ...]
    price: tuple[str, ...]
    stock: tuple[str, ...]
    currency: str
    in_stock_text: str
    out_of_stock_text: str
    strip_chars: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], version: str) -> "SelectorSet":
        def many(value: Any) -> tuple[str, ...]:
            if value is None:
                return ()
            if isinstance(value, str):
                return tuple(part.strip() for part in value.split(",") if part.strip())
            return tuple(str(x) for x in value)

        return cls(
            version=str(data.get("version", version)),
            timeout_sec=int(data.get("timeout_sec", 300)),
            title=many(data.get("title")),
            price=many(data.get("price")),
            stock=many(data.get("stock")),
            currency=str(data.get("currency", "CNY")),
            in_stock_text=str(data.get("in_stock_text", "现货")),
            out_of_stock_text=str(data.get("out_of_stock_text", "缺货")),
            strip_chars=str(data.get("strip_chars", "¥￥, ")),
        )


_DEFAULT = SelectorSet(
    version="v1",
    timeout_sec=300,
    title=("h1.product-title", "h1"),
    price=(".product-price .amount", ".price"),
    stock=(".stock-status",),
    currency="CNY",
    in_stock_text="现货",
    out_of_stock_text="缺货",
    strip_chars="¥￥, ",
)


@dataclass
class SelectorStore:
    root: str
    _cache: dict[tuple[str, str], SelectorSet] = field(default_factory=dict)
    _mtime: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _scan(self) -> float:
        base = Path(self.root)
        if not base.exists():
            return 0.0
        latest = 0.0
        for path in base.rglob("*.yaml"):
            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
        return latest

    def _reload_if_changed(self) -> None:
        mtime = self._scan()
        if mtime <= self._mtime and self._cache:
            return
        with self._lock:
            if mtime <= self._mtime and self._cache:
                return
            cache: dict[tuple[str, str], SelectorSet] = {}
            base = Path(self.root)
            if base.exists():
                for path in base.rglob("*.yaml"):
                    try:
                        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    except Exception:  # noqa: BLE001 - 坏文件不能拖垮 Worker
                        continue
                    adapter = path.parent.name
                    version = path.stem
                    if adapter in ("selectors", "configs", path.parent.name) and "-" in version:
                        # ConfigMap 平铺挂载时文件名形如 mock-v1.yaml
                        adapter, _, version = version.partition("-")
                    cache[(adapter, version)] = SelectorSet.from_dict(data, version)
            self._cache = cache
            self._mtime = mtime

    def get(self, adapter: str, version: str | None) -> SelectorSet:
        self._reload_if_changed()
        version = version or "v1"
        return self._cache.get((adapter, version)) or self._cache.get((adapter, "v1")) or _DEFAULT


def now() -> float:
    return time.time()

