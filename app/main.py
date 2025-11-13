from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Body, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from app.utils.pdf_extract import extract_fields_from_pdf
from app.utils.pdf_filler import fill_pdf, get_base_tag_from_json
from pydantic import BaseModel
from typing import Dict, Any
import logging
import json
import tempfile
import os
import hashlib

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
    docs_url="/docs",  # Swagger UI 경로 (기본값: /docs)
    redoc_url="/redoc",  # ReDoc 경로 (기본값: /redoc)
    openapi_url="/openapi.json"  # OpenAPI 스키마 경로 (기본값: /openapi.json)
)

# CORS 설정 (개발 환경)
# 모든 origin 허용 (개발 환경에서만 사용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 origin 허용
    allow_credentials=False,  # allow_origins=["*"]일 때는 False여야 함
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 422 오류 상세 정보를 반환하는 핸들러
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    logger.error(f"Validation error: {errors}")
    logger.error(f"Request URL: {request.url}")
    logger.error(f"Request method: {request.method}")
    logger.error(f"Request headers: {dict(request.headers)}")
    
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

@app.get(
    "/",
    tags=["Health Check"],
    summary="서버 상태 확인",
    description="PDF 서버가 정상적으로 실행 중인지 확인합니다."
)
def root():
    """서버 상태 확인"""
    return {"message": "PDF Server is running", "status": "ok"}

@app.post(
    "/upload-and-extract",
    tags=["PDF 처리"],
    summary="PDF 필드 추출",
    description="""
    PDF 파일을 업로드하고 XFA 폼의 필드 구조를 추출하여 JSON으로 반환합니다.
    
    - PDF 파일을 서버에 저장
    - XFA 폼의 필드 구조를 자동으로 추출
    - JSON 형식으로 필드 구조 반환
    - 동일한 파일이 이미 업로드된 경우 기존 필드 구조 재사용
    """,
    response_description="추출된 필드 구조 (JSON 형식)"
)
async def upload_and_extract(
    file: UploadFile = File(
        ...,
        description="업로드할 PDF 파일 (XFA 폼 기반)",
        example="IMM0800e.pdf"
    )
):
    logger.info(f"파일 업로드 요청 받음: filename={file.filename}, content_type={file.content_type}")
    
    # 파일명 검증
    if not file.filename:
        logger.error("파일명이 없습니다.")
        raise HTTPException(status_code=400, detail="파일명이 없습니다. 파일을 선택해주세요.")
    
    # 파일 확장자 검증
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")
    
    # 업로드 디렉토리 생성
    upload_dir = Path(__file__).parent.parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    
    # 파일 저장 경로 (원본 파일명 그대로 사용)
    file_path = upload_dir / file.filename
    
    # 파일 내용 읽기
    logger.info(f"파일 읽기 시작: {file.filename}")
    contents = await file.read()
    logger.info(f"파일 크기: {len(contents)} bytes")
    
    if len(contents) == 0:
        logger.error("빈 파일입니다.")
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    
    # 업로드된 파일의 체크섬 계산
    upload_checksum = hashlib.sha256(contents).hexdigest()
    logger.info(f"업로드 파일 체크섬: {upload_checksum[:16]}...")
    
    # 기존 파일이 있는지 확인
    file_exists = file_path.exists()
    should_use_existing = False
    
    if file_exists:
        # 기존 파일의 체크섬 계산
        with open(file_path, "rb") as f:
            existing_checksum = hashlib.sha256(f.read()).hexdigest()
        logger.info(f"기존 파일 체크섬: {existing_checksum[:16]}...")
        
        # 체크섬이 같으면 기존 파일 사용
        if upload_checksum == existing_checksum:
            logger.info(f"파일 내용이 동일합니다. 기존 파일을 사용합니다.")
            should_use_existing = True
        else:
            logger.info(f"파일 내용이 다릅니다. 기존 파일을 업데이트합니다.")
            # 기존 파일 덮어쓰기 (아래에서 처리)
    
    # 기존 파일 사용 (체크섬이 같을 때)
    if should_use_existing:
        try:
            # fields에 이미 JSON이 있는지 확인
            field_maps_dir = Path(__file__).parent.parent / "fields"
            form_name = file_path.stem
            json_file = field_maps_dir / f"{form_name}.json"
            
            if json_file.exists():
                # 기존 JSON 파일 읽기
                logger.info(f"기존 JSON 파일 사용: {json_file}")
                with open(json_file, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
                logger.info(f"기존 필드 맵 로드 완료")
            else:
                # 기존 파일에서 필드 추출
                logger.info(f"기존 파일에서 필드 추출 시작: {file_path}")
                json_data = extract_fields_from_pdf(file_path, save_to_file=True)
                logger.info(f"필드 추출 완료: {len(json_data)} 필드")
            
            # 응답 반환 (fields 키로 감싸서 반환)
            return JSONResponse(content={"fields": json_data})
        except Exception as e:
            logger.error(f"기존 파일 처리 중 오류: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail=f"기존 파일에서 필드를 추출하는 중 오류가 발생했습니다: {str(e)}"
            )
    
    # 새 파일 저장 또는 기존 파일 업데이트
    try:
        logger.info(f"파일 저장 중: {file_path}")
        with open(file_path, "wb") as f:
            f.write(contents)
        logger.info(f"파일 저장 완료: {file_path}")
        
        # 필드 추출
        logger.info(f"필드 추출 시작: {file_path}")
        json_data = extract_fields_from_pdf(file_path, save_to_file=True)
        logger.info(f"필드 추출 완료: {len(json_data)} 필드")
        
        # 응답 반환 (fields만 반환)
        return JSONResponse(content=json_data)
    
    except HTTPException:
        # HTTPException은 그대로 전달
        raise
    except Exception as e:
        # 오류 발생 시 저장된 파일 삭제
        if file_path.exists():
            file_path.unlink()
        import traceback
        error_detail = str(e)
        raise HTTPException(status_code=500, detail=f"파일 처리 중 오류가 발생했습니다: {error_detail}")

# 필드 채우기, 파일 변환, 다운로드
def cleanup_temp_file(file_path: Path):
    """임시 파일 삭제"""
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"임시 파일 삭제 완료: {file_path}")
    except Exception as e:
        logger.error(f"임시 파일 삭제 실패: {file_path} - {e}")

