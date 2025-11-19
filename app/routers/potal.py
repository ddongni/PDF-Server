"""포털 자동화 라우터"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
import time
import logging
import asyncio

from app.services.potal_automation import BrowserAutomation, PROFILE_FORM_DATA

logger = logging.getLogger(__name__)

router = APIRouter(tags=["포털 자동화"])

# 동시 실행 제한을 위한 Semaphore (최대 2개 동시 실행)
max_concurrent = asyncio.Semaphore(2)


@router.post(
    "/potal/pr/profile",
    summary="PR 포털 프로필 업데이트",
    description="""
    PR 포털 프로필 페이지에 로그인하고 폼을 자동으로 채우는 API
    
    - Rate Limit: 분당 5회
    - 동시 실행: 최대 2개
    - 로그인 후 프로필 페이지로 이동하여 폼 자동 채우기
    """,
    response_description="PR 포털 프로필 업데이트 결과"
)
async def update_profile(request: Request):
    """
    PR 포털 프로필 페이지에 로그인하고 폼을 자동으로 채우는 API
    Rate Limit: 분당 5회
    동시 실행: 최대 2개
    """
    # Rate limit은 slowapi 미들웨어가 자동으로 처리
    # 동시 실행 제한 (Semaphore가 자동으로 처리)
    async with max_concurrent:
        automation = None
        try:
            logger.info("프로필 업데이트 작업 시작")
            
            # 브라우저 자동화 시작
            automation = BrowserAutomation()
            
            try:
                # 로그인 실행
                logger.info("로그인 중...")
                automation.login(
                    url="https://prson-srpel.apps.cic.gc.ca/en/login",
                    email="ehddms7691@gmail.com",
                    password="As12ehddms?"
                )
                
                # 프로필 페이지로 이동
                profile_url = "https://prson-srpel.apps.cic.gc.ca/en/application/profile/3950418"
                logger.info(f"프로필 페이지로 이동: {profile_url}")
                automation.driver.get(profile_url)
                
                # 페이지 로드 대기
                WebDriverWait(automation.driver, 20).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                
                # Angular 앱 로드 대기
                try:
                    WebDriverWait(automation.driver, 15).until(
                        lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "[class*='ng-']")) > 0 or
                                      len(driver.find_elements(By.CSS_SELECTOR, "input[name]")) > 0
                    )
                    logger.info("Angular 앱 로드 완료")
                except:
                    logger.warning("Angular 앱 로드 대기 시간 초과 (계속 진행)")
                
                time.sleep(3)
                
                # 페이지 분석 (디버깅용)
                logger.info("페이지 구조 분석 중...")
                automation.analyze_page_inputs()
                
                # 폼 필드 입력 (automation.py에서 정의된 데이터 사용)
                logger.info("폼 필드 입력 중...")
                automation.fill_form_fields(PROFILE_FORM_DATA)
                
                # Save 버튼 클릭
                logger.info("Save 버튼 클릭 중...")
                save_result = automation.click_save_button()
                
                logger.info("작업 완료. 10초 후 브라우저가 종료됩니다.")
                time.sleep(10)  # 10초 대기
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message": "프로필 업데이트가 완료되었습니다.",
                        "save_button_clicked": save_result
                    }
                )
                
            except Exception as e:
                logger.error(f"작업 중 오류 발생: {str(e)}")
                if automation:
                    automation.save_debug_info("api_error")
                raise HTTPException(
                    status_code=500,
                    detail=f"자동화 작업 중 오류가 발생했습니다: {str(e)}"
                )
            finally:
                # 브라우저 종료 (리소스 해제)
                if automation:
                    try:
                        automation.close()
                        logger.info("브라우저 종료 완료")
                    except Exception as e:
                        logger.error(f"브라우저 종료 중 오류: {str(e)}")
                        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"API 오류: {str(e)}")
            if automation:
                try:
                    automation.close()
                except:
                    pass
            raise HTTPException(
                status_code=500,
                detail=f"서버 오류: {str(e)}"
            )

