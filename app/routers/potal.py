"""포털 자동화 라우터"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
import time
import logging
import asyncio
import json
from queue import Queue
from threading import Thread

from app.services.potal_automation import BrowserAutomation, PROFILE_FORM_DATA, EE_PORTAL_FORM_ITEMS
from app.models.schemas import EEPortalLoginRequest

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


def send_progress(progress: int, message: str, status: str = "progress"):
    """SSE 형식으로 진행 상황 전송"""
    data = {
        "progress": progress,
        "message": message,
        "status": status
    }
    return f"data: {json.dumps(data)}\n\n"


async def run_automation_with_progress():
    """자동화 작업을 실행하면서 진행 상황을 스트리밍"""
    automation = None
    try:
        # 브라우저 초기화
        yield send_progress(10, "브라우저 초기화 중...", "progress")
        automation = BrowserAutomation()
        await asyncio.sleep(0.1)
        
        # 로그인 페이지 로드
        yield send_progress(20, "로그인 페이지 로드 중...", "progress")
        automation.login(
            url="https://prson-srpel.apps.cic.gc.ca/en/login",
            email="ehddms7691@gmail.com",
            password="As12ehddms?"
        )
        await asyncio.sleep(0.1)
        
        # 로그인 완료
        yield send_progress(30, "로그인 완료", "progress")
        await asyncio.sleep(0.1)
        
        # 프로필 페이지로 이동
        profile_url = "https://prson-srpel.apps.cic.gc.ca/en/application/profile/3950418"
        yield send_progress(40, f"프로필 페이지로 이동 중... ({profile_url})", "progress")
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
        except:
            pass
        
        await asyncio.sleep(0.1)
        
        # 페이지 분석
        yield send_progress(50, "페이지 구조 분석 중...", "progress")
        automation.analyze_page_inputs()
        await asyncio.sleep(0.1)
        
        # 폼 필드 입력
        yield send_progress(60, "폼 필드 입력 시작...", "progress")
        total_fields = len(PROFILE_FORM_DATA)
        
        # 진행 상황을 전달하기 위한 queue
        progress_queue = Queue()
        
        # 진행 상황 콜백 함수
        def progress_callback(current, total, field_name):
            progress = 60 + int((current / total) * 20)
            progress_queue.put({
                "progress": progress,
                "message": f"필드 입력 중: {field_name} ({current}/{total})",
                "status": "progress"
            })
        
        # fill_form_fields를 별도 스레드에서 실행
        def fill_fields_thread():
            try:
                automation.fill_form_fields(PROFILE_FORM_DATA, progress_callback=progress_callback)
                progress_queue.put({
                    "progress": 80,
                    "message": "폼 필드 입력 완료",
                    "status": "progress"
                })
            except Exception as e:
                progress_queue.put({
                    "progress": -1,
                    "message": f"폼 필드 입력 중 오류: {str(e)}",
                    "status": "error"
                })
        
        # 스레드 시작
        fill_thread = Thread(target=fill_fields_thread)
        fill_thread.start()
        
        # 진행 상황을 실시간으로 전송
        while fill_thread.is_alive():
            try:
                # queue에서 진행 상황 가져오기 (타임아웃 0.1초)
                progress_data = progress_queue.get(timeout=0.1)
                yield send_progress(
                    progress_data["progress"],
                    progress_data["message"],
                    progress_data["status"]
                )
                
                # 오류 발생 시 중단
                if progress_data["status"] == "error":
                    raise Exception(progress_data["message"])
            except:
                # queue가 비어있으면 잠시 대기
                await asyncio.sleep(0.1)
                continue
        
        # 스레드가 종료될 때까지 대기
        fill_thread.join()
        
        # 남은 진행 상황 전송
        while not progress_queue.empty():
            try:
                progress_data = progress_queue.get_nowait()
                yield send_progress(
                    progress_data["progress"],
                    progress_data["message"],
                    progress_data["status"]
                )
            except:
                break
        
        yield send_progress(80, "폼 필드 입력 완료", "progress")
        await asyncio.sleep(0.1)
        
        # Save 버튼 클릭
        yield send_progress(90, "Save 버튼 클릭 중...", "progress")
        save_result = automation.click_save_button()
        await asyncio.sleep(0.1)
        
        # 완료
        yield send_progress(100, "작업 완료", "success")
        
        # 최종 결과 전송
        result_data = {
            "progress": 100,
            "message": "프로필 업데이트가 완료되었습니다.",
            "status": "success",
            "save_button_clicked": save_result
        }
        yield f"data: {json.dumps(result_data)}\n\n"
        
        # 브라우저 종료 전 대기
        await asyncio.sleep(2)
        
    except Exception as e:
        error_message = f"오류 발생: {str(e)}"
        logger.error(error_message)
        yield send_progress(-1, error_message, "error")
        
        error_data = {
            "progress": -1,
            "message": error_message,
            "status": "error",
            "error": str(e)
        }
        yield f"data: {json.dumps(error_data)}\n\n"
    finally:
        # 브라우저 종료
        if automation:
            try:
                automation.close()
                logger.info("브라우저 종료 완료")
            except Exception as e:
                logger.error(f"브라우저 종료 중 오류: {str(e)}")


@router.post(
    "/potal/pr/profile/stream",
    summary="PR 포털 프로필 업데이트 (진행 상황 스트리밍)",
    description="""
    PR 포털 프로필 페이지에 로그인하고 폼을 자동으로 채우는 API (Server-Sent Events)
    
    - 진행 상황을 실시간으로 스트리밍
    - SSE 형식으로 진행율과 메시지 전송
    - 동시 실행: 최대 2개
    """,
    response_description="Server-Sent Events 스트림"
)
async def update_profile_stream(request: Request):
    """
    PR 포털 프로필 업데이트 API (SSE 스트리밍)
    진행 상황을 실시간으로 전송합니다.
    """
    async with max_concurrent:
        return StreamingResponse(
            run_automation_with_progress(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )


@router.post(
    "/potal/ee/profile",
    summary="EE 포털 프로필 업데이트 (2FA 지원)",
    description="""
    EE 포털 프로필 페이지에 로그인하고 폼을 자동으로 채우는 API
    
    - 2FA(2단계 인증) 지원: 이메일로 받은 코드를 입력
    - Rate Limit: 분당 5회
    - 동시 실행: 최대 2개
    - 로그인 후 프로필 페이지로 이동하여 폼 자동 채우기
    
    **사용 방법:**
    1. 첫 번째 요청: `two_factor_code` 없이 요청 (이메일로 코드 발송)
    2. 이메일에서 2FA 코드 확인
    3. 두 번째 요청: `two_factor_code`에 코드를 포함하여 요청
    """,
    response_description="EE 포털 프로필 업데이트 결과"
)
async def update_ee_profile(login_request: EEPortalLoginRequest):
    """
    EE 포털 프로필 페이지에 로그인하고 폼을 자동으로 채우는 API (2FA 지원)
    """
    async with max_concurrent:
        automation = None
        try:
            logger.info("EE 포털 프로필 업데이트 작업 시작")
            
            # 브라우저 자동화 시작
            automation = BrowserAutomation()
            
            try:
                # EE 포털 로그인 URL
                login_url = "https://onlineservices-servicesenligne-cic.fjgc-gccf.gc.ca/mycic/gccf?lang=eng&idp=gckey&svc=/mycic/start"
                
                # EE 포털 로그인 필드 선택자
                email_selectors = [
                    (By.NAME, "token1"),
                ]
                password_selectors = [
                    (By.NAME, "token2"),
                ]
                login_button_selectors = [
                    (By.CSS_SELECTOR, "button[type='submit']"),
                ]
                
                # 2FA 코드가 없으면 로그인만 시도하고 코드 필요 메시지 반환
                if not login_request.two_factor_code:
                    logger.info("로그인 중... (2FA 코드 없음)")
                    # email 필드에 username이 들어올 수 있음
                    automation.login(
                        url=login_url,
                        email=login_request.email,  # 실제로는 username
                        password=login_request.password,
                        email_selectors=email_selectors,
                        password_selectors=password_selectors,
                        login_button_selectors=login_button_selectors
                    )
                    
                    # 2FA 코드 입력 필드 확인
                    needs_2fa = not automation.handle_2fa(code=None, timeout=5)
                    
                    if needs_2fa:
                        return JSONResponse(
                            status_code=200,
                            content={
                                "success": False,
                                "message": "2FA 코드가 필요합니다. 이메일에서 코드를 확인한 후 two_factor_code 필드에 입력하여 다시 요청하세요.",
                                "requires_2fa": True,
                                "status": "waiting_for_2fa"
                            }
                        )
                else:
                    # 2FA 코드가 있으면 로그인 + 2FA 처리
                    logger.info("로그인 및 2FA 처리 중...")
                    # email 필드에 username이 들어올 수 있음
                    login_success = automation.login_with_2fa(
                        url=login_url,
                        email=login_request.email,  # 실제로는 username
                        password=login_request.password,
                        two_factor_code=login_request.two_factor_code,
                        email_selectors=email_selectors,
                        password_selectors=password_selectors,
                        login_button_selectors=login_button_selectors
                    )
                    
                    if not login_success:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "success": False,
                                "message": "2FA 코드가 필요하거나 잘못되었습니다.",
                                "requires_2fa": True
                            }
                        )
                
                # 지원 시작 페이지로 이동
                app_url = "https://onlineservices-servicesenligne.cic.gc.ca/eapp/eapp"
                logger.info(f"지원 시작 페이지로 이동: {app_url}")
                automation.driver.get(app_url)
                
                # 페이지 로드 대기
                WebDriverWait(automation.driver, 20).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                time.sleep(3)
                
                # 하드코딩된 폼 데이터로 순차적으로 처리
                logger.info("순차적 폼 필드 입력 시작...")
                automation.fill_form_sequential(EE_PORTAL_FORM_ITEMS)
                logger.info("순차적 폼 필드 입력 완료")
                
                logger.info("작업 완료. 10초 후 브라우저가 종료됩니다.")
                time.sleep(10)  # 10초 대기
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message": "EE 포털 자동화 작업이 완료되었습니다.",
                        "form_items_processed": len(EE_PORTAL_FORM_ITEMS)
                    }
                )
                
            except Exception as e:
                logger.error(f"작업 중 오류 발생: {str(e)}")
                if automation:
                    automation.save_debug_info("ee_api_error")
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

