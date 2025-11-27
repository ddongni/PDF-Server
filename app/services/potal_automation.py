"""브라우저 자동화 서비스"""
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import asyncio
import os
import logging
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any, Callable

logger = logging.getLogger(__name__)

PROFILE_FORM_DATA = [
    {
        "name": "profileForm-correspondence",
              "tag": "select",
              "value": "French"
	},
    {
        "name": "profileForm-familyName",
              "tag": "input",
              "type": "text",
              "value": "Diana"
      },
     {
        "name": "personalDetailsForm-givenName",
              "tag": "input",
              "type": "text",
              "value": "Shin",
      },
      {
        "name": "personalDetailsForm-dob",
              "tag": "input",
              "type": "text",
              "value": "1996/03/09"
      },
      {
        "name": "postOfficeBox",
              "tag": "input",
              "type": "text",
              "value": "1013"
      },
      {
        "name": "apartmentUnit",
              "tag": "input",
              "type": "text",
              "value": "1602"
      },
      {
        "name": "streetNumber",
              "tag": "input",
              "type": "text",
              "value": "80"
      },
      {
        "name": "streetName",
              "tag": "input",
              "type": "text",
              "value": "Pangyo Daejang Ro"
      },
      {
        "name": "city",
              "tag": "input",
              "type": "text",
              "value": "Seongnam"
      },
      {
        "name": "country",
              "tag": "select",
              "value": "Korea, South"
      },
      {
        "name": "district",
              "tag": "input",
              "type": "text",
              "value": "Gyenggi-do"
      },
      {
        "name": "postalCode",
              "tag": "input",
              "type": "text",
              "value": "12345"
      },
      {
        "name": "residentialSameAsMailingAddress",
              "tag": "input",
              "type": "radio",
              "value": "Yes"
      }
]

# EE 포털 폼 데이터 (하드코딩)
EE_PORTAL_FORM_ITEMS = [
    {
        "name": "answerList[0].value",
        "tag": "select",
        "value": "British Columbia"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    },
    {
        "name": "answerList[1].value",
        "tag": "select",
        "value": "CELPIP"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    },
    {
        "name": "answerList[2].value",
        "tag": "select",
        "value": "2025"
    },
    {
        "name": "answerList[3].value",
        "tag": "select",
        "value": "November"
    },
    {
        "name": "answerList[4].value",
        "tag": "select",
        "value": "09"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    },
    {
        "name": "answerList[1].value",
        "tag": "select",
        "value": "7"
    },
    {
        "name": "answerList[2].value",
        "tag": "select",
        "value": "7"
    },
    {
        "name": "answerList[3].value",
        "tag": "select",
        "value": "7"
    },
    {
        "name": "answerList[4].value",
        "tag": "select",
        "value": "7"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    },
    {
        "name": "answerList[1].value",
        "tag": "select",
        "value": "None"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    },
    {
        "name": "answerList[1].value",
        "tag": "select",
        "value": "One year or more"
    },
    {
        "name": "answerList[2].value",
        "tag": "select",
        "value": "TEER Category 1"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    },
    {
        "tag": "a",
        "value": "Continue"
    },
    {
        "name": "answerList[1].value",
        "tag": "input",
        "type": "text",
        "value": "Shin"
    },
    {
        "name": "answerList[2].value",
        "tag": "input",
        "type": "text",
        "value": "DongEun"
    },
    {
        "name": "answerList[3].value",
        "tag": "select",
        "value": "Female"
    },
    {
        "name": "answerList[5].value",
        "tag": "select",
        "value": "1996"
    },
    {
        "name": "answerList[6].value",
        "tag": "select",
        "value": "March"
    },
    {
        "name": "answerList[7].value",
        "tag": "select",
        "value": "09"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    },
    {
        "name": "answerList[0].value",
        "tag": "select",
        "value": "Never Married/Single"
    },
    {
        "name": "_next",
        "tag": "input",
        "type": "submit"
    }
]

