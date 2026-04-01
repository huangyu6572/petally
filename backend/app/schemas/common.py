"""
Common Pydantic Schemas — Unified API Response
"""
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel
from datetime import datetime

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    code: int = 0
    message: str = "success"
    data: Optional[T] = None
    timestamp: int = int(datetime.utcnow().timestamp())


class PagedData(BaseModel, Generic[T]):
    """分页数据"""
    total: int
    items: list[T]
    page: int
    size: int
