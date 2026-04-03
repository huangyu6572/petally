"""
Anti-Fake Verification API Endpoints (v2)
──────────────────────────────────────────
重构：去掉自有平台码，改为两种真实查验功能：

  F1 - 条形码查询（POST /barcode）  → Open Beauty Facts 产品备案信息
  F2 - 品牌防伪跳转（POST /brand-verify） → 返回品牌官方验证 URL / 小程序
  F3 - 支持品牌列表（GET /brands）   → 前端展示所有支持跳转的品牌
  F4 - 查询历史（GET /history）      → 用户最近的查询记录
"""
from fastapi import APIRouter, Depends, Query, Request
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.security import get_current_user_id
from app.core.dependencies import get_db, get_redis
from app.schemas.anti_fake import (
    BarcodeRequest,
    BarcodeResponse,
    BrandVerifyRequest,
    BrandVerifyResponse,
    BrandListResponse,
    HistoryResponse,
)
from app.schemas.common import ApiResponse
from app.services.open_beauty_service import OpenBeautyService
from app.services.brand_verify_service import BrandVerifyService

# 错误码常量
ERR_BARCODE_NOT_FOUND = 2001
ERR_BARCODE_FORMAT = 2002
ERR_RATE_LIMIT = 2003
ERR_BRAND_NOT_FOUND = 2004

router = APIRouter()


# ── 依赖注入 ──────────────────────────────────────────────────────────────────

def get_open_beauty_service(redis: Redis = Depends(get_redis)) -> OpenBeautyService:
    return OpenBeautyService(redis=redis)


def get_brand_verify_service(redis: Redis = Depends(get_redis)) -> BrandVerifyService:
    return BrandVerifyService(redis=redis)


# ── F1: 条形码查询 ────────────────────────────────────────────────────────────

@router.post("/barcode", response_model=ApiResponse[BarcodeResponse])
async def lookup_barcode(
    body: BarcodeRequest,
    user_id: int = Depends(get_current_user_id),
    svc: OpenBeautyService = Depends(get_open_beauty_service),
    db: AsyncSession = Depends(get_db),
):
    """
    通过条形码查询化妆品产品信息。

    数据源：Open Beauty Facts（开源化妆品数据库，57000+ 产品）
    流程：Redis 缓存 → OBF API → 缓存回写
    """
    product = await svc.lookup_barcode(body.barcode)

    # 记录查询历史
    await _save_history(
        db,
        user_id=user_id,
        query_type="barcode",
        query_value=body.barcode,
        product_name=product["product_name"] if product else None,
        brand_name=product["brand"] if product else None,
        result_summary="已查到产品信息" if product else "未收录该条形码",
    )

    if product is None:
        return ApiResponse(
            code=ERR_BARCODE_NOT_FOUND,
            message="该条形码暂未被 Open Beauty Facts 收录，请检查条码是否正确",
            data=BarcodeResponse(
                found=False,
                message="暂未收录该条形码，建议在产品包装上查看品牌名并使用品牌官方验证",
            ),
        )

    return ApiResponse(
        data=BarcodeResponse(
            found=True,
            product=product,
            message="已查到产品备案信息（数据来源: Open Beauty Facts）",
        ),
    )


# ── F2: 品牌防伪跳转 ──────────────────────────────────────────────────────────

@router.post("/brand-verify", response_model=ApiResponse[BrandVerifyResponse])
async def brand_verify(
    body: BrandVerifyRequest,
    user_id: int = Depends(get_current_user_id),
    svc: BrandVerifyService = Depends(get_brand_verify_service),
    db: AsyncSession = Depends(get_db),
):
    """
    根据品牌名返回官方防伪验证跳转信息。

    返回品牌官方验证 URL 或小程序路径，前端负责跳转。
    如果传入了 code，会尝试自动识别品牌。
    """
    brand_info = None

    # 先尝试通过防伪码格式自动识别品牌
    if body.code:
        brand_info = svc.match_brand_by_code(body.code)

    # 如果自动识别失败，按品牌名查找
    if brand_info is None:
        brand_info = svc.get_brand_verify_info(body.brand_name)

    # 记录查询历史
    await _save_history(
        db,
        user_id=user_id,
        query_type="brand_redirect",
        query_value=body.brand_name,
        product_name=None,
        brand_name=brand_info["brand_name"] if brand_info else body.brand_name,
        result_summary=(
            f"已跳转{brand_info['brand_name']}官方验证" if brand_info
            else f"暂不支持{body.brand_name}的官方跳转"
        ),
    )

    if brand_info is None:
        return ApiResponse(
            code=ERR_BRAND_NOT_FOUND,
            message=f"暂不支持「{body.brand_name}」的官方防伪跳转",
            data=BrandVerifyResponse(
                found=False,
                message=(
                    f"暂不支持「{body.brand_name}」的官方跳转，"
                    "建议直接前往该品牌官方网站或微信公众号查询防伪码"
                ),
            ),
        )

    return ApiResponse(
        data=BrandVerifyResponse(
            found=True,
            brand=brand_info,
            message=brand_info["description"],
        ),
    )


# ── F3: 支持的品牌列表 ────────────────────────────────────────────────────────

@router.get("/brands", response_model=ApiResponse[BrandListResponse])
async def list_brands(
    svc: BrandVerifyService = Depends(get_brand_verify_service),
):
    """
    获取所有支持官方防伪跳转的品牌列表（无需登录）。
    前端用于品牌选择页面展示。
    """
    brands = svc.get_all_brands()
    return ApiResponse(
        data=BrandListResponse(total=len(brands), brands=brands),
    )


# ── F4: 查询历史 ───────────────────────────────────────────────────────────────

@router.get("/history", response_model=ApiResponse[HistoryResponse])
async def get_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户防伪查询历史记录（分页）。"""
    from sqlalchemy import select, func
    from app.models.models import VerifyHistory

    offset = (page - 1) * size

    count_stmt = (
        select(func.count(VerifyHistory.id))
        .where(VerifyHistory.user_id == user_id)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    data_stmt = (
        select(VerifyHistory)
        .where(VerifyHistory.user_id == user_id)
        .order_by(VerifyHistory.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    rows = (await db.execute(data_stmt)).scalars().all()

    items = [
        {
            "query_type": r.query_type,
            "query_value": r.query_value,
            "product_name": r.product_name,
            "brand_name": r.brand_name,
            "result_summary": r.result_summary,
            "queried_at": r.created_at,
        }
        for r in rows
    ]
    return ApiResponse(data={"total": total, "items": items})


# ── 内部工具 ──────────────────────────────────────────────────────────────────

async def _save_history(
    db: AsyncSession,
    user_id: int,
    query_type: str,
    query_value: str,
    product_name: Optional[str],
    brand_name: Optional[str],
    result_summary: str,
) -> None:
    """保存查询历史到数据库。"""
    from app.models.models import VerifyHistory

    record = VerifyHistory(
        user_id=user_id,
        query_type=query_type,
        query_value=query_value,
        product_name=product_name,
        brand_name=brand_name,
        result_summary=result_summary,
    )
    db.add(record)
    await db.flush()

