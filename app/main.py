"""FastAPI 애플리케이션 진입점"""
import logging

from app.core.app import create_app
from app.core.config import settings

# 로깅 설정
logging.basicConfig(level=settings.log_level)

# FastAPI 앱 생성
app = create_app()
