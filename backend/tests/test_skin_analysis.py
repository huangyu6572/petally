"""
AI Skin Analysis Module — 完整测试套件
涵盖:
  F1 - 图片预处理与安全校验
  F2 - 评分计算引擎
  F3 - 建议生成引擎 & 产品推荐
  F4 - 分析任务核心 (submit/get_result, 日限制, 缓存, 越权)
  F5 - 历史记录与趋势分析
"""
import json
import pytest
from io import BytesIO
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.skin_analysis_service import (
    SkinAnalysisService,
    DailyLimitExceeded,
    UnsupportedImageFormat,
    FileSizeTooLarge,
    MaliciousFileDetected,
    AnalysisNotFound,
    PermissionDenied,
    CACHE_KEY_RESULT,
    CACHE_KEY_DAILY,
)
from app.services.image_processor import (
    validate_content_type,
    validate_file_size,
    validate_magic_bytes,
    validate_resolution,
    UnsupportedImageFormat as ImgUnsupportedFmt,
    FileSizeTooLarge as ImgFileTooLarge,
    MaliciousFileDetected as ImgMalicious,
    ImageResolutionTooLow,
    MAX_FILE_SIZE,
    MIN_RESOLUTION,
)
from app.services.scoring_engine import (
    calculate_overall_score,
    get_severity,
    label_for_issue,
    enrich_issues,
)
from app.services.suggestion_engine import generate_suggestions
from app.repositories.skin_analysis_repository import (
    SkinAnalysisRepository,
    STATUS_PROCESSING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_TIMEOUT,
)
from app.schemas.skin import (
    SkinIssue, SkinIssueType, Severity, Suggestion,
)
from app.models.models import SkinAnalysis


# ── Helpers ───────────────────────────────────────────────────────────────────

JPEG_MAGIC = b"\xff\xd8\xff" + b"\x00" * 100   # valid JPEG magic
PNG_MAGIC  = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP_MAGIC = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 100


def make_issue(issue_type: str, score: int, severity: str = None) -> SkinIssue:
    sev = Severity(severity) if severity else Severity.MODERATE
    return SkinIssue(
        type=SkinIssueType(issue_type),
        severity=sev,
        score=score,
        label="test",
        description="test desc",
    )


def make_service(redis=None, db=None):
    if db is None:
        db = AsyncMock()
    if redis is None:
        redis = AsyncMock()
        redis.get.return_value = None
        redis.incr.return_value = 1
        redis.ttl.return_value = 55
    svc = SkinAnalysisService(db=db, redis=redis)
    svc.repo = AsyncMock()
    return svc


def make_analysis_record(
    analysis_id="ana_20260401_abc123",
    user_id=1,
    status=STATUS_PROCESSING,
    overall_score=None,
    skin_type=None,
    analysis_result=None,
    suggestions=None,
):
    record = SkinAnalysis()
    record.id = analysis_id
    record.user_id = user_id
    record.image_url = "/2026/04/01/1/ana_20260401_abc123.jpg"
    record.analysis_type = "face_full"
    record.status = status
    record.overall_score = overall_score
    record.skin_type = skin_type
    record.analysis_result = analysis_result
    record.suggestions = suggestions
    record.model_version = "skin-v2.1"
    record.created_at = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
    return record


# ══════════════════════════════════════════════════════════════════════════════
# F1 — 图片预处理与安全校验
# ══════════════════════════════════════════════════════════════════════════════

