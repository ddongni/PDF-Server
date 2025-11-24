"""FastAPI 앱 생성 및 설정"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.middleware import setup_cors
from app.core.exceptions import validation_exception_handler
from app.routers import health, pdf, potal


def create_app() -> FastAPI:
    """FastAPI 앱 생성 및 설정"""
    app = FastAPI(
        title="PDF Server API",
        description="""
        XFA(XML Forms Architecture) 기반 PDF 폼을 자동으로 처리하는 API 서버입니다.
        
        ## 주요 기능
        
        * **PDF 필드 추출**: PDF 파일을 업로드하여 필드 구조를 JSON으로 추출
        * **PDF 필드 채우기**: JSON 데이터를 사용하여 PDF 폼을 자동으로 채우기
        
        ## 사용 방법
        
        1. `/upload-and-extract` 엔드포인트로 PDF 파일을 업로드하여 필드 구조 추출
        2. 추출된 JSON 구조를 참고하여 데이터 작성
        3. `/fill-pdf` 엔드포인트로 데이터를 전송하여 채워진 PDF 다운로드
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # 미들웨어 및 예외 핸들러 설정
    setup_cors(app)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # Rate Limiter 설정 (프로필 라우터용)
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from fastapi.responses import JSONResponse
    
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request, exc):
        """Rate limit 초과 시 예외 핸들러"""
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "detail": str(exc)}
        )
    
    app.add_middleware(SlowAPIMiddleware)
    
    # 라우터 등록
    app.include_router(health.router)
    app.include_router(pdf.router)
    app.include_router(potal.router)
    
    return app



