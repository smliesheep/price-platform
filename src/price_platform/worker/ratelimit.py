"""域名级限频：Redis 固定窗口计数（原子 Lua），超限短暂退避。"""

from __future__ import annotations

import asyncio
import random
import time

from redis.asyncio import Redis

from price_platform.common.errors import BlockedError

_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return n
"""


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def acquire(self, source_id: int, limit_per_min: int) -> None:
        if limit_per_min <= 0:
            return
        minute = int(time.time() // 60)
        key = f"rl:{source_id}:{minute}"
        waited = 0.0
        while waited < 3.0:
            used = int(await self.redis.eval(_LUA, 1, key, limit_per_min, 120))
            if used <= limit_per_min:
                return
            pause = 0.5 + random.random() * 0.5
            await asyncio.sleep(pause)
            waited += pause
        raise BlockedError(f"rate limit exceeded for source {source_id}")

    async def humanize(self) -> None:
        await asyncio.sleep(random.uniform(0.3, 1.2))