class TestImageProcessor:
    """SK-U-01 ~ SK-U-07: 图片预处理校验"""

    def test_valid_jpeg_content_type_accepted(self):
        """有效 JPEG MIME 类型通过校验"""
        validate_content_type("image/jpeg")  # 不应抛出

    def test_valid_png_content_type_accepted(self):
        """有效 PNG MIME 类型通过校验"""
        validate_content_type("image/png")

    def test_valid_webp_content_type_accepted(self):
        """有效 WebP MIME 类型通过校验"""
        validate_content_type("image/webp")

    def test_bmp_format_rejected(self):
        """SK-U-05: BMP 格式被拒绝"""
        with pytest.raises(ImgUnsupportedFmt, match="不支持的图片格式"):
            validate_content_type("image/bmp")

    def test_text_format_rejected(self):
        """非图片 MIME 被拒绝"""
        with pytest.raises(ImgUnsupportedFmt):
            validate_content_type("text/html")

    def test_file_size_within_limit_accepted(self):
        """SK-U-01: 正常大小文件通过"""
        data = b"x" * (5 * 1024 * 1024)  # 5MB
        validate_file_size(data)  # 不应抛出

    def test_file_size_exactly_max_accepted(self):
        """恰好 10MB 通过"""
        data = b"x" * MAX_FILE_SIZE
        validate_file_size(data)

    def test_file_size_over_limit_rejected(self):
        """SK-U-06: 超过 10MB 被拒绝"""
        data = b"x" * (MAX_FILE_SIZE + 1)
        with pytest.raises(ImgFileTooLarge, match="超过 10MB 限制"):
            validate_file_size(data)

    def test_jpeg_magic_bytes_accepted(self):
        """有效 JPEG magic bytes 通过"""
        validate_magic_bytes(JPEG_MAGIC, "image/jpeg")  # 不应抛出

    def test_png_magic_bytes_accepted(self):
        """有效 PNG magic bytes 通过"""
        validate_magic_bytes(PNG_MAGIC, "image/png")

    def test_webp_magic_bytes_accepted(self):
        """有效 WebP magic bytes 通过"""
        validate_magic_bytes(WEBP_MAGIC, "image/webp")

    def test_fake_jpeg_magic_bytes_rejected(self):
        """SK-U-07: 伪装 JPEG (实为 EXE) 被 magic bytes 检测拒绝"""
        fake_data = b"MZ" + b"\x00" * 100  # EXE magic bytes
        with pytest.raises(ImgMalicious, match="恶意文件"):
            validate_magic_bytes(fake_data, "image/jpeg")

    def test_fake_png_magic_bytes_rejected(self):
        """PNG 格式伪装被拒绝"""
        fake_data = b"\xff\xd8\xff" + b"\x00" * 100  # JPEG bytes declared as PNG
        with pytest.raises(ImgMalicious):
            validate_magic_bytes(fake_data, "image/png")

    def test_resolution_minimum_accepted(self):
        """恰好达到最小分辨率通过"""
        validate_resolution(480, 480)

    def test_resolution_too_low_rejected(self):
        """SK-U-04: 低分辨率被拒绝"""
        with pytest.raises(ImageResolutionTooLow, match="低于最小要求"):
            validate_resolution(320, 240)

    def test_resolution_width_too_low(self):
        """宽度不足被拒绝"""
        with pytest.raises(ImageResolutionTooLow):
            validate_resolution(400, 600)

    def test_resolution_height_too_low(self):
        """高度不足被拒绝"""
        with pytest.raises(ImageResolutionTooLow):
            validate_resolution(600, 400)


# ══════════════════════════════════════════════════════════════════════════════
# F2 — 评分计算引擎
# ══════════════════════════════════════════════════════════════════════════════

