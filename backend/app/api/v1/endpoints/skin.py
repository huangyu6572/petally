"""
F6 — AI Skin Analysis API Endpoints
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

from app.core.security import get_current_user_id
from app.core.dependencies import get_db, get_redis
from app.schemas.skin import AnalyzeResponse, AnalysisResultResponse, HistoryResponse, TrendResponse, AnalysisStatus
from app.schemas.common import ApiResponse
from app.services.skin_analysis_service import (
    SkinAnalysisService,
    DailyLimitExceeded,
    UnsupportedImageFormat,
    FileSizeTooLarge,
    MaliciousFileDetected,
    ImageResolutionTooLow,
    AnalysisNotFound,
    PermissionDenied,
)

router = APIRouter()


def _get_service(db=Depends(get_db), redis=Depends(get_redis)):
    return SkinAnalysisService(db=db, redis=redis)


@router.post("/analyze", response_model=ApiResponse[AnalyzeResponse])
async def submit_analysis(
    image: UploadFile = File(...),
    analysis_type: str = Form(default="face_full"),
    user_id: int = Depends(get_current_user_id),
    svc: SkinAnalysisService = Depends(_get_service),
):
    """提交肌肤分析任务。支持 face_full / skin_close / acne_focus。"""
    try:
        data = await svc.submit_analysis(user_id=user_id, image=image, analysis_type=analysis_type)
    except DailyLimitExceeded as e:
        raise HTTPException(status_code=429, detail={"code": 3005, "message": str(e)})
    except (UnsupportedImageFormat, MaliciousFileDetected, ImageResolutionTooLow) as e:
        raise HTTPException(status_code=422, detail={"code": 3002, "message": str(e)})
    except FileSizeTooLarge as e:
        raise HTTPException(status_code=413, detail={"code": 413, "message": str(e)})

    return ApiResponse(
        code=0,
        message="分析任务已提交",
        data=AnalyzeResponse(
            analysis_id=data["analysis_id"],
            status=AnalysisStatus.PROCESSING,
            estimated_seconds=data["estimated_seconds"],
        ),
    )


@router.get("/analyze/{analysis_id}", response_model=ApiResponse[AnalysisResultResponse])
async def get_analysis_result(
    analysis_id: str,
    user_id: int = Depends(get_current_user_id),
    svc: SkinAnalysisService = Depends(_get_service),
):
    """获取肌肤分析结果（轮询接口）。"""
    try:
        data = await svc.get_result(analysis_id=analysis_id, user_id=user_id)
    except AnalysisNotFound as e:
        raise HTTPException(status_code=404, detail={"code": 404, "message": str(e)})
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail={"code": 403, "message": str(e)})

    return ApiResponse(
        code=0,
        message="success",
        data=AnalysisResultResponse(
            analysis_id=data["analysis_id"],
            status=AnalysisStatus(data["status"]),
            overall_score=data.get("overall_score"),
            skin_type=data.get("skin_type"),
            issues=data.get("issues") or [],
            suggestions=data.get("suggestions") or [],
            recommended_products=data.get("recommended_products") or [],
            created_at=data.get("created_at"),
            model_version=data.get("model_version"),
        ),
    )


@router.get("/history", response_model=ApiResponse[HistoryResponse])
async def get_analysis_history(
    page: int = 1,
    size: int = 10,
    user_id: int = Depends(get_current_user_id),
    svc: SkinAnalysisService = Depends(_get_service),
):
    """获取用户肌肤分析历史记录。"""
    data = await svc.get_history(user_id=user_id, page=page, size=size)
    return ApiResponse(code=0, message="success", data=data)


@router.get("/trend", response_model=ApiResponse[TrendResponse])
async def get_skin_trend(
    days: int = 90,
    user_id: int = Depends(get_current_user_id),
    svc: SkinAnalysisService = Depends(_get_service),
):
    """获取用户肌肤变化趋势。"""
    data = await svc.get_trend(user_id=user_id, days=days)
    return ApiResponse(code=0, message="success", data=data)
