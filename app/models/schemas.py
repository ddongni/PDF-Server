"""API 요청/응답 스키마"""
from pydantic import BaseModel
from typing import Dict, Any


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