class TestScoringEngine:
    """SK-U-13 ~ SK-U-19: 评分计算"""

    def test_no_issues_perfect_score(self):
        """SK-U-13: 无问题时综合评分 = 100"""
        assert calculate_overall_score([]) == 100

    def test_all_issues_zero_score(self):
        """SK-U-15: 所有问题 score=0 综合评分 = 0"""
        issues = [make_issue(t, 0) for t in [
            "acne", "spot", "wrinkle", "pore", "dark_circle",
            "redness", "dryness", "oiliness", "uneven_tone", "sagging"
        ]]
        assert calculate_overall_score(issues) == 0

    def test_all_issues_perfect_score(self):
        """SK-U-13 变体: 所有问题 score=100 综合评分 = 100"""
        issues = [make_issue(t, 100) for t in [
            "acne", "spot", "wrinkle", "pore", "dark_circle",
            "redness", "dryness", "oiliness", "uneven_tone", "sagging"
        ]]
        assert calculate_overall_score(issues) == 100

    def test_mixed_scores(self):
        """SK-U-14: 混合分数加权计算"""
        # acne=35(w=0.20), pore=65(w=0.10), dark_circle=58(w=0.10)
        # = 35*0.20 + 65*0.10 + 58*0.10 + 100*(1-0.40)
        # = 7 + 6.5 + 5.8 + 60 = 79.3 → 79
        issues = [
            make_issue("acne", 35),
            make_issue("pore", 65),
            make_issue("dark_circle", 58),
        ]
        score = calculate_overall_score(issues)
        assert 79 <= score <= 80

    def test_single_severe_acne(self):
        """单一痘痘问题 score=10"""
        # 10*0.20 + 100*0.80 = 2 + 80 = 82
        issues = [make_issue("acne", 10)]
        assert calculate_overall_score(issues) == 82

    def test_severity_none(self):
        """SK-U-16: score=85 → severity=none"""
        assert get_severity(85) == Severity.NONE

    def test_severity_none_boundary(self):
        """score=80 → severity=none (边界)"""
        assert get_severity(80) == Severity.NONE

    def test_severity_mild(self):
        """SK-U-17: score=65 → severity=mild"""
        assert get_severity(65) == Severity.MILD

    def test_severity_mild_boundary(self):
        """score=60 → severity=mild (边界)"""
        assert get_severity(60) == Severity.MILD

    def test_severity_moderate(self):
        """SK-U-18: score=45 → severity=moderate"""
        assert get_severity(45) == Severity.MODERATE

    def test_severity_moderate_boundary(self):
        """score=40 → severity=moderate (边界)"""
        assert get_severity(40) == Severity.MODERATE

    def test_severity_severe(self):
        """SK-U-19: score=30 → severity=severe"""
        assert get_severity(30) == Severity.SEVERE

    def test_severity_severe_boundary(self):
        """score=0 → severity=severe (边界)"""
        assert get_severity(0) == Severity.SEVERE

    def test_label_for_all_issue_types(self):
        """所有问题类型都有中文标签"""
        for issue_type in SkinIssueType:
            label = label_for_issue(issue_type)
            assert label and len(label) > 0

    def test_enrich_issues_recalculates_severity(self):
        """enrich_issues 根据 score 重新计算 severity"""
        issues = [make_issue("acne", 85, severity="severe")]  # wrong severity
        enriched = enrich_issues(issues)
        assert enriched[0].severity == Severity.NONE  # should be recalculated


# ══════════════════════════════════════════════════════════════════════════════
# F3 — 建议生成引擎
# ══════════════════════════════════════════════════════════════════════════════

