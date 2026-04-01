"""
AI Skin Analysis API Endpoints
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form

from app.core.security import get_current_user_id
from app.schemas.skin import AnalyzeResponse, AnalysisResultResponse, HistoryResponse, TrendResponse
from app.schemas.common import ApiResponse

router = APIRouter()


@router.post("/analyze", response_model=ApiResponse[AnalyzeResponse])
async def submit_analysis(
    image: UploadFile = File(...),
    analysis_type: str = Form(default="face_full"),
    user_id: int = Depends(get_current_user_id),
):
    """
    提交肌肤分析任务。
    - 上传人脸/肌肤照片
    - 异步处理，返回 analysis_id
    - 支持 face_full / skin_close / acne_focus 分析类型
    """
    # TODO: Inject SkinAnalysisService and call submit_analysis
    pass


@router.get("/analyze/{analysis_id}", response_model=ApiResponse[AnalysisResultResponse])
async def get_analysis_result(
    analysis_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """获取肌肤分析结果（轮询接口）。"""
    # TODO: Inject SkinAnalysisService and call get_result
    pass


@router.get("/history", response_model=ApiResponse[HistoryResponse])
async def get_analysis_history(
    page: int = 1,
    size: int = 10,
    user_id: int = Depends(get_current_user_id),
):
    """获取用户的肌肤分析历史记录。"""
    # TODO: Inject SkinAnalysisService and call get_history
    pass


@router.get("/trend", response_model=ApiResponse[TrendResponse])
async def get_skin_trend(
    days: int = 90,
    user_id: int = Depends(get_current_user_id),
):
    """获取用户肌肤变化趋势。"""
    # TODO: Inject SkinAnalysisService and call get_trend
    pass
