"""
Open Beauty Facts API Client
────────────────────────────
通过条形码查询化妆品备案信息，数据源自开源化妆品数据库 Open Beauty Facts。

API 文档:  https://world.openbeautyfacts.org/data
接口格式:  GET https://world.openbeautyfacts.org/api/v2/product/{barcode}.json
许可:      Open Database License (ODbL)
"""
import json
import logging
from typing import Optional

import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────
OBF_API_BASE = "https://world.openbeautyfacts.org/api/v2/product"
OBF_TIMEOUT = 10  # 秒
OBF_USER_AGENT = "PetalApp/1.0 (contact: dev@petal.com)"

# 只拉取需要的字段，减少网络传输
OBF_FIELDS = (
    "code,product_name,brands,categories,image_url,"
    "ingredients_text,labels,quantity,packaging"
)

# Redis 缓存
CACHE_KEY_BARCODE = "obf:barcode:{barcode}"
CACHE_TTL_HIT = 86400 * 7       # 查到产品：缓存 7 天
CACHE_TTL_MISS = 3600            # 未查到：缓存 1 小时（避免频繁请求 OBF）


class OpenBeautyService:
    """
    条形码查询服务 — 对接 Open Beauty Facts 开源化妆品数据库。

    流程:
    1. Redis 缓存命中 → 直接返回
    2. 缓存未命中 → 调用 OBF API
    3. 结果写入 Redis 缓存
    4. OBF 无数据 → 返回 None（前端提示"暂未收录"）
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def lookup_barcode(self, barcode: str) -> Optional[dict]:
        """
        通过条形码查询化妆品产品信息。

        返回格式:
        {
            "barcode": "3337875597371",
            "product_name": "CeraVe Moisturizing Cream",
            "brand": "CeraVe",
            "category": "Moisturizers",
            "image_url": "https://...",
            "ingredients": "Water, Glycerin, ...",
            "labels": "Dermatologist Tested",
            "quantity": "50ml",
            "source": "Open Beauty Facts",
            "source_url": "https://world.openbeautyfacts.org/product/3337875597371"
        }

        未找到时返回 None。
        """
        barcode = barcode.strip()

        # 1. 查缓存
        cached = await self._get_cached(barcode)
        if cached is not None:
            return cached if cached != "__MISS__" else None

        # 2. 调用 OBF API
        product = await self._fetch_from_obf(barcode)

        # 3. 写缓存
        if product:
            await self.redis.setex(
                CACHE_KEY_BARCODE.format(barcode=barcode),
                CACHE_TTL_HIT,
                json.dumps(product, ensure_ascii=False),
            )
        else:
            await self.redis.setex(
                CACHE_KEY_BARCODE.format(barcode=barcode),
                CACHE_TTL_MISS,
                '"__MISS__"',
            )

        return product

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _get_cached(self, barcode: str) -> Optional:
        """返回缓存结果。None=缓存未命中；"__MISS__"=之前查过但OBF无数据。"""
        key = CACHE_KEY_BARCODE.format(barcode=barcode)
        raw = await self.redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def _fetch_from_obf(self, barcode: str) -> Optional[dict]:
        """调用 Open Beauty Facts API 查询条形码。"""
        url = f"{OBF_API_BASE}/{barcode}.json"
        params = {"fields": OBF_FIELDS}
        headers = {"User-Agent": OBF_USER_AGENT}

        try:
            async with httpx.AsyncClient(timeout=OBF_TIMEOUT) as client:
                resp = await client.get(url, params=params, headers=headers)

            if resp.status_code != 200:
                logger.warning("OBF API returned %d for barcode %s", resp.status_code, barcode)
                return None

            data = resp.json()

            # OBF 返回 status=0 表示产品不存在
            if data.get("status") == 0 or "product" not in data:
                return None

            p = data["product"]
            product_name = p.get("product_name", "").strip()
            if not product_name:
                return None  # 有条码但没有产品名的脏数据

            return {
                "barcode": barcode,
                "product_name": product_name,
                "brand": p.get("brands", "").strip() or "未知品牌",
                "category": p.get("categories", "").strip() or "化妆品",
                "image_url": p.get("image_url"),
                "ingredients": p.get("ingredients_text", "").strip() or None,
                "labels": p.get("labels", "").strip() or None,
                "quantity": p.get("quantity", "").strip() or None,
                "source": "Open Beauty Facts",
                "source_url": f"https://world.openbeautyfacts.org/product/{barcode}",
            }

        except httpx.TimeoutException:
            logger.error("OBF API timeout for barcode %s", barcode)
            return None
        except Exception:
            logger.exception("OBF API error for barcode %s", barcode)
            return None
