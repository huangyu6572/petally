"""
Anti-Fake Module — Pydantic Schemas
"""
import re
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, field_validator

# 防伪码格式: 排除易混淆字符 O/0/I/1/L
# A-H(无I), J-K(无L), M-N(无O), P-Z(无O), 2-9(无0/1), 连字符
ANTI_FAKE_CODE_PATTERN = re.compile(r'^[ABCDEFGHJKMNPQRSTUVWXYZ23456789-]{10,32}$')


class VerifyRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v: str) -> str:
        v = v.strip().upper()
        if not ANTI_FAKE_CODE_PATTERN.match(v):
            raise ValueError("防伪码格式不正确，请检查输入")
        return v


class ProductInfo(BaseModel):
    id: int
    name: str
    brand: str
    category: str
    cover_image: Optional[str] = None
    batch_no: Optional[str] = None
    production_date: Optional[str] = None
    expiry_date: Optional[str] = None


class VerificationInfo(BaseModel):
    first_verified: bool
    query_count: int
    verified_at: datetime
    first_verified_at: Optional[datetime] = None
    warning: Optional[str] = None


class VerifyResponse(BaseModel):
    is_authentic: bool
    product: Optional[ProductInfo] = None
    verification: Optional[VerificationInfo] = None


class HistoryItem(BaseModel):
    code: str
    product_name: str
    is_authentic: bool
    queried_at: datetime


class HistoryResponse(BaseModel):
    total: int
    items: list[HistoryItem]
