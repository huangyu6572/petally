"""
Anti-Fake Module — Pydantic Schemas (v2)
────────────────────────────────────────
重构：去掉自有平台码，只保留两种功能：
  1. 条形码扫描 → Open Beauty Facts 备案查询
  2. 品牌防伪码 → 跳转品牌官方验证页面
"""
import re
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, field_validator


# ── 条形码查询 ────────────────────────────────────────────────────────────────

# EAN-13 / EAN-8 / UPC-A 条形码格式
BARCODE_PATTERN = re.compile(r'^\d{8,14}$')


class BarcodeRequest(BaseModel):
    """条形码查询请求"""
    barcode: str

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, v: str) -> str:
        v = v.strip()
        if not BARCODE_PATTERN.match(v):
            raise ValueError("请输入有效的商品条形码（8-14位数字）")
        return v


class BarcodeProductInfo(BaseModel):
    """Open Beauty Facts 产品信息"""
    barcode: str
    product_name: str
    brand: str
    category: Optional[str] = None
    image_url: Optional[str] = None
    ingredients: Optional[str] = None
    labels: Optional[str] = None
    quantity: Optional[str] = None
    source: str = "Open Beauty Facts"
    source_url: Optional[str] = None


class BarcodeResponse(BaseModel):
    """条形码查询响应"""
    found: bool
    product: Optional[BarcodeProductInfo] = None
    message: str = ""


# ── 品牌防伪码跳转 ────────────────────────────────────────────────────────────

class BrandVerifyRequest(BaseModel):
    """品牌防伪码跳转请求"""
    brand_name: str
    code: Optional[str] = None  # 防伪码原文（用于自动识别品牌）

    @field_validator("brand_name")
    @classmethod
    def validate_brand(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("请输入品牌名称")
        return v


class BrandInfo(BaseModel):
    """品牌验证跳转信息"""
    brand_key: str
    brand_name: str
    brand_name_en: str
    verify_type: str                        # "url" / "miniprogram" / "wechat_official"
    verify_url: Optional[str] = None        # 官方验证网址
    miniprogram_id: Optional[str] = None    # 小程序 AppID
    miniprogram_path: Optional[str] = None  # 小程序路径
    description: str                        # 验证方式说明
    logo_url: Optional[str] = None


class BrandListItem(BaseModel):
    """品牌列表项（简化版）"""
    brand_key: str
    brand_name: str
    brand_name_en: str
    verify_type: str
    description: str
    logo_url: Optional[str] = None


class BrandVerifyResponse(BaseModel):
    """品牌防伪跳转响应"""
    found: bool
    brand: Optional[BrandInfo] = None
    message: str = ""


class BrandListResponse(BaseModel):
    """支持的品牌列表响应"""
    total: int
    brands: List[BrandListItem]


# ── 查询历史 ──────────────────────────────────────────────────────────────────

class HistoryItem(BaseModel):
    """查询历史记录"""
    query_type: str           # "barcode" / "brand_redirect"
    query_value: str          # 条形码 or 品牌名
    product_name: Optional[str] = None
    brand_name: Optional[str] = None
    result_summary: str       # "已查到产品信息" / "已跳转兰蔻官方验证"
    queried_at: datetime


class HistoryResponse(BaseModel):
    """查询历史响应"""
    total: int
    items: List[HistoryItem]
