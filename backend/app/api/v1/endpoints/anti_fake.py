"""
Anti-Fake Verification API Endpoints
"""
from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.schemas.anti_fake import VerifyRequest, VerifyResponse, HistoryResponse
from app.schemas.common import ApiResponse

router = APIRouter()


@router.post("/verify", response_model=ApiResponse[VerifyResponse])
async def verify_code(
    request: VerifyRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    查询美妆产品防伪码。
    - 支持扫码/手动输入
    - 首次查询标记为已验证
    - 多次查询给出风险提示
    """
    # TODO: Inject AntiFakeService and call verify_code
    pass


@router.get("/history", response_model=ApiResponse[HistoryResponse])
async def get_history(
    page: int = 1,
    size: int = 20,
    user_id: int = Depends(get_current_user_id),
):
    """获取用户防伪查询历史记录。"""
    # TODO: Inject AntiFakeService and call get_history
    pass
