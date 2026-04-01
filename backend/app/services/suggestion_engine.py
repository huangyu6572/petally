"""
F3 — 建议生成引擎 & 产品推荐

职责:
- 基于检测到的肌肤问题生成护肤建议 (规则引擎)
- 严重问题附加就医建议
- 按优先级排序, 去重
- 基于问题类型匹配推荐产品 (标签匹配)
"""
from typing import List, Sequence, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas.skin import (
    SkinIssue, SkinIssueType, Severity, Suggestion, RecommendedProduct
)
from app.models.models import Product

# ── 规则库 ────────────────────────────────────────────────────────────────────

# 每种问题类型对应的护肤建议, key=(issue_type, min_severity)
# priority: 数字越小越优先
_SKINCARE_RULES: list[dict] = [
    {
        "issue": SkinIssueType.ACNE, "severity": Severity.MILD,
        "category": "skincare", "priority": 1,
        "title": "温和清洁",
        "content": "使用氨基酸洁面乳，每天早晚各一次，避免过度清洁损伤皮脂膜",
    },
    {
        "issue": SkinIssueType.ACNE, "severity": Severity.MILD,
        "category": "skincare", "priority": 2,
        "title": "控油精华",
        "content": "T区使用含烟酰胺或水杨酸的控油精华，有效疏通毛孔、减少痘痘",
    },
    {
        "issue": SkinIssueType.ACNE, "severity": Severity.MODERATE,
        "category": "lifestyle", "priority": 3,
        "title": "饮食调整",
        "content": "减少高糖高油食物摄入，多吃富含维生素C的蔬果，有助于控制痘痘",
    },
    {
        "issue": SkinIssueType.ACNE, "severity": Severity.SEVERE,
        "category": "skincare", "priority": 0,
        "title": "建议就医",
        "content": "痘痘较为严重，建议前往皮肤科就诊，避免自行处理留下痘印",
    },
    {
        "issue": SkinIssueType.SPOT, "severity": Severity.MILD,
        "category": "skincare", "priority": 2,
        "title": "美白淡斑",
        "content": "使用含烟酰胺、熊果苷或维生素C的精华液，坚持使用4-8周可见效",
    },
    {
        "issue": SkinIssueType.SPOT, "severity": Severity.MILD,
        "category": "skincare", "priority": 1,
        "title": "防晒第一",
        "content": "每日使用SPF50+防晒霜，紫外线是色斑加深的主要原因",
    },
    {
        "issue": SkinIssueType.WRINKLE, "severity": Severity.MILD,
        "category": "skincare", "priority": 2,
        "title": "抗氧化护理",
        "content": "使用含视黄醇或胜肽的抗衰精华，配合防晒延缓细纹生成",
    },
    {
        "issue": SkinIssueType.WRINKLE, "severity": Severity.MILD,
        "category": "lifestyle", "priority": 3,
        "title": "作息建议",
        "content": "保证每天7-8小时睡眠，避免熬夜，良好睡眠有助于皮肤修复",
    },
    {
        "issue": SkinIssueType.PORE, "severity": Severity.MILD,
        "category": "skincare", "priority": 2,
        "title": "毛孔护理",
        "content": "定期使用含水杨酸的去角质产品，每周1-2次，保持毛孔清洁",
    },
    {
        "issue": SkinIssueType.DARK_CIRCLE, "severity": Severity.MILD,
        "category": "lifestyle", "priority": 2,
        "title": "改善作息",
        "content": "保证充足睡眠，避免熬夜，适量补充铁质和维生素K",
    },
    {
        "issue": SkinIssueType.DARK_CIRCLE, "severity": Severity.MILD,
        "category": "skincare", "priority": 3,
        "title": "眼部护理",
        "content": "使用含咖啡因或维生素K的眼霜，轻柔按摩促进眼周血液循环",
    },
    {
        "issue": SkinIssueType.REDNESS, "severity": Severity.MILD,
        "category": "skincare", "priority": 1,
        "title": "舒缓镇静",
        "content": "选用含积雪草苷或洋甘菊提取物的舒缓精华，减少皮肤刺激",
    },
    {
        "issue": SkinIssueType.REDNESS, "severity": Severity.SEVERE,
        "category": "skincare", "priority": 0,
        "title": "建议就医",
        "content": "皮肤泛红较严重可能为玫瑰痤疮，建议皮肤科就诊确认病因",
    },
    {
        "issue": SkinIssueType.DRYNESS, "severity": Severity.MILD,
        "category": "skincare", "priority": 1,
        "title": "深层补水",
        "content": "使用含透明质酸或神经酰胺的保湿精华，配合锁水乳液",
    },
    {
        "issue": SkinIssueType.OILINESS, "severity": Severity.MILD,
        "category": "skincare", "priority": 2,
        "title": "控油平衡",
        "content": "使用控油保湿乳液，避免过度清洁破坏皮脂膜导致反弹出油",
    },
    {
        "issue": SkinIssueType.UNEVEN_TONE, "severity": Severity.MILD,
        "category": "skincare", "priority": 2,
        "title": "均匀肤色",
        "content": "坚持使用含烟酰胺精华，早晚各一次，配合防晒改善肤色不均",
    },
    {
        "issue": SkinIssueType.SAGGING, "severity": Severity.MILD,
        "category": "skincare", "priority": 2,
        "title": "紧致提升",
        "content": "使用含胜肽或DMAE的紧致精华，配合面部提拉按摩手法",
    },
]

