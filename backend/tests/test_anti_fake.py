"""
Anti-Fake Module — 完整测试套件
涵盖:
  F1 - 防伪码格式校验 & 输入安全（VerifyRequest Validator）
  F2 - 防伪码查询核心（缓存命中/未命中/首次/非首次/穿透防护）
  F3 - 查询频率限制（用户维度 / IP 维度）
  F4 - 查询历史记录（Repository 分页）
  F5 - 批量导入（正常 / 超限 / 去重）
"""
import json
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.anti_fake_service import (
    AntiFakeService,
    RateLimitExceeded,
    AntiFakeCodeNotFound,
    InvalidCodeFormat,
    AntiFakeCodeSuspicious,
    CACHE_KEY_VERIFY,
    CACHE_KEY_EMPTY,
    CACHE_KEY_RATE_USER,
    CACHE_KEY_RATE_IP,
)
from app.repositories.anti_fake_repository import (
    AntiFakeRepository,
    BatchSizeExceeded,
    QUERY_COUNT_WARNING,
    QUERY_COUNT_SUSPICIOUS,
    CODE_STATUS_VERIFIED,
    CODE_STATUS_WARNING,
    CODE_STATUS_SUSPICIOUS,
)
from app.schemas.anti_fake import VerifyRequest
from app.models.models import AntiFakeCode, Product


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_product(id=1001, name="花瓣精华水", brand="Petal",
                 category="护肤", price=Decimal("299.00")):
    p = Product()
    p.id = id
    p.name = name
    p.brand = brand
    p.category = category
    p.price = price
    p.cover_image = f"https://cdn.example.com/products/{id}.jpg"
    return p


def make_af_code(
    id=1,
    code="PET-2B2G4R-A7X9K3M2-Q",
    product_id=1001,
    is_verified=False,
    query_count=0,
    status="unused",
    verified_at=None,
    verified_by=None,
    batch_no="B20260301",
    product=None,
):
    af = AntiFakeCode()
    af.id = id
    af.code = code
    af.product_id = product_id
    af.is_verified = is_verified
    af.query_count = query_count
    af.status = status
    af.verified_at = verified_at
    af.verified_by = verified_by
    af.batch_no = batch_no
    af.product = product or make_product()
    return af


def make_service(redis=None, db=None):
    if db is None:
        db = AsyncMock()
    if redis is None:
        redis = AsyncMock()
        redis.get.return_value = None
        redis.exists.return_value = 0
        redis.incr.return_value = 1
        redis.ttl.return_value = 55
    return AntiFakeService(db=db, redis=redis)


# ══════════════════════════════════════════════════════════════════════════════
# F1 — 防伪码格式校验 & 输入安全
# ══════════════════════════════════════════════════════════════════════════════

class TestVerifyRequestValidation:
    """AF-U: VerifyRequest Schema 格式校验"""

    def test_valid_code_accepted(self):
        """AF-U-01 前置: 标准格式防伪码通过校验"""
        req = VerifyRequest(code="PET-2B2G4R-A7X9K3M2-Q")
        assert req.code == "PET-2B2G4R-A7X9K3M2-Q"

    def test_lowercase_auto_uppercased(self):
        """小写字母自动转大写"""
        req = VerifyRequest(code="pet-2b2g4r-a7x9k3m2-q")
        assert req.code == "PET-2B2G4R-A7X9K3M2-Q"

    def test_whitespace_stripped(self):
        """AF-I-06 前置: 前后空格自动裁剪"""
        req = VerifyRequest(code="  PET-2B2G4R-A7X9K3M2-Q  ")
        assert req.code == "PET-2B2G4R-A7X9K3M2-Q"

    def test_too_short_rejected(self):
        """AF-I-06: 过短的码被拒绝（< 10字符）"""
        with pytest.raises(ValueError, match="防伪码格式不正确"):
            VerifyRequest(code="AB")

    def test_sql_injection_rejected(self):
        """AF-S-01: SQL 注入字符被拒绝"""
        with pytest.raises(ValueError):
            VerifyRequest(code="'; DROP TABLE anti_fake_codes; --")

    def test_xss_injection_rejected(self):
        """AF-S-02: XSS 注入被拒绝"""
        with pytest.raises(ValueError):
            VerifyRequest(code="<script>alert(1)</script>")

    def test_excluded_chars_O_rejected(self):
        """AF-U-05: 字符集排除 O（易混淆）"""
        with pytest.raises(ValueError):
            VerifyRequest(code="OOOOOOOOOOOOO")

    def test_excluded_chars_0_rejected(self):
        """字符集排除 0（数字零）"""
        with pytest.raises(ValueError):
            VerifyRequest(code="000000000000")

    def test_excluded_chars_I_rejected(self):
        """字符集排除 I"""
        with pytest.raises(ValueError):
            VerifyRequest(code="IIIIIIIIIIIII")

    def test_excluded_chars_1_rejected(self):
        """字符集排除 1"""
        with pytest.raises(ValueError):
            VerifyRequest(code="111111111111")

    def test_excluded_chars_L_rejected(self):
        """字符集排除 L"""
        with pytest.raises(ValueError):
            VerifyRequest(code="LLLLLLLLLLLLL")

    def test_valid_no_dash_code(self):
        """不含连字符的有效码"""
        req = VerifyRequest(code="ABCDEFGHJK")
        assert req.code == "ABCDEFGHJK"


