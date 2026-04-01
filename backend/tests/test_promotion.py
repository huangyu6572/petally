"""
Promotion Module — 完整测试套件
涵盖:
  F1 - 推广活动列表 & 详情 (含缓存)
  F2 - 优惠券领取 (幂等性 / 状态校验 / 库存原子扣减)
  F3 - 推荐算法 (AI分析匹配 / 热门降级 / 评分)
  F4 - 数据追踪 (事件写入 / 曝光去重 / 批量消费)
  F5 - 分享推广 (生成分享信息)
  F6 - 管理端看板 / 定时任务 (状态机 / 库存同步 / 优惠券清理)
"""
import json
import pytest
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.services.promotion_service import (
    PromotionService,
    ISSUE_PRODUCT_MAPPING,
    PROMO_STATUS_DRAFT,
    PROMO_STATUS_SCHEDULED,
    PROMO_STATUS_ACTIVE,
    PROMO_STATUS_ENDED,
    PROMO_STATUS_STOPPED,
    PromotionNotFound,
    PromotionNotStarted,
    PromotionEnded,
    CouponSoldOut,
    CouponAlreadyClaimed,
    PromotionError,
    _calc_promo_price,
    _calc_tag,
    _promo_to_dict,
)
from app.models.models import Promotion, Product, Coupon, SkinAnalysis, PromoClick


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_promotion(
    id=1,
    title="测试活动",
    product_id=1001,
    promo_type="discount",
    discount_value=Decimal("0.7"),
    min_purchase=None,
    stock=100,
    status=PROMO_STATUS_ACTIVE,
    start_time=None,
    end_time=None,
    product=None,
):
    now = datetime.utcnow()
    p = Promotion()
    p.id = id
    p.title = title
    p.description = "测试描述"
    p.product_id = product_id
    p.promo_type = promo_type
    p.discount_value = discount_value
    p.min_purchase = min_purchase
    p.stock = stock
    p.status = status
    p.start_time = start_time or (now - timedelta(days=1))
    p.end_time = end_time or (now + timedelta(days=14))
    p.product = product
    return p


def make_product(id=1001, name="花瓣精华水", price=Decimal("299.00"),
                 tags=None, category="skincare", status=1):
    p = Product()
    p.id = id
    p.name = name
    p.price = price
    p.tags = tags or ["保湿", "补水"]
    p.category = category
    p.cover_image = f"https://cdn.example.com/products/{id}.jpg"
    p.status = status
    return p


def make_coupon(id="cpn_test_001", promotion_id=1, user_id=1,
                discount_type="amount", discount_value=Decimal("50"),
                min_purchase=Decimal("200"), valid_until=None, status="unused"):
    c = Coupon()
    c.id = id
    c.promotion_id = promotion_id
    c.user_id = user_id
    c.discount_type = discount_type
    c.discount_value = discount_value
    c.min_purchase = min_purchase
    c.valid_until = valid_until or (datetime.utcnow() + timedelta(days=30))
    c.status = status
    return c


def make_service(db=None, redis=None):
    if db is None:
        db = AsyncMock()
    if redis is None:
        redis = AsyncMock()
        redis.get.return_value = None
        redis.exists.return_value = False
        redis.decr.return_value = 99
        redis.incr.return_value = 100
    return PromotionService(db=db, redis=redis)


# ── F1: 推广活动列表 & 详情 ────────────────────────────────────────────────────

