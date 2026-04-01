"""
AI Skin Analysis Service
"""
import uuid
from datetime import datetime
from fastapi import UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


class SkinAnalysisService:
    """
    AI 肌肤分析业务逻辑层。

    约束:
    1. submit_analysis() 异步处理，立即返回 analysis_id
    2. 分析超时上限 60 秒
    3. 失败自动重试 (最多3次，指数退避)
    4. 图片先上传到对象存储
    5. 每用户每天限制 20 次
    """

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    async def submit_analysis(
        self, user_id: int, image: UploadFile, analysis_type: str
    ) -> dict:
        # 1. 日次数限制检查
        await self._check_daily_limit(user_id)

        # 2. 校验图片 (格式、大小、magic bytes)
        await self._validate_image(image)

        # 3. 内容安全审核
        # await self._content_safety_check(image)

        # 4. 上传到对象存储
        analysis_id = self._generate_analysis_id()
        # image_url = await self._upload_image(image, user_id, analysis_id)

        # 5. 创建数据库记录 (status=PROCESSING)
        # TODO: Implement with SkinAnalysisRepository

        # 6. 发送 Celery 异步任务
        # from app.tasks.skin_tasks import process_skin_analysis
        # process_skin_analysis.delay(analysis_id)

        return {
            "analysis_id": analysis_id,
            "status": "processing",
            "estimated_seconds": 15,
        }

    async def get_result(self, analysis_id: str, user_id: int) -> dict:
        # TODO: Check cache first, then DB
        # Verify ownership (user_id match)
        raise NotImplementedError

    async def get_history(self, user_id: int, page: int, size: int) -> dict:
        raise NotImplementedError

    async def get_trend(self, user_id: int, days: int) -> dict:
        raise NotImplementedError

    async def _check_daily_limit(self, user_id: int) -> None:
        key = f"skin:daily:{user_id}:{datetime.utcnow().strftime('%Y%m%d')}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 86400)
        if count > settings.SKIN_ANALYSIS_DAILY_LIMIT:
            raise DailyLimitExceeded("今日分析次数已用尽，请明天再试")

    async def _validate_image(self, image: UploadFile) -> None:
        ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
        MAX_SIZE = 10 * 1024 * 1024  # 10MB

        if image.content_type not in ALLOWED_TYPES:
            raise UnsupportedImageFormat(f"不支持的图片格式: {image.content_type}")

        content = await image.read()
        await image.seek(0)

        if len(content) > MAX_SIZE:
            raise FileSizeTooLarge("图片大小不能超过 10MB")

        # TODO: Check magic bytes for security
        # TODO: Check minimum resolution (480×480)

    @staticmethod
    def _generate_analysis_id() -> str:
        now = datetime.utcnow().strftime("%Y%m%d")
        short_uuid = uuid.uuid4().hex[:12]
        return f"ana_{now}_{short_uuid}"


class DailyLimitExceeded(Exception):
    pass


class UnsupportedImageFormat(Exception):
    pass


class FileSizeTooLarge(Exception):
    pass
