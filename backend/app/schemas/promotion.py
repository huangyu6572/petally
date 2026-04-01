"""
Promotion Module — Pydantic Schemas
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from enum import Enum


class PromoType(str, Enum):
    DISCOUNT = "discount"
    COUPON = "coupon"
    BUNDLE = "bundle"
    FLASH_SALE = "flash_sale"
    NEW_USER = "new_user"
    AI_RECOMMEND = "ai_recommend"


class CouponType(str, Enum):
    AMOUNT = "amount"
    PERCENT = "percent"
    NO_THRESHOLD = "no_threshold"


class TrackAction(str, Enum):
    IMPRESSION = "impression"
    CLICK = "click"
    VIEW = "view"
    CLAIM = "claim"
    SHARE = "share"
    PURCHASE = "purchase"


class TrackSource(str, Enum):
    HOME_BANNER = "home_banner"
    HOME_FEED = "home_feed"
    SKIN_RESULT = "skin_result_page"
    ANTI_FAKE_RESULT = "anti_fake_result"
    SHARE = "share"
    SEARCH = "search"
    CATEGORY = "category"


# --- Request Schemas ---

class TrackRequest(BaseModel):
    action: TrackAction
    source: TrackSource


# --- Response Schemas ---

class ProductSummary(BaseModel):
    id: int
    name: str
    cover_image: Optional[str] = None
    original_price: float
    promo_price: Optional[float] = None
    tag: Optional[str] = None


class PromotionItem(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    promo_type: PromoType
    product: ProductSummary
    start_time: datetime
    end_time: datetime
    remaining_stock: Optional[int] = None


class PromotionListResponse(BaseModel):
    total: int
    items: list[PromotionItem]


class PromotionDetailResponse(PromotionItem):
    rules: Optional[str] = None  # 活动规则文案


class CouponResponse(BaseModel):
    coupon_id: str
    discount_type: CouponType
    discount_value: float
    min_purchase: Optional[float] = None
    valid_until: datetime
    status: str


class PromotionInfo(BaseModel):
    id: int
    promo_price: Optional[float] = None
    original_price: float
    tag: Optional[str] = None


class RecommendItem(BaseModel):
    product_id: int
    name: str
    match_reason: str
    match_score: int
    promotion: Optional[PromotionInfo] = None


class RecommendResponse(BaseModel):
    based_on: Optional[dict] = None
    recommendations: list[RecommendItem]


class ShareResponse(BaseModel):
    share_url: str
    qrcode_url: str
    share_title: str
    share_image: str
