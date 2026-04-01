"""
Anti-Fake Verification Service
"""
from typing import Optional
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


class AntiFakeService:
    """
    防伪查询业务逻辑层。

    约束:
    1. verify_code() 先查 Redis 缓存，未命中再查数据库
    2. 查询成功后异步更新 query_count
    3. 首次查询记录 verified_by 和 verified_at
    4. 查询频率超限抛出 RateLimitExceeded
    5. 所有数据库操作通过 Repository 完成
    """

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    async def verify_code(self, code: str, user_id: int) -> dict:
        # 1. 频率限制检查
        await self._check_rate_limit(user_id)

        # 2. 查 Redis 缓存
        cached = await self._get_cached_result(code)
        if cached:
            await self._async_increment_count(code)
            return cached

        # 3. 查数据库
        # TODO: Implement with AntiFakeRepository
        # result = await self.repo.find_by_code(code)

        # 4. 写缓存
        # 5. 更新查询计数
        # 6. 返回结果
        raise NotImplementedError

    async def get_history(self, user_id: int, page: int, size: int) -> dict:
        raise NotImplementedError

    async def _check_rate_limit(self, user_id: int) -> None:
        key = f"af:rate:{user_id}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 60)
        if count > settings.ANTI_FAKE_RATE_LIMIT_USER:
            ttl = await self.redis.ttl(key)
            raise RateLimitExceeded(f"查询过于频繁，请 {ttl} 秒后重试")

    async def _get_cached_result(self, code: str) -> Optional[dict]:
        import json
        key = f"af:code:{code}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def _async_increment_count(self, code: str) -> None:
        # TODO: Send to Celery task for async DB update
        pass


class RateLimitExceeded(Exception):
    pass
