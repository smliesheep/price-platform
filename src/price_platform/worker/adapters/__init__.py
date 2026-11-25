"""适配器注册表。"""

from __future__ import annotations

from price_platform.common.settings import Settings
from price_platform.worker.adapters.base import BaseAdapter, GenericAdapter, MockAdapter


def build_adapters(settings: Settings) -> dict[str, BaseAdapter]:
    adapters: list[BaseAdapter] = [MockAdapter(settings), GenericAdapter(settings)]
    return {adapter.name: adapter for adapter in adapters}