class FillPdfRequest(BaseModel):
    """PDF 필드 채우기 요청 모델"""
    filename: str
    fields: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "filename": "IMM0800e.pdf",
                "fields": {
                    "IMM_0800": {
                        "Page1": {
                            "PersonalDetails": {
                                "Name": {
                                    "FamilyName": "홍",
                                    "GivenName": "길동"
                                }
                            }
                        }
                    }
                }
            }
        }

@app.post(
    "/fill-pdf",
    tags=["PDF 처리"],
    summary="PDF 필드 채우기 (JSON body)",
    description="""
    JSON 데이터를 사용하여 PDF 폼의 필드를 채우고 채워진 PDF 파일을 다운로드합니다.
    
    - `uploads` 디렉토리에서 지정된 PDF 파일 사용
    - 제공된 필드 데이터로 PDF 폼 자동 채우기
    - 채워진 PDF 파일을 다운로드
    
    **주의사항:**
    - 먼저 `/upload-and-extract` 엔드포인트로 PDF 파일을 업로드해야 합니다.
    - `fields` 구조는 추출된 필드 구조와 일치해야 합니다.
    """,
    response_description="채워진 PDF 파일 (application/pdf)"
)
async def fill_pdf(
    request: FillPdfRequest,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    upload_dir = Path(__file__).parent.parent / "uploads"
    
    logger.info(f"JSON body 요청: filename={request.filename}")
    file_path = upload_dir / request.filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"파일 '{request.filename}'을 찾을 수 없습니다. 먼저 /upload-and-extract로 파일을 업로드해주세요."
        )
    logger.info(f"기존 파일 사용: {file_path}")
    fields_data = request.fields
    pdf_filename = request.filename
    
    # 공통 PDF 처리 로직
    return await _process_fill_pdf(file_path, fields_data, pdf_filename, background_tasks)

async def _process_fill_pdf(
    file_path: Path,
    fields_data: Dict[str, Any],
    pdf_filename: str,
    background_tasks: BackgroundTasks
):
    """PDF 채우기 공통 로직"""
    logger.info(f"PDF 파일 찾음: {file_path}, fields keys: {list(fields_data.keys()) if fields_data else None}")
    
    try:
        # base_tag 추론
        base_tag = get_base_tag_from_json(fields_data)
        logger.info(f"Base tag: {base_tag}")
        
        # 임시 파일 생성 (다운로드 후 자동 삭제)
        form_name = file_path.stem
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf",
            prefix=f"{form_name}_filled_",
            dir=None
        )
        temp_file.close()
        output_file = Path(temp_file.name)
        
        try:
            # PDF 채우기
            logger.info(f"PDF 채우기 시작: {file_path} -> {output_file}")
            fill_pdf(file_path, fields_data, output_file, base_tag_hint=base_tag)
            logger.info(f"PDF 채우기 완료: {output_file}")
            
            # 파일 다운로드 응답 (다운로드 후 파일 삭제)
            background_tasks.add_task(cleanup_temp_file, output_file)
            return FileResponse(
                path=str(output_file),
                filename=f"{form_name}_filled.pdf",
                media_type="application/pdf"
            )
        except Exception as e:
            # 오류 발생 시 임시 파일 삭제
            if output_file.exists():
                output_file.unlink()
            raise
    
    except Exception as e:
        logger.error(f"PDF 채우기 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"PDF 채우기 중 오류가 발생했습니다: {str(e)}"
        )