class BrowserAutomation:
    def __init__(self):
        """브라우저 자동화 클래스 초기화"""
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    @classmethod
    async def create(cls):
        """비동기 팩토리 메서드로 브라우저 자동화 인스턴스 생성"""
        instance = cls()
        await instance.setup_browser()
        return instance
    
    async def setup_browser(self):
        """Playwright 브라우저 설정"""
        self.playwright = await async_playwright().start()
        
        # 도커 환경 감지
        is_docker = os.path.exists("/usr/bin/chromium")
        
        # 브라우저 옵션 설정
        browser_type = "chromium"
        launch_options = {
            "headless": is_docker,  # 도커 환경에서만 헤드리스
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        }
        
        if is_docker:
            launch_options["executable_path"] = "/usr/bin/chromium"
        
        # 브라우저 실행
        self.browser = await self.playwright.chromium.launch(**launch_options)
        
        # 컨텍스트 생성 (시크릿 모드)
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        self.context = await self.browser.new_context(**context_options)
        
        # 자동화 감지 방지 스크립트 추가
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        # 페이지 생성
        self.page = await self.context.new_page()
        
        logger.info("브라우저가 성공적으로 시작되었습니다.")
    
    async def save_debug_info(self, filename_prefix="debug"):
        """디버깅 정보 저장 (스크린샷 및 페이지 소스)"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{filename_prefix}_screenshot_{timestamp}.png"
            html_path = f"{filename_prefix}_page_source_{timestamp}.html"
            
            await self.page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"스크린샷 저장: {screenshot_path}")
            
            content = await self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"페이지 소스 저장: {html_path}")
            
            return screenshot_path, html_path
        except Exception as e:
            logger.error(f"디버깅 정보 저장 실패: {str(e)}")
            return None, None
    
    async def find_element_multiple_ways(self, selectors: List[Tuple[str, str]], timeout: int = 15000, wait_for_clickable: bool = False):
        """
        여러 방법으로 요소를 찾는 함수
        
        Args:
            selectors: [("name", "email"), ("id", "email"), ...] 형태의 리스트
            timeout: 대기 시간 (밀리초)
            wait_for_clickable: 클릭 가능할 때까지 대기할지 여부
        
        Returns:
            찾은 요소 Locator 또는 None
        """
        # 각 선택자마다 짧은 timeout으로 시도 (전체 timeout을 나눠서 사용)
        per_selector_timeout = min(timeout // len(selectors) if selectors else timeout, 3000)  # 최대 3초
        
        for selector_type, value in selectors:
            try:
                logger.info(f"요소 찾기 시도: {selector_type}={value}")
                
                if selector_type == "name":
                    locator = self.page.locator(f"input[name='{value}']")
                elif selector_type == "id":
                    locator = self.page.locator(f"#{value}")
                elif selector_type == "css":
                    locator = self.page.locator(value)
                elif selector_type == "xpath":
                    locator = self.page.locator(f"xpath={value}")
                else:
                    continue
                
                # 요소가 존재하는지 빠르게 확인
                count = await locator.count()
                if count == 0:
                    logger.debug(f"요소를 찾을 수 없음: {selector_type}={value}")
                    continue
                
                if wait_for_clickable:
                    try:
                        await locator.first.wait_for(state="visible", timeout=per_selector_timeout)
                        if await locator.first.is_visible():
                            logger.info(f"요소 찾기 성공: {selector_type}={value}")
                            return locator.first
                    except Exception as e:
                        logger.debug(f"요소가 보이지 않음 ({selector_type}={value}): {str(e)}")
                        continue
                else:
                    # 요소가 존재하면 바로 반환 (보이는지 확인은 선택적)
                    try:
                        # 짧은 시간 내에 보이는지 확인 시도
                        await locator.first.wait_for(state="visible", timeout=1000)
                    except:
                        pass  # 보이지 않아도 계속 진행 (attached 상태면 충분)
                    
                    logger.info(f"요소 찾기 성공: {selector_type}={value}")
                    return locator.first
            except Exception as e:
                logger.debug(f"요소 찾기 실패 ({selector_type}={value}): {str(e)}")
                continue
        
        return None
    
    async def login(self, url: str, email: str, password: str, 
              email_selectors: Optional[List[Tuple[str, str]]] = None, 
              password_selectors: Optional[List[Tuple[str, str]]] = None, 
              login_button_selectors: Optional[List[Tuple[str, str]]] = None,
              progress_callback: Optional[Callable[[str, Optional[Dict]], None]] = None):
        """
        로그인 자동화 함수
        
        Args:
            url: 로그인 페이지 URL
            email: 이메일 주소
            password: 비밀번호
            email_selectors: 이메일 필드를 찾을 선택자 리스트 [("name", "email"), ...]
            password_selectors: 비밀번호 필드를 찾을 선택자 리스트
            login_button_selectors: 로그인 버튼을 찾을 선택자 리스트
        """
        try:
            # 현재 URL 확인 - 이미 같은 페이지에 있으면 페이지 로드 건너뛰기
            current_url = self.page.url
            if current_url == url or url in current_url:
                logger.info(f"이미 로그인 페이지에 있습니다. URL: {current_url}")
                # 페이지가 이미 로드되어 있으므로 최소 대기만 수행
                await asyncio.sleep(0.1)
            else:
                # 페이지 로드 (재시도 로직 포함)
                # IRCC가 URL을 리다이렉트할 수 있으므로 domcontentloaded 사용
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        # domcontentloaded로 먼저 로드 (리다이렉트 허용)
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        logger.info(f"페이지 로드 완료: {url} (현재 URL: {self.page.url})")
                        
                        # 리다이렉트 후 페이지 안정화를 위한 추가 대기
                        await asyncio.sleep(0.2)
                        
                        # load 상태 확인 (선택적, 실패해도 계속 진행)
                        try:
                            await self.page.wait_for_load_state("load", timeout=5000)
                        except:
                            logger.debug("load 상태 대기 시간 초과 (계속 진행)")
                        
                        break
                    except Exception as e:
                        if retry < max_retries - 1:
                            logger.warning(f"페이지 로드 실패 (재시도 {retry + 1}/{max_retries}): {str(e)}")
                            await asyncio.sleep(0.3)
                        else:
                            logger.error(f"페이지 로드 최종 실패: {str(e)}")
                            raise
            
            # DOM 로드 상태 확인 (networkidle 대신 domcontentloaded 사용)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except:
                logger.debug("domcontentloaded 대기 시간 초과 (리다이렉트로 인한 정상적인 경우일 수 있음, 계속 진행)")
            
            await asyncio.sleep(0.1)  # 최소 대기 시간
            
            # 기본 선택자
            if email_selectors is None:
                email_selectors = [
                    ("name", "username"),
                    ("name", "email"),
                    ("id", "username"),
                    ("id", "email"),
                    ("css", "input[type='text'][name*='user' i]"),
                    ("css", "input[type='text'][name*='email' i]"),
                ]
            
            if password_selectors is None:
                password_selectors = [
                    ("name", "password"),
                ]
            
            if login_button_selectors is None:
                login_button_selectors = [
                    ("css", 'button[type="submit"]'),
                    ("css", 'input[type="submit"]'),
                    ("xpath", "//button[@type='submit']"),
                    ("xpath", "//input[@type='submit']"),
                    ("xpath", "//button[contains(text(), 'Login') or contains(text(), '로그인') or contains(text(), 'Sign in')]"),
                    ("css", "button.btn-primary"),
                    ("css", "button.btn-login"),
                    ("id", "login"),
                    ("id", "loginBtn"),
                ]
            
            # 이메일 입력 필드 찾기 및 입력 (재시도 포함)
            logger.info("이메일 필드 찾기 시작...")
            email_field = None
            for retry in range(3):
                email_field = await self.find_element_multiple_ways(email_selectors, timeout=5000)
                if email_field:
                    break
                if retry < 2:
                    logger.warning(f"이메일 필드를 찾을 수 없음 (재시도 {retry + 1}/3)")
                    await asyncio.sleep(0.3)
            
            if not email_field:
                logger.error("이메일 필드를 찾을 수 없습니다. 디버깅 정보를 저장합니다.")
                await self.save_debug_info("email_field_not_found")
                raise Exception("이메일 입력 필드를 찾을 수 없습니다.")
            
            logger.info("이메일 필드 찾기 성공. 입력 시작...")
            
            # 진행 상황 콜백 호출
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback("이메일 입력 중...", None)
                    else:
                        progress_callback("이메일 입력 중...", None)
                except:
                    pass
            
            # 입력 필드에 포커스
            await email_field.focus()
            await asyncio.sleep(0.05)
            
            # 기존 값 제거
            await email_field.clear()
            await asyncio.sleep(0.05)
            
            # 값 입력 (여러 방법 시도)
            try:
                await email_field.fill(email)
                await asyncio.sleep(0.1)
                
                # 진행 상황 콜백 호출 (이메일 입력 후)
                if progress_callback:
                    try:
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback("이메일 입력 완료", None)
                        else:
                            progress_callback("이메일 입력 완료", None)
                    except:
                        pass
                
                # 입력 확인
                input_value = await email_field.input_value()
                if input_value != email:
                    logger.warning(f"입력 값이 일치하지 않음. 기대: {email}, 실제: {input_value}")
                    # JavaScript로 직접 설정 시도
                    try:
                        await email_field.evaluate(f"""
                            (element, value) => {{
                                element.value = value;
                                element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        """, email)
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"JavaScript 입력 실패: {str(e)}")
            except Exception as e:
                logger.warning(f"fill() 실패, type() 시도: {str(e)}")
                await email_field.type(email, delay=50)
                await asyncio.sleep(0.1)
            
            # 이메일 입력 최종 확인
            final_email = await email_field.input_value()
            if final_email != email:
                logger.warning(f"이메일 입력 확인 실패. 기대: {email}, 실제: {final_email}")
                # 재시도
                await email_field.clear()
                await email_field.fill(email)
                await asyncio.sleep(0.1)
            else:
                logger.info(f"이메일 입력 완료: {email}")
            
            # 비밀번호 입력 필드 찾기 및 입력 (재시도 포함)
            logger.info("비밀번호 필드 찾기 시작...")
            password_field = None
            for retry in range(3):
                password_field = await self.find_element_multiple_ways(password_selectors, timeout=5000)
                if password_field:
                    break
                if retry < 2:
                    logger.warning(f"비밀번호 필드를 찾을 수 없음 (재시도 {retry + 1}/3)")
                    await asyncio.sleep(0.3)
            
            if not password_field:
                logger.error("비밀번호 필드를 찾을 수 없습니다. 디버깅 정보를 저장합니다.")
                await self.save_debug_info("password_field_not_found")
                raise Exception("비밀번호 입력 필드를 찾을 수 없습니다.")
            
            logger.info("비밀번호 필드 찾기 성공. 입력 시작...")
            
            # 진행 상황 콜백 호출
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback("비밀번호 입력 중...", None)
                    else:
                        progress_callback("비밀번호 입력 중...", None)
                except:
                    pass
            
            # 입력 필드에 포커스
            await password_field.focus()
            await asyncio.sleep(0.05)
            
            # 기존 값 제거
            await password_field.clear()
            await asyncio.sleep(0.05)
            
            # 값 입력 (여러 방법 시도)
            try:
                await password_field.fill(password)
                await asyncio.sleep(0.2)  # 비밀번호 입력 후 화면 안정화 대기
                
                # 진행 상황 콜백 호출 (비밀번호 입력 후 - 스크린샷 촬영을 위해 먼저 호출)
                if progress_callback:
                    try:
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback("비밀번호 입력 완료", None)
                        else:
                            progress_callback("비밀번호 입력 완료", None)
                    except:
                        pass
                
                # 스크린샷 촬영을 위한 추가 대기 (비밀번호 입력한 화면이 보이도록)
                await asyncio.sleep(0.3)
                
                # 입력 확인 (비밀번호 필드는 보안상 확인하지 않을 수도 있음)
                try:
                    input_value = await password_field.input_value()
                    if len(input_value) != len(password):
                        logger.warning(f"비밀번호 입력 길이가 일치하지 않음")
                        # JavaScript로 직접 설정 시도
                        try:
                            await password_field.evaluate(f"""
                                (element, value) => {{
                                    element.value = value;
                                    element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                }}
                            """, password)
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            logger.warning(f"JavaScript 비밀번호 입력 실패: {str(e)}")
                except:
                    pass  # 비밀번호 필드는 보안상 값을 읽을 수 없을 수 있음
            except Exception as e:
                logger.warning(f"fill() 실패, type() 시도: {str(e)}")
                await password_field.type(password, delay=50)
                await asyncio.sleep(0.2)
                
                # 진행 상황 콜백 호출 (type() 방식으로 입력한 경우)
                if progress_callback:
                    try:
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback("비밀번호 입력 완료", None)
                        else:
                            progress_callback("비밀번호 입력 완료", None)
                    except:
                        pass
                
                # 스크린샷 촬영을 위한 추가 대기
                await asyncio.sleep(0.3)
            
            logger.info("비밀번호 입력 완료")
            
            # 로그인 버튼 찾기 및 클릭 (재시도 포함)
            login_btn = None
            for retry in range(3):
                login_btn = await self.find_element_multiple_ways(login_button_selectors, wait_for_clickable=True, timeout=10000)
                if login_btn:
                    break
                if retry < 2:
                    logger.warning(f"로그인 버튼을 찾을 수 없음 (재시도 {retry + 1}/3)")
                    await asyncio.sleep(0.3)
            
            if not login_btn:
                logger.error("로그인 버튼을 찾을 수 없습니다. 디버깅 정보를 저장합니다.")
                await self.save_debug_info("login_button_not_found")
                raise Exception("로그인 버튼을 찾을 수 없습니다.")
            
            # 진행 상황 콜백 호출
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback("로그인 버튼 클릭 준비 중...", None)
                    else:
                        progress_callback("로그인 버튼 클릭 준비 중...", None)
                except:
                    pass
            
            # 스크롤하여 버튼이 보이도록
            await login_btn.scroll_into_view_if_needed()
            await asyncio.sleep(0.2)
            
            # 클릭 (여러 방법 시도)
            clicked = False
            for click_method in ["normal", "javascript", "evaluate"]:
                try:
                    if click_method == "normal":
                        await login_btn.click()
                        clicked = True
                    elif click_method == "javascript":
                        await login_btn.evaluate("element => element.click()")
                        clicked = True
                    elif click_method == "evaluate":
                        await self.page.evaluate("""
                            (selector) => {
                                const btn = document.querySelector(selector);
                                if (btn) btn.click();
                            }
                        """, login_button_selectors[0][1] if login_button_selectors else "button[type='submit']")
                        clicked = True
                    
                    if clicked:
                        logger.info(f"로그인 버튼 클릭 완료 ({click_method})")
                        break
                except Exception as e:
                    logger.debug(f"{click_method} 클릭 실패: {str(e)}")
                    continue
            
            if not clicked:
                logger.error("모든 클릭 방법 실패")
                raise Exception("로그인 버튼 클릭 실패")
            
            # 로그인 후 페이지 로드 대기
            await asyncio.sleep(0.3)
            
            # URL 변경 감지 (로그인 성공 확인)
            initial_url = self.page.url
            max_wait = 3  # 최대 3초 대기 (5초 -> 3초)
            waited = 0
            
            while waited < max_wait:
                try:
                    await asyncio.sleep(0.3)  # 0.5초 -> 0.3초로 단축
                    current_url = self.page.url
                    if current_url != initial_url:
                        logger.info(f"페이지 전환 확인: {initial_url} -> {current_url}")
                        break
                    waited += 1
                except:
                    break
            
            # DOM 로드 상태 확인 (networkidle 대신 domcontentloaded 사용)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except:
                logger.warning("domcontentloaded 대기 시간 초과 (계속 진행)")
            
            # 추가 대기 (페이지 안정화)
            await asyncio.sleep(0.1)  # 최소 대기 시간
            
            # 현재 URL 확인
            current_url = self.page.url
            logger.info(f"로그인 후 현재 URL: {current_url}")
            
            # 로그인 실패 확인 (에러 메시지나 같은 페이지에 머물러 있는지)
            try:
                # 에러 메시지 확인
                error_elements = await self.page.locator("text=/error|invalid|incorrect|wrong/i").count()
                if error_elements > 0:
                    error_text = await self.page.locator("text=/error|invalid|incorrect|wrong/i").first.text_content()
                    logger.warning(f"로그인 에러 메시지 발견: {error_text}")
            except:
                pass
            
        except Exception as e:
            logger.error(f"로그인 중 오류 발생: {str(e)}")
            await self.save_debug_info("login_error")
            raise
    
    async def handle_2fa(self, code: Optional[str] = None, code_selectors: Optional[List[Tuple[str, str]]] = None, 
                   submit_selectors: Optional[List[Tuple[str, str]]] = None, timeout: int = 60000,
                   progress_callback: Optional[Callable[[str, Optional[Dict]], None]] = None):
        """
        2FA 코드 입력 처리 함수
        
        Args:
            code: 2FA 코드 (None이면 대기 상태로 전환)
            code_selectors: 코드 입력 필드를 찾을 선택자 리스트
            submit_selectors: 제출 버튼을 찾을 선택자 리스트
            timeout: 코드 입력 필드가 나타날 때까지 대기 시간 (밀리초)
        
        Returns:
            True: 2FA 처리 완료, False: 코드가 필요함
        """
        try:
            logger.info("2FA 코드 입력 필드 감지 중...")
            
            # 기본 선택자
            if code_selectors is None:
                code_selectors = [
                    ("name", "code"),
                    ("name", "verificationCode"),
                    ("name", "twoFactorCode"),
                    ("name", "token3"),  # GCKey 2FA 필드
                    ("id", "code"),
                    ("id", "verificationCode"),
                    ("id", "token3"),  # GCKey 2FA 필드
                    ("css", "input[type='text'][placeholder*='code' i]"),
                    ("css", "input[type='text'][name*='code' i]"),
                    ("css", "input[type='text'][id*='code' i]"),
                    ("css", "input[type='text'][name*='token' i]"),
                ]
            
            if submit_selectors is None:
                submit_selectors = [
                    ("css", "button[type='submit']"),
                    ("xpath", "//button[contains(text(), 'Verify') or contains(text(), '확인')]"),
                    ("xpath", "//button[contains(text(), 'Submit') or contains(text(), '제출')]"),
                    ("css", "button.btn-primary"),
                ]
            
            # 2FA 코드 입력 필드 찾기
            code_field = None
            for selector_type, value in code_selectors:
                try:
                    if selector_type == "name":
                        locator = self.page.locator(f"input[name='{value}']")
                    elif selector_type == "id":
                        locator = self.page.locator(f"#{value}")
                    elif selector_type == "css":
                        locator = self.page.locator(value)
                    else:
                        continue
                    
                    # 짧은 timeout으로 먼저 시도
                    try:
                        await locator.wait_for(state="visible", timeout=min(timeout, 10000))
                        if await locator.is_visible():
                            code_field = locator
                            logger.info(f"2FA 코드 입력 필드 발견: {selector_type}={value}")
                            break
                    except:
                        # 다음 선택자 시도
                        continue
                except Exception as e:
                    logger.debug(f"2FA 필드 찾기 실패 ({selector_type}={value}): {str(e)}")
                    continue
            
            if not code_field:
                # 페이지 소스를 확인하여 디버깅
                try:
                    current_url = self.page.url
                    page_title = await self.page.title()
                    logger.info(f"2FA 필드를 찾을 수 없습니다. 현재 URL: {current_url}, 페이지 제목: {page_title}")
                    
                    # 페이지에 "code" 또는 "verification" 텍스트가 있는지 확인
                    page_content = await self.page.content()
                    if "code" in page_content.lower() or "verification" in page_content.lower():
                        logger.warning("페이지에 'code' 또는 'verification' 텍스트가 있지만 필드를 찾을 수 없습니다.")
                        # 디버깅 정보 저장
                        await self.save_debug_info("2fa_field_not_found")
                except:
                    pass
                
                logger.info("2FA 코드 입력 필드를 찾을 수 없습니다. (2FA가 필요하지 않을 수 있습니다)")
                return True  # 2FA가 필요 없으면 성공으로 처리
            
            # 코드가 제공되지 않았으면 False 반환 (코드 필요)
            if not code:
                logger.warning("2FA 코드가 필요하지만 제공되지 않았습니다.")
                return False
            
            # 코드 입력
            logger.info("2FA 코드 입력 중...")
            await code_field.clear()
            await asyncio.sleep(0.1)
            await code_field.fill(code)
            logger.info("2FA 코드 입력 완료")
            
            # 진행 상황 콜백 호출 (코드 입력 후)
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback("2FA 코드 입력 완료", None)
                    else:
                        progress_callback("2FA 코드 입력 완료", None)
                except:
                    pass
            
            # 제출 버튼 찾기 및 클릭
            submit_btn = await self.find_element_multiple_ways(submit_selectors, wait_for_clickable=True, timeout=8000)
            if submit_btn:
                await submit_btn.scroll_into_view_if_needed()
                await asyncio.sleep(0.2)
                await submit_btn.click()
                logger.info("2FA 제출 버튼 클릭 완료")
                
                # 제출 후 페이지 로드 대기 (대기 시간 단축)
                await asyncio.sleep(0.3)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except:
                    logger.warning("domcontentloaded 대기 시간 초과 (계속 진행)")
                
                logger.info("2FA 검증 완료")
                
                # 세션 만료 확인
                try:
                    page_content = await self.page.content()
                    page_text = await self.page.locator("body").text_content()
                    
                    # 세션 만료 관련 텍스트 확인
                    if page_text and ("session" in page_text.lower() and "expired" in page_text.lower() or 
                                     "세션" in page_text and "만료" in page_text or
                                     "timeout" in page_text.lower()):
                        logger.warning("세션 만료 감지됨. 추가 버튼 클릭을 건너뜁니다.")
                        return True
                except:
                    pass
                
                # 2FA 제출 완료 후 submit 버튼 클릭 (조건부 - 세션 만료가 아닐 때만)
                try:
                    # URL 변경 확인 (페이지가 전환되었는지)
                    current_url = self.page.url
                    
                    # submit 버튼이 있고, 세션 만료 화면이 아닐 때만 클릭
                    submit_button = self.page.locator("button[type='submit']")
                    count = await submit_button.count()
                    
                    if count > 0:
                        # 세션 만료 화면이 아닌지 다시 확인
                        page_text = await self.page.locator("body").text_content()
                        if page_text and not ("session" in page_text.lower() and "expired" in page_text.lower()):
                            logger.info("2FA 제출 후 submit 버튼 클릭 중...")
                            await submit_button.first.scroll_into_view_if_needed()
                            await asyncio.sleep(0.3)
                            await submit_button.first.click()
                            logger.info("2FA 제출 후 submit 버튼 클릭 완료")
                            
                            # 버튼 클릭 후 페이지 로드 대기 (대기 시간 단축)
                            await asyncio.sleep(0.3)
                            try:
                                await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                            except:
                                pass
                        else:
                            logger.info("세션 만료 화면 감지. submit 버튼 클릭을 건너뜁니다.")
                except Exception as e:
                    logger.debug(f"2FA 제출 후 submit 버튼 클릭 실패 (무시): {str(e)}")
                
                return True
            else:
                logger.warning("2FA 제출 버튼을 찾을 수 없습니다. (Enter 키로 시도)")
                # Enter 키로 제출 시도
                await code_field.press("Enter")
                await asyncio.sleep(0.3)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except:
                    pass
                return True
                
        except Exception as e:
            logger.error(f"2FA 처리 중 오류 발생: {str(e)}")
            await self.save_debug_info("2fa_error")
            raise
    
    async def click_continue_button(self, max_attempts: int = 5):
        """
        로그인 후 Continue 버튼을 클릭하는 함수 (반복적으로 나타나는 경우)
        
        Args:
            max_attempts: 최대 클릭 시도 횟수
        """
        for attempt in range(max_attempts):
            try:
                # _eventId_continue 버튼 찾기
                continue_btn = self.page.locator("input[name='_eventId_continue'][type='submit']")
                count = await continue_btn.count()
                
                if count > 0:
                    logger.info(f"Continue 버튼 발견 (시도 {attempt + 1}/{max_attempts})")
                    await continue_btn.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await continue_btn.first.click()
                    logger.info("Continue 버튼 클릭 완료")
                    
                    # 페이지 로드 대기
                    await asyncio.sleep(0.2)
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass
                    
                    # 다음 페이지에서도 같은 버튼이 있는지 확인하기 위해 잠시 대기
                    await asyncio.sleep(0.1)
                else:
                    logger.info(f"Continue 버튼을 찾을 수 없음 (시도 {attempt + 1}/{max_attempts})")
                    break
            except Exception as e:
                logger.debug(f"Continue 버튼 클릭 시도 중 오류 (시도 {attempt + 1}): {str(e)}")
                break
    
    async def handle_question_answer(self, answer: Optional[str] = None, 
                                     progress_callback: Optional[Callable[[str, Optional[Dict]], None]] = None):
        """
        질문-답변 처리 함수
        
        Args:
            answer: 사용자로부터 받은 답변 (None이면 질문만 감지하고 반환)
        
        Returns:
            dict: {
                "has_question": bool,  # 질문이 있는지 여부
                "question": str,  # 질문 텍스트 (질문이 있을 때만)
                "completed": bool  # 답변 처리 완료 여부
            }
        """
        try:
            # Identity validation 페이지에서 Question-label 찾기
            question_text = ""
            
            # 방법 1: Question-label 클래스 찾기 (우선)
            question_label = self.page.locator(".Question-label, [class*='Question-label'], [class*='question-label']")
            question_count = await question_label.count()
            
            if question_count > 0:
                question_text = await question_label.first.text_content()
                question_text = question_text.strip() if question_text else ""
                logger.info(f"Question-label에서 질문 발견: {question_text}")
            
            # 방법 2: answer 필드가 있고 Question-label이 없으면 answer 필드 근처의 label 찾기
            if not question_text:
                answer_field = self.page.locator("input[name='answer'][type='text']")
                answer_count = await answer_field.count()
                
                if answer_count > 0:
                    # answer 필드 근처의 label 찾기
                    nearby_labels = answer_field.locator("xpath=./ancestor::*//label | ./preceding-sibling::label | ./parent::*/label")
                    label_count = await nearby_labels.count()
                    
                    if label_count > 0:
                        # 첫 번째 label을 질문으로 사용
                        question_text = await nearby_labels.first.text_content()
                        question_text = question_text.strip() if question_text else ""
                        logger.info(f"answer 필드 근처에서 질문 발견: {question_text}")
            
            # 질문이 있으면 처리
            if question_text:
                # 답변이 제공되지 않았으면 질문만 반환
                if not answer:
                    return {
                        "has_question": True,
                        "question": question_text,
                        "completed": False
                    }
                
                # 답변이 제공되었으면 answer 필드에 입력하고 _continue 클릭
                answer_field = self.page.locator("input[name='answer'][type='text']")
                answer_count = await answer_field.count()
                
                if answer_count == 0:
                    logger.warning("answer 필드를 찾을 수 없습니다.")
                    return {
                        "has_question": True,
                        "question": question_text,
                        "completed": False
                    }
                
                logger.info(f"answer 필드에 답변 입력 중: {answer}")
                await answer_field.first.scroll_into_view_if_needed()
                await asyncio.sleep(0.3)
                await answer_field.first.clear()
                await answer_field.first.fill(answer)
                logger.info("답변 입력 완료")
                
                # 진행 상황 콜백 호출 (답변 입력 후)
                if progress_callback:
                    try:
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback("답변 입력 완료", None)
                        else:
                            progress_callback("답변 입력 완료", None)
                    except:
                        pass
                
                # _continue 버튼 클릭
                continue_btn = self.page.locator("input[name='_continue'][type='submit']")
                count = await continue_btn.count()
                
                if count > 0:
                    logger.info("_continue 버튼 클릭 중...")
                    await continue_btn.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await continue_btn.first.click()
                    logger.info("_continue 버튼 클릭 완료")
                    
                    # 페이지 로드 대기
                    await asyncio.sleep(0.3)
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except:
                        pass
                    
                    return {
                        "has_question": True,
                        "question": question_text,
                        "completed": True
                    }
                else:
                    logger.warning("_continue 버튼을 찾을 수 없습니다.")
                    return {
                        "has_question": True,
                        "question": question_text,
                        "completed": False
                    }
            else:
                # 질문이 없음
                logger.debug("질문을 찾을 수 없습니다.")
                return {
                    "has_question": False,
                    "question": "",
                    "completed": True
                }
                
        except Exception as e:
            logger.error(f"질문-답변 처리 중 오류 발생: {str(e)}")
            await self.save_debug_info("question_answer_error")
            return {
                "has_question": False,
                "question": "",
                "completed": False
            }
    
    async def delete_existing_application_if_needed(self):
        """
        기존 애플리케이션이 있으면 삭제하는 함수
        
        1. 현재 URL이 applicationChecklist 페이지인지 확인
        2. 맞다면 home 페이지로 이동
        3. Express Entry 애플리케이션의 _delete 버튼 클릭
        4. 삭제 확인 페이지에서 _continue 클릭
        5. kitReferenceClaim 페이지로 이동
        6. Express Entry (EE) 버튼 클릭
        """
        try:
            current_url = self.page.url
            logger.info(f"현재 URL 확인: {current_url}")
            
            # applicationChecklist 페이지인지 확인
            if "applicationChecklist" in current_url:
                logger.info("applicationChecklist 페이지 감지. 기존 애플리케이션 삭제 시작...")
                
                # home 페이지로 이동
                home_url = "https://onlineservices-servicesenligne.cic.gc.ca/mycic/home?&lang=en"
                logger.info(f"home 페이지로 이동: {home_url}")
                await self.page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(0.3)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except:
                    pass
                
                # Express Entry 텍스트가 있는 row에서 _delete 버튼 찾기
                logger.info("Express Entry 애플리케이션의 _delete 버튼 찾기 중...")
                express_entry_text = self.page.locator("text=/Express Entry/i")
                express_entry_count = await express_entry_text.count()
                
                if express_entry_count > 0:
                    logger.info("Express Entry 애플리케이션 발견")
                    delete_btn = None
                    
                    # Express Entry 텍스트가 있는 row에서 _delete 버튼 찾기
                    for i in range(express_entry_count):
                        ee_element = express_entry_text.nth(i)
                        
                        # 같은 tr(row) 내에서 _delete 찾기
                        tr_delete = ee_element.locator("xpath=./ancestor::tr//input[@name='_delete' and @type='submit']")
                        tr_count = await tr_delete.count()
                        
                        if tr_count > 0:
                            delete_btn = tr_delete.first
                            logger.info(f"Express Entry 애플리케이션의 _delete 버튼 발견 (같은 tr, 인덱스 {i})")
                            break
                        
                        # 같은 div row 내에서 _delete 찾기
                        div_row = ee_element.locator("xpath=./ancestor::div[contains(@class, 'row') or contains(@class, 'Row')]//input[@name='_delete' and @type='submit']")
                        div_count = await div_row.count()
                        
                        if div_count > 0:
                            delete_btn = div_row.first
                            logger.info(f"Express Entry 애플리케이션의 _delete 버튼 발견 (같은 div row, 인덱스 {i})")
                            break
                        
                        # 같은 form 내에서 _delete 찾기
                        form_delete = ee_element.locator("xpath=./ancestor::form//input[@name='_delete' and @type='submit']")
                        form_count = await form_delete.count()
                        
                        if form_count > 0:
                            # Express Entry와 가장 가까운 _delete 찾기
                            ee_box = await ee_element.bounding_box()
                            
                            if ee_box:
                                closest_btn = None
                                min_distance = float('inf')
                                
                                all_delete_in_form = self.page.locator("xpath=//form//input[@name='_delete' and @type='submit']")
                                all_delete_count = await all_delete_in_form.count()
                                
                                for j in range(all_delete_count):
                                    btn = all_delete_in_form.nth(j)
                                    btn_box = await btn.bounding_box()
                                    
                                    if btn_box:
                                        y_diff = abs(ee_box['y'] - btn_box['y'])
                                        
                                        if y_diff < 50:  # 같은 row로 간주
                                            distance = abs(ee_box['x'] - btn_box['x'])
                                            if distance < min_distance:
                                                min_distance = distance
                                                closest_btn = btn
                                
                                if closest_btn:
                                    delete_btn = closest_btn
                                    logger.info(f"Express Entry 애플리케이션의 _delete 버튼 발견 (가장 가까운 버튼, 인덱스 {i})")
                                    break
                    
                    if delete_btn:
                        logger.info("Express Entry 애플리케이션의 _delete 버튼 클릭 중...")
                        await delete_btn.scroll_into_view_if_needed()
                        await asyncio.sleep(0.2)
                        await delete_btn.click()
                        logger.info("_delete 버튼 클릭 완료")
                        
                        # 페이지 로드 대기
                        await asyncio.sleep(0.3)
                        try:
                            await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                        except:
                            pass
                        
                        # 삭제 확인 페이지에서 _continue 버튼 찾기 및 클릭
                        logger.info("삭제 확인 페이지에서 _continue 버튼 찾기 중...")
                        continue_btn = self.page.locator("input[name='_continue'][type='submit']")
                        continue_count = await continue_btn.count()
                        
                        if continue_count > 0:
                            logger.info("_continue 버튼 발견. 클릭 중...")
                            await continue_btn.first.scroll_into_view_if_needed()
                            await asyncio.sleep(0.2)
                            await continue_btn.first.click()
                            logger.info("_continue 버튼 클릭 완료 (삭제 최종 완료)")
                            
                            # 페이지 로드 대기
                            await asyncio.sleep(0.3)
                            try:
                                await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                            except:
                                pass
                        else:
                            logger.warning("_continue 버튼을 찾을 수 없습니다.")
                    else:
                        logger.warning("Express Entry 애플리케이션의 _delete 버튼을 찾을 수 없습니다.")
                else:
                    logger.info("Express Entry 애플리케이션이 없습니다. 삭제할 애플리케이션이 없습니다.")
                
                # kitReferenceClaim 페이지로 이동
                kit_url = "https://onlineservices-servicesenligne.cic.gc.ca/mycic/home/kitReferenceClaim?"
                logger.info(f"kitReferenceClaim 페이지로 이동: {kit_url}")
                await self.page.goto(kit_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(0.3)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except:
                    pass
                
                # Express Entry (EE) 버튼 찾기 및 클릭
                logger.info("Express Entry (EE) 버튼 찾기 중...")
                ee_button = self.page.locator("input[type='submit'][value='Express Entry (EE)']")
                count = await ee_button.count()
                
                if count > 0:
                    logger.info("Express Entry (EE) 버튼 발견. 클릭 중...")
                    await ee_button.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await ee_button.first.click()
                    logger.info("Express Entry (EE) 버튼 클릭 완료")
                    
                    # 페이지 로드 대기
                    await asyncio.sleep(0.3)
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except:
                        pass
                    
                    logger.info("기존 애플리케이션 삭제 및 새 EE 지원 페이지 이동 완료")
                    return True
                else:
                    logger.warning("Express Entry (EE) 버튼을 찾을 수 없습니다.")
                    return False
            else:
                logger.info("applicationChecklist 페이지가 아닙니다. 삭제 과정을 건너뜁니다.")
                return False
                
        except Exception as e:
            logger.error(f"기존 애플리케이션 삭제 중 오류: {str(e)}")
            await self.save_debug_info("delete_existing_app_error")
            raise
    
    async def navigate_to_ee_application(self):
        """
        EE 지원 페이지로 이동하는 함수
        1. continue application에 Express Entry가 있으면 해당 애플리케이션의 _continue 클릭
        2. 없으면 kitReferenceClaim 페이지로 이동해서 Express Entry (EE) 버튼 클릭
        """
        try:
            # 현재 페이지에서 "continue application" 영역 확인
            logger.info("continue application 영역 확인 중...")
            await asyncio.sleep(0.1)
            
            # Express Entry 텍스트가 있는지 확인
            express_entry_text = self.page.locator("text=/Express Entry/i")
            express_entry_count = await express_entry_text.count()
            
            if express_entry_count > 0:
                # Express Entry가 있으면 해당 애플리케이션의 _continue 버튼 찾기
                logger.info("Express Entry 애플리케이션 발견")
                
                # 같은 row에 있는 _continue 버튼 찾기
                continue_btn = None
                
                # Express Entry 텍스트가 있는 row에서 _continue 버튼 찾기
                for i in range(express_entry_count):
                    ee_element = express_entry_text.nth(i)
                    
                    # 방법 1: 같은 tr(row) 내에서 _continue 찾기 (table 구조)
                    tr_continue = ee_element.locator("xpath=./ancestor::tr//input[@name='_continue' and @type='submit']")
                    tr_count = await tr_continue.count()
                    
                    if tr_count > 0:
                        continue_btn = tr_continue.first
                        logger.info(f"Express Entry 애플리케이션의 _continue 버튼 발견 (같은 tr, 인덱스 {i})")
                        break
                    
                    # 방법 2: 같은 div row 내에서 _continue 찾기 (div 구조)
                    div_row = ee_element.locator("xpath=./ancestor::div[contains(@class, 'row') or contains(@class, 'Row')]//input[@name='_continue' and @type='submit']")
                    div_count = await div_row.count()
                    
                    if div_count > 0:
                        continue_btn = div_row.first
                        logger.info(f"Express Entry 애플리케이션의 _continue 버튼 발견 (같은 div row, 인덱스 {i})")
                        break
                    
                    # 방법 3: 가장 가까운 부모 요소에서 _continue 찾기 (일반적인 구조)
                    # Express Entry 텍스트의 부모 요소들을 순회하면서 같은 레벨의 _continue 찾기
                    parent = ee_element.locator("xpath=./parent::*")
                    parent_count = await parent.count()
                    
                    if parent_count > 0:
                        # 부모 요소에서 _continue 찾기
                        parent_continue = parent.locator("xpath=./input[@name='_continue' and @type='submit'] | ./descendant::input[@name='_continue' and @type='submit']")
                        parent_continue_count = await parent_continue.count()
                        
                        if parent_continue_count > 0:
                            continue_btn = parent_continue.first
                            logger.info(f"Express Entry 애플리케이션의 _continue 버튼 발견 (부모 요소, 인덱스 {i})")
                            break
                    
                    # 방법 4: 같은 form 내에서 _continue 찾기
                    form_continue = ee_element.locator("xpath=./ancestor::form//input[@name='_continue' and @type='submit']")
                    form_count = await form_continue.count()
                    
                    if form_count > 0:
                        # Express Entry와 가장 가까운 _continue 찾기
                        # 모든 _continue 버튼을 확인하고 Express Entry와 가장 가까운 것 선택
                        all_continue_in_form = self.page.locator("xpath=//form//input[@name='_continue' and @type='submit']")
                        all_continue_count = await all_continue_in_form.count()
                        
                        if all_continue_count > 0:
                            # Express Entry 요소의 위치 확인
                            ee_box = await ee_element.bounding_box()
                            
                            if ee_box:
                                closest_btn = None
                                min_distance = float('inf')
                                
                                for j in range(all_continue_count):
                                    btn = all_continue_in_form.nth(j)
                                    btn_box = await btn.bounding_box()
                                    
                                    if btn_box:
                                        # 수직 거리 계산 (같은 row면 y 좌표가 비슷해야 함)
                                        y_diff = abs(ee_box['y'] - btn_box['y'])
                                        
                                        if y_diff < 50:  # 같은 row로 간주 (50px 이내)
                                            distance = abs(ee_box['x'] - btn_box['x'])
                                            if distance < min_distance:
                                                min_distance = distance
                                                closest_btn = btn
                                
                                if closest_btn:
                                    continue_btn = closest_btn
                                    logger.info(f"Express Entry 애플리케이션의 _continue 버튼 발견 (가장 가까운 버튼, 인덱스 {i})")
                                    break
                
                if continue_btn:
                    logger.info("Express Entry 애플리케이션의 _continue 버튼 클릭 중...")
                    await continue_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await continue_btn.click()
                    logger.info("_continue 버튼 클릭 완료")
                    
                    # 페이지 로드 대기
                    await asyncio.sleep(0.3)
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except:
                        pass
                    
                    # applicationChecklist 페이지인지 확인하고 삭제 처리
                    current_url = self.page.url
                    logger.info(f"_continue 클릭 후 현재 URL: {current_url}")
                    if "applicationChecklist" in current_url:
                        logger.info("applicationChecklist 페이지 감지. 기존 애플리케이션 삭제 시작...")
                        await self.delete_existing_application_if_needed()
                        return  # 삭제 후 kitReferenceClaim에서 EE 버튼 클릭하여 이동 완료
                    
                    return True
                else:
                    logger.warning("Express Entry는 있지만 _continue 버튼을 찾을 수 없습니다.")
            else:
                logger.info("continue application에 Express Entry가 없습니다.")
            
            # Express Entry가 없으면 kitReferenceClaim 페이지로 이동
            logger.info("kitReferenceClaim 페이지로 이동 중...")
            kit_url = "https://onlineservices-servicesenligne.cic.gc.ca/mycic/home/kitReferenceClaim?"
            await self.page.goto(kit_url, wait_until="domcontentloaded", timeout=60000)
            
            # 페이지 로드 대기
            await asyncio.sleep(0.3)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except:
                pass
            
            # Express Entry (EE) 버튼 찾기 및 클릭
            logger.info("Express Entry (EE) 버튼 찾기 중...")
            ee_button = self.page.locator("input[type='submit'][value='Express Entry (EE)']")
            count = await ee_button.count()
            
            if count > 0:
                logger.info("Express Entry (EE) 버튼 발견. 클릭 중...")
                await ee_button.first.scroll_into_view_if_needed()
                await asyncio.sleep(0.2)
                await ee_button.first.click()
                logger.info("Express Entry (EE) 버튼 클릭 완료")
                
                # 페이지 로드 대기
                await asyncio.sleep(0.3)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except:
                    pass
                
                return True
            else:
                logger.warning("Express Entry (EE) 버튼을 찾을 수 없습니다.")
                return False
                
        except Exception as e:
            logger.error(f"EE 지원 페이지로 이동 중 오류: {str(e)}")
            await self.save_debug_info("navigate_to_ee_error")
            raise
    
    async def find_element_safe(self, selector_type: str, value: str, timeout: int = 10000):
        """
        안전하게 요소를 찾는 함수
        
        Args:
            selector_type: 찾을 방법 ("name", "id", "css", "xpath")
            value: 찾을 값
            timeout: 대기 시간 (밀리초)
        
        Returns:
            찾은 요소 Locator 또는 None
        """
        try:
            if selector_type == "name":
                locator = self.page.locator(f"input[name='{value}'], select[name='{value}']")
            elif selector_type == "id":
                locator = self.page.locator(f"#{value}")
            elif selector_type == "css":
                locator = self.page.locator(value)
            elif selector_type == "xpath":
                locator = self.page.locator(f"xpath={value}")
            else:
                return None
            
            await locator.wait_for(state="attached", timeout=timeout)
            if await locator.count() > 0:
                return locator
            return None
        except Exception as e:
            logger.debug(f"요소를 찾을 수 없습니다 ({selector_type}={value}): {str(e)}")
            return None
    
    async def fill_form_fields(self, form_data: Dict[str, Any], progress_callback: Optional[Callable] = None):
        """
        JSON 형식의 폼 데이터를 받아서 필드에 입력하는 함수
        
        Args:
            form_data: 딕셔너리 형태의 폼 데이터
            progress_callback: 진행 상황을 전달할 콜백 함수 (current, total, field_name) => None
        """
        try:
            logger.info("\n=== 폼 필드 입력 시작 ===")
            
            total_fields = len(form_data)
            current_field = 0
            
            for field_name, field_info in form_data.items():
                current_field += 1
                
                # 진행 상황 콜백 호출
                if progress_callback:
                    try:
                        progress_callback(current_field, total_fields, field_name)
                    except:
                        pass
                
                tag = field_info.get("tag", "input")
                field_type = field_info.get("type", "text")
                value = field_info.get("value") or field_info.get("Value", "")
                
                logger.info(f"\n필드 처리: {field_name}")
                logger.info(f"  Tag: {tag}, Type: {field_type}, Value: {value}")
                
                # name 속성으로 요소 찾기
                element = await self.find_element_safe("name", field_name, timeout=10000)
                
                if not element:
                    logger.warning(f"  ⚠️ 필드를 찾을 수 없습니다: {field_name}")
                    continue
                
                # 요소가 보이도록 스크롤
                try:
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(0.1)  # 0.5초 → 0.1초
                except:
                    pass
                
                # tag와 type에 따라 처리
                if tag == "input":
                    if field_type == "text":
                        try:
                            await element.clear()
                            await asyncio.sleep(0.05)  # 0.2초 → 0.05초
                            await element.fill(value)
                            await asyncio.sleep(0.1)  # 0.3초 → 0.1초
                            
                            # 입력 확인
                            final_value = await element.input_value()
                            if final_value == value or (final_value and value in final_value):
                                logger.info(f"  ✓ 텍스트 입력 완료: {value}")
                            else:
                                logger.warning(f"  ⚠️ 입력 확인 실패. 현재 값: {final_value}, 기대 값: {value}")
                        except Exception as e:
                            logger.warning(f"  ⚠️ 텍스트 입력 중 오류: {str(e)}")
                    elif field_type == "radio":
                        # 라디오 버튼의 경우
                        try:
                            value_lower = value.lower().strip()
                            
                            # 모든 라디오 버튼 가져오기
                            radios_locator = self.page.locator(f"input[name='{field_name}'][type='radio']")
                            radios_count = await radios_locator.count()
                            logger.info(f"  📻 라디오 버튼 개수: {radios_count}")
                            
                            # 여러 방법으로 매칭 시도
                            radio_found = None
                            for i in range(radios_count):
                                r = radios_locator.nth(i)
                                r_id = ((await r.get_attribute("id")) or "").lower().strip()
                                r_value = ((await r.get_attribute("value")) or "").strip()
                                
                                if value_lower == r_id or value == r_value or value_lower == r_value.lower():
                                    radio_found = r
                                    break
                                
                                # label 텍스트로 찾기
                                try:
                                    r_id_for_label = await r.get_attribute("id")
                                    if r_id_for_label:
                                        label = self.page.locator(f"label[for='{r_id_for_label}']")
                                        if await label.count() > 0:
                                            label_text = ((await label.text_content()) or "").strip()
                                            if value == label_text or value_lower == label_text.lower():
                                                radio_found = r
                                                break
                                except:
                                    pass
                            
                            if radio_found:
                                if not await radio_found.is_checked():
                                    await radio_found.check()
                                    await asyncio.sleep(0.1)  # 0.5초 → 0.1초
                                    logger.info(f"  ✓ 라디오 버튼 선택 완료: {value}")
                                else:
                                    logger.info(f"  ✓ 라디오 버튼 이미 선택됨: {value}")
                            else:
                                logger.warning(f"  ⚠️ 라디오 버튼을 찾을 수 없습니다: {field_name}={value}")
                        except Exception as e:
                            logger.warning(f"  ⚠️ 라디오 버튼 선택 실패: {str(e)}")
                    else:
                        await element.clear()
                        await element.fill(value)
                        logger.info(f"  ✓ 입력 완료: {value}")
                
                elif tag == "select" or tag == "selection":
                    try:
                        # 셀렉트 박스 처리
                        options_locator = element.locator("option")
                        options_count = await options_locator.count()
                        logger.info(f"  📋 셀렉트 박스 옵션 개수: {options_count}")
                        
                        # 옵션 검색 (정확한 매칭 우선)
                        target_value = None
                        matched_option_index = None
                        
                        # 1단계: 정확한 매칭 (대소문자 구분)
                        for i in range(options_count):
                            opt = options_locator.nth(i)
                            option_text = ((await opt.text_content()) or "").strip()
                            option_value = ((await opt.get_attribute("value")) or "").strip()
                            
                            if value == option_value or value == option_text:
                                target_value = option_value if option_value else option_text
                                matched_option_index = i
                                logger.info(f"  정확한 매칭 발견 (인덱스 {i}): value={option_value}, text={option_text}")
                                break
                        
                        # 2단계: 정확한 매칭 (대소문자 무시)
                        if not target_value:
                            for i in range(options_count):
                                opt = options_locator.nth(i)
                                option_text = ((await opt.text_content()) or "").strip()
                                option_value = ((await opt.get_attribute("value")) or "").strip()
                                
                                if value.lower() == option_value.lower() or value.lower() == option_text.lower():
                                    target_value = option_value if option_value else option_text
                                    matched_option_index = i
                                    logger.info(f"  대소문자 무시 정확한 매칭 발견 (인덱스 {i}): value={option_value}, text={option_text}")
                                    break
                        
                        # 3단계: 부분 일치 (단어 단위로만, 숫자는 정확히 일치해야 함)
                        if not target_value:
                            # 숫자만 있는 경우 정확한 매칭만 허용
                            is_numeric = value.strip().isdigit()
                            
                            if not is_numeric:
                                # 숫자가 아닌 경우에만 부분 일치 시도
                                for i in range(options_count):
                                    opt = options_locator.nth(i)
                                    option_text = ((await opt.text_content()) or "").strip()
                                    option_value = ((await opt.get_attribute("value")) or "").strip()
                                    
                                    # 단어 경계를 고려한 부분 일치 (공백이나 구분자로 분리된 단어)
                                    if value.lower() in option_text.lower() or value.lower() in option_value.lower():
                                        # 단어 단위로 확인 (부분 문자열이 아닌 단어로)
                                        option_words = option_text.lower().split()
                                        value_words = value.lower().split()
                                        
                                        if any(vw in option_words for vw in value_words) or value.lower() == option_text.lower() or value.lower() == option_value.lower():
                                            target_value = option_value if option_value else option_text
                                            matched_option_index = i
                                            logger.info(f"  부분 일치 발견 (인덱스 {i}): value={option_value}, text={option_text}")
                                            break
                        
                        if target_value:
                            # select_option에 인덱스나 값을 전달
                            try:
                                # value 속성이 있으면 value로, 없으면 텍스트로 선택
                                if matched_option_index is not None:
                                    # 인덱스로 선택 시도
                                    await element.select_option(index=matched_option_index)
                                else:
                                    # 값으로 선택
                                    await element.select_option(target_value)
                                await asyncio.sleep(0.2)
                                
                                # 선택 확인
                                selected_value = await element.input_value()
                                logger.info(f"  ✓ 셀렉트 박스 선택 완료: {target_value} (선택된 값: {selected_value})")
                            except Exception as select_error:
                                logger.warning(f"  select_option 실패, 대체 방법 시도: {str(select_error)}")
                                # 대체 방법: 직접 클릭
                                try:
                                    opt = options_locator.nth(matched_option_index) if matched_option_index is not None else None
                                    if opt:
                                        await opt.click()
                                        await asyncio.sleep(0.2)
                                        logger.info(f"  ✓ 셀렉트 박스 선택 완료 (클릭 방식): {target_value}")
                                except:
                                    logger.warning(f"  대체 방법도 실패")
                        else:
                            logger.warning(f"  ⚠️ 셀렉트 박스에서 값을 찾을 수 없습니다: {value}")
                            # 디버깅: 모든 옵션 출력
                            logger.info(f"  사용 가능한 옵션:")
                            for i in range(min(options_count, 10)):  # 최대 10개만 출력
                                opt = options_locator.nth(i)
                                option_text = ((await opt.text_content()) or "").strip()
                                option_value = ((await opt.get_attribute("value")) or "").strip()
                                logger.info(f"    [{i}] value='{option_value}', text='{option_text}'")
                    except Exception as e:
                        logger.warning(f"  ⚠️ 셀렉트 박스 선택 실패: {str(e)}")
                
                await asyncio.sleep(0.1)  # 각 필드 입력 사이 대기 (0.5초 → 0.1초)
            
            logger.info("\n=== 폼 필드 입력 완료 ===\n")
            
        except Exception as e:
            logger.error(f"폼 입력 중 오류 발생: {str(e)}")
            await self.save_debug_info("form_fill_error")
            raise
    
    async def click_save_button(self, button_selectors: Optional[List[Tuple[str, str]]] = None):
        """
        Save 버튼을 찾아서 클릭하는 함수
        
        Args:
            button_selectors: 버튼을 찾을 선택자 리스트 (기본값: None)
        """
        try:
            if button_selectors is None:
                button_selectors = [
                    ("xpath", "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save')]"),
                    ("xpath", "//button[contains(text(), 'Save') or contains(text(), '저장')]"),
                    ("css", "button[type='submit']"),
                    ("name", "save"),
                    ("id", "save"),
                    ("css", "button.btn-primary"),
                ]
            
            save_btn = await self.find_element_multiple_ways(button_selectors, wait_for_clickable=True, timeout=10000)
            
            if not save_btn:
                logger.warning("Save 버튼을 찾을 수 없습니다. 모든 버튼 검색 중...")
                try:
                    all_submit_buttons_locator = self.page.locator("button[type='submit']")
                    buttons_count = await all_submit_buttons_locator.count()
                    logger.info(f"  발견된 submit 버튼 개수: {buttons_count}")
                    for i in range(buttons_count):
                        btn = all_submit_buttons_locator.nth(i)
                        btn_text = ((await btn.text_content()) or "").strip()
                        logger.info(f"    버튼 {i+1}: text='{btn_text}'")
                        if "save" in btn_text.lower():
                            save_btn = btn
                            logger.info(f"  ✓ 'Save' 텍스트를 포함한 버튼 발견: '{btn_text}'")
                            break
                except Exception as e:
                    logger.error(f"  버튼 검색 중 오류: {str(e)}")
            
            if not save_btn:
                logger.warning("Save 버튼을 찾을 수 없습니다.")
                await self.save_debug_info("save_button_not_found")
                return False
            
            # 버튼 정보 로깅
            btn_text = ((await save_btn.text_content()) or "").strip()
            btn_type = (await save_btn.get_attribute("type")) or ""
            logger.info(f"  찾은 Save 버튼: text='{btn_text}', type='{btn_type}'")
            
            # 현재 URL 저장
            current_url = self.page.url
            logger.info(f"  저장 전 URL: {current_url}")
            
            # 스크롤하여 버튼이 보이도록
            await save_btn.scroll_into_view_if_needed()
            await asyncio.sleep(0.2)
            
            # 클릭
            await save_btn.click()
            logger.info("  Save 버튼 클릭 완료")
            
            # 저장 후 대기 및 확인 (다음 화면이 나올 때까지 충분히 대기)
            logger.info("  저장 후 대기 중...")
            await asyncio.sleep(1.0)  # 저장 버튼 클릭 후 초기 대기
            
            # 페이지 전환 또는 로드 완료까지 대기
            max_wait_time = 15  # 최대 15초 대기
            waited = 0
            page_changed = False
            
            while waited < max_wait_time:
                try:
                    # URL 변경 확인
                    new_url = self.page.url
                    if new_url != current_url:
                        logger.info(f"  ✓ 페이지 전환 확인: {new_url}")
                        page_changed = True
                        break
                    
                    # 페이지 로드 상태 확인
                    try:
                        await self.page.wait_for_load_state("load", timeout=2000)
                        # load 상태가 완료되었으면 추가로 networkidle 확인 시도
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=3000)
                            logger.info("  ✓ 페이지 로드 완료 (networkidle)")
                            break
                        except:
                            # networkidle 실패해도 load는 완료되었으므로 계속 진행
                            logger.debug("  networkidle 대기 시간 초과 (계속 진행)")
                            break
                    except:
                        pass
                    
                    await asyncio.sleep(0.5)
                    waited += 0.5
                except Exception as e:
                    logger.debug(f"  대기 중 오류: {str(e)}")
                    break
            
            if not page_changed:
                # URL이 변경되지 않았어도 페이지가 로드되었는지 확인
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                    logger.info("  페이지 로드 완료 (URL 변경 없음)")
                except:
                    logger.warning("  페이지 로드 대기 시간 초과 (계속 진행)")
            
            # 최종 안정화 대기
            await asyncio.sleep(0.5)
            
            logger.info("  저장 프로세스 완료")
            return True
            
        except Exception as e:
            logger.error(f"Save 버튼 클릭 중 오류: {str(e)}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
            return False
    
    async def fill_form_sequential(self, form_items: List[Dict[str, Any]], progress_callback: Optional[Callable] = None):
        """
        JSON 배열을 순서대로 처리하여 폼을 채우는 함수
        
        Args:
            form_items: 딕셔너리 리스트 형태의 폼 데이터
            progress_callback: 진행 상황을 전달할 콜백 함수 (current, total, item) => None
        """
        try:
            logger.info("\n=== 순차적 폼 필드 입력 시작 ===")
            
            total_items = len(form_items)
            current_item = 0
            
            for item in form_items:
                current_item += 1
                
                # 진행 상황 콜백 호출
                if progress_callback:
                    try:
                        # async 콜백인 경우 await, 동기 콜백인 경우 그대로 호출
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback(current_item, total_items, item)
                        else:
                            progress_callback(current_item, total_items, item)
                    except:
                        pass
                
                tag = item.get("tag", "input")
                field_name = item.get("name", "")
                field_type = item.get("type", "text")
                value = item.get("value", "")
                
                logger.info(f"\n[항목 {current_item}/{total_items}] 처리 중...")
                logger.info(f"  Tag: {tag}, Name: {field_name}, Type: {field_type}, Value: {value}")
                
                # 페이지 로드 대기 (타임아웃 단축) - 첫 번째 항목만 대기
                if current_item == 1:
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass
                    await asyncio.sleep(0.2)  # 첫 번째 항목은 화면 안정화 대기
                else:
                    # 이후 항목들은 최소 대기만
                    await asyncio.sleep(0.05)  # 최소 대기 시간
                
                # 태그 타입에 따라 처리
                if tag == "select":
                    # 셀렉트 박스 처리
                    if not field_name:
                        logger.warning("  ⚠️ name이 없어 셀렉트 박스를 찾을 수 없습니다.")
                        continue
                    
                    element = await self.find_element_safe("name", field_name, timeout=10000)
                    if not element:
                        logger.warning(f"  ⚠️ 셀렉트 박스를 찾을 수 없습니다: {field_name}")
                        continue
                    
                    try:
                        await element.scroll_into_view_if_needed()
                        await asyncio.sleep(0.05)  # 최소 대기 시간
                        
                        # 옵션 검색 (정확한 매칭 우선)
                        options_locator = element.locator("option")
                        options_count = await options_locator.count()
                        target_value = None
                        matched_option_index = None
                        
                        # 1단계: 정확한 매칭 (대소문자 구분)
                        for i in range(options_count):
                            opt = options_locator.nth(i)
                            option_text = ((await opt.text_content()) or "").strip()
                            option_value = ((await opt.get_attribute("value")) or "").strip()
                            
                            if value == option_value or value == option_text:
                                target_value = option_value if option_value else option_text
                                matched_option_index = i
                                logger.info(f"  정확한 매칭 발견 (인덱스 {i}): value={option_value}, text={option_text}")
                                break
                        
                        # 2단계: 정확한 매칭 (대소문자 무시)
                        if not target_value:
                            for i in range(options_count):
                                opt = options_locator.nth(i)
                                option_text = ((await opt.text_content()) or "").strip()
                                option_value = ((await opt.get_attribute("value")) or "").strip()
                                
                                if value.lower() == option_value.lower() or value.lower() == option_text.lower():
                                    target_value = option_value if option_value else option_text
                                    matched_option_index = i
                                    logger.info(f"  대소문자 무시 정확한 매칭 발견 (인덱스 {i}): value={option_value}, text={option_text}")
                                    break
                        
                        # 3단계: 부분 일치 (숫자는 정확히 일치해야 함)
                        if not target_value:
                            # 숫자만 있는 경우 정확한 매칭만 허용
                            is_numeric = value.strip().isdigit()
                            
                            if not is_numeric:
                                # 숫자가 아닌 경우에만 부분 일치 시도
                                for i in range(options_count):
                                    opt = options_locator.nth(i)
                                    option_text = ((await opt.text_content()) or "").strip()
                                    option_value = ((await opt.get_attribute("value")) or "").strip()
                                    
                                    # 단어 경계를 고려한 부분 일치
                                    if value.lower() in option_text.lower() or value.lower() in option_value.lower():
                                        # 단어 단위로 확인
                                        option_words = option_text.lower().split()
                                        value_words = value.lower().split()
                                        
                                        if any(vw in option_words for vw in value_words) or value.lower() == option_text.lower() or value.lower() == option_value.lower():
                                            target_value = option_value if option_value else option_text
                                            matched_option_index = i
                                            logger.info(f"  부분 일치 발견 (인덱스 {i}): value={option_value}, text={option_text}")
                                            break
                        
                        if target_value:
                            try:
                                # value 속성이 있으면 value로, 없으면 인덱스로 선택
                                if matched_option_index is not None:
                                    await element.select_option(index=matched_option_index)
                                else:
                                    await element.select_option(target_value)
                                await asyncio.sleep(0.05)  # 최소 대기 시간
                                
                                # 선택 확인
                                selected_value = await element.input_value()
                                logger.info(f"  ✓ 셀렉트 박스 선택 완료: {target_value} (선택된 값: {selected_value})")
                            except Exception as select_error:
                                logger.warning(f"  select_option 실패, 대체 방법 시도: {str(select_error)}")
                                try:
                                    opt = options_locator.nth(matched_option_index) if matched_option_index is not None else None
                                    if opt:
                                        await opt.click()
                                        await asyncio.sleep(0.05)  # 최소 대기 시간
                                        logger.info(f"  ✓ 셀렉트 박스 선택 완료 (클릭 방식): {target_value}")
                                except:
                                    logger.warning(f"  대체 방법도 실패")
                        else:
                            logger.warning(f"  ⚠️ 옵션을 찾을 수 없습니다: {value}")
                            # 디버깅: 모든 옵션 출력
                            logger.info(f"  사용 가능한 옵션:")
                            for i in range(min(options_count, 10)):  # 최대 10개만 출력
                                opt = options_locator.nth(i)
                                option_text = ((await opt.text_content()) or "").strip()
                                option_value = ((await opt.get_attribute("value")) or "").strip()
                                logger.info(f"    [{i}] value='{option_value}', text='{option_text}'")
                    except Exception as e:
                        logger.warning(f"  ⚠️ 셀렉트 박스 선택 실패: {str(e)}")
                
                elif tag == "input":
                    if field_type == "submit":
                        # 제출 버튼 클릭
                        if not field_name:
                            submit_buttons_locator = self.page.locator("input[type='submit']")
                            if await submit_buttons_locator.count() > 0:
                                submit_btn = submit_buttons_locator.first
                            else:
                                logger.warning("  ⚠️ 제출 버튼을 찾을 수 없습니다.")
                                continue
                        else:
                            submit_btn = await self.find_element_safe("name", field_name, timeout=10000)
                            if not submit_btn:
                                logger.warning(f"  ⚠️ 제출 버튼을 찾을 수 없습니다: {field_name}")
                                continue
                        
                        try:
                            await submit_btn.scroll_into_view_if_needed()
                            await asyncio.sleep(0.1)  # 0.5초 → 0.1초
                            await submit_btn.click()
                            logger.info(f"  ✓ 제출 버튼 클릭 완료: {field_name}")
                            
                            # 페이지 전환 대기 (타임아웃 단축)
                            await asyncio.sleep(1.5)  # 3초 → 1.5초
                            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)  # networkidle → domcontentloaded, 30초 → 15초
                        except Exception as e:
                            logger.warning(f"  ⚠️ 제출 버튼 클릭 실패: {str(e)}")
                    
                    elif field_type == "text":
                        # 텍스트 입력
                        if not field_name:
                            logger.warning("  ⚠️ name이 없어 입력 필드를 찾을 수 없습니다.")
                            continue
                        
                        element = await self.find_element_safe("name", field_name, timeout=10000)
                        if not element:
                            logger.warning(f"  ⚠️ 입력 필드를 찾을 수 없습니다: {field_name}")
                            continue
                        
                        try:
                            await element.scroll_into_view_if_needed()
                            await asyncio.sleep(0.05)  # 최소 대기 시간
                            await element.clear()
                            await asyncio.sleep(0.02)  # 최소 대기 시간
                            await element.fill(value)
                            logger.info(f"  ✓ 텍스트 입력 완료: {value}")
                        except Exception as e:
                            logger.warning(f"  ⚠️ 텍스트 입력 실패: {str(e)}")
                
                elif tag == "a":
                    # 링크 클릭
                    try:
                        link = self.page.locator(f"a:has-text('{value}')").first
                        if await link.count() == 0:
                            link = self.page.locator("a").filter(has_text=value).first
                        
                        if await link.count() > 0:
                            await link.scroll_into_view_if_needed()
                            await asyncio.sleep(0.1)  # 0.5초 → 0.1초
                            await link.click()
                            logger.info(f"  ✓ 링크 클릭 완료: {value}")
                            
                            # 페이지 전환 대기 (타임아웃 단축)
                            await asyncio.sleep(1.5)  # 3초 → 1.5초
                            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)  # networkidle → domcontentloaded, 30초 → 15초
                        else:
                            logger.warning(f"  ⚠️ 링크를 찾을 수 없습니다: {value}")
                    except Exception as e:
                        logger.warning(f"  ⚠️ 링크 클릭 실패: {str(e)}")
                
                # 각 항목 처리 후 대기 (최소화)
                await asyncio.sleep(0.05)
            
            logger.info("\n=== 순차적 폼 필드 입력 완료 ===\n")
            
        except Exception as e:
            logger.error(f"순차적 폼 입력 중 오류 발생: {str(e)}")
            await self.save_debug_info("sequential_form_fill_error")
            raise
    
    async def close(self):
        """브라우저 종료"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("브라우저가 종료되었습니다.")
        except Exception as e:
            logger.error(f"브라우저 종료 중 오류: {str(e)}")
