"""
AI Skin Analysis Module — Pydantic Schemas
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from enum import Enum


class AnalysisType(str, Enum):
    FACE_FULL = "face_full"
    SKIN_CLOSE = "skin_close"
    ACNE_FOCUS = "acne_focus"


class AnalysisStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class SkinIssueType(str, Enum):
    ACNE = "acne"
    SPOT = "spot"
    WRINKLE = "wrinkle"
    PORE = "pore"
    DARK_CIRCLE = "dark_circle"
    REDNESS = "redness"
    DRYNESS = "dryness"
    OILINESS = "oiliness"
    UNEVEN_TONE = "uneven_tone"
    SAGGING = "sagging"


class Severity(str, Enum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class Region(BaseModel):
    x: int
    y: int
    w: int
    h: int
    confidence: float


class SkinIssue(BaseModel):
    type: SkinIssueType
    severity: Severity
    score: int
    label: str
    description: str
    regions: list[Region] = []


class Suggestion(BaseModel):
    category: str  # skincare | lifestyle
    title: str
    content: str
    priority: int = 0


class RecommendedProduct(BaseModel):
    product_id: int
    name: str
    match_reason: str
    match_score: int


class AnalyzeResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    estimated_seconds: int = 15


class AnalysisResultResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    overall_score: Optional[int] = None
    skin_type: Optional[str] = None
    issues: list[SkinIssue] = []
    suggestions: list[Suggestion] = []
    recommended_products: list[RecommendedProduct] = []
    created_at: Optional[datetime] = None
    model_version: Optional[str] = None


class HistoryItem(BaseModel):
    analysis_id: str
    overall_score: Optional[int]
    skin_type: Optional[str]
    status: AnalysisStatus
    created_at: datetime


class HistoryResponse(BaseModel):
    total: int
    items: list[HistoryItem]


class TrendPoint(BaseModel):
    date: str
    score: int


class TrendResponse(BaseModel):
    overall_scores: list[TrendPoint]
    improvement: str
    best_improved: Optional[str] = None
    needs_attention: Optional[str] = None
