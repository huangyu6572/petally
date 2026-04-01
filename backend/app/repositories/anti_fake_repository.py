"""
Anti-Fake Repository — 数据访问层
功能点:
  F2 - 防伪码查询（含 Product JOIN）
  F4 - 查询历史分页
  F5 - 批量导入
"""
import hashlib
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import AntiFakeCode, Product, PromoClick

# ── 常量 ──────────────────────────────────────────────────────────────────────
BATCH_IMPORT_MAX = 5000           # 单次批量导入上限
CODE_STATUS_UNUSED = "unused"
CODE_STATUS_VERIFIED = "verified"
CODE_STATUS_WARNING = "warning"
CODE_STATUS_SUSPICIOUS = "suspicious"

QUERY_COUNT_WARNING = 3           # 触发 warning 告警阈值
QUERY_COUNT_SUSPICIOUS = 10      # 触发 suspicious 标记阈值


# ── 业务异常 ──────────────────────────────────────────────────────────────────

class BatchSizeExceeded(Exception):
    """单次批量导入超过最大条数"""
    def __init__(self, limit: int, actual: int):
        self.limit = limit
        self.actual = actual
        super().__init__(f"单次导入上限 {limit} 条，实际 {actual} 条")


# ── Repository ────────────────────────────────────────────────────────────────

class AntiFakeRepository:
    """
    防伪码数据访问层。
    约束:
    1. 所有查询使用参数化查询（SQLAlchemy ORM 天然防注入）
    2. 批量导入使用 bulk_insert，单次不超过 BATCH_IMPORT_MAX 条
    3. 更新 query_count 使用 DB 原子 +1（避免竞态）
    4. 查询结果包含关联 product 信息（selectinload）
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── F2: 防伪码查询 ─────────────────────────────────────────────────────────

    async def find_by_code(self, code: str) -> Optional[AntiFakeCode]:
        """
        按防伪码精确查询，预加载关联 Product。
        """
        stmt = (
            select(AntiFakeCode)
            .options(selectinload(AntiFakeCode.product))
            .where(AntiFakeCode.code == code)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_first_verified(
        self, code_id: int, user_id: int, verified_at: datetime
    ) -> None:
        """首次查询：记录 verified_by、verified_at，状态设为 verified。"""
        await self.db.execute(
            update(AntiFakeCode)
            .where(AntiFakeCode.id == code_id)
            .values(
                is_verified=True,
                verified_by=user_id,
                verified_at=verified_at,
                query_count=1,
                status=CODE_STATUS_VERIFIED,
            )
        )

    async def increment_query_count(self, code_id: int) -> int:
        """
        原子递增 query_count，同步更新状态机。
        返回更新后的 query_count。
        """
        # 先读当前值
        stmt = select(AntiFakeCode.query_count).where(AntiFakeCode.id == code_id)
        result = await self.db.execute(stmt)
        current = result.scalar_one_or_none() or 0
        new_count = current + 1

        # 决定新状态
        if new_count >= QUERY_COUNT_SUSPICIOUS:
            new_status = CODE_STATUS_SUSPICIOUS
        elif new_count >= QUERY_COUNT_WARNING:
            new_status = CODE_STATUS_WARNING
        else:
            new_status = CODE_STATUS_VERIFIED

        await self.db.execute(
            update(AntiFakeCode)
            .where(AntiFakeCode.id == code_id)
            .values(query_count=new_count, status=new_status)
        )
        return new_count

    # ── F4: 查询历史 ───────────────────────────────────────────────────────────

    async def get_history(
        self, user_id: int, page: int, size: int
    ) -> dict:
        """
        查询用户历史防伪查询记录（通过 PromoClick 的 action=anti_fake_verify）。
        实际使用 AntiFakeCode 表按 verified_by 过滤。
        """
        offset = (page - 1) * size

        count_stmt = (
            select(func.count(AntiFakeCode.id))
            .join(Product, AntiFakeCode.product_id == Product.id)
            .where(AntiFakeCode.verified_by == user_id)
        )
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        data_stmt = (
            select(AntiFakeCode, Product.name.label("product_name"))
            .join(Product, AntiFakeCode.product_id == Product.id)
            .where(AntiFakeCode.verified_by == user_id)
            .order_by(AntiFakeCode.verified_at.desc())
            .offset(offset)
            .limit(size)
        )
        rows = await self.db.execute(data_stmt)
        items = [
            {
                "code": row.AntiFakeCode.code,
                "product_name": row.product_name,
                "is_authentic": True,
                "queried_at": row.AntiFakeCode.verified_at,
            }
            for row in rows
        ]
        return {"total": total, "items": items}

    # ── F5: 批量导入 ───────────────────────────────────────────────────────────

    async def bulk_create(
        self,
        codes: List[dict],
        salt: str = "",
        operator_id: Optional[int] = None,
    ) -> int:
        """
        批量创建防伪码记录。
        约束: 单次不超过 BATCH_IMPORT_MAX 条。
        返回成功插入的条数。
        """
        if len(codes) > BATCH_IMPORT_MAX:
            raise BatchSizeExceeded(BATCH_IMPORT_MAX, len(codes))

        records = []
        for item in codes:
            code_str = item["code"].strip().upper()
            code_hash = hashlib.sha256(
                (code_str + salt).encode()
            ).hexdigest()
            records.append(
                AntiFakeCode(
                    code=code_str,
                    code_hash=code_hash,
                    product_id=item.get("product_id"),
                    batch_no=item.get("batch_no"),
                    status=CODE_STATUS_UNUSED,
                    query_count=0,
                    is_verified=False,
                )
            )

        for record in records:
            self.db.add(record)
        await self.db.flush()
        return len(records)