class TestSuggestionEngine:
    """SK-U-20 ~ SK-U-23: 建议生成"""

    def test_no_issues_no_suggestions(self):
        """无问题时返回空建议列表"""
        assert generate_suggestions([]) == []

    def test_acne_moderate_generates_skincare_advice(self):
        """SK-U-20: 中度痘痘生成清洁和控油建议"""
        issues = [make_issue("acne", 45, severity="moderate")]
        suggestions = generate_suggestions(issues)
        titles = [s.title for s in suggestions]
        assert len(suggestions) > 0
        # 应包含清洁或控油相关建议
        has_relevant = any("清洁" in t or "控油" in t for t in titles)
        assert has_relevant

    def test_severe_acne_includes_medical_advice(self):
        """SK-U-22: 严重痘痘建议就医"""
        issues = [make_issue("acne", 20, severity="severe")]
        suggestions = generate_suggestions(issues)
        titles = [s.title for s in suggestions]
        assert "建议就医" in titles

    def test_no_duplicate_suggestions(self):
        """SK-U-21: 建议不重复"""
        issues = [
            make_issue("acne", 45, severity="moderate"),
            make_issue("pore", 55, severity="moderate"),
            make_issue("oiliness", 50, severity="moderate"),
        ]
        suggestions = generate_suggestions(issues)
        titles = [s.title for s in suggestions]
        assert len(titles) == len(set(titles))

    def test_suggestions_sorted_by_priority(self):
        """SK-U-21: 建议按优先级排序"""
        issues = [make_issue("acne", 20, severity="severe")]
        suggestions = generate_suggestions(issues)
        priorities = [s.priority for s in suggestions]
        assert priorities == sorted(priorities)

    def test_mild_severity_generates_advice(self):
        """轻度问题也生成建议"""
        issues = [make_issue("spot", 70, severity="mild")]
        suggestions = generate_suggestions(issues)
        assert len(suggestions) > 0

    def test_multiple_issue_types(self):
        """多种问题类型各自触发相应建议"""
        issues = [
            make_issue("dryness", 55, severity="moderate"),
            make_issue("redness", 65, severity="mild"),
        ]
        suggestions = generate_suggestions(issues)
        assert len(suggestions) > 0

    def test_suggestion_fields_present(self):
        """建议包含必要字段"""
        issues = [make_issue("wrinkle", 55, severity="moderate")]
        suggestions = generate_suggestions(issues)
        for s in suggestions:
            assert s.category in ("skincare", "lifestyle")
            assert len(s.title) <= 10
            assert len(s.content) <= 80  # 允许稍长，50字是目标


# ══════════════════════════════════════════════════════════════════════════════
# F4 — 分析任务核心
# ══════════════════════════════════════════════════════════════════════════════

class TestSubmitAnalysis:
    """SK-U-24 ~ SK-U-25: 提交分析"""

    @pytest.mark.asyncio
    async def test_submit_normal_returns_analysis_id(self):
        """SK-U-24: 正常提交返回 analysis_id + status=processing"""
        svc = make_service()
        svc.repo.create = AsyncMock(return_value=None)

        mock_image = AsyncMock()
        mock_image.content_type = "image/jpeg"
        mock_image.filename = "face.jpg"
        mock_image.read = AsyncMock(return_value=JPEG_MAGIC + b"\x00" * 1000)
        mock_image.seek = AsyncMock()

        result = await svc.submit_analysis(user_id=1, image=mock_image)

        assert "analysis_id" in result
        assert result["status"] == "processing"
        assert result["analysis_id"].startswith("ana_")
        svc.repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_limit_exceeded(self):
        """SK-U-25: 超过日限制抛出 DailyLimitExceeded"""
        redis = AsyncMock()
        redis.incr.return_value = 21  # over limit of 20
        svc = make_service(redis=redis)

        mock_image = AsyncMock()
        mock_image.content_type = "image/jpeg"

        with pytest.raises(DailyLimitExceeded, match="今日分析次数已用尽"):
            await svc.submit_analysis(user_id=1, image=mock_image)

    @pytest.mark.asyncio
    async def test_unsupported_format_rejected(self):
        """不支持的图片格式被拒绝"""
        svc = make_service()

        mock_image = AsyncMock()
        mock_image.content_type = "image/bmp"
        mock_image.filename = "face.bmp"
        mock_image.read = AsyncMock(return_value=b"BM" + b"\x00" * 100)
        mock_image.seek = AsyncMock()

        with pytest.raises(UnsupportedImageFormat):
            await svc.submit_analysis(user_id=1, image=mock_image)

    @pytest.mark.asyncio
    async def test_file_too_large_rejected(self):
        """超过 10MB 被拒绝"""
        svc = make_service()

        mock_image = AsyncMock()
        mock_image.content_type = "image/jpeg"
        mock_image.filename = "face.jpg"
        mock_image.read = AsyncMock(return_value=JPEG_MAGIC + b"\x00" * (11 * 1024 * 1024))
        mock_image.seek = AsyncMock()

        with pytest.raises(FileSizeTooLarge):
            await svc.submit_analysis(user_id=1, image=mock_image)

    @pytest.mark.asyncio
    async def test_malicious_file_rejected(self):
        """伪装为 JPEG 的恶意文件被拒绝"""
        svc = make_service()

        mock_image = AsyncMock()
        mock_image.content_type = "image/jpeg"
        mock_image.filename = "evil.jpg"
        mock_image.read = AsyncMock(return_value=b"MZ" + b"\x00" * 100)  # EXE magic
        mock_image.seek = AsyncMock()

        with pytest.raises(MaliciousFileDetected):
            await svc.submit_analysis(user_id=1, image=mock_image)

    @pytest.mark.asyncio
    async def test_daily_limit_first_call_sets_expire(self):
        """首次调用设置 Redis TTL"""
        redis = AsyncMock()
        redis.incr.return_value = 1  # first call
        svc = make_service(redis=redis)
        svc.repo.create = AsyncMock()

        mock_image = AsyncMock()
        mock_image.content_type = "image/jpeg"
        mock_image.filename = "face.jpg"
        mock_image.read = AsyncMock(return_value=JPEG_MAGIC + b"\x00" * 100)
        mock_image.seek = AsyncMock()

        await svc.submit_analysis(user_id=1, image=mock_image)
        redis.expire.assert_called_once()

    def test_generate_analysis_id_format(self):
        """生成的 ID 格式正确: ana_YYYYMMDD_xxxxxxxxxxxx"""
        aid = SkinAnalysisService._generate_analysis_id()
        assert aid.startswith("ana_")
        parts = aid.split("_")
        assert len(parts) == 3
        assert len(parts[1]) == 8
        assert len(parts[2]) == 12


