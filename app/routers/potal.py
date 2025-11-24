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


async def send_with_screenshot(websocket: WebSocket, automation: BrowserAutomation, message_data: Dict, progress: Optional[int] = None):
    """
    WebSocket 메시지를 스크린샷과 함께 전송하는 헬퍼 함수
    
    Args:
        websocket: WebSocket 연결
        automation: BrowserAutomation 인스턴스
        message_data: 전송할 메시지 데이터 (dict)
        progress: 진행률 (0-100, 선택사항)
    """
    try:
        # progress 필드 추가
        if progress is not None:
            message_data["progress"] = progress
        
        # 스크린샷 촬영 (base64 인코딩)
        screenshot_base64 = None
        try:
            screenshot_bytes = await automation.page.screenshot(full_page=False)
            if screenshot_bytes:
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                logger.info(f"스크린샷 촬영 성공 (길이: {len(screenshot_base64)} 문자, 처음 50자: {screenshot_base64[:50]}...)")
            else:
                logger.warning("스크린샷이 None으로 반환됨")
        except Exception as screenshot_error:
            logger.warning(f"스크린샷 촬영 실패: {str(screenshot_error)}")
        
        # 스크린샷이 있으면 메시지에 추가
        if screenshot_base64:
            message_data["screenshot"] = screenshot_base64
            logger.info(f"메시지에 스크린샷 추가됨 (키: 'screenshot', 길이: {len(screenshot_base64)} 문자)")
        else:
            logger.info("스크린샷이 없어 메시지에 추가하지 않음")
        
        await websocket.send_json(message_data)
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
            # 1. 로그인 정보 수신 대기
            await websocket.send_json({
                "success": True,
                "message": "로그인 정보를 입력하세요.",
                "status": "waiting_for_login",
                "progress": 5,
                "instruction": "JSON 형식으로 전송하세요: {\"username\": \"username\", \"password\": \"password\"}"
            })
            
            login_data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
            
            if "username" not in login_data or "password" not in login_data:
                await websocket.send_json({
                    "success": False,
                    "message": "로그인 정보가 올바르지 않습니다. 'username'과 'password' 필드가 필요합니다.",
                    "status": "error",
                    "progress": 5,
                    "error": "invalid_login_data"
                })
                await websocket.close()
                return
            
            username = login_data["username"]
            password = login_data["password"]
            
            logger.info("로그인 정보 수신 완료. 브라우저 자동화 시작...")
            await websocket.send_json({
                "success": True,
                "message": "로그인 정보를 받았습니다. 브라우저 자동화를 시작합니다...",
                "status": "starting_automation",
                "progress": 10
            })
            
            # 브라우저 자동화 시작
            automation = await BrowserAutomation.create()
            
            # EE 포털 로그인 URL
            login_url = "https://onlineservices-servicesenligne-cic.fjgc-gccf.gc.ca/mycic/gccf?lang=eng&idp=gckey&svc=/mycic/start"
            
            # EE 포털 로그인 필드 선택자
            email_selectors = [("name", "token1")]
            password_selectors = [("name", "token2")]
            login_button_selectors = [("css", "button[type='submit']")]
            
            # 로그인 시도
            logger.info("로그인 중...")
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "로그인 중...",
                "status": "logging_in",
                "progress": 15
            })
            
            await automation.login(
                url=login_url,
                email=username,
                password=password,
                email_selectors=email_selectors,
                password_selectors=password_selectors,
                login_button_selectors=login_button_selectors,
                wait_for_angular=False
            )
            
            # 로그인 후 페이지 로드 대기
            await asyncio.sleep(3)
            try:
                await automation.page.wait_for_load_state("networkidle", timeout=30000)
            except:
                logger.warning("네트워크 유휴 상태 대기 시간 초과 (계속 진행)")
            
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
            await asyncio.sleep(3)
            try:
                await automation.page.wait_for_load_state("networkidle", timeout=30000)
            except:
                pass
            
            # Continue 버튼 클릭 후 스크린샷 전송
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "Continue 버튼 클릭 완료",
                "status": "continue_clicked",
                "progress": 30
            })
            
            # 2FA 코드 입력 필드 확인
            logger.info("2FA 코드 필요 여부 확인 중...")
            needs_2fa = not await automation.handle_2fa(code=None, timeout=20000)
            
            if needs_2fa:
                # 2FA 코드 필요
                await send_with_screenshot(websocket, automation, {
                    "success": True,
                    "message": "2FA 인증 코드가 필요합니다.",
                    "status": "waiting_for_2fa",
                    "progress": 35,
                    "instruction": "이메일에서 받은 2FA 코드를 JSON 형식으로 전송하세요: {\"code\": \"123456\"}"
                })
                
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
                            # 2FA 코드 입력 및 처리
                            result = await automation.handle_2fa(code=two_factor_code, timeout=20000)
                        
                            if result:
                                # 2FA 처리 성공
                                await send_with_screenshot(websocket, automation, {
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
            await asyncio.sleep(1)
            try:
                auth_success_btn = automation.page.locator("button[type='submit']")
                count = await auth_success_btn.count()
                if count > 0:
                    logger.info("Authentication success 페이지의 submit 버튼 클릭 중...")
                    await auth_success_btn.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await auth_success_btn.first.click()
                    logger.info("Authentication success submit 버튼 클릭 완료")
                    
                    await asyncio.sleep(1)
                    try:
                        await automation.page.wait_for_load_state("networkidle", timeout=15000)
                    except:
                        pass
            except Exception as e:
                logger.debug(f"Authentication success 버튼 클릭 실패: {str(e)}")
            
            # 5. Terms and Conditions 페이지의 _continue 클릭
            logger.info("Terms and Conditions 페이지 확인 중...")
            await asyncio.sleep(1)
            try:
                terms_continue_btn = automation.page.locator("input[name='_continue'][type='submit']")
                count = await terms_continue_btn.count()
                if count > 0:
                    logger.info("Terms and Conditions 페이지의 _continue 버튼 클릭 중...")
                    await terms_continue_btn.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await terms_continue_btn.first.click()
                    logger.info("Terms and Conditions _continue 버튼 클릭 완료")
                    
                    await asyncio.sleep(1)
                    try:
                        await automation.page.wait_for_load_state("networkidle", timeout=15000)
                    except:
                        pass
            except Exception as e:
                logger.debug(f"Terms and Conditions 버튼 클릭 실패: {str(e)}")
            
            # 6. Identity validation 페이지 - 질문-답변 처리
            logger.info("Identity validation 페이지 확인 중...")
            await asyncio.sleep(1)
            
            # 질문 확인 (답변 없이)
            qa_result = await automation.handle_question_answer(answer=None)
            
            if qa_result["has_question"]:
                logger.info(f"질문 발견: {qa_result['question']}")
                
                # 질문을 클라이언트에게 전송 (스크린샷 포함)
                await send_with_screenshot(websocket, automation, {
                    "success": True,
                    "message": f"질문: {qa_result['question']}",
                    "status": "question",
                    "progress": 50,
                    "question": qa_result["question"],
                    "question_number": 1,
                    "instruction": "답변을 JSON 형식으로 전송하세요: {\"answer\": \"답변\"}"
                })
                
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
                    
                    # 답변 처리 (answer 필드에 입력하고 _continue 클릭)
                    qa_result2 = await automation.handle_question_answer(answer=user_answer)
                    
                    if qa_result2["completed"]:
                        await send_with_screenshot(websocket, automation, {
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
            await automation.page.wait_for_load_state("domcontentloaded")
            await automation.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            # 폼 필드 입력 시작 알림
            await send_with_screenshot(websocket, automation, {
                "success": True,
                "message": "EE 지원 페이지로 이동 완료. JSON 데이터를 순서대로 입력합니다...",
                "status": "filling_forms",
                "progress": 65,
                "total_items": len(EE_PORTAL_FORM_ITEMS)
            })
            
            # 진행률 콜백 함수 정의
            async def progress_callback(current: int, total: int, item: Dict):
                """폼 필드 입력 진행률을 WebSocket으로 전송 (스크린샷 포함)"""
                try:
                    # 전체 진행률 계산 (65% ~ 90% 사이)
                    # 65%부터 시작해서 폼 필드 입력이 90%까지
                    form_progress = 65 + int((current / total) * 25) if total > 0 else 65
                    
                    # 스크린샷 촬영 (base64 인코딩)
                    screenshot_base64 = None
                    try:
                        screenshot_bytes = await automation.page.screenshot(full_page=False)
                        if screenshot_bytes:
                            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                            logger.debug(f"진행률 스크린샷 촬영 성공 (길이: {len(screenshot_base64)} 문자)")
                    except Exception as screenshot_error:
                        logger.warning(f"진행률 스크린샷 촬영 실패: {str(screenshot_error)}")
                    
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
                    
                    # 스크린샷이 있으면 추가
                    if screenshot_base64:
                        progress_data["screenshot"] = screenshot_base64
                        logger.debug(f"진행률 메시지에 스크린샷 추가됨 (길이: {len(screenshot_base64)} 문자)")
                    
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
                # 저장 완료 메시지 전송
                await send_with_screenshot(websocket, automation, {
                    "success": True,
                    "message": "EE 포털 자동화 작업이 완료되었습니다. 모든 데이터가 저장되었습니다.",
                    "status": "completed",
                    "progress": 100,
                    "form_items_processed": len(EE_PORTAL_FORM_ITEMS),
                    "saved": True
                })
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
            await asyncio.sleep(3)
            
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
                "progress": -1
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
                    "progress": -1,
                    "error": str(e)
                })
            except:
                pass


async def send_progress_sse_with_screenshot(automation: BrowserAutomation, progress: int, message: str, status: str = "progress"):
    """SSE 형식으로 진행 상황 전송 (스크린샷 포함)"""
    data = {
        "progress": progress,
        "message": message,
        "status": status
    }
    
    # 스크린샷 촬영 (base64 인코딩)
    try:
        screenshot_bytes = await automation.page.screenshot(full_page=False)
        if screenshot_bytes:
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            data["screenshot"] = screenshot_base64
    except Exception as screenshot_error:
        logger.debug(f"스크린샷 촬영 실패: {str(screenshot_error)}")
    
    return f"data: {json.dumps(data)}\n\n"


async def run_pr_automation_with_progress():
    """PR 포털 자동화 작업을 실행하면서 진행 상황을 스트리밍"""
    automation = None
    try:
        # 브라우저 초기화
        automation = await BrowserAutomation.create()
        yield await send_progress_sse_with_screenshot(automation, 10, "브라우저 초기화 중...", "progress")
        await asyncio.sleep(0.1)
        
        # 로그인 페이지 로드
        yield await send_progress_sse_with_screenshot(automation, 20, "로그인 페이지 로드 중...", "progress")
        login_url = "https://prson-srpel.apps.cic.gc.ca/en/login"
        email_selectors = [("name", "username")]
        password_selectors = [("name", "password")]
        login_button_selectors = [("css", "button[type='submit']")]
        
        await automation.login(
            url=login_url,
            email="ehddms7691@gmail.com",
            password="As12ehddms?",
            email_selectors=email_selectors,
            password_selectors=password_selectors,
            login_button_selectors=login_button_selectors,
            wait_for_angular=True
        )
        await asyncio.sleep(0.1)
        
        # 로그인 완료
        yield await send_progress_sse_with_screenshot(automation, 30, "로그인 완료", "progress")
        await asyncio.sleep(0.1)
        
        # 프로필 페이지로 이동
        profile_url = "https://prson-srpel.apps.cic.gc.ca/en/application/profile/3950418"
        yield await send_progress_sse_with_screenshot(automation, 40, f"프로필 페이지로 이동 중... ({profile_url})", "progress")
        await automation.page.goto(profile_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Angular 앱 로드 대기
        try:
            await automation.page.wait_for_selector("[class*='ng-'], input[name]", timeout=15000)
        except:
            pass
        
        await asyncio.sleep(0.1)
        
        # 프로필 페이지 로드 완료
        yield await send_progress_sse_with_screenshot(automation, 45, "프로필 페이지 로드 완료", "progress")
        await asyncio.sleep(0.1)
        
        # 폼 필드 입력
        yield await send_progress_sse_with_screenshot(automation, 50, "폼 필드 입력 시작...", "progress")
        total_fields = len(PROFILE_FORM_DATA)
        
        # 진행률 콜백을 위한 queue
        progress_queue = asyncio.Queue()
        
        # 진행률 콜백 함수 정의 (동기 함수)
        def pr_progress_callback(current: int, total: int, field_name: str):
            """PR 포털 폼 필드 입력 진행률을 queue에 추가"""
            try:
                # 전체 진행률 계산 (50% ~ 80% 사이)
                form_progress = 50 + int((current / total) * 30) if total > 0 else 50
                
                progress_queue.put_nowait({
                    "progress": form_progress,
                    "message": f"필드 입력 중: {field_name} ({current}/{total})",
                    "status": "filling_forms",
                    "current": current,
                    "total": total,
                    "percentage": round((current / total) * 100, 1) if total > 0 else 0,
                    "current_field": field_name
                })
            except:
                pass
        
        # fill_form_fields를 별도 태스크로 실행
        async def fill_fields_task():
            await automation.fill_form_fields(PROFILE_FORM_DATA, progress_callback=pr_progress_callback)
            progress_queue.put_nowait(None)  # 완료 신호
        
        fill_task = asyncio.create_task(fill_fields_task())
        
        # 진행률을 실시간으로 전송
        while True:
            try:
                # queue에서 진행률 데이터 가져오기 (타임아웃 0.1초)
                progress_data = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                
                if progress_data is None:  # 완료 신호
                    break
                
                # 스크린샷 촬영
                screenshot_base64 = None
                try:
                    screenshot_bytes = await automation.page.screenshot(full_page=False)
                    if screenshot_bytes:
                        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                except:
                    pass
                
                if screenshot_base64:
                    progress_data["screenshot"] = screenshot_base64
                
                yield f"data: {json.dumps(progress_data)}\n\n"
            except asyncio.TimeoutError:
                # queue가 비어있으면 태스크 완료 여부 확인
                if fill_task.done():
                    break
                continue
        
        # 태스크 완료 대기
        await fill_task
        await asyncio.sleep(0.1)
        
        yield await send_progress_sse_with_screenshot(automation, 80, "폼 필드 입력 완료", "progress")
        await asyncio.sleep(0.1)
        
        # Save 버튼 클릭
        yield await send_progress_sse_with_screenshot(automation, 90, "Save 버튼 클릭 중...", "progress")
        save_result = await automation.click_save_button()
        await asyncio.sleep(0.1)
        
        # 완료
        yield await send_progress_sse_with_screenshot(automation, 100, "작업 완료", "success")
        
        # 최종 결과 전송 (스크린샷 포함)
        result_data = {
            "progress": 100,
            "message": "프로필 업데이트가 완료되었습니다.",
            "status": "success",
            "save_button_clicked": save_result
        }
        
        # 최종 스크린샷 추가
        try:
            screenshot_bytes = await automation.page.screenshot(full_page=False)
            if screenshot_bytes:
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                result_data["screenshot"] = screenshot_base64
        except Exception as screenshot_error:
            logger.debug(f"최종 스크린샷 촬영 실패: {str(screenshot_error)}")
        
        yield f"data: {json.dumps(result_data)}\n\n"
        
        # 브라우저 종료 전 대기
        await asyncio.sleep(2)
        
    except Exception as e:
        error_message = f"오류 발생: {str(e)}"
        logger.error(error_message)
        
        error_data = {
            "progress": -1,
            "message": error_message,
            "status": "error",
            "error": str(e)
        }
        
        # 에러 발생 시에도 스크린샷 시도
        if automation:
            try:
                screenshot_bytes = await automation.page.screenshot(full_page=False)
                if screenshot_bytes:
                    screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    error_data["screenshot"] = screenshot_base64
            except:
                pass
        
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

