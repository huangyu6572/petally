"""
Anti-Fake Verification API Endpoints
功能点:
  F1 - 防伪码格式校验（Pydantic VerifyRequest）
  F2 - 防伪码查询（POST /verify）
  F3 - 频率限制（RateLimitExceeded → 429）
  F4 - 查询历史（GET /history）
  F5 - 批量导入管理端（POST /admin/anti-fake/import）
"""
from fastapi import APIRouter, Depends, Query, Request, HTTPException, status, UploadFile, File
from typing import Optional
import csv
import io

from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.security import get_current_user_id
from app.core.dependencies import get_db, get_redis
from app.schemas.anti_fake import VerifyRequest, VerifyResponse, HistoryResponse
from app.schemas.common import ApiResponse
from app.services.anti_fake_service import (
    AntiFakeService,
    AntiFakeCodeNotFound,
    RateLimitExceeded,
    AntiFakeCodeSuspicious,
)

# 错误码常量
ERR_CODE_NOT_FOUND = 2001
ERR_CODE_FORMAT = 2002
ERR_RATE_LIMIT = 2003
ERR_CODE_SUSPICIOUS = 2004
ERR_IMPORT_FORMAT = 2005

router = APIRouter()


def get_anti_fake_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AntiFakeService:
    return AntiFakeService(db=db, redis=redis)


# ── F1 + F2 + F3: 防伪码查询 ──────────────────────────────────────────────────

@router.post("/verify", response_model=ApiResponse[VerifyResponse])
async def verify_code(
    request: Request,
    body: VerifyRequest,
    user_id: int = Depends(get_current_user_id),
    svc: AntiFakeService = Depends(get_anti_fake_service),
):
    """
    查询美妆产品防伪码。
    - 格式校验由 VerifyRequest 完成（F1）
    - Redis 缓存 → DB 查询，缓存穿透防护（F2）
    - 用户/IP 双维度频率限制（F3）
    - 首次查询标记；多次查询给出风险提示
    """
    client_ip = request.client.host if request.client else "0.0.0.0"
    try:
        data = await svc.verify_code(
            code=body.code,
            user_id=user_id,
            client_ip=client_ip,
        )
    except RateLimitExceeded as e:
        return ApiResponse(
            code=ERR_RATE_LIMIT,
            message=str(e),
            data={"retry_after": e.ttl},
        )
    except AntiFakeCodeNotFound:
        return ApiResponse(
            code=ERR_CODE_NOT_FOUND,
            message="防伪码不存在，请确认输入是否正确",
            data=None,
        )
    except AntiFakeCodeSuspicious:
        return ApiResponse(
            code=ERR_CODE_SUSPICIOUS,
            message="该防伪码已被标记为可疑，建议联系客服核实",
            data=None,
        )
    return ApiResponse(data=data)


# ── F4: 查询历史 ───────────────────────────────────────────────────────────────

@router.get("/history", response_model=ApiResponse[HistoryResponse])
async def get_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    svc: AntiFakeService = Depends(get_anti_fake_service),
):
    """获取用户防伪查询历史记录（分页）。"""
    data = await svc.get_history(user_id=user_id, page=page, size=size)
    return ApiResponse(data=data)


# ── F5: 批量导入管理端 ──────────────────────────────────────────────────────────

@router.post("/admin/import", response_model=ApiResponse)
async def batch_import(
    file: UploadFile = File(..., description="CSV 文件，列：code,product_id,batch_no"),
    user_id: int = Depends(get_current_user_id),
    svc: AntiFakeService = Depends(get_anti_fake_service),
):
    """
    管理端批量导入防伪码（CSV 格式）。
    CSV 列: code, product_id, batch_no（可选）
    单次上限 5000 条。
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # 兼容 BOM
        reader = csv.DictReader(io.StringIO(text))
        codes = []
        for i, row in enumerate(reader, start=2):  # 行号从第2行（跳过header）
            code = row.get("code", "").strip()
            product_id = row.get("product_id", "").strip()
            batch_no = row.get("batch_no", "").strip()
            if not code:
                return ApiResponse(
                    code=ERR_IMPORT_FORMAT,
                    message=f"第 {i} 行 code 字段为空",
                )
            try:
                product_id_int = int(product_id) if product_id else None
            except ValueError:
                return ApiResponse(
                    code=ERR_IMPORT_FORMAT,
                    message=f"第 {i} 行 product_id 格式错误",
                )
            codes.append({
                "code": code,
                "product_id": product_id_int,
                "batch_no": batch_no or None,
            })
    except Exception as e:
        return ApiResponse(code=ERR_IMPORT_FORMAT, message=f"CSV 解析失败: {e}")

    try:
        result = await svc.batch_import(codes)
    except Exception as e:
        return ApiResponse(code=ERR_IMPORT_FORMAT, message=str(e))

    return ApiResponse(data=result, message=f"成功导入 {result['imported']} 条防伪码")

