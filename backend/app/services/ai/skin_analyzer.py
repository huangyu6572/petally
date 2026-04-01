"""
AI Skin Analyzer — Abstract Base & Factory
"""
from abc import ABC, abstractmethod
from typing import List

from app.schemas.skin import SkinIssue, Suggestion
from app.core.config import settings


class SkinAnalyzerBase(ABC):
    """
    AI 分析器抽象基类。
    所有 AI 实现必须继承此类，便于切换不同的 AI 供应商。
    """

    @abstractmethod
    async def detect_issues(self, image_url: str, analysis_type: str) -> List[SkinIssue]:
        """检测肌肤问题。"""
        ...

    @abstractmethod
    async def generate_suggestions(
        self, issues: List[SkinIssue], skin_type: str
    ) -> List[Suggestion]:
        """基于检测结果生成修复建议。"""
        ...

    @abstractmethod
    async def classify_skin_type(self, image_url: str) -> str:
        """判断肤质类型。"""
        ...

    def get_overall_score(self, issues: List[SkinIssue]) -> int:
        """
        计算综合评分 (0-100)。
        权重表:
        - acne: 0.20, spot: 0.15, wrinkle: 0.15, pore: 0.10
        - dark_circle: 0.10, redness: 0.10, dryness: 0.05
        - oiliness: 0.05, uneven_tone: 0.05, sagging: 0.05
        """
        WEIGHTS = {
            "acne": 0.20, "spot": 0.15, "wrinkle": 0.15, "pore": 0.10,
            "dark_circle": 0.10, "redness": 0.10, "dryness": 0.05,
            "oiliness": 0.05, "uneven_tone": 0.05, "sagging": 0.05,
        }
        if not issues:
            return 100

        total_weighted_score = 0
        total_weight = 0
        for issue in issues:
            weight = WEIGHTS.get(issue.type, 0.05)
            total_weighted_score += issue.score * weight
            total_weight += weight

        # Fill remaining weight with perfect score
        remaining_weight = 1.0 - total_weight
        total_weighted_score += 100 * remaining_weight

        return round(total_weighted_score)


class OpenAISkinAnalyzer(SkinAnalyzerBase):
    """OpenAI GPT-4 Vision 实现。"""

    async def detect_issues(self, image_url: str, analysis_type: str) -> List[SkinIssue]:
        # TODO: Call OpenAI Vision API
        raise NotImplementedError

    async def generate_suggestions(
        self, issues: List[SkinIssue], skin_type: str
    ) -> List[Suggestion]:
        # TODO: Call OpenAI Chat API with structured prompt
        raise NotImplementedError

    async def classify_skin_type(self, image_url: str) -> str:
        raise NotImplementedError


class BaiduSkinAnalyzer(SkinAnalyzerBase):
    """百度 AI 人脸分析实现。"""

    async def detect_issues(self, image_url: str, analysis_type: str) -> List[SkinIssue]:
        raise NotImplementedError

    async def generate_suggestions(
        self, issues: List[SkinIssue], skin_type: str
    ) -> List[Suggestion]:
        raise NotImplementedError

    async def classify_skin_type(self, image_url: str) -> str:
        raise NotImplementedError


def get_skin_analyzer(provider: str = None) -> SkinAnalyzerBase:
    """工厂方法：根据配置返回对应的 AI 分析器实例。"""
    provider = provider or settings.AI_PROVIDER
    analyzers = {
        "openai": OpenAISkinAnalyzer,
        "baidu": BaiduSkinAnalyzer,
    }
    analyzer_cls = analyzers.get(provider)
    if not analyzer_cls:
        raise ValueError(f"Unsupported AI provider: {provider}")
    return analyzer_cls()
