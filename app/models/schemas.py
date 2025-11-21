"""API 요청/응답 스키마"""
from pydantic import BaseModel
from typing import Dict, Any, List, Optional


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


class ExtractFieldTypesRequest(BaseModel):
    """필드 타입 추출 요청 모델"""
    filename: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "filename": "IMM0800e.pdf"
            }
        }


class ExtractFieldValuesRequest(BaseModel):
    """필드 값 추출 요청 모델"""
    filename: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "filename": "IMM0800e.pdf"
            }
        }


class EEPortalLoginRequest(BaseModel):
    """EE 포털 로그인 요청 모델 (2FA 지원)
    
    폼 데이터는 하드코딩되어 있어 별도로 입력할 필요가 없습니다.
    """
    email: str  # 실제로는 username
    password: str
    two_factor_code: Optional[str] = None  # 2FA 코드 (선택사항, 필요시 입력)
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "your_username",
                "password": "your_password",
                "two_factor_code": "123456"
            }
        }

