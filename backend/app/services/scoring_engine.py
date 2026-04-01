"""
F2 — 评分计算引擎

职责:
- 综合肌肤评分计算 (加权平均, 0-100)
- 单项严重度判定 (none/mild/moderate/severe)
- 肤质分类标签映射
"""
from typing import List

from app.schemas.skin import SkinIssue, SkinIssueType, Severity

# ── 常量 ─────────────────────────────────────────────────────────────────────

ISSUE_WEIGHTS: dict[str, float] = {
    SkinIssueType.ACNE:         0.20,
    SkinIssueType.SPOT:         0.15,
    SkinIssueType.WRINKLE:      0.15,
    SkinIssueType.PORE:         0.10,
    SkinIssueType.DARK_CIRCLE:  0.10,
    SkinIssueType.REDNESS:      0.10,
    SkinIssueType.DRYNESS:      0.05,
    SkinIssueType.OILINESS:     0.05,
    SkinIssueType.UNEVEN_TONE:  0.05,
    SkinIssueType.SAGGING:      0.05,
}

# 严重度阈值 (score 越高越好)
SEVERITY_THRESHOLDS = [
    (80, Severity.NONE),
    (60, Severity.MILD),
    (40, Severity.MODERATE),
    (0,  Severity.SEVERE),
]

# ── 评分函数 ──────────────────────────────────────────────────────────────────

def calculate_overall_score(issues: List[SkinIssue]) -> int:
    """
    综合评分 = Σ(各问题评分 × 权重) + 剩余权重 × 100
    返回 0-100 整数，越高越好。
    """
    if not issues:
        return 100

    total_weighted_score = 0.0
    total_weight = 0.0

    for issue in issues:
        weight = ISSUE_WEIGHTS.get(issue.type, 0.05)
        total_weighted_score += issue.score * weight
        total_weight += weight

    # 未出现的问题视作满分
    remaining_weight = max(0.0, 1.0 - total_weight)
    total_weighted_score += 100.0 * remaining_weight

    return round(total_weighted_score)


def get_severity(score: int) -> Severity:
    """
    单项严重度判定:
      score >= 80  → none
      score 60-79  → mild
      score 40-59  → moderate
      score  < 40  → severe
    """
    for threshold, severity in SEVERITY_THRESHOLDS:
        if score >= threshold:
            return severity
    return Severity.SEVERE


def label_for_issue(issue_type: SkinIssueType) -> str:
    """返回肌肤问题的中文标签。"""
    LABELS = {
        SkinIssueType.ACNE:         "痘痘/粉刺",
        SkinIssueType.SPOT:         "色斑/雀斑",
        SkinIssueType.WRINKLE:      "皱纹/细纹",
        SkinIssueType.PORE:         "毛孔粗大",
        SkinIssueType.DARK_CIRCLE:  "黑眼圈",
        SkinIssueType.REDNESS:      "泛红/敏感",
        SkinIssueType.DRYNESS:      "干燥/脱皮",
        SkinIssueType.OILINESS:     "出油/油光",
        SkinIssueType.UNEVEN_TONE:  "肤色不均",
        SkinIssueType.SAGGING:      "松弛/下垂",
    }
    return LABELS.get(issue_type, str(issue_type))


def enrich_issues(issues: List[SkinIssue]) -> List[SkinIssue]:
    """
    根据 score 重新计算每条 issue 的 severity 和 label（若缺失）。
    返回新列表，不修改原对象。
    """
    enriched = []
    for issue in issues:
        enriched.append(
            SkinIssue(
                type=issue.type,
                severity=get_severity(issue.score),
                score=issue.score,
                label=issue.label or label_for_issue(issue.type),
                description=issue.description,
                regions=issue.regions,
            )
        )
    return enriched
