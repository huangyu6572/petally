"""
Promotion Module — Unit Tests
"""
import pytest
from unittest.mock import AsyncMock

from app.services.promotion_service import PromotionService, ISSUE_PRODUCT_MAPPING


class TestPromotionMatchScore:
    """推荐匹配评分算法测试"""

    def test_exact_match_single_issue(self):
        """单问题完全匹配"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne"],
            product_tags=["清洁", "控油", "祛痘"]
        )
        assert score > 0

    def test_no_match(self):
        """完全不匹配"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne"],
            product_tags=["抗皱", "紧致"]
        )
        assert score == 0

    def test_multiple_issues_match(self):
        """多问题匹配"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne", "dryness"],
            product_tags=["清洁", "控油", "保湿", "补水"]
        )
        assert score > 0

    def test_empty_issues(self):
        """无问题"""
        score = PromotionService.calculate_match_score(
            issue_types=[],
            product_tags=["清洁"]
        )
        assert score == 0

    def test_empty_tags(self):
        """无标签"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne"],
            product_tags=[]
        )
        assert score == 0

    def test_score_not_exceed_100(self):
        """分数不超过 100"""
        score = PromotionService.calculate_match_score(
            issue_types=["acne", "spot", "wrinkle", "pore", "dryness"],
            product_tags=["清洁", "控油", "祛痘", "水杨酸", "美白", "淡斑",
                          "维C", "抗皱", "紧致", "收毛孔", "保湿", "补水"]
        )
        assert score <= 100


class TestPromotionService:
    """推广 Service 层测试"""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        return redis

    @pytest.fixture
    def service(self, mock_db, mock_redis):
        return PromotionService(db=mock_db, redis=mock_redis)

    @pytest.mark.asyncio
    async def test_track_event_writes_to_redis(self, service, mock_redis):
        """追踪事件写入 Redis"""
        await service.track_event(
            promo_id=1, user_id=1, action="click", source="home_feed"
        )
        mock_redis.rpush.assert_called_once()
        args = mock_redis.rpush.call_args
        assert args[0][0] == "promo:events"

    @pytest.mark.asyncio
    async def test_track_event_data_format(self, service, mock_redis):
        """追踪事件数据格式正确"""
        import json

        await service.track_event(
            promo_id=1, user_id=42, action="purchase", source="skin_result_page"
        )
        call_args = mock_redis.rpush.call_args[0]
        event_data = json.loads(call_args[1])
        assert event_data["promotion_id"] == 1
        assert event_data["user_id"] == 42
        assert event_data["action"] == "purchase"
        assert event_data["source"] == "skin_result_page"
        assert "created_at" in event_data


class TestIssueProductMapping:
    """问题-功效映射表完整性测试"""

    def test_all_issue_types_have_mapping(self):
        """所有肌肤问题类型都有对应的产品标签映射"""
        expected_types = [
            "acne", "spot", "wrinkle", "pore", "dark_circle",
            "redness", "dryness", "oiliness", "uneven_tone", "sagging"
        ]
        for issue_type in expected_types:
            assert issue_type in ISSUE_PRODUCT_MAPPING
            assert len(ISSUE_PRODUCT_MAPPING[issue_type]) > 0

    def test_no_empty_tags(self):
        """所有映射的标签不为空字符串"""
        for issue_type, tags in ISSUE_PRODUCT_MAPPING.items():
            for tag in tags:
                assert tag.strip() != "", f"{issue_type} has empty tag"