class TestGetResult:
    """SK-U-26 ~ SK-U-29: 查询结果"""

    @pytest.mark.asyncio
    async def test_get_result_processing(self):
        """SK-U-27: 处理中返回 status=processing"""
        svc = make_service()
        record = make_analysis_record(status=STATUS_PROCESSING)
        svc.repo.find_by_id = AsyncMock(return_value=record)

        result = await svc.get_result("ana_20260401_abc123", user_id=1)
        assert result["status"] == "processing"

    @pytest.mark.asyncio
    async def test_get_result_completed(self):
        """SK-U-26: 完成时返回完整结果"""
        svc = make_service()
        record = make_analysis_record(
            status=STATUS_COMPLETED,
            overall_score=72,
            skin_type="混合偏油",
            analysis_result=[],
            suggestions=[],
        )
        svc.repo.find_by_id = AsyncMock(return_value=record)

        result = await svc.get_result("ana_20260401_abc123", user_id=1)
        assert result["status"] == "completed"
        assert result["overall_score"] == 72
        assert result["skin_type"] == "混合偏油"

    @pytest.mark.asyncio
    async def test_get_result_not_found(self):
        """SK-U-28: 不存在的分析抛出 AnalysisNotFound"""
        svc = make_service()
        svc.repo.find_by_id = AsyncMock(return_value=None)

        with pytest.raises(AnalysisNotFound):
            await svc.get_result("not_exist", user_id=1)

    @pytest.mark.asyncio
    async def test_get_result_permission_denied(self):
        """SK-U-29: 查看他人结果抛出 PermissionDenied"""
        svc = make_service()
        record = make_analysis_record(user_id=99)  # owned by user 99
        svc.repo.find_by_id = AsyncMock(return_value=record)

        with pytest.raises(PermissionDenied):
            await svc.get_result("ana_20260401_abc123", user_id=1)  # user 1 tries

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        """缓存命中直接返回，不查数据库"""
        redis = AsyncMock()
        cached_data = {
            "analysis_id": "ana_20260401_abc123",
            "status": "completed",
            "user_id": 1,
        }
        redis.get.return_value = json.dumps(cached_data)
        svc = make_service(redis=redis)

        result = await svc.get_result("ana_20260401_abc123", user_id=1)
        assert result["status"] == "completed"
        svc.repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_permission_denied(self):
        """缓存命中时也校验越权"""
        redis = AsyncMock()
        cached_data = {
            "analysis_id": "ana_20260401_abc123",
            "status": "completed",
            "user_id": 99,
        }
        redis.get.return_value = json.dumps(cached_data)
        svc = make_service(redis=redis)

        with pytest.raises(PermissionDenied):
            await svc.get_result("ana_20260401_abc123", user_id=1)

    @pytest.mark.asyncio
    async def test_completed_result_cached(self):
        """完成的结果写入缓存"""
        svc = make_service()
        record = make_analysis_record(
            status=STATUS_COMPLETED,
            overall_score=75,
            skin_type="干性",
            analysis_result=[],
            suggestions=[],
        )
        svc.repo.find_by_id = AsyncMock(return_value=record)

        await svc.get_result("ana_20260401_abc123", user_id=1)
        svc.redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_processing_result_not_cached(self):
        """处理中的结果不写入缓存"""
        svc = make_service()
        record = make_analysis_record(status=STATUS_PROCESSING)
        svc.repo.find_by_id = AsyncMock(return_value=record)

        await svc.get_result("ana_20260401_abc123", user_id=1)
        svc.redis.set.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# F5 — 历史记录与趋势分析