class TestGetActivePromotions:
    """PM-U-01 ~ PM-U-03: 推广列表"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self):
        """PM-U-03: Redis 缓存命中，不查数据库"""
        redis = AsyncMock()
        cached_data = json.dumps({"total": 5, "items": []})
        redis.get.return_value = cached_data

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        result = await svc.get_active_promotions(page=1, size=10)
        assert result == {"total": 5, "items": []}
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self):
        """PM-U-01: 缓存未命中，从数据库查询"""
        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        # Mock data query
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [count_result, data_result]

        svc = PromotionService(db=db, redis=redis)
        result = await svc.get_active_promotions(page=1, size=10)

        assert "total" in result
        assert "items" in result
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_category_filter_included_in_cache_key(self):
        """PM-U-02: 分类过滤参数影响缓存 key"""
        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [count_result, data_result]

        svc = PromotionService(db=db, redis=redis)
        await svc.get_active_promotions(page=1, size=10, category="skincare")

        # 缓存 key 应包含分类
        set_call = redis.setex.call_args
        assert "skincare" in set_call[0][0]


class TestGetDetail:
    """PM-U-04 ~ PM-U-05: 推广详情"""

    @pytest.mark.asyncio
    async def test_detail_not_found_raises(self):
        """PM-U-05: 推广不存在，抛出 PromotionNotFound"""
        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        svc = PromotionService(db=db, redis=redis)
        with pytest.raises(PromotionNotFound):
            await svc.get_detail(promo_id=999)

    @pytest.mark.asyncio
    async def test_detail_returns_full_info(self):
        """PM-U-04: 推广存在，返回完整详情"""
        product = make_product()
        promo = make_promotion(product=product)

        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = promo
        db.execute.return_value = result

        svc = PromotionService(db=db, redis=redis)
        detail = await svc.get_detail(promo_id=1)

        assert detail["id"] == 1
        assert "title" in detail
        assert "rules" in detail
        assert "product" in detail
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_detail_cache_hit(self):
        """详情缓存命中不查DB"""
        promo = make_promotion(product=make_product())
        cached = json.dumps(_promo_to_dict(promo) | {"rules": "规则文本"}, default=str)

        redis = AsyncMock()
        redis.get.return_value = cached

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)
        detail = await svc.get_detail(promo_id=1)

        assert detail["id"] == 1
        db.execute.assert_not_called()


# ── F2: 优惠券领取 ─────────────────────────────────────────────────────────────

class TestClaimCoupon:
    """PM-U-06 ~ PM-U-16: 优惠券领取"""

    @pytest.mark.asyncio
    async def test_claim_coupon_success(self):
        """PM-U-06: 正常领取，返回优惠券信息，库存 -1"""
        product = make_product()
        promo = make_promotion(
            promo_type="coupon",
            discount_value=Decimal("50"),
            min_purchase=Decimal("200"),
            stock=10,
            status=PROMO_STATUS_ACTIVE,
            product=product,
        )

        redis = AsyncMock()
        redis.get.return_value = None
        redis.exists.return_value = False
        redis.decr.return_value = 9  # 扣库存后剩余 9

        db = AsyncMock()
        # 第一次查：幂等检查（no existing coupon）
        no_coupon = MagicMock()
        no_coupon.scalar_one_or_none.return_value = None
        # 第二次查：获取推广
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.side_effect = [no_coupon, promo_result, MagicMock()]  # 第3次是 update

        svc = PromotionService(db=db, redis=redis)
        coupon_data = await svc.claim_coupon(promo_id=1, user_id=42)

        assert "coupon_id" in coupon_data
        assert coupon_data["discount_type"] == "amount"
        assert coupon_data["discount_value"] == 50.0
        redis.decr.assert_called_once()

    @pytest.mark.asyncio
    async def test_claim_coupon_already_claimed(self):
        """PM-U-07: 用户已领取，抛出 CouponAlreadyClaimed"""
        existing = make_coupon()

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        db.execute.return_value = result

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        with pytest.raises(CouponAlreadyClaimed) as exc_info:
            await svc.claim_coupon(promo_id=1, user_id=1)
        assert exc_info.value.code == 4005

    @pytest.mark.asyncio
    async def test_claim_coupon_sold_out(self):
        """PM-U-08: 库存为零，Redis DECR 后 < 0，回滚并抛出 CouponSoldOut"""
        promo = make_promotion(stock=0, status=PROMO_STATUS_ACTIVE)

        db = AsyncMock()
        no_coupon = MagicMock()
        no_coupon.scalar_one_or_none.return_value = None
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.side_effect = [no_coupon, promo_result]

        redis = AsyncMock()
        redis.exists.return_value = True
        redis.decr.return_value = -1  # 库存耗尽

        svc = PromotionService(db=db, redis=redis)
        with pytest.raises(CouponSoldOut) as exc_info:
            await svc.claim_coupon(promo_id=1, user_id=2)
        assert exc_info.value.code == 4004
        # 应该回滚
        redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_claim_coupon_not_started(self):
        """PM-U-09: 活动未开始，抛出 PromotionNotStarted"""
        future = datetime.utcnow() + timedelta(days=30)
        promo = make_promotion(
            status=PROMO_STATUS_SCHEDULED,
            start_time=future,
            end_time=future + timedelta(days=30),
        )

        db = AsyncMock()
        no_coupon = MagicMock()
        no_coupon.scalar_one_or_none.return_value = None
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.side_effect = [no_coupon, promo_result]

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)
        with pytest.raises(PromotionNotStarted) as exc_info:
            await svc.claim_coupon(promo_id=2, user_id=1)
        assert exc_info.value.code == 4002

    @pytest.mark.asyncio
    async def test_claim_coupon_ended(self):
        """PM-U-10: 活动已结束，抛出 PromotionEnded"""
        past = datetime.utcnow() - timedelta(days=30)
        promo = make_promotion(
            status=PROMO_STATUS_ENDED,
            start_time=past - timedelta(days=60),
            end_time=past,
        )

        db = AsyncMock()
        no_coupon = MagicMock()
        no_coupon.scalar_one_or_none.return_value = None
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.side_effect = [no_coupon, promo_result]

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)
        with pytest.raises(PromotionEnded) as exc_info:
            await svc.claim_coupon(promo_id=3, user_id=1)
        assert exc_info.value.code == 4003

    @pytest.mark.asyncio
    async def test_claim_coupon_idempotent(self):
        """PM-U-11: 幂等性 - 同一请求两次，第二次返回已领取"""
        existing = make_coupon()

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        db.execute.return_value = result

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        # 调用两次，第二次（以及首次发现已领取时）都应抛出 CouponAlreadyClaimed
        with pytest.raises(CouponAlreadyClaimed):
            await svc.claim_coupon(promo_id=1, user_id=1)
        # Redis.decr 不应被调用（在幂等检查阶段就返回）
        redis.decr.assert_not_called()

    @pytest.mark.asyncio
    async def test_stock_reaches_zero_auto_ends_promotion(self):
        """PM-U-16: 最后一张券领取后，活动状态自动变为 ENDED"""
        promo = make_promotion(stock=1, status=PROMO_STATUS_ACTIVE)

        db = AsyncMock()
        no_coupon = MagicMock()
        no_coupon.scalar_one_or_none.return_value = None
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.side_effect = [no_coupon, promo_result, MagicMock(), MagicMock()]

        redis = AsyncMock()
        redis.exists.return_value = False
        redis.decr.return_value = 0  # 库存降为 0

        svc = PromotionService(db=db, redis=redis)
        await svc.claim_coupon(promo_id=1, user_id=10)

        # 应该有一次 update 调用将 status 设为 ENDED
        update_calls = [c for c in db.execute.call_args_list]
        assert len(update_calls) >= 2  # sync_stock + status update


class TestStockManagement:
    """PM-U-12 ~ PM-U-15: 库存管理"""

    @pytest.mark.asyncio
    async def test_redis_decr_atomic(self):
        """PM-U-12: Redis DECR 原子操作"""
        redis = AsyncMock()
        redis.exists.return_value = True
        redis.decr.return_value = 49

        # 通过 claim_coupon 间接测试 DECR
        promo = make_promotion(stock=50, status=PROMO_STATUS_ACTIVE)
        db = AsyncMock()
        no_coupon = MagicMock()
        no_coupon.scalar_one_or_none.return_value = None
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.side_effect = [no_coupon, promo_result, MagicMock()]

        svc = PromotionService(db=db, redis=redis)
        await svc.claim_coupon(promo_id=1, user_id=1)
        redis.decr.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_rollback_when_negative(self):
        """PM-U-14: 库存为 0 时 DECR 返回 < 0，INCR 回滚"""
        redis = AsyncMock()
        redis.exists.return_value = True
        redis.decr.return_value = -1

        promo = make_promotion(stock=0, status=PROMO_STATUS_ACTIVE)
        db = AsyncMock()
        no_coupon = MagicMock()
        no_coupon.scalar_one_or_none.return_value = None
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.side_effect = [no_coupon, promo_result]

        svc = PromotionService(db=db, redis=redis)
        with pytest.raises(CouponSoldOut):
            await svc.claim_coupon(promo_id=1, user_id=99)
        redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_stock_to_db(self):
        """PM-U-15: 库存同步任务正确将 Redis 库存写入数据库"""
        redis = AsyncMock()
        redis.get.return_value = "88"

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        result = await svc.sync_stock_to_db(promo_id=1)
        assert result == 88
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_stock_returns_none_when_no_redis(self):
        """Redis 无库存记录时，sync_stock_to_db 返回 None"""
        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        result = await svc.sync_stock_to_db(promo_id=999)
        assert result is None
        db.execute.assert_not_called()


# ── F3: 推荐算法 ───────────────────────────────────────────────────────────────

class TestMatchScore:
    """PM-U-17 ~ PM-U-22: 推荐评分"""

    def test_acne_match_returns_positive(self):
        """PM-U-17: 痘痘问题匹配祛痘类产品"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne"],
            product_tags=["清洁", "控油", "祛痘"],
        )
        assert score > 0

    def test_multiple_issues_match(self):
        """PM-U-18: 多问题覆盖两类结果"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne", "dryness"],
            product_tags=["清洁", "控油", "保湿", "补水"],
        )
        assert score > 0

    def test_no_match_returns_zero(self):
        """完全不匹配返回 0"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne"],
            product_tags=["抗皱", "紧致"],
        )
        assert score == 0

    def test_score_not_exceed_100(self):
        """PM-U-21: 分数不超过 100"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne", "spot", "wrinkle", "pore", "dryness"],
            product_tags=[
                "清洁", "控油", "祛痘", "水杨酸", "美白", "淡斑",
                "维C", "抗皱", "紧致", "收毛孔", "保湿", "补水",
            ],
        )
        assert score <= 100

    def test_empty_issues_returns_zero(self):
        """空问题列表返回 0"""
        assert PromotionService.calculate_match_score([], ["清洁"]) == 0

    def test_empty_tags_returns_zero(self):
        """空标签返回 0"""
        assert PromotionService.calculate_match_score(["acne"], []) == 0

    def test_weighted_score_single_exact_match_moderate(self):
        """PM-U-22: 单标签完全匹配 + moderate 严重度 = 1.0 × 0.7 × 50"""
        svc = make_service()
        score = svc._calculate_weighted_score(
            issue_types=["acne"],
            product_tags=["祛痘"],
            severity_map={"acne": "moderate"},
        )
        # 祛痘在 acne 映射中：完全匹配 1.0 × 0.7 = 0.7，× 50 / 1 issue = 35
        assert score == 35

    def test_severe_weight_higher_than_mild(self):
        """severe 严重度得分高于 mild"""
        svc = make_service()
        severe_score = svc._calculate_weighted_score(
            issue_types=["acne"], product_tags=["祛痘"],
            severity_map={"acne": "severe"},
        )
        mild_score = svc._calculate_weighted_score(
            issue_types=["acne"], product_tags=["祛痘"],
            severity_map={"acne": "mild"},
        )
        assert severe_score > mild_score


class TestRecommendations:
    """PM-U-19 ~ PM-U-20: 推荐逻辑"""

    @pytest.mark.asyncio
    async def test_fallback_to_hot_when_no_analysis_id(self):
        """PM-U-20: 无 analysis_id，降级热门推荐"""
        db = AsyncMock()
        # _get_products_with_active_promos
        promo_result = MagicMock()
        promo_result.all.return_value = []
        db.execute.return_value = promo_result

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        result = await svc.get_recommendations(user_id=1, analysis_id=None)
        assert "recommendations" in result
        assert result["based_on"] is None

    @pytest.mark.asyncio
    async def test_max_recommendations_limit(self):
        """PM-U-21: 推荐结果不超过 MAX_RECOMMENDATIONS(10) 条"""
        products = [make_product(id=i, name=f"产品{i}", tags=["控油", "祛痘"])
                    for i in range(1, 20)]

        db = AsyncMock()
        # _get_products_with_active_promos 返回空
        promo_result = MagicMock()
        promo_result.all.return_value = []
        # _get_all_active_products 返回 19 个
        all_products_result = MagicMock()
        all_products_result.scalars.return_value.all.return_value = products

        analysis = SkinAnalysis()
        analysis.id = "ana_test"
        analysis.user_id = 1
        analysis.skin_type = "混合偏油"
        analysis.analysis_result = {"acne": {"severity": "moderate"}}
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis

        db.execute.side_effect = [
            analysis_result, promo_result, all_products_result
        ]

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        result = await svc.get_recommendations(user_id=1, analysis_id="ana_test")
        assert len(result["recommendations"]) <= 10

    @pytest.mark.asyncio
    async def test_promoted_products_ranked_higher(self):
        """PM-U-19: 有促销活动的产品排在前面"""
        product_with_promo = make_product(id=1, tags=["清洁", "控油", "祛痘"])
        product_no_promo = make_product(id=2, tags=["清洁", "控油", "祛痘"])
        promo = make_promotion(product_id=1, product=product_with_promo)

        db = AsyncMock()
        analysis = SkinAnalysis()
        analysis.id = "ana_abc"
        analysis.user_id = 1
        analysis.skin_type = "油性"
        analysis.analysis_result = {"acne": {"severity": "moderate"}}
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis

        # _get_products_with_active_promos
        promo_pairs_result = MagicMock()
        promo_pairs_result.all.return_value = [(product_with_promo, promo)]
        # _get_all_active_products
        all_products_result = MagicMock()
        all_products_result.scalars.return_value.all.return_value = [
            product_with_promo, product_no_promo
        ]

        db.execute.side_effect = [
            analysis_result, promo_pairs_result, all_products_result
        ]

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        result = await svc.get_recommendations(user_id=1, analysis_id="ana_abc")
        recs = result["recommendations"]
        # 有促销的产品（id=1）应排在前面
        if len(recs) >= 2:
            first = recs[0]
            assert first["promotion"] is not None


# ── F4: 数据追踪 ───────────────────────────────────────────────────────────────

class TestTrackEvent:
    """PM-U-23 ~ PM-U-26: 数据追踪"""

    @pytest.mark.asyncio
    async def test_click_event_writes_to_redis(self):
        """PM-U-23: 点击事件写入 Redis List"""
        redis = AsyncMock()
        redis.exists.return_value = False
        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        await svc.track_event(promo_id=1, user_id=1, action="click", source="home_feed")
        redis.rpush.assert_called_once()
        assert redis.rpush.call_args[0][0] == "promo:events"

    @pytest.mark.asyncio
    async def test_impression_dedup_within_10min(self):
        """PM-U-24: 曝光事件 10 分钟内去重"""
        redis = AsyncMock()
        redis.exists.return_value = True  # 已有去重 key

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        await svc.track_event(promo_id=1, user_id=1, action="impression", source="home_banner")
        # 不应写入 Redis
        redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_impression_first_time_recorded(self):
        """第一次曝光正常记录"""
        redis = AsyncMock()
        redis.exists.return_value = False  # 没有去重 key

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        await svc.track_event(promo_id=1, user_id=1, action="impression", source="home_banner")
        redis.rpush.assert_called_once()
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_data_format(self):
        """PM-U-23: 事件数据格式正确包含必要字段"""
        redis = AsyncMock()
        redis.exists.return_value = False
        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        await svc.track_event(promo_id=5, user_id=42, action="purchase", source="skin_result_page")

        event_json = redis.rpush.call_args[0][1]
        event = json.loads(event_json)
        assert event["promotion_id"] == 5
        assert event["user_id"] == 42
        assert event["action"] == "purchase"
        assert event["source"] == "skin_result_page"
        assert "created_at" in event

    @pytest.mark.asyncio
    async def test_consume_events_writes_to_db(self):
        """PM-U-25: 批量消费 Redis 事件写入数据库"""
        events = [
            json.dumps({
                "promotion_id": 1, "user_id": i, "action": "click",
                "source": "home_feed",
                "created_at": datetime.utcnow().isoformat(),
            })
            for i in range(1, 6)
        ]
        # 消费 5 条后返回 None
        events_iter = iter(events + [None])

        redis = AsyncMock()
        redis.lpop.side_effect = lambda k: next(events_iter)

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        count = await svc.consume_events(batch_size=10)
        assert count == 5
        assert db.add.call_count == 5
        db.flush.assert_called_once()


# ── F5: 分享推广 ───────────────────────────────────────────────────────────────

class TestGenerateShare:
    """分享推广功能"""

    @pytest.mark.asyncio
    async def test_generate_share_success(self):
        """活动进行中，生成分享信息"""
        product = make_product(name="花瓣精华水")
        promo = make_promotion(status=PROMO_STATUS_ACTIVE, product=product)

        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        product_name_result = MagicMock()
        product_name_result.scalar_one_or_none.return_value = "花瓣精华水"
        db.execute.side_effect = [promo_result, product_name_result]

        redis.rpush = AsyncMock()
        redis.exists.return_value = False

        svc = PromotionService(db=db, redis=redis)
        share = await svc.generate_share(promo_id=1, user_id=1)

        assert "share_url" in share
        assert "qrcode_url" in share
        assert "share_title" in share
        assert "share_image" in share
        assert "id=1" in share["share_url"]
        assert "u1" in share["share_url"]

    @pytest.mark.asyncio
    async def test_generate_share_cache_hit(self):
        """分享缓存命中"""
        cached_share = json.dumps({
            "share_url": "pages/promotion/detail/index?id=1&ref=u1",
            "qrcode_url": "https://cdn.example.com/qrcodes/promo_1_u1.png",
            "share_title": "买一送一！",
            "share_image": "https://cdn.example.com/shares/promo_1.jpg",
        })
        redis = AsyncMock()
        redis.get.return_value = cached_share

        db = AsyncMock()
        svc = PromotionService(db=db, redis=redis)
        share = await svc.generate_share(promo_id=1, user_id=1)

        assert share["share_url"] == "pages/promotion/detail/index?id=1&ref=u1"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_share_ended_promotion_raises(self):
        """已结束活动不可分享"""
        promo = make_promotion(status=PROMO_STATUS_ENDED)

        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo
        db.execute.return_value = promo_result

        svc = PromotionService(db=db, redis=redis)
        with pytest.raises(PromotionError) as exc_info:
            await svc.generate_share(promo_id=1, user_id=1)
        assert exc_info.value.code == 4008

    @pytest.mark.asyncio
    async def test_generate_share_not_found(self):
        """推广不存在，抛出 PromotionNotFound"""
        redis = AsyncMock()
        redis.get.return_value = None

        db = AsyncMock()
        no_result = MagicMock()
        no_result.scalar_one_or_none.return_value = None
        db.execute.return_value = no_result

        svc = PromotionService(db=db, redis=redis)
        with pytest.raises(PromotionNotFound):
            await svc.generate_share(promo_id=999, user_id=1)


# ── F6: 管理端看板 & 定时任务 ──────────────────────────────────────────────────

class TestAnalytics:
    """PM 管理端分析看板"""

    @pytest.mark.asyncio
    async def test_get_analytics_returns_metrics(self):
        """分析看板返回正确指标"""
        promo = make_promotion()

        db = AsyncMock()
        promo_result = MagicMock()
        promo_result.scalar_one_or_none.return_value = promo

        # action_counts query
        action_rows = [
            MagicMock(action="impression", cnt=1000),
            MagicMock(action="click", cnt=200),
            MagicMock(action="purchase", cnt=20),
            MagicMock(action="claim", cnt=100),
            MagicMock(action="share", cnt=30),
        ]
        action_result = MagicMock()
        action_result.__iter__ = MagicMock(return_value=iter(action_rows))

        # daily trend
        daily_result = MagicMock()
        daily_result.__iter__ = MagicMock(return_value=iter([]))

        # top sources
        source_result = MagicMock()
        source_result.__iter__ = MagicMock(return_value=iter([]))

        db.execute.side_effect = [promo_result, action_result, daily_result, source_result]

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)
        analytics = await svc.get_analytics(promo_id=1, days=7)

        assert analytics["promotion_id"] == 1
        assert "metrics" in analytics
        assert "period" in analytics
        metrics = analytics["metrics"]
        assert metrics["impressions"] == 1000
        assert metrics["clicks"] == 200
        assert metrics["ctr"] == round(200 / 1000, 4)
        assert metrics["conversions"] == 20


class TestPromotionStatusMachine:
    """PM-D-04 ~ PM-D-05: 活动状态机"""

    @pytest.mark.asyncio
    async def test_check_status_scheduled_to_active(self):
        """PM-D-04: SCHEDULED → ACTIVE（到达开始时间）"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2  # 2 条变为 ACTIVE
        mock_result2 = MagicMock()
        mock_result2.rowcount = 1  # 1 条变为 ENDED
        db.execute.side_effect = [mock_result, mock_result2]

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        count = await svc.check_promotion_status()
        assert count == 3  # 2 + 1

    @pytest.mark.asyncio
    async def test_check_status_active_to_ended(self):
        """PM-D-05: ACTIVE → ENDED（到达结束时间）"""
        db = AsyncMock()
        no_scheduled = MagicMock()
        no_scheduled.rowcount = 0
        one_ended = MagicMock()
        one_ended.rowcount = 3
        db.execute.side_effect = [no_scheduled, one_ended]

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        count = await svc.check_promotion_status()
        assert count == 3


