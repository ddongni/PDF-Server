"""예외 핸들러"""
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logger = logging.getLogger(__name__)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """422 Validation Error 핸들러"""
    errors = exc.errors()
    import json
    logger.error(f"Validation error: {json.dumps(errors, indent=2, ensure_ascii=False)}")
    logger.error(f"Request URL: {request.url}")
    logger.error(f"Request method: {request.method}")
    logger.error(f"Request headers: {dict(request.headers)}")
    
    # 요청 본문 확인 (가능한 경우)
    try:
        body = await request.body()
        logger.error(f"Request body size: {len(body)} bytes")
        if len(body) < 1000:  # 작은 경우만 로그 출력
            logger.error(f"Request body (first 500 bytes): {body[:500]}")
    except Exception as e:
        logger.error(f"Request body 읽기 실패: {e}")
    
    # errors를 JSON 직렬화 가능한 형태로 변환
    errors_serializable = []
    for err in errors:
        error_dict = {
            "loc": list(err.get("loc", [])),
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "")),
        }
        if "ctx" in err:
            error_dict["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
        errors_serializable.append(error_dict)
    
    # 'file' 필드가 없는 경우 특별한 메시지
    missing_file = any(
        err.get("loc") == ("body", "file") and err.get("type") == "missing" 
        for err in errors
    )
    
    if missing_file:
        message = "❌ 'file' 필드가 요청에 없습니다. multipart/form-data 형식으로 'file' 필드에 PDF 파일을 첨부해주세요."
    else:
        message = "요청 형식이 올바르지 않습니다. 'file' 필드로 PDF 파일을 업로드해주세요."
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": errors_serializable,
            "message": message,
            "required_field": "file",
            "content_type": "multipart/form-data",
            "examples": {
                "curl": 'curl -X POST "http://localhost:8000/upload-and-extract" -F "file=@your_file.pdf"',
                "python_requests": 'import requests\nurl = "http://localhost:8000/upload-and-extract"\nfiles = {"file": ("test.pdf", open("test.pdf", "rb"), "application/pdf")}\nresponse = requests.post(url, files=files)',
                "javascript_fetch": 'const formData = new FormData();\nformData.append("file", fileInput.files[0]);\nfetch("http://localhost:8000/upload-and-extract", { method: "POST", body: formData })'
            }
        }
    )

