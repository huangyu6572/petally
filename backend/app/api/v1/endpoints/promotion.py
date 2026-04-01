"""
Promotion API Endpoints
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.core.security import get_current_user_id
from app.schemas.promotion import (
    PromotionListResponse, PromotionDetailResponse,
    CouponResponse, RecommendResponse, ShareResponse, TrackRequest,
)
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("", response_model=ApiResponse[PromotionListResponse])
async def get_promotions(
    page: int = 1,
    size: int = 20,
    category: Optional[str] = Query(None, description="商品分类过滤"),
):
    """获取推广活动列表（公开接口，无需登录）。"""
    # TODO: Inject PromotionService and call get_active_promotions
    pass


@router.get("/recommend", response_model=ApiResponse[RecommendResponse])
async def get_recommendations(
    analysis_id: Optional[str] = Query(None, description="AI 分析 ID，用于精准推荐"),
    user_id: int = Depends(get_current_user_id),
):
    """基于 AI 肌肤分析结果获取个性化商品推荐。"""
    # TODO: Inject PromotionService and call get_recommendations
    pass


@router.get("/{promotion_id}", response_model=ApiResponse[PromotionDetailResponse])
async def get_promotion_detail(promotion_id: int):
    """获取推广活动详情。"""
    # TODO: Inject PromotionService and call get_detail
    pass


@router.post("/{promotion_id}/claim-coupon", response_model=ApiResponse[CouponResponse])
async def claim_coupon(
    promotion_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """领取推广活动优惠券。"""
    # TODO: Inject PromotionService and call claim_coupon
    pass


@router.post("/{promotion_id}/track")
async def track_event(
    promotion_id: int,
    request: TrackRequest,
    user_id: int = Depends(get_current_user_id),
):
    """记录推广行为事件（曝光/点击/购买等）。"""
    # TODO: Inject PromotionService and call track_event
    pass


@router.post("/{promotion_id}/share", response_model=ApiResponse[ShareResponse])
async def generate_share(
    promotion_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """生成推广分享信息（小程序码 + 分享文案）。"""
    # TODO: Inject PromotionService and call generate_share
    pass