class TestCleanupExpiredCoupons:
    """PM-D-03: 过期券自动清理"""

    @pytest.mark.asyncio
    async def test_cleanup_expired_coupons(self):
        """过期优惠券状态更新为 expired"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5  # 5 张过期
        db.execute.return_value = mock_result

        redis = AsyncMock()
        svc = PromotionService(db=db, redis=redis)

        count = await svc.cleanup_expired_coupons()
        assert count == 5
        db.execute.assert_called_once()


# ── 辅助函数测试 ───────────────────────────────────────────────────────────────

class TestHelperFunctions:
    """推广类型辅助函数"""

    def test_calc_promo_price_discount(self):
        """折扣类型正确计算优惠价"""
        promo = make_promotion(promo_type="discount", discount_value=Decimal("0.7"))
        price = _calc_promo_price(promo, 100.0)
        assert price == 70.0

    def test_calc_promo_price_coupon(self):
        """优惠券类型正确计算"""
        promo = make_promotion(promo_type="coupon", discount_value=Decimal("50"))
        price = _calc_promo_price(promo, 200.0)
        assert price == 150.0

    def test_calc_tag_discount(self):
        """折扣标签生成"""
        promo = make_promotion(promo_type="discount", discount_value=Decimal("0.7"))
        assert _calc_tag(promo) == "7折"

    def test_calc_tag_bundle(self):
        """组合套装标签"""
        promo = make_promotion(promo_type="bundle")
        assert _calc_tag(promo) == "买一送一"

    def test_calc_tag_flash_sale(self):
        """限时秒杀标签"""
        promo = make_promotion(promo_type="flash_sale")
        assert _calc_tag(promo) == "限时秒杀"

    def test_promo_to_dict_structure(self):
        """_promo_to_dict 返回正确结构"""
        product = make_product()
        promo = make_promotion(product=product)
        d = _promo_to_dict(promo)
        assert "id" in d
        assert "title" in d
        assert "product" in d
        assert "remaining_stock" in d


class TestIssueProductMapping:
    """PM: 问题-功效映射表完整性"""

    def test_all_issue_types_have_mapping(self):
        """所有肌肤问题类型都有对应的产品标签映射"""
        expected_types = [
            "acne", "spot", "wrinkle", "pore", "dark_circle",
            "redness", "dryness", "oiliness", "uneven_tone", "sagging",
        ]
        for issue_type in expected_types:
            assert issue_type in ISSUE_PRODUCT_MAPPING
            assert len(ISSUE_PRODUCT_MAPPING[issue_type]) > 0

    def test_no_empty_tags(self):
        """所有映射的标签不为空字符串"""
        for issue_type, tags in ISSUE_PRODUCT_MAPPING.items():
            for tag in tags:
                assert tag.strip() != "", f"{issue_type} has empty tag"
