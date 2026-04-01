"""
Anti-Fake Verification Service
功能点:
  F1 - 防伪码格式校验 & 输入安全
  F2 - 防伪码查询核心（缓存 → DB → 状态机 + 缓存穿透防护）
  F3 - 查询频率限制（用户滑动窗口 + IP 限流）
  F4 - 查询历史记录（分页）
  F5 - 批量导入管理端
"""
import json
from datetime import datetime, timezone
from typing import Optional, List

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.anti_fake_repository import (
    AntiFakeRepository,
    QUERY_COUNT_WARNING,
    QUERY_COUNT_SUSPICIOUS,
    BatchSizeExceeded,
)

# ── Redis Key 设计 ─────────────────────────────────────────────────────────────
CACHE_KEY_VERIFY = "af:code:{code}"         # 查询结果缓存，TTL=24h
CACHE_KEY_EMPTY = "af:empty:{code}"         # 缓存穿透：不存在的码，TTL=5min
CACHE_KEY_RATE_USER = "af:rate:{user_id}"   # 用户查询频率，TTL=60s
CACHE_KEY_RATE_IP = "af:ip_rate:{ip}"       # IP 查询频率，TTL=60s

CACHE_TTL_VERIFY = 86400    # 24h
CACHE_TTL_EMPTY = 300       # 5min（缓存穿透防护）
RATE_LIMIT_WINDOW = 60      # 滑动窗口 60s


# ── 业务异常 ──────────────────────────────────────────────────────────────────

class RateLimitExceeded(Exception):
    def __init__(self, message: str, ttl: int = 0):
        self.ttl = ttl
        super().__init__(message)


class AntiFakeCodeNotFound(Exception):
    """防伪码不存在"""
    pass


class InvalidCodeFormat(Exception):
    """防伪码格式非法"""
    pass


class AntiFakeCodeSuspicious(Exception):
    """防伪码已标记为可疑"""
    pass


# ── Service ───────────────────────────────────────────────────────────────────

