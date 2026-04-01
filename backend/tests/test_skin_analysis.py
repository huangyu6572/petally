"""
AI Skin Analysis Module — Unit Tests
"""
import pytest
from unittest.mock import AsyncMock

from app.services.skin_analysis_service import (
    SkinAnalysisService, DailyLimitExceeded,
    UnsupportedImageFormat, FileSizeTooLarge,
)
from app.services.ai.skin_analyzer import SkinAnalyzerBase
from app.schemas.skin import SkinIssue, SkinIssueType, Severity


class TestSkinAnalysisService:
    """肌肤分析 Service 层测试"""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr.return_value = 1
        return redis

    @pytest.fixture
    def service(self, mock_db, mock_redis):
        return SkinAnalysisService(db=mock_db, redis=mock_redis)

    @pytest.mark.asyncio
    async def test_daily_limit_normal(self, service, mock_redis):
        """正常次数不被限制"""
        mock_redis.incr.return_value = 10
        await service._check_daily_limit(user_id=1)

    @pytest.mark.asyncio
    async def test_daily_limit_exceeded(self, service, mock_redis):
        """超过日限制"""
        mock_redis.incr.return_value = 21
        with pytest.raises(DailyLimitExceeded, match="今日分析次数已用尽"):
            await service._check_daily_limit(user_id=1)

    @pytest.mark.asyncio
    async def test_validate_image_invalid_type(self, service):
        """不支持的图片格式"""
        mock_file = AsyncMock()
        mock_file.content_type = "image/bmp"
        with pytest.raises(UnsupportedImageFormat):
            await service._validate_image(mock_file)

    @pytest.mark.asyncio
    async def test_validate_image_too_large(self, service):
        """图片过大"""
        mock_file = AsyncMock()
        mock_file.content_type = "image/jpeg"
        mock_file.read = AsyncMock(return_value=b"x" * (11 * 1024 * 1024))
        mock_file.seek = AsyncMock()
        with pytest.raises(FileSizeTooLarge):
            await service._validate_image(mock_file)

    def test_generate_analysis_id(self, service):
        """生成的 ID 格式正确"""
        aid = service._generate_analysis_id()
        assert aid.startswith("ana_")
        parts = aid.split("_")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 12  # short uuid


class TestSkinAnalyzerScoring:
    """AI 分析器评分计算测试"""

    def _make_analyzer(self):
        """创建一个可以测试评分的子类实例"""

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
        analyzer = self._make_analyzer()
        score = analyzer.get_overall_score([])
        assert score == 100

    def test_all_issues_zero_score(self):
        analyzer = self._make_analyzer()
        issues = [
            self._make_issue("acne", 0),
            self._make_issue("spot", 0),
            self._make_issue("wrinkle", 0),
            self._make_issue("pore", 0),
            self._make_issue("dark_circle", 0),
            self._make_issue("redness", 0),
            self._make_issue("dryness", 0),
            self._make_issue("oiliness", 0),
            self._make_issue("uneven_tone", 0),
            self._make_issue("sagging", 0),
        ]
        score = analyzer.get_overall_score(issues)
        assert score == 0

    def test_mixed_scores(self):
        analyzer = self._make_analyzer()
        issues = [
            self._make_issue("acne", 35),      # weight 0.20
            self._make_issue("pore", 65),       # weight 0.10
            self._make_issue("dark_circle", 58),  # weight 0.10
        ]
        score = analyzer.get_overall_score(issues)
        # (35*0.20 + 65*0.10 + 58*0.10) + 100*(1-0.40) = 7+6.5+5.8+60 = 79.3
        assert 79 <= score <= 80

    def test_single_severe_issue(self):
        analyzer = self._make_analyzer()
        issues = [self._make_issue("acne", 10)]  # weight 0.20
        score = analyzer.get_overall_score(issues)
        # 10*0.20 + 100*0.80 = 2 + 80 = 82
        assert score == 82
