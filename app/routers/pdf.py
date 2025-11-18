"""PDF 처리 라우터"""
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
import logging
from pathlib import Path

from app.services.pdf_extract_service import upload_and_extract, extract_field_values
from app.services.pdf_filler_service import fill_pdf_with_data
from app.services.pdf_field_type_service import extract_field_types
from app.models.schemas import FillPdfRequest, ExtractFieldTypesRequest, ExtractFieldValuesRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["PDF 처리"])


@router.post(
    "/upload-and-extract",
    summary="PDF 필드 추출",
    description="""
    PDF 파일을 업로드하고 XFA 폼의 필드 구조를 추출하여 JSON으로 반환합니다.
    
    - PDF 파일을 서버에 저장
    - XFA 폼의 필드 구조를 자동으로 추출
    - JSON 형식으로 필드 구조 반환 (값은 빈 문자열)
    - 동일한 파일이 이미 업로드된 경우 기존 필드 구조 재사용
    """,
    response_description="추출된 필드 구조 (JSON 형식)"
)
async def upload_and_extract_endpoint(
    file: UploadFile = File(
        ...,
        description="업로드할 PDF 파일 (XFA 폼 기반)",
        example="IMM0800e.pdf"
    )
):
    logger.info(f"파일 업로드 요청 받음: filename={file.filename}, content_type={file.content_type}")
    
    # 파일 내용 읽기
    contents = await file.read()
    logger.info(f"파일 크기: {len(contents)} bytes")
    
    # 서비스를 통해 업로드 및 필드 추출
    result = await upload_and_extract(file.filename, contents)
    
    return JSONResponse(content=result)


@router.post(
    "/fill-pdf",
    summary="PDF 필드 채우기",
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
async def fill_pdf_endpoint(
    request: FillPdfRequest,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    logger.info(f"JSON body 요청: filename={request.filename}")
    
    # 서비스를 통해 PDF 채우기
    return await fill_pdf_with_data(
        request.filename,
        request.fields,
        background_tasks
    )


@router.post(
    "/extract-field-types",
    summary="PDF 필드 타입 추출",
    description="""
    업로드된 PDF 파일에서 필드 타입, 옵션, 포맷 정보를 추출합니다.
    
    - 필드 타입: text, select, checkbox, radio, date, time 등
    - select/radio 필드의 옵션 목록
    - date/time 필드의 포맷 정보
    
    **주의사항:**
    - 먼저 `/upload-and-extract` 엔드포인트로 PDF 파일을 업로드해야 합니다.
    
    **응답 예시:**
    ```json
    {
        "IMM_0800": {
            "Page1": {
                "PersonalDetails": {
                    "Name": {
                        "FamilyName": {"type": "text"},
                        "GivenName": {"type": "text"}
                    },
                    "BirthDate": {"type": "date", "format": "YYYY-MM-DD"},
                    "Citizenship": {"type": "select", "options": ["Canada", "USA"]},
                    "Agree": {"type": "checkbox"},
                    "Language": {"type": "radio", "options": ["English", "French"]}
                }
            }
        }
    }
    ```
    """,
    response_description="필드 타입 정보 (JSON 형식)"
)
async def extract_field_types_endpoint(
    request: ExtractFieldTypesRequest
):
    """PDF 필드 타입 추출 엔드포인트"""
    logger.info(f"필드 타입 추출 요청: filename={request.filename}")
    
    # 업로드 디렉토리에서 파일 찾기
    base_dir = Path(__file__).parent.parent.parent
    upload_dir = base_dir / "uploads"
    file_path = upload_dir / request.filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"파일 '{request.filename}'을 찾을 수 없습니다. 먼저 /upload-and-extract로 파일을 업로드해주세요."
        )
    
    try:
        # 필드 타입 추출
        field_types = extract_field_types(file_path)
        logger.info(f"필드 타입 추출 완료: {len(field_types)}개 필드")
        
        return JSONResponse(content=field_types)
    except ValueError as e:
        logger.error(f"필드 타입 추출 중 오류: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"필드 타입 추출 실패: {str(e)}"
        )
    except Exception as e:
        logger.error(f"필드 타입 추출 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"필드 타입 추출 중 오류가 발생했습니다: {str(e)}"
        )


@router.post(
    "/extract-field-values",
    summary="PDF 필드 값 추출",
    description="""
    업로드된 PDF 파일에서 필드 키와 실제 값을 모두 추출합니다.
    
    - 필드 구조와 함께 실제 값까지 추출
    - datasets.xml과 form.xml에서 값을 읽어옴
    - 빈 필드는 빈 문자열로 표시
    
    **주의사항:**
    - 먼저 `/upload-and-extract` 엔드포인트로 PDF 파일을 업로드해야 합니다.
    
    **응답 예시:**
    ```json
    {
        "IMM_0800": {
            "Page1": {
                "PersonalDetails": {
                    "Name": {
                        "FamilyName": "홍",
                        "GivenName": "길동"
                    },
                    "BirthDate": "1990-01-01",
                    "Citizenship": "Canada"
                }
            }
        }
    }
    ```
    """,
    response_description="필드 키와 값이 포함된 JSON 형식"
)
async def extract_field_values_endpoint(
    request: ExtractFieldValuesRequest
):
    """PDF 필드 값 추출 엔드포인트"""
    logger.info(f"필드 값 추출 요청: filename={request.filename}")
    
    # 업로드 디렉토리에서 파일 찾기
    base_dir = Path(__file__).parent.parent.parent
    upload_dir = base_dir / "uploads"
    file_path = upload_dir / request.filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"파일 '{request.filename}'을 찾을 수 없습니다. 먼저 /upload-and-extract로 파일을 업로드해주세요."
        )
    
    try:
        # 필드 값 추출
        field_values = extract_field_values(file_path)
        logger.info(f"필드 값 추출 완료: filename={request.filename}")
        
        return JSONResponse(content=field_values)
    except ValueError as e:
        logger.error(f"필드 값 추출 중 오류: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"필드 값 추출 실패: {str(e)}"
        )
    except Exception as e:
        logger.error(f"필드 값 추출 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"필드 값 추출 중 오류가 발생했습니다: {str(e)}"
        )