# ══════════════════════════════════════════════════════════════════════════════
# F2 — 防伪码查询核心
# ══════════════════════════════════════════════════════════════════════════════

class TestVerifyCodeCacheHit:
    """AF-U-06: 缓存命中场景"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self):
        """缓存命中直接返回，不查数据库"""
        cached_data = {
            "is_authentic": True,
            "product": {"id": 1001, "name": "花瓣精华水",
                        "brand": "Petal", "category": "护肤",
                        "cover_image": None, "batch_no": None,
                        "production_date": None, "expiry_date": None},
            "verification": {
                "first_verified": False,
                "query_count": 2,
                "verified_at": "2026-04-01T10:00:00+00:00",
            },
        }

        redis = AsyncMock()
        redis.incr.return_value = 1   # rate limit ok
        redis.exists.return_value = 0  # no empty cache
        redis.get.return_value = json.dumps(cached_data)

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)

        # Patch _async_increment_db_count to avoid DB call
        svc._async_increment_db_count = AsyncMock()

        result = await svc.verify_code("PET-2B2G4R-A7X9K3M2-Q", user_id=1)

        assert result["is_authentic"] is True
        assert result["verification"]["query_count"] == 3  # incremented
        db.execute.assert_not_called()
        svc._async_increment_db_count.assert_called_once_with("PET-2B2G4R-A7X9K3M2-Q")

    @pytest.mark.asyncio
    async def test_cache_hit_adds_warning_when_threshold_reached(self):
        """缓存命中且计数达到告警阈值，返回 warning"""
        cached_data = {
            "is_authentic": True,
            "product": None,
            "verification": {
                "first_verified": False,
                "query_count": QUERY_COUNT_WARNING - 1,  # 下一次触发
                "verified_at": "2026-04-01T10:00:00+00:00",
            },
        }

        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = json.dumps(cached_data)

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc._async_increment_db_count = AsyncMock()

        result = await svc.verify_code("PET-2B2G4R-A7X9K3M2-Q", user_id=1)
        assert "warning" in result["verification"]


class TestVerifyCodeDbQuery:
    """AF-U-01 ~ AF-U-04: 数据库查询场景"""

    @pytest.mark.asyncio
    async def test_first_verify_returns_first_verified_true(self):
        """AF-U-01: 首次查询返回 first_verified=True"""
        af_code = make_af_code(is_verified=False, query_count=0)

        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = None  # 缓存未命中

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.find_by_code.return_value = af_code
        svc.repo.mark_first_verified.return_value = None

        result = await svc.verify_code("PET-2B2G4R-A7X9K3M2-Q", user_id=42)

        assert result["is_authentic"] is True
        assert result["verification"]["first_verified"] is True
        assert result["verification"]["query_count"] == 1
        svc.repo.mark_first_verified.assert_called_once()

    @pytest.mark.asyncio
    async def test_second_verify_returns_query_count(self):
        """AF-U-02: 非首次查询返回正确 query_count"""
        af_code = make_af_code(
            is_verified=True,
            query_count=2,
            status=CODE_STATUS_VERIFIED,
            verified_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = None

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.find_by_code.return_value = af_code
        svc.repo.increment_query_count.return_value = 3

        result = await svc.verify_code("PET-2B2G4R-A7X9K3M2-Q", user_id=1)

        assert result["verification"]["first_verified"] is False
        assert result["verification"]["query_count"] == 3
        svc.repo.increment_query_count.assert_called_once_with(af_code.id)

    @pytest.mark.asyncio
    async def test_warning_returned_at_threshold(self):
        """AF-U-03: query_count >= 3 时返回 warning"""
        af_code = make_af_code(is_verified=True, query_count=9,
                               status=CODE_STATUS_WARNING)

        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = None

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.find_by_code.return_value = af_code
        svc.repo.increment_query_count.return_value = 10

        result = await svc.verify_code("PET-2B2G4R-A7X9K3M2-Q", user_id=1)
        assert "warning" in result["verification"]
        assert "10" in result["verification"]["warning"]

    @pytest.mark.asyncio
    async def test_not_found_raises_exception(self):
        """AF-U-04: 防伪码不存在抛出 AntiFakeCodeNotFound"""
        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = None

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.find_by_code.return_value = None

        with pytest.raises(AntiFakeCodeNotFound):
            await svc.verify_code("NOT-EXIST-CODE", user_id=1)

    @pytest.mark.asyncio
    async def test_not_found_writes_empty_cache(self):
        """AF-U-08: 不存在的码写入空缓存（防穿透）"""
        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = None

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.find_by_code.return_value = None

        with pytest.raises(AntiFakeCodeNotFound):
            await svc.verify_code("NOT-EXIST-CODE", user_id=1)

        # 应写入空缓存
        redis.setex.assert_called_once()
        call_args = redis.setex.call_args[0]
        assert "af:empty:" in call_args[0]

    @pytest.mark.asyncio
    async def test_empty_cache_hit_prevents_db_query(self):
        """AF-U-08: 命中空缓存不再查 DB"""
        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 1  # 空缓存存在

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()

        with pytest.raises(AntiFakeCodeNotFound):
            await svc.verify_code("NOT-EXIST-CODE", user_id=1)

        svc.repo.find_by_code.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_writes_to_redis_cache(self):
        """查询成功后将结果写入 Redis 缓存"""
        af_code = make_af_code(is_verified=False, query_count=0)

        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = None

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.find_by_code.return_value = af_code
        svc.repo.mark_first_verified.return_value = None

        await svc.verify_code("PET-2B2G4R-A7X9K3M2-Q", user_id=1)

        redis.setex.assert_called_once()
        cache_key = redis.setex.call_args[0][0]
        assert "af:code:" in cache_key

    @pytest.mark.asyncio
    async def test_result_contains_product_info(self):
        """返回结果包含完整产品信息"""
        product = make_product(name="花瓣精华水", brand="Petal")
        af_code = make_af_code(is_verified=False, product=product)

        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.exists.return_value = 0
        redis.get.return_value = None

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.find_by_code.return_value = af_code
        svc.repo.mark_first_verified.return_value = None

        result = await svc.verify_code("PET-2B2G4R-A7X9K3M2-Q", user_id=1)

        assert result["product"]["name"] == "花瓣精华水"
        assert result["product"]["brand"] == "Petal"
        assert result["product"]["batch_no"] == "B20260301"


# ══════════════════════════════════════════════════════════════════════════════
# F3 — 查询频率限制
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimit:
    """AF-U-07 / AF-S-03: 频率限制"""

    @pytest.mark.asyncio
    async def test_normal_rate_no_exception(self):
        """正常频率不被限制"""
        redis = AsyncMock()
        redis.incr.return_value = 5   # 5次/min，在限制内
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)

        # 不应抛出异常
        await svc._check_rate_limit(user_id=1)

    @pytest.mark.asyncio
    async def test_user_rate_limit_exceeded(self):
        """AF-U-07: 用户超过 10次/min，抛出 RateLimitExceeded"""
        redis = AsyncMock()
        redis.incr.return_value = 11   # 超限
        redis.ttl.return_value = 45

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)

        with pytest.raises(RateLimitExceeded) as exc_info:
            await svc._check_rate_limit(user_id=1)
        assert "45" in str(exc_info.value)
        assert exc_info.value.ttl == 45

    @pytest.mark.asyncio
    async def test_rate_limit_sets_expire_on_first_call(self):
        """首次 INCR 时设置过期时间"""
        redis = AsyncMock()
        redis.incr.return_value = 1  # 首次调用

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        await svc._check_rate_limit(user_id=1)

        redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_ip_rate_limit_exceeded(self):
        """AF-S-03: IP 超过 30次/min，抛出 RateLimitExceeded"""
        redis = AsyncMock()
        # 用户维度通过（1次），IP 维度超限（31次）
        redis.incr.side_effect = [1, 31]
        redis.ttl.return_value = 30

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)

        with pytest.raises(RateLimitExceeded):
            await svc._check_rate_limit(user_id=1, client_ip="192.168.1.1")

    @pytest.mark.asyncio
    async def test_rate_limit_key_includes_user_id(self):
        """频率限制 Redis Key 包含 user_id"""
        redis = AsyncMock()
        redis.incr.return_value = 1

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        await svc._check_rate_limit(user_id=999)

        # 找到包含 user_id 的 incr 调用
        incr_keys = [call[0][0] for call in redis.incr.call_args_list]
        assert any("999" in k for k in incr_keys)

    @pytest.mark.asyncio
    async def test_rate_limit_key_includes_ip(self):
        """IP 限制 Redis Key 包含 IP 地址"""
        redis = AsyncMock()
        redis.incr.return_value = 1

        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        await svc._check_rate_limit(user_id=1, client_ip="10.0.0.1")

        incr_keys = [call[0][0] for call in redis.incr.call_args_list]
        assert any("10.0.0.1" in k for k in incr_keys)


# ══════════════════════════════════════════════════════════════════════════════
# F4 — 查询历史
# ══════════════════════════════════════════════════════════════════════════════

class TestGetHistory:
    """AF-I-03 / AF-I-04: 查询历史分页"""

    @pytest.mark.asyncio
    async def test_get_history_returns_paged_result(self):
        """get_history 返回分页结构"""
        redis = AsyncMock()
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.get_history.return_value = {
            "total": 5,
            "items": [
                {
                    "code": "PET-2B2G4R-A7X9K3M2-Q",
                    "product_name": "花瓣精华水",
                    "is_authentic": True,
                    "queried_at": datetime.now(timezone.utc),
                }
            ],
        }

        result = await svc.get_history(user_id=1, page=1, size=20)

        assert result["total"] == 5
        assert len(result["items"]) == 1
        svc.repo.get_history.assert_called_once_with(user_id=1, page=1, size=20)

    @pytest.mark.asyncio
    async def test_get_history_passes_correct_pagination(self):
        """AF-I-04: 分页参数正确透传给 Repository"""
        redis = AsyncMock()
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.get_history.return_value = {"total": 10, "items": []}

        await svc.get_history(user_id=42, page=3, size=5)
        svc.repo.get_history.assert_called_once_with(user_id=42, page=3, size=5)

    @pytest.mark.asyncio
    async def test_history_empty_returns_zero_total(self):
        """无历史记录时返回 total=0"""
        redis = AsyncMock()
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.get_history.return_value = {"total": 0, "items": []}

        result = await svc.get_history(user_id=99, page=1, size=20)
        assert result["total"] == 0
        assert result["items"] == []


# ══════════════════════════════════════════════════════════════════════════════
# F5 — 批量导入
# ══════════════════════════════════════════════════════════════════════════════

class TestBatchImport:
    """AF-U-12 ~ AF-U-14: 批量导入"""

    @pytest.mark.asyncio
    async def test_batch_import_success(self):
        """AF-U-12: 正常批量导入返回成功数量"""
        codes = [
            {"code": f"PET-202604-A{i:07d}-Q", "product_id": 1, "batch_no": "B001"}
            for i in range(100)
        ]

        redis = AsyncMock()
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.bulk_create.return_value = 100

        result = await svc.batch_import(codes)

        assert result["imported"] == 100
        assert result["total"] == 100
        svc.repo.bulk_create.assert_called_once_with(codes, salt="")

    @pytest.mark.asyncio
    async def test_batch_import_exceeds_limit_raises(self):
        """AF-U-14: 超过单次上限 5000 抛出 BatchSizeExceeded"""
        codes = [
            {"code": f"PET-202604-X{i:07d}-Z", "product_id": 1}
            for i in range(6000)
        ]

        redis = AsyncMock()
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.bulk_create.side_effect = BatchSizeExceeded(5000, 6000)

        with pytest.raises(BatchSizeExceeded) as exc_info:
            await svc.batch_import(codes)
        assert exc_info.value.limit == 5000
        assert exc_info.value.actual == 6000

    @pytest.mark.asyncio
    async def test_batch_import_with_salt(self):
        """批量导入传递 salt 参数"""
        codes = [{"code": "PET-2B2G4R-A7X9K3M2-Q", "product_id": 1}]

        redis = AsyncMock()
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)
        svc.repo = AsyncMock()
        svc.repo.bulk_create.return_value = 1

        await svc.batch_import(codes, salt="secret-salt")
        svc.repo.bulk_create.assert_called_once_with(codes, salt="secret-salt")


# ══════════════════════════════════════════════════════════════════════════════
# Repository 层单元测试
# ══════════════════════════════════════════════════════════════════════════════

class TestAntiFakeRepository:
    """AF-U-09 ~ AF-U-14: Repository 层"""

    @pytest.mark.asyncio
    async def test_find_by_code_returns_none_when_not_found(self):
        """AF-U-10: 不存在的防伪码返回 None"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        repo = AntiFakeRepository(db)
        result = await repo.find_by_code("NOT-EXIST")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_code_returns_object_when_found(self):
        """AF-U-09: 存在的防伪码返回 AntiFakeCode 对象"""
        af_code = make_af_code()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = af_code
        db.execute.return_value = mock_result

        repo = AntiFakeRepository(db)
        result = await repo.find_by_code("PET-2B2G4R-A7X9K3M2-Q")
        assert result is not None
        assert result.code == "PET-2B2G4R-A7X9K3M2-Q"

    @pytest.mark.asyncio
    async def test_increment_query_count_transitions_to_warning(self):
        """query_count 达到 WARNING 阈值时状态变为 warning"""
        db = AsyncMock()

        # 第一次 execute：读当前 query_count = QUERY_COUNT_WARNING - 1
        count_result = MagicMock()
        count_result.scalar_one_or_none.return_value = QUERY_COUNT_WARNING - 1
        # 第二次 execute：update
        update_result = MagicMock()
        db.execute.side_effect = [count_result, update_result]

        repo = AntiFakeRepository(db)
        new_count = await repo.increment_query_count(code_id=1)

        assert new_count == QUERY_COUNT_WARNING
        # 验证 update 调用（第2次 execute）
        assert db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_increment_query_count_transitions_to_suspicious(self):
        """query_count 达到 SUSPICIOUS 阈值时状态变为 suspicious"""
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one_or_none.return_value = QUERY_COUNT_SUSPICIOUS - 1
        update_result = MagicMock()
        db.execute.side_effect = [count_result, update_result]

        repo = AntiFakeRepository(db)
        new_count = await repo.increment_query_count(code_id=2)

        assert new_count == QUERY_COUNT_SUSPICIOUS

    @pytest.mark.asyncio
    async def test_bulk_create_exceeds_limit_raises(self):
        """AF-U-14: bulk_create 超过 5000 条抛出 BatchSizeExceeded"""
        db = AsyncMock()
        repo = AntiFakeRepository(db)

        codes = [{"code": f"CODE{i:010d}", "product_id": 1} for i in range(5001)]
        with pytest.raises(BatchSizeExceeded):
            await repo.bulk_create(codes)

    @pytest.mark.asyncio
    async def test_bulk_create_stores_correct_count(self):
        """AF-U-12: 正常批量导入，add 调用次数 == 数据量"""
        db = AsyncMock()
        repo = AntiFakeRepository(db)

        codes = [
            {"code": f"PET-202604-A{i:07d}-Q", "product_id": 1, "batch_no": "B001"}
            for i in range(10)
        ]
        result = await repo.bulk_create(codes, salt="test-salt")

        assert result == 10
        assert db.add.call_count == 10
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_hashes_code_with_salt(self):
        """批量导入时 code_hash 使用 SHA-256(code+salt)"""
        import hashlib

        db = AsyncMock()
        repo = AntiFakeRepository(db)

        codes = [{"code": "PET-2B2G4R-A7X9K3M2-Q", "product_id": 1}]
        await repo.bulk_create(codes, salt="my-salt")

        # 获取 add 调用的第一个参数
        af_record = db.add.call_args[0][0]
        expected_hash = hashlib.sha256(
            ("PET-2B2G4R-A7X9K3M2-Q" + "my-salt").encode()
        ).hexdigest()
        assert af_record.code_hash == expected_hash

    @pytest.mark.asyncio
    async def test_bulk_create_auto_uppercases_code(self):
        """批量导入时防伪码自动转大写"""
        db = AsyncMock()
        repo = AntiFakeRepository(db)

        codes = [{"code": "pet-2b2g4r-a7x9k3m2-q", "product_id": 1}]
        await repo.bulk_create(codes)

        af_record = db.add.call_args[0][0]
        assert af_record.code == "PET-2B2G4R-A7X9K3M2-Q"

    @pytest.mark.asyncio
    async def test_mark_first_verified_sets_fields(self):
        """mark_first_verified 调用 update，设置 is_verified=True"""
        db = AsyncMock()
        mock_result = MagicMock()
        db.execute.return_value = mock_result

        repo = AntiFakeRepository(db)
        now = datetime.now(timezone.utc)
        await repo.mark_first_verified(code_id=1, user_id=42, verified_at=now)

        db.execute.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Service 缓存辅助方法测试
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceCacheHelpers:
    """缓存辅助函数"""

    @pytest.mark.asyncio
    async def test_get_cached_result_returns_none_on_miss(self):
        """AF-U-06: 缓存未命中返回 None"""
        redis = AsyncMock()
        redis.get.return_value = None
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)

        result = await svc._get_cached_result("SOME-CODE")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_result_returns_parsed_json(self):
        """缓存命中返回解析后的字典"""
        data = {"is_authentic": True, "product": {"name": "Test"}}
        redis = AsyncMock()
        redis.get.return_value = json.dumps(data)
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)

        result = await svc._get_cached_result("SOME-CODE")
        assert result["is_authentic"] is True
        assert result["product"]["name"] == "Test"

    @pytest.mark.asyncio
    async def test_invalidate_cache_deletes_both_keys(self):
        """invalidate_cache 删除查询缓存和空缓存"""
        redis = AsyncMock()
        db = AsyncMock()
        svc = AntiFakeService(db=db, redis=redis)

        await svc.invalidate_cache("SOME-CODE")
        assert redis.delete.call_count == 2
        deleted_keys = [c[0][0] for c in redis.delete.call_args_list]
        assert any("af:code:" in k for k in deleted_keys)
        assert any("af:empty:" in k for k in deleted_keys)


