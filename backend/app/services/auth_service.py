"""
Auth Service — 微信登录 & Token 刷新
"""
import httpx
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.models import User


WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def wechat_login(self, code: str) -> dict:
        """
        微信登录流程:
        1. code2session → 获取 openid
        2. 查找或创建用户记录
        3. 签发 access_token + refresh_token
        """
        openid = await self._code2session(code)

        # 查找或创建用户
        user = await self._get_or_create_user(openid)

        # 签发 token
        token_data = {"sub": str(user.id), "openid": openid}
        access_token  = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return {
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "token_type":    "bearer",
            "expires_in":    settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    def refresh_tokens(self, refresh_token: str) -> dict:
        """使用 refresh_token 签发新的 token 对。"""
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        token_data = {"sub": payload["sub"], "openid": payload.get("openid", "")}
        new_access  = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data)

        return {
            "access_token":  new_access,
            "refresh_token": new_refresh,
            "token_type":    "bearer",
            "expires_in":    settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def _code2session(self, code: str) -> str:
        """调用微信 code2session 接口获取 openid。"""
        params = {
            "appid":      settings.WECHAT_APP_ID,
            "secret":     settings.WECHAT_APP_SECRET,
            "js_code":    code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(WECHAT_CODE2SESSION_URL, params=params)
            data = resp.json()

        if "errcode" in data and data["errcode"] != 0:
            raise ValueError(f"微信登录失败: {data.get('errmsg', 'unknown error')}")
        if "openid" not in data:
            raise ValueError("微信返回数据异常")

        return data["openid"]

    async def _get_or_create_user(self, openid: str) -> User:
        """根据 openid 查找用户，不存在则创建。"""
        result = await self.db.execute(
            select(User).where(User.openid == openid)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                openid=openid,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.db.add(user)
            await self.db.flush()

        return user
