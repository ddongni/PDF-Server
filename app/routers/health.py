"""Health check 라우터"""
from fastapi import APIRouter

router = APIRouter(tags=["Health Check"])


@router.get(
    "/",
    summary="서버 상태 확인",
    description="PDF 서버가 정상적으로 실행 중인지 확인합니다."
)
def root():
    """서버 상태 확인"""
    return {"message": "PDF Server is running", "status": "ok"}