# ══════════════════════════════════════════════════════════════════════════════
# _build_result 静态方法测试
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildResult:
    """AntiFakeService._build_result 静态方法"""

    def test_first_verify_result_structure(self):
        """首次查询结果结构正确"""
        af_code = make_af_code(is_verified=False)
        product = make_product()
        now = datetime.now(timezone.utc)

        result = AntiFakeService._build_result(
            af_code, product, query_count=1, is_first=True, verified_at=now
        )
        assert result["is_authentic"] is True
        assert result["verification"]["first_verified"] is True
        assert result["verification"]["query_count"] == 1
        assert "warning" not in result["verification"]
        assert result["product"]["name"] == "花瓣精华水"

    def test_non_first_verify_has_first_verified_at(self):
        """非首次查询包含 first_verified_at 字段"""
        past = datetime.now(timezone.utc) - timedelta(days=10)
        af_code = make_af_code(is_verified=True, verified_at=past)
        product = make_product()
        now = datetime.now(timezone.utc)

        result = AntiFakeService._build_result(
            af_code, product, query_count=3, is_first=False, verified_at=now
        )
        assert result["verification"]["first_verified"] is False
        assert "first_verified_at" in result["verification"]

    def test_warning_added_when_query_count_gte_threshold(self):
        """query_count >= QUERY_COUNT_WARNING 时包含 warning"""
        af_code = make_af_code()
        product = make_product()
        now = datetime.now(timezone.utc)

        result = AntiFakeService._build_result(
            af_code, product,
            query_count=QUERY_COUNT_WARNING,
            is_first=False,
            verified_at=now,
        )
        assert "warning" in result["verification"]

    def test_no_warning_below_threshold(self):
        """query_count < QUERY_COUNT_WARNING 时无 warning"""
        af_code = make_af_code()
        product = make_product()
        now = datetime.now(timezone.utc)

        result = AntiFakeService._build_result(
            af_code, product,
            query_count=QUERY_COUNT_WARNING - 1,
            is_first=True,
            verified_at=now,
        )
        assert "warning" not in result["verification"]

    def test_no_product_info_when_product_none(self):
        """无关联产品时 product 字段为 None"""
        af_code = make_af_code(product=None)
        af_code.product = None
        now = datetime.now(timezone.utc)

        result = AntiFakeService._build_result(
            af_code, None, query_count=1, is_first=True, verified_at=now
        )
        assert result["product"] is None

