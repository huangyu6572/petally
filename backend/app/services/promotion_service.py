"""
Promotion Service
功能点:
  F1 - 推广活动列表 & 详情 (Redis 缓存)
  F2 - 优惠券领取 (幂等性 + Redis 原子库存扣减)
  F3 - 个性化推荐 (AI分析结果匹配 + 热门降级)
  F4 - 数据追踪 (埋点事件 + 曝光去重)
  F5 - 分享推广 (生成分享信息)
  F6 - 管理端分析看板 + 定时任务 (状态机 + 库存同步)
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from redis.asyncio import Redis
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.models import Promotion, Product, Coupon, PromoClick, SkinAnalysis

# ── 错误码常量 ──────────────────────────────────────────────────────────────
ERR_PROMO_NOT_FOUND = 4001
ERR_PROMO_NOT_STARTED = 4002
ERR_PROMO_ENDED = 4003
ERR_COUPON_SOLD_OUT = 4004
ERR_COUPON_ALREADY_CLAIMED = 4005
ERR_COUPON_EXPIRED = 4006
ERR_STOCK_INSUFFICIENT = 4007
ERR_SHARE_NOT_ALLOWED = 4008

# ── 推广活动状态 ─────────────────────────────────────────────────────────────
PROMO_STATUS_DRAFT = 0
PROMO_STATUS_SCHEDULED = 1
PROMO_STATUS_ACTIVE = 2
PROMO_STATUS_ENDED = 3
PROMO_STATUS_STOPPED = 4

# ── 推荐：问题-功效映射表 ────────────────────────────────────────────────────
ISSUE_PRODUCT_MAPPING = {
    "acne": ["清洁", "控油", "祛痘", "水杨酸"],
    "spot": ["美白", "淡斑", "维C", "烟酰胺"],
    "wrinkle": ["抗皱", "紧致", "视黄醇", "胶原蛋白"],
    "pore": ["收毛孔", "控油", "清洁"],
    "dark_circle": ["眼霜", "淡化黑眼圈", "咖啡因"],
    "redness": ["舒缓", "修护", "敏感肌专用"],
    "dryness": ["保湿", "补水", "透明质酸", "神经酰胺"],
    "oiliness": ["控油", "清爽", "哑光"],
    "uneven_tone": ["均匀肤色", "提亮", "美白"],
    "sagging": ["紧致", "提拉", "胶原蛋白"],
}

# 严重度权重
SEVERITY_WEIGHTS = {"severe": 1.0, "moderate": 0.7, "mild": 0.4}

# Redis key 前缀
REDIS_KEY_PROMO_LIST = "promo:list:{category}:{page}:{size}"
REDIS_KEY_PROMO_DETAIL = "promo:detail:{promo_id}"
REDIS_KEY_PROMO_STOCK = "promo:stock:{promo_id}"
REDIS_KEY_PROMO_IMPRESSION = "promo:imp:{user_id}:{promo_id}"
REDIS_KEY_PROMO_EVENTS = "promo:events"
REDIS_KEY_SHARE_CACHE = "promo:share:{promo_id}:{user_id}"

CACHE_TTL_LIST = 60       # 列表缓存 60s
CACHE_TTL_DETAIL = 300    # 详情缓存 5min
IMPRESSION_DEDUP_TTL = 600  # 曝光去重 10min

# 优惠券有效期（天）
COUPON_VALID_DAYS = 30
# 最大推荐数量
MAX_RECOMMENDATIONS = 10


# ── 业务异常 ─────────────────────────────────────────────────────────────────
class PromotionError(Exception):
    def __init__(self, code: int, message: str, data: Optional[dict] = None):
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(message)


class PromotionNotFound(PromotionError):
    def __init__(self):
        super().__init__(ERR_PROMO_NOT_FOUND, "推广活动不存在")


class PromotionNotStarted(PromotionError):
    def __init__(self, start_time: datetime):
        super().__init__(ERR_PROMO_NOT_STARTED, "推广活动未开始",
                         {"start_time": start_time.isoformat()})


class PromotionEnded(PromotionError):
    def __init__(self):
        super().__init__(ERR_PROMO_ENDED, "推广活动已结束")


class CouponSoldOut(PromotionError):
    def __init__(self):
        super().__init__(ERR_COUPON_SOLD_OUT, "优惠券已领完")


class CouponAlreadyClaimed(PromotionError):
    def __init__(self, coupon: dict):
        super().__init__(ERR_COUPON_ALREADY_CLAIMED, "已领取过优惠券", coupon)


class StockInsufficient(PromotionError):
    def __init__(self):
        super().__init__(ERR_STOCK_INSUFFICIENT, "库存不足")


# ─────────────────────────────────────────────────────────────────────────────


def _promo_to_dict(promo: Promotion, product: Optional[Product] = None) -> dict:
    """将 ORM 对象转为可序列化字典（用于缓存 & 响应）。"""
    product = product or promo.product
    original_price = float(product.price) if product and product.price else 0.0
    promo_price = _calc_promo_price(promo, original_price)
    tag = _calc_tag(promo)

    return {
        "id": promo.id,
        "title": promo.title,
        "description": promo.description,
        "promo_type": promo.promo_type,
        "product": {
            "id": product.id if product else 0,
            "name": product.name if product else "",
            "cover_image": product.cover_image if product else None,
            "original_price": original_price,
            "promo_price": promo_price,
            "tag": tag,
        },
        "start_time": promo.start_time.isoformat() if promo.start_time else None,
        "end_time": promo.end_time.isoformat() if promo.end_time else None,
        "remaining_stock": promo.stock,
        "status": promo.status,
    }


def _calc_promo_price(promo: Promotion, original_price: float) -> Optional[float]:
    """根据推广类型计算优惠价格。"""
    if not promo.discount_value:
        return original_price
    v = float(promo.discount_value)
    if promo.promo_type == "discount":
        # v 是折扣率, e.g. 0.7 = 7折
        return round(original_price * v, 2)
    elif promo.promo_type in ("coupon", "flash_sale", "new_user"):
        # v 是直减金额
        return max(0.0, round(original_price - v, 2))
    return original_price


def _calc_tag(promo: Promotion) -> Optional[str]:
    """生成推广标签文案。"""
    type_tag_map = {
        "bundle": "买一送一",
        "flash_sale": "限时秒杀",
        "new_user": "新人专享",
        "ai_recommend": "AI专属",
    }
    if promo.promo_type in type_tag_map:
        return type_tag_map[promo.promo_type]
    if promo.promo_type == "discount" and promo.discount_value:
        discount_pct = int(float(promo.discount_value) * 10)
        return f"{discount_pct}折"
    if promo.promo_type == "coupon" and promo.discount_value and promo.min_purchase:
        return f"满{int(float(promo.min_purchase))}减{int(float(promo.discount_value))}"
    return None


class PromotionService:
    """
    商品推广业务逻辑层。

    约束:
    1. get_active_promotions() 优先 Redis 缓存
    2. claim_coupon() 保证幂等性，Redis DECR 原子扣库存
    3. recommend() 关联 AI 分析结果，无分析时降级热门推荐，最多返回 10 条
    4. track_event() 异步写入 Redis List，曝光 10min 内去重
    5. 活动状态通过定时任务自动管理 (check_promotion_status)
    """

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    # ── F1: 推广活动列表 & 详情 ────────────────────────────────────────────

    async def get_active_promotions(
        self, page: int, size: int, category: Optional[str] = None
    ) -> dict:
        """获取活跃推广列表，优先 Redis 缓存。"""
        cache_key = REDIS_KEY_PROMO_LIST.format(
            category=category or "all", page=page, size=size
        )
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        offset = (page - 1) * size
        stmt = (
            select(Promotion)
            .options(selectinload(Promotion.product))
            .where(Promotion.status == PROMO_STATUS_ACTIVE)
        )
        if category:
            stmt = stmt.join(Product, Promotion.product_id == Product.id).where(
                Product.category == category
            )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.offset(offset).limit(size)
        result = await self.db.execute(stmt)
        promotions = result.scalars().all()

        items = [_promo_to_dict(p) for p in promotions]
        payload = {"total": total, "items": items}

        await self.redis.setex(cache_key, CACHE_TTL_LIST, json.dumps(payload, default=str))
        return payload

    async def get_detail(self, promo_id: int) -> dict:
        """获取推广详情，优先 Redis 缓存。"""
        cache_key = REDIS_KEY_PROMO_DETAIL.format(promo_id=promo_id)
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        stmt = (
            select(Promotion)
            .options(selectinload(Promotion.product))
            .where(Promotion.id == promo_id)
        )
        result = await self.db.execute(stmt)
        promo = result.scalar_one_or_none()
        if not promo:
            raise PromotionNotFound()

        detail = _promo_to_dict(promo)
        detail["rules"] = self._build_rules_text(promo)
        await self.redis.setex(cache_key, CACHE_TTL_DETAIL, json.dumps(detail, default=str))
        return detail

    @staticmethod
    def _build_rules_text(promo: Promotion) -> str:
        lines = []
        if promo.start_time and promo.end_time:
            lines.append(
                f"活动时间：{promo.start_time.strftime('%Y-%m-%d')} 至 "
                f"{promo.end_time.strftime('%Y-%m-%d')}"
            )
        if promo.stock is not None:
            lines.append(f"活动库存：{promo.stock} 件")
        if promo.promo_type == "coupon" and promo.min_purchase:
            lines.append(
                f"优惠规则：满 {float(promo.min_purchase):.0f} 元减 "
                f"{float(promo.discount_value):.0f} 元"
            )
        lines.append("每人限领一张优惠券，领完即止。")
        return "；".join(lines)

    # ── F2: 优惠券领取 ──────────────────────────────────────────────────────

    async def claim_coupon(self, promo_id: int, user_id: int) -> dict:
        """
        领取优惠券，保证幂等性。
        流程: 查重 → 检查状态 → Redis原子扣库存 → 写DB → 异步同步库存
        """
        # 1. 幂等检查：已领过则返回已有券
        existing = await self._get_user_coupon(promo_id, user_id)
        if existing:
            raise CouponAlreadyClaimed(self._coupon_to_dict(existing))

        # 2. 获取推广并校验状态
        promo = await self._get_promotion_or_raise(promo_id)
        now = datetime.utcnow()
        if promo.status == PROMO_STATUS_SCHEDULED or (
            promo.start_time and promo.start_time > now
        ):
            raise PromotionNotStarted(promo.start_time)
        if promo.status in (PROMO_STATUS_ENDED, PROMO_STATUS_STOPPED) or (
            promo.end_time and promo.end_time < now
        ):
            raise PromotionEnded()

        # 3. Redis 原子扣库存
        stock_key = REDIS_KEY_PROMO_STOCK.format(promo_id=promo_id)
        # 初始化 Redis 库存（首次领券时同步数据库库存到 Redis）
        if not await self.redis.exists(stock_key):
            await self.redis.set(stock_key, promo.stock)

        remaining = await self.redis.decr(stock_key)
        if remaining < 0:
            # 回滚
            await self.redis.incr(stock_key)
            raise CouponSoldOut()

        # 4. 创建优惠券记录
        coupon_id = f"cpn_{datetime.utcnow().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        valid_until = now + timedelta(days=COUPON_VALID_DAYS)

        # 决定优惠券类型
        discount_type = "amount"
        if promo.promo_type == "discount":
            discount_type = "percent"
        elif promo.promo_type in ("coupon", "flash_sale", "new_user", "ai_recommend"):
            discount_type = "amount"

        coupon = Coupon(
            id=coupon_id,
            promotion_id=promo_id,
            user_id=user_id,
            discount_type=discount_type,
            discount_value=promo.discount_value,
            min_purchase=promo.min_purchase,
            valid_until=valid_until,
            status="unused",
        )
        self.db.add(coupon)
        await self.db.flush()

        # 5. 异步同步数据库库存（写回DB）
        await self._sync_db_stock(promo_id, int(remaining))

        # 若库存降为 0，自动更新活动状态
        if remaining == 0:
            await self.db.execute(
                update(Promotion)
                .where(Promotion.id == promo_id)
                .values(stock=0, status=PROMO_STATUS_ENDED)
            )

        return self._coupon_to_dict(coupon)

    async def _get_user_coupon(self, promo_id: int, user_id: int) -> Optional[Coupon]:
        stmt = select(Coupon).where(
            and_(Coupon.promotion_id == promo_id, Coupon.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_promotion_or_raise(self, promo_id: int) -> Promotion:
        stmt = select(Promotion).where(Promotion.id == promo_id)
        result = await self.db.execute(stmt)
        promo = result.scalar_one_or_none()
        if not promo:
            raise PromotionNotFound()
        return promo

    async def _sync_db_stock(self, promo_id: int, remaining: int) -> None:
        """将 Redis 库存写回数据库（最终一致性）。"""
        await self.db.execute(
            update(Promotion)
            .where(Promotion.id == promo_id)
            .values(stock=remaining)
        )

    @staticmethod
    def _coupon_to_dict(coupon: Coupon) -> dict:
        return {
            "coupon_id": coupon.id,
            "discount_type": coupon.discount_type,
            "discount_value": float(coupon.discount_value) if coupon.discount_value else 0.0,
            "min_purchase": float(coupon.min_purchase) if coupon.min_purchase else None,
            "valid_until": coupon.valid_until.isoformat() if coupon.valid_until else None,
            "status": coupon.status,
        }

    # ── F3: 个性化推荐 ──────────────────────────────────────────────────────

    async def get_recommendations(
        self, user_id: int, analysis_id: Optional[str] = None
    ) -> dict:
        if analysis_id:
            return await self._recommend_by_analysis(user_id, analysis_id)
        return await self._recommend_hot(user_id)

    async def _recommend_by_analysis(self, user_id: int, analysis_id: str) -> dict:
        """基于 AI 肌肤分析结果推荐产品。"""
        # 获取分析结果
        stmt = select(SkinAnalysis).where(SkinAnalysis.id == analysis_id)
        result = await self.db.execute(stmt)
        analysis = result.scalar_one_or_none()

        if not analysis or not analysis.analysis_result:
            # 降级
            return await self._recommend_hot(user_id)

        # 提取主要问题（severity >= mild）
        issues = []  # [{type, severity}]
        analysis_result = analysis.analysis_result
        if isinstance(analysis_result, dict):
            for issue_key, issue_data in analysis_result.items():
                if isinstance(issue_data, dict):
                    severity = issue_data.get("severity", "")
                    if severity in SEVERITY_WEIGHTS:
                        issues.append({"type": issue_key, "severity": severity})
                elif issue_key in ISSUE_PRODUCT_MAPPING:
                    issues.append({"type": issue_key, "severity": "mild"})

        if not issues:
            return await self._recommend_hot(user_id)

        issue_types = [i["type"] for i in issues]
        severity_map = {i["type"]: i["severity"] for i in issues}

        # 获取所有上架产品（含活跃推广）
        products_with_promos = await self._get_products_with_active_promos()
        all_products = await self._get_all_active_products()

        # 合并并计算分数
        seen_ids = set()
        candidates = []
        for product, promo in products_with_promos:
            if product.id in seen_ids:
                continue
            seen_ids.add(product.id)
            tags = product.tags or []
            score = self._calculate_weighted_score(issue_types, tags, severity_map)
            if score > 0:
                candidates.append((product, promo, score))

        for product in all_products:
            if product.id in seen_ids:
                continue
            seen_ids.add(product.id)
            tags = product.tags or []
            score = self._calculate_weighted_score(issue_types, tags, severity_map)
            if score > 0:
                candidates.append((product, None, score))

        # 排序：有促销优先，同分按 score 降序
        candidates.sort(key=lambda x: (0 if x[1] else 1, -x[2]))
        candidates = candidates[:MAX_RECOMMENDATIONS]

        recommendations = []
        for product, promo, score in candidates:
            reason = self._build_match_reason(issue_types, product.tags or [], product.name)
            rec = {
                "product_id": product.id,
                "name": product.name,
                "match_reason": reason,
                "match_score": score,
                "promotion": None,
            }
            if promo:
                original_price = float(product.price) if product.price else 0.0
                rec["promotion"] = {
                    "id": promo.id,
                    "promo_price": _calc_promo_price(promo, original_price),
                    "original_price": original_price,
                    "tag": _calc_tag(promo),
                }
            recommendations.append(rec)

        skin_type = analysis.skin_type or "未知"
        main_issues = issue_types[:3]
        return {
            "based_on": {"skin_type": skin_type, "main_issues": main_issues},
            "recommendations": recommendations,
        }

    async def _recommend_hot(self, user_id: int) -> dict:
        """无 AI 分析时，降级为热门推荐（按曝光量排序）。"""
        # 热门: 取有活跃推广的产品（最多 MAX_RECOMMENDATIONS 个）
        products_with_promos = await self._get_products_with_active_promos()
        recommendations = []
        for product, promo in products_with_promos[:MAX_RECOMMENDATIONS]:
            original_price = float(product.price) if product.price else 0.0
            rec = {
                "product_id": product.id,
                "name": product.name,
                "match_reason": "热门推荐",
                "match_score": 0,
                "promotion": None,
            }
            if promo:
                rec["promotion"] = {
                    "id": promo.id,
                    "promo_price": _calc_promo_price(promo, original_price),
                    "original_price": original_price,
                    "tag": _calc_tag(promo),
                }
            recommendations.append(rec)
        return {"based_on": None, "recommendations": recommendations}

    async def _get_products_with_active_promos(self) -> List[tuple]:
        """获取有活跃推广的产品列表。"""
        now = datetime.utcnow()
        stmt = (
            select(Product, Promotion)
            .join(Promotion, Promotion.product_id == Product.id)
            .where(
                and_(
                    Promotion.status == PROMO_STATUS_ACTIVE,
                    Product.status == 1,
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def _get_all_active_products(self) -> List[Product]:
        """获取所有上架产品。"""
        stmt = select(Product).where(Product.status == 1)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def _calculate_weighted_score(
        issue_types: List[str],
        product_tags: List[str],
        severity_map: dict,
    ) -> int:
        """
        加权匹配分数：
        match_score = Σ(标签匹配权重 × 问题严重度权重) × 100 / issue_count
        """
        if not issue_types or not product_tags:
            return 0
        total = 0.0
        for issue_type in issue_types:
            target_tags = ISSUE_PRODUCT_MAPPING.get(issue_type, [])
            severity_weight = SEVERITY_WEIGHTS.get(
                severity_map.get(issue_type, "mild"), 0.4
            )
            for tag in target_tags:
                if tag in product_tags:
                    total += 1.0 * severity_weight
                elif any(t in tag or tag in t for t in product_tags):
                    total += 0.6 * severity_weight
        if total == 0:
            return 0
        return min(100, int((total / len(issue_types)) * 50))

    @staticmethod
    def _build_match_reason(
        issue_types: List[str], product_tags: List[str], product_name: str
    ) -> str:
        issue_zh = {
            "acne": "痘痘", "spot": "色斑", "wrinkle": "皱纹",
            "pore": "毛孔", "dark_circle": "黑眼圈", "redness": "泛红",
            "dryness": "干燥", "oiliness": "出油", "uneven_tone": "肤色不均",
            "sagging": "松弛",
        }
        matched_issues = [issue_zh.get(i, i) for i in issue_types
                          if any(t in product_tags for t in ISSUE_PRODUCT_MAPPING.get(i, []))]
        if matched_issues:
            return f"针对{'/'.join(matched_issues[:2])}问题，适合您的肤质"
        return f"{product_name}，综合护肤推荐"

    @staticmethod
    def calculate_match_score(issue_types: List[str], product_tags: List[str]) -> int:
        """
        计算产品匹配度分数 (0-100)，不含严重度权重，供外部简单调用。
        完全匹配: 1.0, 部分匹配: 0.6
        """
        if not issue_types or not product_tags:
            return 0
        total_score = 0.0
        matched = 0
        for issue_type in issue_types:
            target_tags = ISSUE_PRODUCT_MAPPING.get(issue_type, [])
            for tag in target_tags:
                if tag in product_tags:
                    total_score += 1.0
                    matched += 1
                elif any(t in tag or tag in t for t in product_tags):
                    total_score += 0.6
                    matched += 1
        if matched == 0:
            return 0
        return min(100, int((total_score / max(len(issue_types), 1)) * 50))

    # ── F4: 数据追踪 & 埋点 ────────────────────────────────────────────────

    async def track_event(
        self, promo_id: int, user_id: int, action: str, source: str
    ) -> None:
        """
        异步记录推广事件到 Redis List，由消费者批量写入 DB。
        曝光事件 10 分钟内去重。
        """
        # 曝光去重
        if action == "impression":
            dedup_key = REDIS_KEY_PROMO_IMPRESSION.format(
                user_id=user_id, promo_id=promo_id
            )
            if await self.redis.exists(dedup_key):
                return
            await self.redis.setex(dedup_key, IMPRESSION_DEDUP_TTL, "1")

        event = json.dumps({
            "promotion_id": promo_id,
            "user_id": user_id,
            "action": action,
            "source": source,
            "created_at": datetime.utcnow().isoformat(),
        })
        await self.redis.rpush(REDIS_KEY_PROMO_EVENTS, event)

    async def consume_events(self, batch_size: int = 100) -> int:
        """
        从 Redis List 批量消费事件并写入数据库。
        返回实际消费的事件数量。
        """
        events = []
        for _ in range(batch_size):
            raw = await self.redis.lpop(REDIS_KEY_PROMO_EVENTS)
            if raw is None:
                break
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue

        if not events:
            return 0

        clicks = [
            PromoClick(
                promotion_id=e["promotion_id"],
                user_id=e["user_id"],
                action=e["action"],
                source=e["source"],
                created_at=datetime.fromisoformat(e["created_at"]),
            )
            for e in events
        ]
        for click in clicks:
            self.db.add(click)
        await self.db.flush()
        return len(clicks)

    # ── F5: 分享推广 ───────────────────────────────────────────────────────

    async def generate_share(self, promo_id: int, user_id: int) -> dict:
        """生成推广分享信息（小程序码 + 分享文案），带缓存。"""
        cache_key = REDIS_KEY_SHARE_CACHE.format(promo_id=promo_id, user_id=user_id)
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        promo = await self._get_promotion_or_raise(promo_id)
        if promo.status not in (PROMO_STATUS_ACTIVE, PROMO_STATUS_SCHEDULED):
            raise PromotionError(ERR_SHARE_NOT_ALLOWED, "活动不可分享")

        share_url = (
            f"pages/promotion/detail/index?id={promo_id}&ref=u{user_id}"
        )
        qrcode_url = (
            f"https://cdn.example.com/qrcodes/promo_{promo_id}_u{user_id}.png"
        )

        # 获取产品名称用于分享文案
        product_name = ""
        if promo.product_id:
            stmt = select(Product.name).where(Product.id == promo.product_id)
            result = await self.db.execute(stmt)
            product_name = result.scalar_one_or_none() or ""

        tag = _calc_tag(promo)
        if tag:
            share_title = f"{product_name}{tag}，快来看看！"
        else:
            share_title = f"{promo.title}，快来看看！"

        share_info = {
            "share_url": share_url,
            "qrcode_url": qrcode_url,
            "share_title": share_title,
            "share_image": f"https://cdn.example.com/shares/promo_{promo_id}.jpg",
        }
        # 缓存分享信息（有效期与活动结束时间一致，最长 1 天）
        ttl = 86400
        if promo.end_time:
            remaining_secs = int((promo.end_time - datetime.utcnow()).total_seconds())
            ttl = max(60, min(ttl, remaining_secs))
        await self.redis.setex(cache_key, ttl, json.dumps(share_info))

        # 记录分享事件
        await self.track_event(promo_id, user_id, "share", "share")
        return share_info

    # ── F6: 管理端分析看板 + 定时任务 ─────────────────────────────────────

    async def get_analytics(self, promo_id: int, days: int = 7) -> dict:
        """
        获取推广数据看板（管理端）。
        返回 impressions / clicks / CTR / coupon_claimed / conversions 等指标。
        """
        promo = await self._get_promotion_or_raise(promo_id)
        start = datetime.utcnow() - timedelta(days=days)

        stmt = select(
            PromoClick.action,
            func.count(PromoClick.id).label("cnt"),
        ).where(
            and_(
                PromoClick.promotion_id == promo_id,
                PromoClick.created_at >= start,
            )
        ).group_by(PromoClick.action)
        result = await self.db.execute(stmt)
        action_counts = {row.action: row.cnt for row in result}

        impressions = action_counts.get("impression", 0)
        clicks = action_counts.get("click", 0)
        conversions = action_counts.get("purchase", 0)
        coupon_claimed = action_counts.get("claim", 0)
        share_count = action_counts.get("share", 0)

        ctr = round(clicks / impressions, 4) if impressions else 0.0
        conv_rate = round(conversions / clicks, 4) if clicks else 0.0

        # 每日趋势（简化：聚合 action=click）
        daily_stmt = select(
            func.date(PromoClick.created_at).label("date"),
            func.count(PromoClick.id).label("cnt"),
        ).where(
            and_(
                PromoClick.promotion_id == promo_id,
                PromoClick.action == "click",
                PromoClick.created_at >= start,
            )
        ).group_by(func.date(PromoClick.created_at)).order_by(func.date(PromoClick.created_at))
        daily_result = await self.db.execute(daily_stmt)
        daily_trend = [
            {"date": str(row.date), "clicks": row.cnt}
            for row in daily_result
        ]

        # 来源分析
        source_stmt = select(
            PromoClick.source,
            func.count(PromoClick.id).label("cnt"),
        ).where(
            and_(
                PromoClick.promotion_id == promo_id,
                PromoClick.action == "click",
                PromoClick.created_at >= start,
            )
        ).group_by(PromoClick.source).order_by(func.count(PromoClick.id).desc()).limit(5)
        source_result = await self.db.execute(source_stmt)
        top_sources = [
            {"source": row.source, "clicks": row.cnt}
            for row in source_result
        ]

        period_start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        period_end = datetime.utcnow().strftime("%Y-%m-%d")
        return {
            "promotion_id": promo_id,
            "period": f"{period_start} ~ {period_end}",
            "metrics": {
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "coupon_claimed": coupon_claimed,
                "conversions": conversions,
                "conversion_rate": conv_rate,
                "share_count": share_count,
            },
            "daily_trend": daily_trend,
            "top_sources": top_sources,
        }

    async def check_promotion_status(self) -> int:
        """
        定时任务：检查并自动更新推广活动状态。
        SCHEDULED → ACTIVE（到达开始时间）
        ACTIVE → ENDED（到达结束时间）
        返回更新的记录数。
        """
        now = datetime.utcnow()
        count = 0

        # SCHEDULED → ACTIVE
        result = await self.db.execute(
            update(Promotion)
            .where(
                and_(
                    Promotion.status == PROMO_STATUS_SCHEDULED,
                    Promotion.start_time <= now,
                )
            )
            .values(status=PROMO_STATUS_ACTIVE)
        )
        count += result.rowcount

        # ACTIVE → ENDED
        result = await self.db.execute(
            update(Promotion)
            .where(
                and_(
                    Promotion.status == PROMO_STATUS_ACTIVE,
                    Promotion.end_time <= now,
                )
            )
            .values(status=PROMO_STATUS_ENDED)
        )
        count += result.rowcount
        return count

    async def sync_stock_to_db(self, promo_id: int) -> Optional[int]:
        """
        定时任务：将 Redis 库存同步回数据库。
        返回同步后的库存值，如 Redis 无记录则返回 None。
        """
        stock_key = REDIS_KEY_PROMO_STOCK.format(promo_id=promo_id)
        stock_val = await self.redis.get(stock_key)
        if stock_val is None:
            return None
        stock = int(stock_val)
        await self.db.execute(
            update(Promotion).where(Promotion.id == promo_id).values(stock=stock)
        )
        return stock

    async def cleanup_expired_coupons(self) -> int:
        """
        定时任务：将过期优惠券状态更新为 expired。
        返回更新数量。
        """
        now = datetime.utcnow()
        result = await self.db.execute(
            update(Coupon)
            .where(and_(Coupon.status == "unused", Coupon.valid_until < now))
            .values(status="expired")
        )
        return result.rowcount
