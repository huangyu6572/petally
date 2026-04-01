"""
Petal Backend — API v1 Router Aggregator
"""
from fastapi import APIRouter

from app.api.v1.endpoints import anti_fake, skin, promotion, auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(anti_fake.router, prefix="/anti-fake", tags=["防伪查询"])
api_router.include_router(skin.router, prefix="/skin", tags=["AI 肌肤分析"])
api_router.include_router(promotion.router, prefix="/promotions", tags=["商品推广"])
