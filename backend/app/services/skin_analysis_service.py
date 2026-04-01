"""
AI Skin Analysis Service — 完整业务逻辑层

功能点:
  F1 - 图片预处理由 image_processor 完成
  F2 - 评分由 scoring_engine 完成
  F3 - 建议由 suggestion_engine 完成
  F4 - 分析任务核心 (submit/get_result, 日限制, 缓存, 越权校验)
  F5 - 历史记录与趋势分析
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.skin_analysis_repository import (
    SkinAnalysisRepository,
    STATUS_PROCESSING, STATUS_COMPLETED, STATUS_FAILED, STATUS_TIMEOUT,
    MODEL_VERSION,
)
from app.services.image_processor import (
    validate_content_type, validate_file_size, validate_magic_bytes,
)
from app.schemas.skin import AnalysisStatus

# ── Redis key 模板 ─────────────────────────────────────────────────────────────
CACHE_KEY_RESULT  = "skin:result:{analysis_id}"
CACHE_KEY_DAILY   = "skin:daily:{user_id}:{date}"

RESULT_CACHE_TTL = 3600
DAILY_TTL        = 86400

_STATUS_MAP = {
    STATUS_PROCESSING: AnalysisStatus.PROCESSING,
    STATUS_COMPLETED:  AnalysisStatus.COMPLETED,
    STATUS_FAILED:     AnalysisStatus.FAILED,
    STATUS_TIMEOUT:    AnalysisStatus.TIMEOUT,
}


# ── 异常 ──────────────────────────────────────────────────────────────────────

class DailyLimitExceeded(Exception):
    """用户每日分析次数超限 (3005)"""


class UnsupportedImageFormat(Exception):
    """不支持的图片格式 (3002)"""


class FileSizeTooLarge(Exception):
    """文件过大 (413)"""


class ImageResolutionTooLow(Exception):
    """图片分辨率过低 (3007)"""


class MaliciousFileDetected(Exception):
    """恶意文件检测 (3002)"""


class AnalysisNotFound(Exception):
    """分析记录不存在 (404)"""


class PermissionDenied(Exception):
    """无权访问他人分析记录 (403)"""


class NoFaceDetected(Exception):
    """未检测到人脸 (3003)"""


# ── Service ───────────────────────────────────────────────────────────────────

class SkinAnalysisService:
    """AI 肌肤分析业务逻辑层。"""

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis
        self.repo = SkinAnalysisRepository(db)

    # ── F4: 提交分析任务 ──────────────────────────────────────────────────────

    async def submit_analysis(
        self,
        user_id: int,
        image: UploadFile,
        analysis_type: str = "face_full",
    ) -> dict:
        await self._check_daily_limit(user_id)

        content = await image.read()
        await image.seek(0)
        await self._validate_image_bytes(content, image.content_type or "")

        analysis_id = self._generate_analysis_id()
        image_url = self._build_image_url(user_id, analysis_id, image.filename or "img.jpg")

        await self.repo.create(
            analysis_id=analysis_id,
            user_id=user_id,
            image_url=image_url,
            analysis_type=analysis_type,
        )

        return {
            "analysis_id": analysis_id,
            "status": "processing",
            "estimated_seconds": 15,
        }

    # ── F4: 查询分析结果 ──────────────────────────────────────────────────────

    async def get_result(self, analysis_id: str, user_id: int) -> dict:
        cached = await self._get_cached_result(analysis_id)
        if cached:
            if cached.get("user_id") != user_id:
                raise PermissionDenied("无权访问该分析记录")
            return cached

        record = await self.repo.find_by_id(analysis_id)
        if record is None:
            raise AnalysisNotFound(f"分析记录 {analysis_id} 不存在")

        if record.user_id != user_id:
            raise PermissionDenied("无权访问该分析记录")

        result = self._build_result_dict(record)

        if record.status == STATUS_COMPLETED:
            await self._cache_result(analysis_id, result)

        return result

    # ── F5: 历史记录 ─────────────────────────────────────────────────────────

    async def get_history(self, user_id: int, page: int = 1, size: int = 10) -> dict:
        total, items = await self.repo.get_history(user_id, page, size)
        return {
            "total": total,
            "items": [
                {
                    "analysis_id": r.id,
                    "overall_score": r.overall_score,
                    "skin_type": r.skin_type,
                    "status": _STATUS_MAP.get(r.status, AnalysisStatus.FAILED).value,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in items
            ],
        }

    # ── F5: 肌肤趋势 ─────────────────────────────────────────────────────────

    async def get_trend(self, user_id: int, days: int = 90) -> dict:
        data_points = await self.repo.get_trend_scores(user_id, days)

        if not data_points:
            return {
                "overall_scores": [],
                "improvement": "0%",
                "best_improved": None,
                "needs_attention": None,
            }

        scores_list = [{"date": date, "score": score} for date, score in data_points]

        first_score = data_points[0][1]
        last_score  = data_points[-1][1]
        if first_score > 0:
            delta = last_score - first_score
            improvement = f"{delta:+.0f}%" if delta != 0 else "0%"
        else:
            improvement = "0%"

        return {
            "overall_scores": scores_list,
            "improvement": improvement,
            "best_improved": None,
            "needs_attention": None,
        }

    # ── F4: 日次数限制 ────────────────────────────────────────────────────────

    async def _check_daily_limit(self, user_id: int) -> None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = CACHE_KEY_DAILY.format(user_id=user_id, date=date_str)
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, DAILY_TTL)
        if count > settings.SKIN_ANALYSIS_DAILY_LIMIT:
            raise DailyLimitExceeded("今日分析次数已用尽，请明天再试")

    # ── F1: 图片校验 ──────────────────────────────────────────────────────────

    async def _validate_image_bytes(self, content: bytes, content_type: str) -> None:
        from app.services.image_processor import (
            UnsupportedImageFormat as _UnsupportedFmt,
            FileSizeTooLarge as _FileTooLarge,
            MaliciousFileDetected as _Malicious,
        )
        try:
            validate_content_type(content_type)
            validate_file_size(content)
            validate_magic_bytes(content, content_type)
        except _UnsupportedFmt as e:
            raise UnsupportedImageFormat(str(e)) from e
        except _FileTooLarge as e:
            raise FileSizeTooLarge(str(e)) from e
        except _Malicious as e:
            raise MaliciousFileDetected(str(e)) from e

    # ── 缓存 ──────────────────────────────────────────────────────────────────

    async def _get_cached_result(self, analysis_id: str) -> Optional[dict]:
        key = CACHE_KEY_RESULT.format(analysis_id=analysis_id)
        raw = await self.redis.get(key)
        if raw:
            return json.loads(raw)
        return None

    async def _cache_result(self, analysis_id: str, result: dict) -> None:
        key = CACHE_KEY_RESULT.format(analysis_id=analysis_id)
        await self.redis.set(key, json.dumps(result, default=str), ex=RESULT_CACHE_TTL)

    async def invalidate_cache(self, analysis_id: str) -> None:
        key = CACHE_KEY_RESULT.format(analysis_id=analysis_id)
        await self.redis.delete(key)

    # ── 静态工具 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_analysis_id() -> str:
        now = datetime.now(timezone.utc).strftime("%Y%m%d")
        short_uuid = uuid.uuid4().hex[:12]
        return f"ana_{now}_{short_uuid}"

    @staticmethod
    def _build_image_url(user_id: int, analysis_id: str, filename: str) -> str:
        now = datetime.now(timezone.utc)
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
        return (
            f"/{now.year}/{now.month:02d}/{now.day:02d}"
            f"/{user_id}/{analysis_id}.{ext}"
        )

    @staticmethod
    def _build_result_dict(record) -> dict:
        status = _STATUS_MAP.get(record.status, AnalysisStatus.FAILED).value
        result: dict = {
            "analysis_id": record.id,
            "status": status,
            "user_id": record.user_id,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "model_version": record.model_version,
        }
        if record.status == STATUS_COMPLETED:
            result.update(
                {
                    "overall_score": record.overall_score,
                    "skin_type": record.skin_type,
                    "issues": record.analysis_result or [],
                    "suggestions": record.suggestions or [],
                    "recommended_products": [],
                }
            )
        return result
