"""
Authentication API Endpoints (WeChat Login + Token Refresh)
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_db
from app.schemas.auth import WechatLoginRequest, TokenResponse
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService


router = APIRouter()


def _get_service(db=Depends(get_db)):
    return AuthService(db=db)


@router.post("/wechat-login", response_model=ApiResponse[TokenResponse])
async def wechat_login(
    request: WechatLoginRequest,
    svc: AuthService = Depends(_get_service),
):
    """
    微信小程序登录:
    - 接收 wx.login() 返回的 code
    - 调用微信 code2session 获取 openid
    - 签发 JWT access_token + refresh_token
    """
    try:
        data = await svc.wechat_login(request.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 1002, "message": str(e)})

    return ApiResponse(
        code=0,
        message="登录成功",
        data=TokenResponse(**data),
    )


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token(
    body: dict,
    svc: AuthService = Depends(_get_service),
):
    """使用 refresh_token 刷新 access_token。"""
    token = body.get("refresh_token", "")
    if not token:
        raise HTTPException(status_code=400, detail={"code": 1002, "message": "refresh_token 不能为空"})
    try:
        data = svc.refresh_tokens(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail={"code": 1002, "message": str(e)})

    return ApiResponse(code=0, message="success", data=TokenResponse(**data))
