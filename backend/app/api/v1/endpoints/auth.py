"""
Authentication API Endpoints (WeChat Login)
"""
from fastapi import APIRouter

from app.schemas.auth import WechatLoginRequest, TokenResponse
from app.schemas.common import ApiResponse

router = APIRouter()


@router.post("/wechat-login", response_model=ApiResponse[TokenResponse])
async def wechat_login(request: WechatLoginRequest):
    """
    微信小程序登录。
    - 接收 wx.login() 返回的 code
    - 调用微信 code2session 获取 openid
    - 签发 JWT access_token + refresh_token
    """
    # TODO: Inject AuthService and call wechat_login
    pass


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token():
    """使用 refresh_token 刷新 access_token。"""
    # TODO: Inject AuthService and call refresh
    pass
