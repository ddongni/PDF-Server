"""포털 자동화 라우터"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
import logging
import asyncio
import base64
import json
from typing import Dict, Optional

from app.services.potal_automation import BrowserAutomation, EE_PORTAL_FORM_ITEMS, PROFILE_FORM_DATA

logger = logging.getLogger(__name__)

router = APIRouter(tags=["포털 자동화"])

# 동시 실행 제한을 위한 Semaphore (최대 2개 동시 실행)
max_concurrent = asyncio.Semaphore(2)

# 중요 단계에서만 스크린샷 촬영 (사용하지 않음 - 특정 시점에서만 수동으로 촬영)
IMPORTANT_STATUSES = {
    # 비밀번호 입력 완료와 마지막 필드 입력 완료 시에만 수동으로 스크린샷 촬영
}

# 스크린샷 최적화 설정
SCREENSHOT_CONFIG = {
    "max_width": 1280,  # 최대 너비
    "max_height": 720,  # 최대 높이
    "quality": 75,  # JPEG 품질 (0-100, PNG는 무시됨)
}


async def take_screenshot_optimized(automation: BrowserAutomation) -> Optional[str]:
    """
    최적화된 스크린샷 촬영 (크기/품질 조정)
    take_screenshot_optimized
    Args:
        automation: BrowserAutomation 인스턴스
    
    Returns:
        base64 인코딩된 스크린샷 문자열 또는 None
    """
    try:
        # 뷰포트 크기 가져오기
        viewport = automation.page.viewport_size
        if not viewport:
            viewport = {"width": 1920, "height": 1080}
        
        # 크기 계산 (비율 유지)
        width = min(viewport["width"], SCREENSHOT_CONFIG["max_width"])
        height = min(viewport["height"], SCREENSHOT_CONFIG["max_height"])
        
        # 비율 조정
        if viewport["width"] > width:
            ratio = width / viewport["width"]
            height = int(viewport["height"] * ratio)
        
        # 스크린샷 촬영 (크기 제한)
        screenshot_bytes = await automation.page.screenshot(
            full_page=False,
            clip={"x": 0, "y": 0, "width": width, "height": height}
        )
        
        if screenshot_bytes:
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            logger.debug(f"최적화된 스크린샷 촬영 성공 (크기: {width}x{height}, 길이: {len(screenshot_base64)} 문자)")
            return screenshot_base64
    except Exception as screenshot_error:
        logger.debug(f"스크린샷 촬영 실패: {str(screenshot_error)}")
    return None


async def send_with_screenshot(websocket: WebSocket, automation: BrowserAutomation, message_data: Dict, progress: Optional[int] = None, force_screenshot: bool = False):
    """
    WebSocket 메시지를 스크린샷과 함께 전송하는 헬퍼 함수 (최적화됨)
    
    Args:
        websocket: WebSocket 연결
        automation: BrowserAutomation 인스턴스
        message_data: 전송할 메시지 데이터 (dict)
        progress: 진행률 (0-100, 선택사항)
        force_screenshot: 강제로 스크린샷 촬영 여부
    """
    try:
        # progress 필드 추가
        if progress is not None:
            message_data["progress"] = progress
        
        # 중요 단계에서만 스크린샷 촬영 (또는 강제 요청 시)
        status = message_data.get("status", "")
        should_take_screenshot = force_screenshot or status in IMPORTANT_STATUSES
        
        # 메시지는 먼저 전송 (스크린샷은 비동기로 처리)
        message_to_send = message_data.copy()
        
        if should_take_screenshot:
            # 비동기로 스크린샷 촬영 (백그라운드 태스크)
            async def add_screenshot():
                try:
                    # 화면 안정화를 위한 짧은 대기
                    await asyncio.sleep(0.1)
                    screenshot_base64 = await take_screenshot_optimized(automation)
                    if screenshot_base64:
                        # 스크린샷을 별도 메시지로 전송 (또는 원본 메시지 업데이트)
                        screenshot_message = {
                            "status": "screenshot",
                            "original_status": status,
                            "message": message_data.get("message", ""),
                            "screenshot": screenshot_base64
                        }
                        await websocket.send_json(screenshot_message)
                        logger.info(f"스크린샷 전송 완료 (상태: {status})")
                except Exception as e:
                    logger.error(f"스크린샷 처리 중 오류: {str(e)}")
            
            # 백그라운드 태스크로 실행 (메시지 전송을 블로킹하지 않음)
            asyncio.create_task(add_screenshot())
            logger.info(f"스크린샷 촬영 태스크 생성 (상태: {status})")
        else:
            logger.debug(f"스크린샷 생략 (상태: {status})")
        
        # 메시지 즉시 전송 (스크린샷 대기하지 않음)
        await websocket.send_json(message_to_send)
    except Exception as e:
        logger.debug(f"메시지 전송 실패: {str(e)}")
        # 스크린샷 없이라도 메시지는 전송 시도
        try:
            await websocket.send_json(message_data)
        except:
            pass


@router.websocket("/potal/ee/profile/ws")
async def websocket_automation_handler(websocket: WebSocket):
    """
    WebSocket을 통한 EE 포털 자동화 전체 프로세스 처리
    
    사용 방법:
    1. WebSocket으로 연결: ws://server/potal/ee/profile/ws
    2. 첫 메시지로 로그인 정보 전송: {"username": "username", "password": "password"}
    3. 2FA 코드 필요 시: {"code": "123456"} 전송
    4. 질문 필요 시: {"answer": "답변"} 전송
    5. 서버가 모든 단계를 자동으로 처리하고 진행 상황을 실시간으로 전송
    """
    await websocket.accept()
    logger.info("WebSocket 연결 수락")
    
    automation = None
    async with max_concurrent:
        try:
            # 브라우저 자동화 시작
            logger.info("브라우저 자동화 시작...")
            automation = await BrowserAutomation.create()
            
            # EE 포털 로그인 URL
            login_url = "https://onlineservices-servicesenligne-cic.fjgc-gccf.gc.ca/mycic/gccf?lang=eng&idp=gckey&svc=/mycic/start"
            
            # 로그인 페이지로 이동
            logger.info(f"로그인 페이지로 이동 중: {login_url}")
            await automation.page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(0.3)
            try:
                await automation.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except:
                logger.warning("domcontentloaded 대기 시간 초과 (계속 진행)")
            
            # 로그인 페이지 로드 완료 후 로그인 정보 요청 (스크린샷 포함 - 로그인 화면)
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "로그인 정보를 입력하세요.",
                "status": "waiting_for_login",
                "progress": 10,
                "instruction": "JSON 형식으로 전송하세요: {\"username\": \"username\", \"password\": \"password\"}"
            }, force_screenshot=True)
            
            # 로그인 정보 수신 대기
            login_data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
            
            if "username" not in login_data or "password" not in login_data:
                await send_with_screenshot(websocket, automation, {
                    "success": False,
                    "message": "로그인 정보가 올바르지 않습니다. 'username'과 'password' 필드가 필요합니다.",
                    "status": "error",
                    "progress": 10,
                    "error": "invalid_login_data"
                })
                await websocket.close()
                return
            
            username = login_data["username"]
            password = login_data["password"]
            
            # EE 포털 로그인 필드 선택자
            email_selectors = [("name", "token1")]
            password_selectors = [("name", "token2")]
            login_button_selectors = [("css", "button[type='submit']")]
            
            # 로그인 진행 상황 콜백 함수 (비밀번호 입력 완료 시에만 스크린샷 촬영)
            async def login_progress_callback(message: str, data: Optional[Dict] = None):
                """로그인 진행 상황 전송 (비밀번호 입력 완료 시 스크린샷)"""
                try:
                    # 비밀번호 입력 완료 시에만 스크린샷 촬영
                    should_take_screenshot = "비밀번호 입력 완료" in message
                    
                    # 메시지 먼저 전송
                    await websocket.send_json({
                        "success": True,
                        "message": message,
                        "status": "logging_in",
                        "progress": 15
                    })
                    
                    if should_take_screenshot:
                        # 비밀번호 입력 완료 후 스크린샷 촬영 (비동기 처리)
                        async def add_login_screenshot():
                            try:
                                # 화면 안정화를 위한 짧은 대기
                                await asyncio.sleep(0.1)
                                screenshot_base64 = await take_screenshot_optimized(automation)
                                if screenshot_base64:
                                    screenshot_message = {
                                        "status": "screenshot",
                                        "original_status": "logging_in",
                                        "message": message,
                                        "progress": 15,
                                        "screenshot": screenshot_base64
                                    }
                                    await websocket.send_json(screenshot_message)
                                    logger.info("비밀번호 입력 완료 스크린샷 전송 완료")
                            except Exception as e:
                                logger.error(f"로그인 스크린샷 처리 중 오류: {str(e)}")
                        
                        # 백그라운드 태스크로 실행 (메시지 전송을 블로킹하지 않음)
                        asyncio.create_task(add_login_screenshot())
                except Exception as e:
                    logger.error(f"로그인 진행 상황 콜백 오류: {str(e)}")
                    pass
            
            # 로그인 시도
            logger.info("로그인 중...")
            await automation.login(
                url=login_url,
                email=username,
                password=password,
                email_selectors=email_selectors,
                password_selectors=password_selectors,
                login_button_selectors=login_button_selectors,
                progress_callback=login_progress_callback
            )
            
            # 로그인 후 페이지 로드 대기
            await asyncio.sleep(0.3)
            try:
                await automation.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except:
                logger.warning("domcontentloaded 대기 시간 초과 (계속 진행)")
            
            # 로그인 후 스크린샷 전송
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "로그인 완료",
                "status": "login_completed",
                "progress": 20
            })
            
            # Continue 버튼 클릭
            logger.info("Continue 버튼 클릭 중...")
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "Continue 버튼 클릭 중...",
                "status": "clicking_continue",
                "progress": 25
            })
            
            await automation.click_continue_button()
            
            # Continue 버튼 클릭 후 페이지 로드 대기
            await asyncio.sleep(0.3)
            try:
                await automation.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except:
                pass
            
            # Continue 버튼 클릭 완료 (스크린샷 없음 - 성능 최적화)
            await websocket.send_json({
                "success": True,
                "message": "Continue 버튼 클릭 완료",
                "status": "continue_clicked",
                "progress": 30
            })
            
            # 2FA 코드 입력 필드 확인
            logger.info("2FA 코드 필요 여부 확인 중...")
            needs_2fa = not await automation.handle_2fa(code=None, timeout=20000)
            
            if needs_2fa:
                # 2FA 코드 필요 (스크린샷 포함 - 2FA 인증코드 입력 화면)
                await send_with_screenshot(websocket, automation, {
                    "success": True,
                    "message": "2FA 인증 코드가 필요합니다.",
                    "status": "waiting_for_2fa",
                    "progress": 35,
                    "instruction": "이메일에서 받은 2FA 코드를 JSON 형식으로 전송하세요: {\"code\": \"123456\"}"
                }, force_screenshot=True)
                
                # 2FA 코드 수신 대기 (최대 5분)
                code_received = False
                timeout = 300
                
                while not code_received:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=timeout)
                    
                    if "code" in data:
                        two_factor_code = data["code"]
                        logger.info(f"2FA 코드 수신: {two_factor_code[:2]}**")
                        
                        await send_with_screenshot(websocket, automation, {
                            "success": True,
                            "message": "2FA 코드를 처리 중입니다...",
                            "status": "processing_2fa",
                            "progress": 40
                        })
                        
                        try:
                            # 2FA 코드 입력 및 처리 (진행 상황 콜백 포함)
                            async def _2fa_progress_callback(message: str, data: Optional[Dict] = None):
                                """2FA 진행 상황 전송 (코드 입력 완료 시 스크린샷)"""
                                try:
                                    await websocket.send_json({
                                        "success": True,
                                        "message": message,
                                        "status": "processing_2fa",
                                        "progress": 40
                                    })
                                    
                                    # 2FA 코드 입력 완료 시 스크린샷 촬영 (입력된 값이 보이는 화면)
                                    if "2FA 코드 입력 완료" in message:
                                        async def add_2fa_input_screenshot():
                                            try:
                                                # 화면 안정화를 위한 짧은 대기
                                                await asyncio.sleep(0.2)
                                                screenshot_base64 = await take_screenshot_optimized(automation)
                                                if screenshot_base64:
                                                    screenshot_message = {
                                                        "status": "screenshot",
                                                        "original_status": "processing_2fa",
                                                        "message": "2FA 인증코드 입력 완료",
                                                        "progress": 40,
                                                        "screenshot": screenshot_base64
                                                    }
                                                    await websocket.send_json(screenshot_message)
                                                    logger.info("2FA 인증코드 입력 완료 스크린샷 전송 완료")
                                            except Exception as e:
                                                logger.error(f"2FA 입력 완료 스크린샷 처리 중 오류: {str(e)}")
                                        
                                        asyncio.create_task(add_2fa_input_screenshot())
                                except:
                                    pass
                            
                            result = await automation.handle_2fa(
                                code=two_factor_code, 
                                timeout=20000,
                                progress_callback=_2fa_progress_callback
                            )
                        
                            if result:
                                # 2FA 처리 성공 메시지 전송 (스크린샷 없음 - 이미 입력 완료 시 촬영함)
                                await websocket.send_json({
                                    "success": True,
                                    "message": "2FA 인증이 완료되었습니다.",
                                    "status": "2fa_completed",
                                    "progress": 45
                                })
                                code_received = True
                            else:
                                # 2FA 코드가 잘못됨
                                await send_with_screenshot(websocket, automation, {
                                    "success": False,
                                    "message": "2FA 코드가 잘못되었습니다. 다시 시도하세요.",
                                    "status": "invalid_code",
                                    "progress": 35
                                })
                        except Exception as e:
                            logger.error(f"2FA 처리 중 오류: {str(e)}")
                            await websocket.send_json({
                                "success": False,
                                "message": f"2FA 처리 중 오류가 발생했습니다: {str(e)}",
                                "status": "error",
                                "progress": 35,
                                "error": str(e)
                            })
                            raise
                    else:
                        # 잘못된 형식의 메시지
                        await websocket.send_json({
                            "success": False,
                            "message": "잘못된 메시지 형식입니다. 'code' 필드를 포함하세요.",
                            "status": "invalid_message",
                            "progress": 35
                        })
            else:
                # 2FA가 필요 없는 경우
                await send_with_screenshot(websocket, automation, {
                    "success": True,
                    "message": "2FA 인증이 필요하지 않습니다. 계속 진행합니다...",
                    "status": "no_2fa_required",
                    "progress": 45
                })
            
            # 4. Authentication success 페이지의 submit button 클릭
            logger.info("Authentication success 페이지 확인 중...")
            # 페이지 로드 완료 대기
            await asyncio.sleep(0.3)
            try:
                await automation.page.wait_for_load_state("domcontentloaded", timeout=10000)
                logger.info("Authentication success 페이지 로드 완료")
            except:
                logger.warning("Authentication success 페이지 로드 대기 시간 초과 (계속 진행)")
            
            try:
                auth_success_btn = automation.page.locator("button[type='submit']")
                count = await auth_success_btn.count()
                if count > 0:
                    logger.info("Authentication success 페이지의 submit 버튼 클릭 중...")
                    await auth_success_btn.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await auth_success_btn.first.click()
                    logger.info("Authentication success submit 버튼 클릭 완료")
                    
                    # 다음 페이지 로드 완료 대기
                    await asyncio.sleep(0.5)
                    try:
                        await automation.page.wait_for_load_state("domcontentloaded", timeout=10000)
                        logger.info("Authentication success 클릭 후 페이지 로드 완료")
                    except:
                        logger.warning("Authentication success 클릭 후 페이지 로드 대기 시간 초과 (계속 진행)")
            except Exception as e:
                logger.debug(f"Authentication success 버튼 클릭 실패: {str(e)}")
            
            # 5. Terms and Conditions 페이지의 _continue 클릭
            logger.info("Terms and Conditions 페이지 확인 중...")
            # 페이지 로드 완료 대기
            await asyncio.sleep(0.3)
            try:
                await automation.page.wait_for_load_state("domcontentloaded", timeout=10000)
                logger.info("Terms and Conditions 페이지 로드 완료")
            except:
                logger.warning("Terms and Conditions 페이지 로드 대기 시간 초과 (계속 진행)")
            
            try:
                terms_continue_btn = automation.page.locator("input[name='_continue'][type='submit']")
                count = await terms_continue_btn.count()
                if count > 0:
                    logger.info("Terms and Conditions 페이지의 _continue 버튼 클릭 중...")
                    await terms_continue_btn.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await terms_continue_btn.first.click()
                    logger.info("Terms and Conditions _continue 버튼 클릭 완료")
                    
                    # 다음 페이지 로드 완료 대기
                    await asyncio.sleep(0.5)
                    try:
                        await automation.page.wait_for_load_state("domcontentloaded", timeout=10000)
                        logger.info("Terms and Conditions 클릭 후 페이지 로드 완료")
                    except:
                        logger.warning("Terms and Conditions 클릭 후 페이지 로드 대기 시간 초과 (계속 진행)")
            except Exception as e:
                logger.debug(f"Terms and Conditions 버튼 클릭 실패: {str(e)}")
            
            # 6. Identity validation 페이지 - 질문-답변 처리
            logger.info("Identity validation 페이지 확인 중...")
            # 페이지 로드 완료 대기
            await asyncio.sleep(0.3)
            try:
                await automation.page.wait_for_load_state("domcontentloaded", timeout=10000)
                logger.info("Identity validation 페이지 로드 완료")
            except:
                logger.warning("Identity validation 페이지 로드 대기 시간 초과 (계속 진행)")
            
            # 질문 확인 (답변 없이)
            qa_result = await automation.handle_question_answer(answer=None)
            
            if qa_result["has_question"]:
                logger.info(f"질문 발견: {qa_result['question']}")
                
                # 질문을 클라이언트에게 전송 (스크린샷 포함 - 질의응답 화면)
                await send_with_screenshot(websocket, automation, {
                    "success": True,
                    "message": f"질문: {qa_result['question']}",
                    "status": "question",
                    "progress": 50,
                    "question": qa_result["question"],
                    "question_number": 1,
                    "instruction": "답변을 JSON 형식으로 전송하세요: {\"answer\": \"답변\"}"
                }, force_screenshot=True)
                
                # 사용자로부터 답변 받기
                try:
                    answer_data = await websocket.receive_json()
                    user_answer = answer_data.get("answer", "").strip()
                    
                    if not user_answer:
                        await websocket.send_json({
                            "success": False,
                            "message": "답변이 제공되지 않았습니다.",
                            "status": "answer_required",
                            "progress": 50
                        })
                        raise Exception("답변이 제공되지 않았습니다.")
                    
                    logger.info(f"사용자 답변 받음: {user_answer}")
                    
                    # 답변 처리 진행 상황 콜백 함수
                    async def qa_progress_callback(message: str, data: Optional[Dict] = None):
                        """질의응답 진행 상황 전송 (답변 입력 완료 시 스크린샷)"""
                        try:
                            await websocket.send_json({
                                "success": True,
                                "message": message,
                                "status": "processing_answer",
                                "progress": 52
                            })
                            
                            # 답변 입력 완료 시 스크린샷 촬영 (입력된 값이 보이는 화면)
                            if "답변 입력 완료" in message:
                                async def add_qa_input_screenshot():
                                    try:
                                        # 화면 안정화를 위한 짧은 대기
                                        await asyncio.sleep(0.2)
                                        screenshot_base64 = await take_screenshot_optimized(automation)
                                        if screenshot_base64:
                                            screenshot_message = {
                                                "status": "screenshot",
                                                "original_status": "processing_answer",
                                                "message": "질의응답 입력 완료",
                                                "progress": 52,
                                                "screenshot": screenshot_base64
                                            }
                                            await websocket.send_json(screenshot_message)
                                            logger.info("질의응답 입력 완료 스크린샷 전송 완료")
                                    except Exception as e:
                                        logger.error(f"질의응답 입력 완료 스크린샷 처리 중 오류: {str(e)}")
                                
                                asyncio.create_task(add_qa_input_screenshot())
                        except:
                            pass
                    
                    # 답변 처리 (answer 필드에 입력하고 _continue 클릭)
                    qa_result2 = await automation.handle_question_answer(
                        answer=user_answer,
                        progress_callback=qa_progress_callback
                    )
                    
                    if qa_result2["completed"]:
                        # 질의응답 제출 완료 메시지 전송 (스크린샷 없음 - 이미 입력 완료 시 촬영함)
                        await websocket.send_json({
                            "success": True,
                            "message": "답변이 제출되었습니다.",
                            "status": "answer_submitted",
                            "progress": 55
                        })
                        logger.info("Identity validation 질문-답변 처리 완료")
                    else:
                        await send_with_screenshot(websocket, automation, {
                            "success": False,
                            "message": "답변 제출에 실패했습니다.",
                            "status": "answer_failed",
                            "progress": 50
                        })
                        raise Exception("답변 제출 실패")
                    
                except Exception as e:
                    logger.error(f"답변 처리 중 오류: {str(e)}")
                    await websocket.send_json({
                        "success": False,
                        "message": f"답변 처리 중 오류 발생: {str(e)}",
                        "status": "error",
                        "progress": 50
                    })
                    raise
            else:
                logger.info("질문이 없습니다. 바로 EE 페이지로 이동합니다.")
            
            # 모든 질문-답변 처리 완료 후 EE 지원 페이지로 이동
            logger.info("모든 질문-답변 처리 완료. EE 지원 페이지로 이동합니다...")
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "모든 질문-답변 처리 완료. EE 지원 페이지로 이동합니다...",
                "status": "moving_to_ee_app",
                "progress": 55
            })
            
            # 기존 애플리케이션 삭제 확인 및 처리
            logger.info("기존 애플리케이션 삭제 확인 중...")
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "기존 애플리케이션 삭제 확인 중...",
                "status": "checking_existing_app",
                "progress": 60
            })
            
            # continue application 확인 후 EE 지원 페이지로 이동
            # (navigate_to_ee_application 내부에서 applicationChecklist 페이지 확인 및 삭제 처리)
            await automation.navigate_to_ee_application()
            
            # 페이지 로드 대기
            try:
                await automation.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except:
                pass
            await asyncio.sleep(0.3)
            
            # 폼 필드 입력 시작 알림 (스크린샷 포함 - 폼 채우기 첫 화면)
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "EE 지원 페이지로 이동 완료. JSON 데이터를 순서대로 입력합니다...",
                "status": "filling_forms_start",
                "progress": 65,
                "total_items": len(EE_PORTAL_FORM_ITEMS)
            }, force_screenshot=True)
            
            # 진행률 콜백 함수 정의 (스크린샷 최적화: 10개마다 1번만 촬영)
            screenshot_counter = {"count": 0}
            async def progress_callback(current: int, total: int, item: Dict):
                """폼 필드 입력 진행률을 WebSocket으로 전송 (스크린샷 최적화)"""
                try:
                    # 전체 진행률 계산 (65% ~ 90% 사이)
                    form_progress = 65 + int((current / total) * 25) if total > 0 else 65
                    
                    progress_data = {
                        "success": True,
                        "message": f"폼 필드 입력 중... ({current}/{total})",
                        "status": "filling_forms",
                        "progress": form_progress,
                        "current": current,
                        "total": total,
                        "percentage": round((current / total) * 100, 1) if total > 0 else 0,
                        "current_item": {
                            "tag": item.get("tag", ""),
                            "name": item.get("name", ""),
                            "value": item.get("value", "")
                        }
                    }
                    
                    # 마지막 필드 입력 완료 시 스크린샷 촬영하지 않음 (작업 완료 후 최종 화면에서 촬영)
                    
                    screenshot_counter["count"] += 1
                    await websocket.send_json(progress_data)
                except Exception as e:
                    logger.debug(f"진행률 전송 실패: {str(e)}")
            
            # 제공된 JSON 데이터를 순서대로 처리
            logger.info(f"JSON 데이터 순차 처리 시작 (총 {len(EE_PORTAL_FORM_ITEMS)}개 항목)...")
            await automation.fill_form_sequential(EE_PORTAL_FORM_ITEMS, progress_callback=progress_callback)
            logger.info("JSON 데이터 순차 처리 완료")
            
            # 저장 버튼 클릭 알림
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "모든 폼 필드 입력 완료. 저장 중...",
                "status": "saving",
                "progress": 90
            })
            
            # 저장 버튼 클릭 (마지막 단계)
            save_result = await automation.click_save_button()
            
            if save_result:
                # 저장 완료 후 최종 화면 대기
                await asyncio.sleep(0.5)
                try:
                    await automation.page.wait_for_load_state("domcontentloaded", timeout=10000)
                except:
                    pass
                
                # 최종 화면 스크린샷 먼저 촬영 및 전송 (커넥션 끊김 방지)
                screenshot_base64 = None
                try:
                    # 화면 안정화를 위한 대기
                    await asyncio.sleep(0.3)
                    try:
                        await automation.page.wait_for_load_state("load", timeout=5000)
                    except:
                        pass
                    
                    screenshot_base64 = await take_screenshot_optimized(automation)
                    if screenshot_base64:
                        screenshot_message = {
                            "status": "screenshot",
                            "original_status": "completed",
                            "message": "작업 완료 - 마지막 화면",
                            "progress": 100,
                            "screenshot": screenshot_base64
                        }
                        await websocket.send_json(screenshot_message)
                        logger.info("작업 완료 마지막 화면 스크린샷 전송 완료")
                    else:
                        logger.warning("스크린샷 촬영 실패 (None 반환)")
                except Exception as e:
                    logger.error(f"작업 완료 스크린샷 처리 중 오류: {str(e)}")
                
                # 저장 완료 메시지 전송 (스크린샷 전송 후)
                try:
                    await websocket.send_json({
                        "success": True,
                        "message": "EE 포털 자동화 작업이 완료되었습니다. 모든 데이터가 저장되었습니다.",
                        "status": "completed",
                        "progress": 100,
                        "form_items_processed": len(EE_PORTAL_FORM_ITEMS),
                        "saved": True
                    })
                except Exception as e:
                    logger.error(f"완료 메시지 전송 중 오류: {str(e)}")
            else:
                # 저장 실패 메시지 전송
                await send_with_screenshot(websocket, automation, {
                    "success": False,
                    "message": "폼 필드 입력은 완료되었지만 저장 버튼을 찾을 수 없습니다.",
                    "status": "save_failed",
                    "progress": 95,
                    "form_items_processed": len(EE_PORTAL_FORM_ITEMS),
                    "saved": False
                })
            
            # 작업 완료 후 브라우저 종료 전 대기
            await asyncio.sleep(0.5)
            
            # 모든 작업 완료 후 브라우저 종료
            if automation:
                await automation.close()
            logger.info("모든 작업 완료. 브라우저 종료됨.")
            
            # 모든 작업 완료 후 WebSocket 연결 종료
            try:
                await websocket.close()
                logger.info("WebSocket 연결 종료됨.")
            except:
                pass
            
        except asyncio.TimeoutError:
            await websocket.send_json({
                "success": False,
                "message": "요청 시간이 초과되었습니다.",
                "status": "timeout",
                "progress": 0
            })
            if automation:
                try:
                    await automation.close()
                except:
                    pass
        except WebSocketDisconnect:
            logger.info("WebSocket 연결 종료")
            if automation:
                try:
                    await automation.close()
                except:
                    pass
        except Exception as e:
            logger.error(f"WebSocket 처리 중 오류: {str(e)}")
            if automation:
                try:
                    await automation.save_debug_info("ee_websocket_error")
                    await automation.close()
                except:
                    pass
            try:
                await websocket.send_json({
                    "success": False,
                    "message": f"오류가 발생했습니다: {str(e)}",
                    "status": "error",
                    "progress": 0,
                    "error": str(e)
                })
            except:
                pass


async def send_progress_sse_with_screenshot(automation: BrowserAutomation, progress: int, message: str, status: str = "progress", force_screenshot: bool = False):
    """SSE 형식으로 진행 상황 전송 (스크린샷 조건부 포함)"""
    data = {
        "progress": progress,
        "message": message,
        "status": status
    }
    
    # 중요 단계에서만 스크린샷 촬영
    if force_screenshot or status in IMPORTANT_STATUSES:
        # 화면 안정화를 위한 짧은 대기
        await asyncio.sleep(0.1)
        screenshot_base64 = await take_screenshot_optimized(automation)
        if screenshot_base64:
            data["screenshot"] = screenshot_base64
            logger.info(f"스크린샷 촬영 완료 (상태: {status}, 메시지: {message})")
    
    return f"data: {json.dumps(data)}\n\n"


async def run_pr_automation_with_progress():
    """PR 포털 자동화 작업을 실행하면서 진행 상황을 스트리밍"""
    automation = None
    try:
        # 브라우저 초기화
        automation = await BrowserAutomation.create()
        
        # 로그인 페이지로 이동
        login_url = "https://prson-srpel.apps.cic.gc.ca/en/login"
        logger.info(f"로그인 페이지로 이동 중: {login_url}")
        await automation.page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(0.3)
        
        # 로그인 페이지 로드 완료 (스크린샷 포함 - 로그인 화면)
        yield await send_progress_sse_with_screenshot(automation, 20, "로그인 페이지 로드 완료", "waiting_for_login", force_screenshot=True)
        await asyncio.sleep(0.1)
        
        email_selectors = [("name", "username")]
        password_selectors = [("name", "password")]
        login_button_selectors = [("css", "button[type='submit']")]
        
        # 로그인 진행 상황을 받을 큐
        login_progress_queue = asyncio.Queue()
        
        # 로그인 진행 상황 콜백 함수
        async def login_progress_callback(message: str, data: Optional[Dict] = None):
            """로그인 진행 상황을 큐에 추가"""
            try:
                await login_progress_queue.put(message)
            except:
                pass
        
        # 로그인을 별도 태스크로 실행
        async def login_task():
            try:
                await automation.login(
                    url=login_url,
                    email="ehddms7691@gmail.com",
                    password="As12ehddms?",
                    email_selectors=email_selectors,
                    password_selectors=password_selectors,
                    login_button_selectors=login_button_selectors,
                    progress_callback=login_progress_callback
                )
            finally:
                await login_progress_queue.put(None)  # 완료 신호
        
        login_task_obj = asyncio.create_task(login_task())
        
        # 로그인 진행 상황을 실시간으로 전송
        while True:
            try:
                message = await asyncio.wait_for(login_progress_queue.get(), timeout=0.1)
                if message is None:  # 완료 신호
                    break
                
                # 비밀번호 입력 완료 시에만 스크린샷 촬영
                should_take_screenshot = "비밀번호 입력 완료" in message
                
                # 진행 상황 전송
                yield await send_progress_sse_with_screenshot(automation, 22, message, "logging_in", force_screenshot=should_take_screenshot)
            except asyncio.TimeoutError:
                if login_task_obj.done():
                    break
                continue
        
        await login_task_obj
        await asyncio.sleep(0.1)
        
        # 로그인 완료 (스크린샷 없음)
        yield await send_progress_sse_with_screenshot(automation, 30, "로그인 완료", "login_completed", force_screenshot=False)
        await asyncio.sleep(0.1)
        
        # 프로필 페이지로 이동 (스크린샷 없음)
        profile_url = "https://prson-srpel.apps.cic.gc.ca/en/application/profile/3950418"
        yield await send_progress_sse_with_screenshot(automation, 40, f"프로필 페이지로 이동 중... ({profile_url})", "progress", force_screenshot=False)
        await automation.page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(0.3)
        
        # 프로필 페이지 로드 완료 (스크린샷 포함 - 프로필 화면)
        yield await send_progress_sse_with_screenshot(automation, 45, "프로필 페이지 로드 완료", "progress", force_screenshot=True)
        await asyncio.sleep(0.1)
        
        # 폼 필드 입력 시작 (스크린샷 없음)
        yield await send_progress_sse_with_screenshot(automation, 50, "폼 필드 입력 시작...", "filling_forms_start", force_screenshot=False)
        total_fields = len(PROFILE_FORM_DATA)
        
        # 진행률 콜백을 위한 queue
        progress_queue = asyncio.Queue()
        
        # 진행률 콜백 함수 정의 (동기 함수)
        def pr_progress_callback(current: int, total: int, item: Dict):
            """PR 포털 폼 필드 입력 진행률을 queue에 추가"""
            try:
                # 전체 진행률 계산 (50% ~ 80% 사이)
                form_progress = 50 + int((current / total) * 30) if total > 0 else 50
                
                # item에서 필드 이름 추출
                field_name = item.get("name", "")
                
                progress_queue.put_nowait({
                    "progress": form_progress,
                    "message": f"필드 입력 중: {field_name} ({current}/{total})",
                    "status": "filling_forms",
                    "current": current,
                    "total": total,
                    "percentage": round((current / total) * 100, 1) if total > 0 else 0,
                    "current_field": field_name,
                    "current_item": {
                        "tag": item.get("tag", ""),
                        "name": item.get("name", ""),
                        "value": item.get("value", "")
                    }
                })
            except:
                pass
        
        # fill_form_sequential을 별도 태스크로 실행
        async def fill_fields_task():
            await automation.fill_form_sequential(PROFILE_FORM_DATA, progress_callback=pr_progress_callback)
            progress_queue.put_nowait(None)  # 완료 신호
        
        fill_task = asyncio.create_task(fill_fields_task())
        
        # 진행률을 실시간으로 전송
        while True:
            try:
                # queue에서 진행률 데이터 가져오기 (타임아웃 0.1초)
                progress_data = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                
                if progress_data is None:  # 완료 신호
                    break
                
                # 메시지 먼저 전송
                yield f"data: {json.dumps(progress_data)}\n\n"
                
                # 마지막 필드 입력 완료 시에만 스크린샷 촬영
                current = progress_data.get("current", 0)
                total = progress_data.get("total", 0)
                should_take_screenshot = (current == total and total > 0)  # 마지막 필드인지 확인
                
                if should_take_screenshot:
                    # 동기적으로 처리 (SSE generator에서는 yield를 사용해야 함)
                    try:
                        await asyncio.sleep(0.1)  # 화면 안정화
                        screenshot_base64 = await take_screenshot_optimized(automation)
                        if screenshot_base64:
                            current_field = progress_data.get("current_field", "")
                            screenshot_data = {
                                "status": "screenshot",
                                "original_status": "filling_forms",
                                "progress": progress_data.get("progress", 0),
                                "current": current,
                                "total": total,
                                "message": f"마지막 필드 입력 완료: {current_field} ({current}/{total})",
                                "screenshot": screenshot_base64
                            }
                            yield f"data: {json.dumps(screenshot_data)}\n\n"
                            logger.info(f"마지막 필드 입력 완료 스크린샷 전송 완료: {current_field}")
                    except Exception as e:
                        logger.error(f"SSE 스크린샷 처리 중 오류: {str(e)}")
            except asyncio.TimeoutError:
                # queue가 비어있으면 태스크 완료 여부 확인
                if fill_task.done():
                    break
                continue
        
        # 태스크 완료 대기
        await fill_task
        await asyncio.sleep(0.1)
        
        yield await send_progress_sse_with_screenshot(automation, 80, "폼 필드 입력 완료", "progress", force_screenshot=False)
        await asyncio.sleep(0.1)
        
        # Save 버튼 클릭 (스크린샷 없음)
        yield await send_progress_sse_with_screenshot(automation, 90, "Save 버튼 클릭 중...", "progress", force_screenshot=False)
        save_result = await automation.click_save_button()
        await asyncio.sleep(0.1)
        
        # 완료 (스크린샷 없음)
        yield await send_progress_sse_with_screenshot(automation, 100, "작업 완료", "completed", force_screenshot=False)
        
        # 최종 결과 전송 (스크린샷 포함)
        result_data = {
            "progress": 100,
            "message": "프로필 업데이트가 완료되었습니다.",
            "status": "completed",
            "save_button_clicked": save_result
        }
        
        # 최종 스크린샷 추가 (최적화된 방식)
        screenshot_base64 = await take_screenshot_optimized(automation)
        if screenshot_base64:
            result_data["screenshot"] = screenshot_base64
        
        yield f"data: {json.dumps(result_data)}\n\n"
        
        # 브라우저 종료 전 대기
        await asyncio.sleep(0.5)
        
    except Exception as e:
        error_message = f"오류 발생: {str(e)}"
        logger.error(error_message)
        
        error_data = {
            "progress": 0,
            "message": error_message,
            "status": "error",
            "error": str(e)
        }
        
        # 에러 발생 시에도 스크린샷 시도 (최적화된 방식)
        if automation:
            screenshot_base64 = await take_screenshot_optimized(automation)
            if screenshot_base64:
                error_data["screenshot"] = screenshot_base64
        
        yield f"data: {json.dumps(error_data)}\n\n"
    finally:
        # 브라우저 종료
        if automation:
            try:
                await automation.close()
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
async def update_pr_profile_stream(request: Request):
    """
    PR 포털 프로필 업데이트 API (SSE 스트리밍)
    진행 상황을 실시간으로 전송합니다.
    """
    async with max_concurrent:
        return StreamingResponse(
            run_pr_automation_with_progress(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

