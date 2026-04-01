"""
F4 — 肌肤分析 Repository

职责:
- 创建/查询/更新 SkinAnalysis 记录
- 分页查询历史
- 趋势数据聚合
"""
import json
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.models.models import SkinAnalysis

# ── 状态常量 ──────────────────────────────────────────────────────────────────
STATUS_PROCESSING = 0
STATUS_COMPLETED  = 1
STATUS_FAILED     = 2
STATUS_TIMEOUT    = 3

MODEL_VERSION = "skin-v2.1"


class SkinAnalysisRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 写操作 ────────────────────────────────────────────────────────────────

    async def create(
        self,
        analysis_id: str,
        user_id: int,
        image_url: str,
        analysis_type: str = "face_full",
    ) -> SkinAnalysis:
        """创建分析记录，初始状态为 PROCESSING。"""
        record = SkinAnalysis(
            id=analysis_id,
            user_id=user_id,
            image_url=image_url,
            analysis_type=analysis_type,
            status=STATUS_PROCESSING,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def mark_completed(
        self,
        analysis_id: str,
        overall_score: int,
        skin_type: str,
        analysis_result: dict,
        suggestions: list,
    ) -> None:
        """将分析记录标记为完成，写入结果。"""
        stmt = (
            update(SkinAnalysis)
            .where(SkinAnalysis.id == analysis_id)
            .values(
                status=STATUS_COMPLETED,
                overall_score=overall_score,
                skin_type=skin_type,
                analysis_result=analysis_result,
                suggestions=suggestions,
                model_version=MODEL_VERSION,
            )
        )
        await self.db.execute(stmt)

    async def mark_failed(self, analysis_id: str) -> None:
        """将分析记录标记为失败。"""
        stmt = (
            update(SkinAnalysis)
            .where(SkinAnalysis.id == analysis_id)
            .values(status=STATUS_FAILED)
        )
        await self.db.execute(stmt)

    async def mark_timeout(self, analysis_id: str) -> None:
        """将分析记录标记为超时。"""
        stmt = (
            update(SkinAnalysis)
            .where(SkinAnalysis.id == analysis_id)
            .values(status=STATUS_TIMEOUT)
        )
        await self.db.execute(stmt)

    # ── 读操作 ────────────────────────────────────────────────────────────────

    async def find_by_id(self, analysis_id: str) -> Optional[SkinAnalysis]:
        """根据 analysis_id 查询记录。"""
        result = await self.db.execute(
            select(SkinAnalysis).where(SkinAnalysis.id == analysis_id)
        )
        return result.scalar_one_or_none()

    async def get_history(
        self,
        user_id: int,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[int, List[SkinAnalysis]]:
        """
        分页查询用户历史，按创建时间倒序。
        返回 (total, items)
        """
        base = select(SkinAnalysis).where(SkinAnalysis.user_id == user_id)

        # 总数
        count_stmt = select(func.count()).select_from(
            base.subquery()
        )
        total: int = (await self.db.execute(count_stmt)).scalar_one()

        # 分页
        items_stmt = (
            base
            .order_by(SkinAnalysis.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = (await self.db.execute(items_stmt)).scalars().all()
        return total, list(rows)

    async def get_trend_scores(
        self,
        user_id: int,
        days: int = 90,
    ) -> List[Tuple[str, int]]:
        """
        查询最近 N 天内已完成的分析评分，按时间升序。
        返回 [(date_str, overall_score), ...]
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(SkinAnalysis.created_at, SkinAnalysis.overall_score)
            .where(
                SkinAnalysis.user_id == user_id,
                SkinAnalysis.status == STATUS_COMPLETED,
                SkinAnalysis.created_at >= since,
                SkinAnalysis.overall_score.isnot(None),
            )
            .order_by(SkinAnalysis.created_at.asc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            (row[0].strftime("%Y-%m-%d"), row[1])
            for row in rows
        ]

    async def count_today(self, user_id: int) -> int:
        """统计用户今日已提交的分析次数（含所有状态）。"""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        stmt = select(func.count()).where(
            SkinAnalysis.user_id == user_id,
            SkinAnalysis.created_at >= today,
        )
        return (await self.db.execute(stmt)).scalar_one()
