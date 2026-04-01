"""
Anti-Fake Module — Unit Tests
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.anti_fake_service import AntiFakeService, RateLimitExceeded
from app.schemas.anti_fake import VerifyRequest


class TestVerifyRequest:
    """防伪码格式校验测试"""

    def test_valid_code(self):
        req = VerifyRequest(code="PET-202604-A7X9K3M2-Q")
        assert req.code == "PET-202604-A7X9K3M2-Q"

    def test_valid_code_with_whitespace(self):
        req = VerifyRequest(code="  pet-202604-a7x9k3m2-q  ")
        assert req.code == "PET-202604-A7X9K3M2-Q"

    def test_invalid_code_too_short(self):
        with pytest.raises(ValueError, match="防伪码格式不正确"):
            VerifyRequest(code="AB")

    def test_invalid_code_special_chars(self):
        with pytest.raises(ValueError, match="防伪码格式不正确"):
            VerifyRequest(code="'; DROP TABLE--")

    def test_invalid_code_with_excluded_chars(self):
        """O, 0, I, 1, L are excluded from valid charset"""
        with pytest.raises(ValueError):
            VerifyRequest(code="OOOOO00000IIIII11111LLLLL")


class TestAntiFakeService:
    """防伪查询 Service 层测试"""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.get.return_value = None
        return redis

    @pytest.fixture
    def service(self, mock_db, mock_redis):
        return AntiFakeService(db=mock_db, redis=mock_redis)

    @pytest.mark.asyncio
    async def test_rate_limit_normal(self, service, mock_redis):
        """正常频率不被限制"""
        mock_redis.incr.return_value = 5
        await service._check_rate_limit(user_id=1)
        # No exception raised

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, service, mock_redis):
        """超过频率限制"""
        mock_redis.incr.return_value = 11
        mock_redis.ttl.return_value = 45
        with pytest.raises(RateLimitExceeded, match="45"):
            await service._check_rate_limit(user_id=1)

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, service, mock_redis):
        """缓存未命中返回 None"""
        mock_redis.get.return_value = None
        result = await service._get_cached_result("TEST-CODE")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_data(self, service, mock_redis):
        """缓存命中返回数据"""
        import json
        cached_data = {"is_authentic": True, "product": {"name": "Test"}}
        mock_redis.get.return_value = json.dumps(cached_data)
        result = await service._get_cached_result("TEST-CODE")
        assert result["is_authentic"] is True
