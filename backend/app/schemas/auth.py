"""
Auth Module — Pydantic Schemas
"""
from pydantic import BaseModel


class WechatLoginRequest(BaseModel):
    code: str  # wx.login() 返回的 code


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