# ══════════════════════════════════════════════════════════════════════════════

class TestGetHistory:
    """SK-U-*: 历史记录"""

    @pytest.mark.asyncio
    async def test_get_history_returns_paged_result(self):
        """历史记录返回分页结果"""
        svc = make_service()
        records = [
            make_analysis_record(f"ana_{i}", status=STATUS_COMPLETED, overall_score=70 + i)
            for i in range(3)
        ]
        svc.repo.get_history = AsyncMock(return_value=(3, records))

        result = await svc.get_history(user_id=1, page=1, size=10)
        assert result["total"] == 3
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_get_history_empty(self):
        """无历史记录返回空列表"""
        svc = make_service()
        svc.repo.get_history = AsyncMock(return_value=(0, []))

        result = await svc.get_history(user_id=1)
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_history_item_fields(self):
        """历史记录包含必要字段"""
        svc = make_service()
        record = make_analysis_record(status=STATUS_COMPLETED, overall_score=75, skin_type="油性")
        svc.repo.get_history = AsyncMock(return_value=(1, [record]))

        result = await svc.get_history(user_id=1)
        item = result["items"][0]
        assert "analysis_id" in item
        assert "overall_score" in item
        assert "status" in item
        assert "created_at" in item


class TestGetTrend:
    """SK-*: 趋势分析"""

    @pytest.mark.asyncio
    async def test_trend_empty_when_no_data(self):
        """无数据时返回空趋势"""
        svc = make_service()
        svc.repo.get_trend_scores = AsyncMock(return_value=[])

        result = await svc.get_trend(user_id=1, days=90)
        assert result["overall_scores"] == []
        assert result["improvement"] == "0%"

    @pytest.mark.asyncio
    async def test_trend_improvement_positive(self):
        """评分提升时 improvement 为正数"""
        svc = make_service()
        svc.repo.get_trend_scores = AsyncMock(return_value=[
            ("2026-01-15", 60),
            ("2026-02-10", 70),
            ("2026-03-20", 80),
        ])

        result = await svc.get_trend(user_id=1)
        assert result["improvement"].startswith("+")
        assert "20" in result["improvement"]

    @pytest.mark.asyncio
    async def test_trend_improvement_negative(self):
        """评分下降时 improvement 为负数"""
        svc = make_service()
        svc.repo.get_trend_scores = AsyncMock(return_value=[
            ("2026-01-15", 80),
            ("2026-03-20", 60),
        ])

        result = await svc.get_trend(user_id=1)
        assert result["improvement"].startswith("-")

    @pytest.mark.asyncio
    async def test_trend_score_list_format(self):
        """趋势数据包含 date 和 score 字段"""
        svc = make_service()
        svc.repo.get_trend_scores = AsyncMock(return_value=[
            ("2026-01-15", 62),
            ("2026-02-10", 68),
        ])

        result = await svc.get_trend(user_id=1)
        for point in result["overall_scores"]:
            assert "date" in point
            assert "score" in point


