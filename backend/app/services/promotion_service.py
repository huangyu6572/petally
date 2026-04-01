"""
Promotion Service
"""
from typing import Optional, List
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


# 问题-功效映射表 (AI 推荐核心)
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


class PromotionService:
    """
    商品推广业务逻辑层。

    约束:
    1. get_active_promotions() 优先 Redis 缓存
    2. claim_coupon() 保证幂等性
    3. recommend() 关联 AI 分析结果，无分析时降级热门推荐
    4. track_event() 异步处理不阻塞
    5. 活动状态通过定时任务自动管理
    """

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    async def get_active_promotions(
        self, page: int, size: int, category: Optional[str] = None
    ) -> dict:
        # 1. Try Redis cache
        # 2. Fallback to DB
        raise NotImplementedError

    async def get_detail(self, promo_id: int) -> dict:
        raise NotImplementedError

    async def claim_coupon(self, promo_id: int, user_id: int) -> dict:
        # 1. 检查用户是否已领取 (幂等性)
        # 2. 检查活动状态 (ACTIVE?)
        # 3. Redis DECR 预扣库存
        # 4. 如果库存 < 0，INCR 回滚，返回已领完
        # 5. 创建优惠券记录
        # 6. 异步同步数据库库存
        raise NotImplementedError

    async def get_recommendations(
        self, user_id: int, analysis_id: Optional[str] = None
    ) -> dict:
        if analysis_id:
            return await self._recommend_by_analysis(user_id, analysis_id)
        return await self._recommend_hot(user_id)

    async def track_event(
        self, promo_id: int, user_id: int, action: str, source: str
    ) -> None:
        """异步记录推广事件到 Redis List，由消费者批量写入 DB。"""
        import json
        from datetime import datetime

        event = json.dumps({
            "promotion_id": promo_id,
            "user_id": user_id,
            "action": action,
            "source": source,
            "created_at": datetime.utcnow().isoformat(),
        })
        await self.redis.rpush("promo:events", event)

    async def generate_share(self, promo_id: int, user_id: int) -> dict:
        raise NotImplementedError

    async def _recommend_by_analysis(self, user_id: int, analysis_id: str) -> dict:
        """基于 AI 肌肤分析结果推荐产品。"""
        # 1. 获取分析结果
        # 2. 提取主要问题
        # 3. 匹配产品标签
        # 4. 计算 match_score
        # 5. 优先展示有促销的产品
        raise NotImplementedError

    async def _recommend_hot(self, user_id: int) -> dict:
        """无 AI 分析时，降级为热门推荐。"""
        raise NotImplementedError

    @staticmethod
    def calculate_match_score(issue_types: List[str], product_tags: List[str]) -> int:
        """
        计算产品匹配度分数 (0-100)。
        完全匹配: 1.0, 部分匹配: 0.6, 品类匹配: 0.3
        """
        if not issue_types or not product_tags:
            return 0

        total_score = 0
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
