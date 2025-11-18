"""애플리케이션 설정"""
from typing import List


class Settings:
    """애플리케이션 설정"""
    
    # CORS 설정
    cors_allow_origins: List[str] = ["*"]
    cors_allow_credentials: bool = False
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    
    # 로깅 설정
    log_level: str = "INFO"


settings = Settings()