# 问题类型 → 产品标签映射
ISSUE_TO_PRODUCT_TAGS: dict[SkinIssueType, list[str]] = {
    SkinIssueType.ACNE:        ["祛痘", "控油", "清洁"],
    SkinIssueType.SPOT:        ["美白", "淡斑", "防晒"],
    SkinIssueType.WRINKLE:     ["抗衰", "紧致", "抗氧化"],
    SkinIssueType.PORE:        ["控油", "收缩毛孔", "清洁"],
    SkinIssueType.DARK_CIRCLE: ["眼部护理", "提亮"],
    SkinIssueType.REDNESS:     ["舒缓", "修复", "敏感肌"],
    SkinIssueType.DRYNESS:     ["保湿", "补水", "修护"],
    SkinIssueType.OILINESS:    ["控油", "清爽", "平衡"],
    SkinIssueType.UNEVEN_TONE: ["美白", "提亮", "均匀"],
    SkinIssueType.SAGGING:     ["紧致", "抗衰", "弹力"],
}

_SEVERITY_ORDER = {
    Severity.NONE: 0,
    Severity.MILD: 1,
    Severity.MODERATE: 2,
    Severity.SEVERE: 3,
}


# ── 建议生成 ──────────────────────────────────────────────────────────────────

def generate_suggestions(issues: List[SkinIssue]) -> List[Suggestion]:
    """
    基于问题列表生成建议:
    1. 遍历规则库，匹配 issue_type 且 severity >= rule.severity 的规则
    2. 按优先级升序排列 (0 = 最高)
    3. 去重 (相同 title 只保留一条)
    """
    if not issues:
        return []

    # 建立 issue_type → severity 映射
    issue_severity: dict[SkinIssueType, Severity] = {
        i.type: i.severity for i in issues
    }

    candidates: list[Suggestion] = []
    seen_titles: set[str] = set()

    for rule in sorted(_SKINCARE_RULES, key=lambda r: r["priority"]):
        issue_type = rule["issue"]
        if issue_type not in issue_severity:
            continue
        actual_severity = issue_severity[issue_type]
        required_severity = rule["severity"]
        if _SEVERITY_ORDER[actual_severity] < _SEVERITY_ORDER[required_severity]:
            continue
        if rule["title"] in seen_titles:
            continue
        seen_titles.add(rule["title"])
        candidates.append(
            Suggestion(
                category=rule["category"],
                title=rule["title"],
                content=rule["content"],
                priority=rule["priority"],
            )
        )

    return candidates


# ── 产品推荐 ──────────────────────────────────────────────────────────────────

async def recommend_products(
    issues: List[SkinIssue],
    db: AsyncSession,
    limit: int = 5,
) -> List[RecommendedProduct]:
    """
    基于问题类型匹配推荐产品:
    1. 收集问题对应的标签集合
    2. 从数据库查询 tags 有交集的在售产品
    3. 按 match_score (标签命中数 × 10) 降序排列
    """
    if not issues:
        return []

    # 收集所有相关标签
    needed_tags: set[str] = set()
    issue_tag_map: dict[str, list[str]] = {}
    for issue in issues:
        tags = ISSUE_TO_PRODUCT_TAGS.get(issue.type, [])
        for tag in tags:
            needed_tags.add(tag)
        issue_tag_map[issue.type] = tags

    if not needed_tags:
        return []

    # 查询在售产品 (status=1)
    stmt = select(Product).where(Product.status == 1)
    result = await db.execute(stmt)
    products: Sequence[Product] = result.scalars().all()

    # 计算匹配分数
    scored: list[tuple[int, Product]] = []
    for product in products:
        product_tags: list[str] = product.tags or []
        hit_count = sum(1 for t in product_tags if t in needed_tags)
        if hit_count > 0:
            match_score = min(100, hit_count * 20)
            scored.append((match_score, product))

    # 按匹配分数降序排列
    scored.sort(key=lambda x: x[0], reverse=True)

    recommendations: list[RecommendedProduct] = []
    for match_score, product in scored[:limit]:
        # 生成匹配原因
        matched_tags = [t for t in (product.tags or []) if t in needed_tags]
        reason = f"含 {'、'.join(matched_tags[:3])} 成分，适合当前肌肤状态"
        recommendations.append(
            RecommendedProduct(
                product_id=product.id,
                name=product.name,
                match_reason=reason,
                match_score=match_score,
            )
        )

    return recommendations