# ══════════════════════════════════════════════════════════════════════════════
# Repository 层测试
# ══════════════════════════════════════════════════════════════════════════════

class TestSkinAnalysisRepository:
    """Repository 单元测试"""

    @pytest.mark.asyncio
    async def test_create_record(self):
        """create 向 db.add 添加记录"""
        db = AsyncMock()
        db.flush = AsyncMock()
        repo = SkinAnalysisRepository(db)

        record = await repo.create(
            analysis_id="ana_20260401_test",
            user_id=1,
            image_url="/2026/04/01/1/ana_test.jpg",
        )

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert record.id == "ana_20260401_test"
        assert record.status == STATUS_PROCESSING

    @pytest.mark.asyncio
    async def test_mark_completed_executes_update(self):
        """mark_completed 调用 db.execute"""
        db = AsyncMock()
        repo = SkinAnalysisRepository(db)

        await repo.mark_completed(
            analysis_id="ana_test",
            overall_score=75,
            skin_type="油性",
            analysis_result=[],
            suggestions=[],
        )
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_failed_executes_update(self):
        """mark_failed 调用 db.execute"""
        db = AsyncMock()
        repo = SkinAnalysisRepository(db)
        await repo.mark_failed("ana_test")
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_timeout_executes_update(self):
        """mark_timeout 调用 db.execute"""
        db = AsyncMock()
        repo = SkinAnalysisRepository(db)
        await repo.mark_timeout("ana_test")
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_missing(self):
        """find_by_id 不存在时返回 None"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result
        repo = SkinAnalysisRepository(db)

        result = await repo.find_by_id("not_exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_id_returns_record(self):
        """find_by_id 找到时返回记录"""
        db = AsyncMock()
        record = make_analysis_record()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        db.execute.return_value = mock_result
        repo = SkinAnalysisRepository(db)

        result = await repo.find_by_id("ana_20260401_abc123")
        assert result is not None
        assert result.id == "ana_20260401_abc123"


# ══════════════════════════════════════════════════════════════════════════════
# AI Analyzer 评分引擎测试 (原有 + 扩展)
# ══════════════════════════════════════════════════════════════════════════════

class TestSkinAnalyzerScoring:
    """AI 分析器 get_overall_score (继承自 SkinAnalyzerBase) 测试"""

    def _make_analyzer(self):
        from app.services.ai.skin_analyzer import SkinAnalyzerBase

        class TestAnalyzer(SkinAnalyzerBase):
            async def detect_issues(self, image_url, analysis_type):
                return []
            async def generate_suggestions(self, issues, skin_type):
                return []
            async def classify_skin_type(self, image_url):
                return "normal"

        return TestAnalyzer()

    def _make_issue(self, issue_type: str, score: int) -> SkinIssue:
        return SkinIssue(
            type=SkinIssueType(issue_type),
            severity=Severity.MODERATE,
            score=score,
            label="test",
            description="test",
        )

    def test_no_issues_perfect_score(self):
        score = self._make_analyzer().get_overall_score([])
        assert score == 100

    def test_all_issues_zero_score(self):
        issues = [
            self._make_issue(t, 0)
            for t in ["acne", "spot", "wrinkle", "pore", "dark_circle",
                      "redness", "dryness", "oiliness", "uneven_tone", "sagging"]
        ]
        assert self._make_analyzer().get_overall_score(issues) == 0

    def test_mixed_scores(self):
        issues = [
            self._make_issue("acne", 35),
            self._make_issue("pore", 65),
            self._make_issue("dark_circle", 58),
        ]
        score = self._make_analyzer().get_overall_score(issues)
        assert 79 <= score <= 80

    def test_single_severe_issue(self):
        issues = [self._make_issue("acne", 10)]
        score = self._make_analyzer().get_overall_score(issues)
        assert score == 82
