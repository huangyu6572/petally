"""
Promotion API Endpoints
功能点:
  F1 - 推广活动列表 & 详情
  F2 - 优惠券领取
  F3 - 个性化推荐
  F4 - 数据追踪埋点
  F5 - 分享推广
  F6 - 管理端分析看板 (admin)
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.security import get_current_user_id
from app.core.dependencies import get_db, get_redis
from app.schemas.promotion import (
    PromotionListResponse, PromotionDetailResponse,
    CouponResponse, RecommendResponse, ShareResponse, TrackRequest,
)
from app.schemas.common import ApiResponse
from app.services.promotion_service import (
    PromotionService,
    PromotionNotFound, PromotionNotStarted, PromotionEnded,
    CouponSoldOut, CouponAlreadyClaimed, PromotionError,
)

router = APIRouter()


def get_promotion_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> PromotionService:
    return PromotionService(db=db, redis=redis)


# ── F1: 推广活动列表 ──────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[PromotionListResponse])
async def get_promotions(
    page: int = 1,
    size: int = 20,
    category: Optional[str] = Query(None, description="商品分类过滤"),
    svc: PromotionService = Depends(get_promotion_service),
):
    """获取推广活动列表（公开接口，无需登录）。"""
    data = await svc.get_active_promotions(page=page, size=size, category=category)
    return ApiResponse(data=data)


# ── F3: 个性化推荐（必须在 /{promotion_id} 之前注册，防止路由冲突）─────────────

@router.get("/recommend", response_model=ApiResponse[RecommendResponse])
async def get_recommendations(
    analysis_id: Optional[str] = Query(None, description="AI 分析 ID，用于精准推荐"),
    user_id: int = Depends(get_current_user_id),
    svc: PromotionService = Depends(get_promotion_service),
):
    """基于 AI 肌肤分析结果获取个性化商品推荐。"""
    data = await svc.get_recommendations(user_id=user_id, analysis_id=analysis_id)
    return ApiResponse(data=data)


# ── F1: 推广活动详情 ───────────────────────────────────────────────────────────

@router.get("/{promotion_id}", response_model=ApiResponse[PromotionDetailResponse])
async def get_promotion_detail(
    promotion_id: int,
    svc: PromotionService = Depends(get_promotion_service),
):
    """获取推广活动详情。"""
    try:
        data = await svc.get_detail(promo_id=promotion_id)
    except PromotionNotFound as e:
        return ApiResponse(code=e.code, message=e.message, data=None)
    return ApiResponse(data=data)


# ── F2: 优惠券领取 ─────────────────────────────────────────────────────────────

@router.post("/{promotion_id}/claim-coupon", response_model=ApiResponse[CouponResponse])
async def claim_coupon(
    promotion_id: int,
    user_id: int = Depends(get_current_user_id),
    svc: PromotionService = Depends(get_promotion_service),
):
    """领取推广活动优惠券（幂等，每人限领一张）。"""
    try:
        data = await svc.claim_coupon(promo_id=promotion_id, user_id=user_id)
    except CouponAlreadyClaimed as e:
        return ApiResponse(code=e.code, message=e.message, data=e.data)
    except (PromotionNotFound, PromotionNotStarted, PromotionEnded,
            CouponSoldOut, PromotionError) as e:
        return ApiResponse(code=e.code, message=e.message, data=e.data or None)
    return ApiResponse(data=data)


# ── F4: 数据追踪埋点 ───────────────────────────────────────────────────────────

@router.post("/{promotion_id}/track")
async def track_event(
    promotion_id: int,
    request: TrackRequest,
    user_id: int = Depends(get_current_user_id),
    svc: PromotionService = Depends(get_promotion_service),
):
    """记录推广行为事件（曝光/点击/购买等），异步非阻塞。"""
    await svc.track_event(
        promo_id=promotion_id,
        user_id=user_id,
        action=request.action.value,
        source=request.source.value,
    )
    return ApiResponse(message="ok")


# ── F5: 分享推广 ───────────────────────────────────────────────────────────────

@router.post("/{promotion_id}/share", response_model=ApiResponse[ShareResponse])
async def generate_share(
    promotion_id: int,
    user_id: int = Depends(get_current_user_id),
    svc: PromotionService = Depends(get_promotion_service),
):
    """生成推广分享信息（小程序码 + 分享文案）。"""
    try:
        data = await svc.generate_share(promo_id=promotion_id, user_id=user_id)
    except PromotionError as e:
        return ApiResponse(code=e.code, message=e.message)
    return ApiResponse(data=data)


# ── F6: 管理端分析看板 ─────────────────────────────────────────────────────────

@router.get("/admin/{promotion_id}/analytics")
async def get_analytics(
    promotion_id: int,
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    user_id: int = Depends(get_current_user_id),
    svc: PromotionService = Depends(get_promotion_service),
):
    """获取推广数据看板（管理端）。"""
    try:
        data = await svc.get_analytics(promo_id=promotion_id, days=days)
    except PromotionNotFound as e:
        return ApiResponse(code=e.code, message=e.message)
    return ApiResponse(data=data)