class AntiFakeService:
    """
    防伪查询业务逻辑层。
    约束:
    1. verify_code() 先查 Redis 缓存，未命中再查数据库
    2. 缓存命中仍需异步更新 query_count（最终一致性）
    3. 首次查询记录 verified_by 和 verified_at
    4. 查询频率超限抛出 RateLimitExceeded（用户 10次/min）
    5. 缓存穿透防护：对不存在的码写空缓存，TTL=5min
    6. 所有数据库操作通过 AntiFakeRepository 完成
    """

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis
        self.repo = AntiFakeRepository(db)

    # ── F2 + F3: 防伪码查询核心 ────────────────────────────────────────────────

    async def verify_code(
        self, code: str, user_id: int, client_ip: str = "0.0.0.0"
    ) -> dict:
        """
        验证防伪码。流程:
        频率限制 → Redis缓存 → DB查询 → 写缓存 → 更新计数 → 返回结果
        """
        # F3: 频率限制
        await self._check_rate_limit(user_id, client_ip)

        # F2: 缓存穿透防护
        empty_key = CACHE_KEY_EMPTY.format(code=code)
        if await self.redis.exists(empty_key):
            raise AntiFakeCodeNotFound(code)

        # F2: 查 Redis 缓存
        cached = await self._get_cached_result(code)
        if cached is not None:
            # 缓存命中：仍异步更新计数（fire-and-forget）
            await self._async_increment_db_count(code)
            # 动态更新 query_count
            cached["verification"]["query_count"] = (
                cached["verification"]["query_count"] + 1
            )
            # 重新计算 warning
            qc = cached["verification"]["query_count"]
            if qc >= QUERY_COUNT_WARNING:
                cached["verification"]["warning"] = (
                    f"该防伪码已被查询过 {qc} 次，请注意辨别"
                )
            return cached

        # F2: 查数据库
        af_code = await self.repo.find_by_code(code)
        if af_code is None:
            # 缓存穿透防护：写空缓存
            await self.redis.setex(empty_key, CACHE_TTL_EMPTY, "1")
            raise AntiFakeCodeNotFound(code)

        now = datetime.now(timezone.utc)
        is_first = not af_code.is_verified

        if is_first:
            # 首次查询：写 verified_at / verified_by
            await self.repo.mark_first_verified(af_code.id, user_id, now)
            query_count = 1
        else:
            # 非首次：递增计数
            query_count = await self.repo.increment_query_count(af_code.id)

        product = af_code.product
        result = self._build_result(af_code, product, query_count, is_first, now)

        # 写入缓存
        await self.redis.setex(
            CACHE_KEY_VERIFY.format(code=code),
            CACHE_TTL_VERIFY,
            json.dumps(result, default=str),
        )
        return result

    @staticmethod
    def _build_result(
        af_code, product, query_count: int, is_first: bool, verified_at: datetime
    ) -> dict:
        """构建统一的查询结果字典。"""
        verification: dict = {
            "first_verified": is_first,
            "query_count": query_count,
            "verified_at": verified_at.isoformat(),
        }
        if not is_first and af_code.verified_at:
            verification["first_verified_at"] = af_code.verified_at.isoformat()
        if query_count >= QUERY_COUNT_WARNING:
            verification["warning"] = (
                f"该防伪码已被查询过 {query_count} 次，请注意辨别"
            )

        product_info = None
        if product:
            product_info = {
                "id": product.id,
                "name": product.name,
                "brand": product.brand or "",
                "category": product.category or "",
                "cover_image": product.cover_image,
                "batch_no": af_code.batch_no,
                "production_date": None,
                "expiry_date": None,
            }

        return {
            "is_authentic": True,
            "product": product_info,
            "verification": verification,
        }

    # ── F3: 频率限制 ───────────────────────────────────────────────────────────

    async def _check_rate_limit(self, user_id: int, client_ip: str = "0.0.0.0") -> None:
        """
        双维度频率限制：
        - 用户：10 次/分钟
        - IP：30 次/分钟
        使用 Redis INCR + EXPIRE 滑动窗口。
        """
        # 用户维度
        user_key = CACHE_KEY_RATE_USER.format(user_id=user_id)
        user_count = await self.redis.incr(user_key)
        if user_count == 1:
            await self.redis.expire(user_key, RATE_LIMIT_WINDOW)
        if user_count > settings.ANTI_FAKE_RATE_LIMIT_USER:
            ttl = await self.redis.ttl(user_key)
            raise RateLimitExceeded(
                f"查询过于频繁，请 {ttl} 秒后重试", ttl=int(ttl)
            )

        # IP 维度
        ip_key = CACHE_KEY_RATE_IP.format(ip=client_ip)
        ip_count = await self.redis.incr(ip_key)
        if ip_count == 1:
            await self.redis.expire(ip_key, RATE_LIMIT_WINDOW)
        if ip_count > settings.ANTI_FAKE_RATE_LIMIT_IP:
            ttl = await self.redis.ttl(ip_key)
            raise RateLimitExceeded(
                f"IP 请求过于频繁，请 {ttl} 秒后重试", ttl=int(ttl)
            )

    # ── F2: 缓存操作 ───────────────────────────────────────────────────────────

    async def _get_cached_result(self, code: str) -> Optional[dict]:
        key = CACHE_KEY_VERIFY.format(code=code)
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def invalidate_cache(self, code: str) -> None:
        """主动失效防伪码缓存（状态变更时调用）。"""
        await self.redis.delete(CACHE_KEY_VERIFY.format(code=code))
        await self.redis.delete(CACHE_KEY_EMPTY.format(code=code))

    async def _async_increment_db_count(self, code: str) -> None:
        """
        缓存命中时异步更新 DB 计数。
        生产环境应发送 Celery 任务；此处直接调用 repo（测试友好）。
        """
        af_code = await self.repo.find_by_code(code)
        if af_code:
            await self.repo.increment_query_count(af_code.id)

    # ── F4: 查询历史 ───────────────────────────────────────────────────────────

    async def get_history(self, user_id: int, page: int, size: int) -> dict:
        """获取用户防伪查询历史（分页）。"""
        return await self.repo.get_history(user_id=user_id, page=page, size=size)

    # ── F5: 批量导入（管理端）──────────────────────────────────────────────────

    async def batch_import(
        self,
        codes: List[dict],
        salt: str = "",
    ) -> dict:
        """
        批量导入防伪码。
        codes: [{"code": "...", "product_id": 1, "batch_no": "B001"}, ...]
        """
        count = await self.repo.bulk_create(codes, salt=salt)
        return {"imported": count, "total": len(codes)}

