"""브라우저 자동화 서비스"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 폼 데이터 정의
# PROFILE_FORM_DATA = {
#       "profileForm-correspondence" : {
#               "tag": "select",
#               "value": "English"
# 	},
#       "profileForm-familyName" : {
#               "tag": "input",
#               "type": "text",
#               "value": "Jeongwook"
#       },
#       "personalDetailsForm-givenName" : {
#               "tag": "input",
#               "type": "text",
#               "value": "Kim",
#       },
#       "personalDetailsForm-dob" : {
#               "tag": "input",
#               "type": "text",
#               "value": "1992/11/14"
#       },
#       "postOfficeBox" : {
#               "tag": "input",
#               "type": "text",
#               "value": "123"
#       },
#       "apartmentUnit" : {
#               "tag": "input",
#               "type": "text",
#               "value": "3611"
#       },
#       "streetNumber" : {
#               "tag": "input",
#               "type": "text",
#               "value": "4168"
#       },
#       "streetName" : {
#               "tag": "input",
#               "type": "text",
#               "value": "Lougheed Hwy"
#       },
#       "city" : {
#               "tag": "input",
#               "type": "text",
#               "value": "Burnaby"
#       },
#       "country" : {
#               "tag": "select",
#               "value": "Canada"
#       },
#       "province" : {
#               "tag": "select",
#               "value": "BC"
#       },
#       "postalCode" : {
#               "tag": "input",
#               "type": "text",
#               "value": "V5C 0N9"
#       },
#       "residentialSameAsMailingAddress" : {
#               "tag": "input",
#               "type": "radio",
#               "value": "Yes"
#       }
# }

PROFILE_FORM_DATA = {
      "profileForm-correspondence" : {
              "tag": "select",
              "value": "French"
	},
      "profileForm-familyName" : {
              "tag": "input",
              "type": "text",
              "value": "Diana"
      },
      "personalDetailsForm-givenName" : {
              "tag": "input",
              "type": "text",
              "value": "Shin",
      },
      "personalDetailsForm-dob" : {
              "tag": "input",
              "type": "text",
              "value": "1996/03/09"
      },
      "postOfficeBox" : {
              "tag": "input",
              "type": "text",
              "value": "1013"
      },
      "apartmentUnit" : {
              "tag": "input",
              "type": "text",
              "value": "1602"
      },
      "streetNumber" : {
              "tag": "input",
              "type": "text",
              "value": "80"
      },
      "streetName" : {
              "tag": "input",
              "type": "text",
              "value": "Pangyo Daejang Ro"
      },
      "city" : {
              "tag": "input",
              "type": "text",
              "value": "Seongnam"
      },
      "country" : {
              "tag": "select",
              "value": "Korea, South"
      },
      "district": {
              "tag": "input",
              "type": "text",
              "value": "Gyenggi-do"
      },
      "postalCode" : {
              "tag": "input",
              "type": "text",
              "value": "12345"
      },
      "residentialSameAsMailingAddress" : {
              "tag": "input",
              "type": "radio",
              "value": "Yes"
      }
}

class BrowserAutomation:
    def __init__(self):
        """브라우저 자동화 클래스 초기화"""
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        """Chrome 드라이버 설정"""
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        
        # 도커 환경 감지 (chromium이 시스템에 설치되어 있으면 도커 환경)
        is_docker = os.path.exists("/usr/bin/chromium")
        
        if is_docker:
            # 도커 환경: 헤드리스 모드 필수 (디스플레이가 없음)
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.binary_location = "/usr/bin/chromium"
            # chromium-driver 경로 확인
            chromedriver_path = "/usr/bin/chromedriver"
            if os.path.exists(chromedriver_path):
                service = Service(chromedriver_path)
            else:
                # chromedriver가 없으면 ChromeDriverManager 사용
                service = Service(ChromeDriverManager().install())
        else:
            # 로컬 환경: 헤드리스 모드 없음 (브라우저 보임)
            service = Service(ChromeDriverManager().install())
        
        # 자동화 감지 방지
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(
            service=service,
            options=options
        )
        # 자동화 감지 방지 스크립트 실행
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("브라우저가 성공적으로 시작되었습니다.")
    
    def save_debug_info(self, filename_prefix="debug"):
        """디버깅 정보 저장 (스크린샷 및 페이지 소스)"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{filename_prefix}_screenshot_{timestamp}.png"
            html_path = f"{filename_prefix}_page_source_{timestamp}.html"
            
            self.driver.save_screenshot(screenshot_path)
            logger.info(f"스크린샷 저장: {screenshot_path}")
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"페이지 소스 저장: {html_path}")
            
            return screenshot_path, html_path
        except Exception as e:
            logger.error(f"디버깅 정보 저장 실패: {str(e)}")
            return None, None
    
    def analyze_page_inputs(self):
        """페이지의 모든 input 요소를 분석하여 출력"""
        try:
            logger.info("\n=== 페이지 입력 필드 분석 ===")
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            logger.info(f"총 {len(inputs)}개의 input 요소를 찾았습니다.\n")
            
            for i, inp in enumerate(inputs, 1):
                try:
                    input_type = inp.get_attribute("type") or "text"
                    input_name = inp.get_attribute("name") or "없음"
                    input_id = inp.get_attribute("id") or "없음"
                    input_class = inp.get_attribute("class") or "없음"
                    input_placeholder = inp.get_attribute("placeholder") or "없음"
                    
                    logger.info(f"[Input {i}]")
                    logger.info(f"  Type: {input_type}")
                    logger.info(f"  Name: {input_name}")
                    logger.info(f"  ID: {input_id}")
                    logger.info(f"  Class: {input_class}")
                    logger.info(f"  Placeholder: {input_placeholder}")
                    logger.info("")
                except Exception as e:
                    logger.error(f"  Input {i} 분석 실패: {str(e)}")
            
            # 버튼도 분석
            logger.info("\n=== 페이지 버튼 분석 ===")
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            submit_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='submit']")
            logger.info(f"총 {len(buttons)}개의 button 요소와 {len(submit_inputs)}개의 submit input을 찾았습니다.\n")
            
            for i, btn in enumerate(buttons, 1):
                try:
                    btn_type = btn.get_attribute("type") or "button"
                    btn_id = btn.get_attribute("id") or "없음"
                    btn_class = btn.get_attribute("class") or "없음"
                    btn_text = btn.text or "없음"
                    
                    logger.info(f"[Button {i}]")
                    logger.info(f"  Type: {btn_type}")
                    logger.info(f"  ID: {btn_id}")
                    logger.info(f"  Class: {btn_class}")
                    logger.info(f"  Text: {btn_text}")
                    logger.info("")
                except Exception as e:
                    logger.error(f"  Button {i} 분석 실패: {str(e)}")
            
            logger.info("=" * 50 + "\n")
            
        except Exception as e:
            logger.error(f"페이지 분석 중 오류: {str(e)}")
    
    def find_element_multiple_ways(self, selectors, timeout=15, wait_for_clickable=False):
        """
        여러 방법으로 요소를 찾는 함수
        
        Args:
            selectors: [(By.NAME, "email"), (By.ID, "email"), ...] 형태의 리스트
            timeout: 대기 시간 (초)
            wait_for_clickable: 클릭 가능할 때까지 대기할지 여부
        
        Returns:
            찾은 요소 또는 None
        """
        wait = WebDriverWait(self.driver, timeout)
        
        for by, value in selectors:
            try:
                logger.info(f"요소 찾기 시도: {by}={value}")
                if wait_for_clickable:
                    element = wait.until(EC.element_to_be_clickable((by, value)))
                else:
                    element = wait.until(EC.presence_of_element_located((by, value)))
                logger.info(f"요소 찾기 성공: {by}={value}")
                return element
            except Exception as e:
                logger.debug(f"요소 찾기 실패 ({by}={value})")
                continue
        
        return None
    
    def login(self, url, email, password, 
              email_selectors=None, 
              password_selectors=None, 
              login_button_selectors=None):
        """
        로그인 자동화 함수
        
        Args:
            url: 로그인 페이지 URL
            email: 이메일 주소
            password: 비밀번호
            email_selectors: 이메일 필드를 찾을 선택자 리스트 [(By.NAME, "email"), ...]
            password_selectors: 비밀번호 필드를 찾을 선택자 리스트
            login_button_selectors: 로그인 버튼을 찾을 선택자 리스트
        """
        try:
            # 페이지 로드
            self.driver.get(url)
            logger.info(f"페이지 로드 중: {url}")
            
            # 페이지가 완전히 로드될 때까지 대기
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # JavaScript 로드 완료 대기
            WebDriverWait(self.driver, 20).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Angular 앱 로드 대기 (ng- 클래스가 있는 경우)
            try:
                WebDriverWait(self.driver, 15).until(
                    lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "[class*='ng-']")) > 0 or
                                  len(driver.find_elements(By.CSS_SELECTOR, "input.form-input__field")) > 0
                )
                logger.info("Angular 앱 로드 완료 감지")
            except:
                logger.warning("Angular 앱 로드 대기 시간 초과 (계속 진행)")
            
            time.sleep(2)  # 추가 대기 시간
            
            # 페이지 분석 (디버깅용) - 메인 프레임에서 먼저
            logger.info("페이지 구조 분석 중...")
            self.analyze_page_inputs()
            
            # iframe이 있는지 확인 (참고용)
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                if iframes:
                    logger.info(f"{len(iframes)}개의 iframe을 발견했습니다. (필요시 사용)")
            except Exception as e:
                pass
            
            # 기본 선택자 - name 속성만 사용
            if email_selectors is None:
                email_selectors = [
                    (By.NAME, "username"),
                ]
            
            if password_selectors is None:
                password_selectors = [
                    (By.NAME, "password"),
                ]
            
            if login_button_selectors is None:
                login_button_selectors = [
                    # 일반적인 로그인 버튼
                    (By.CSS_SELECTOR, 'button[type="submit"]'),
                    (By.CSS_SELECTOR, 'input[type="submit"]'),
                    (By.XPATH, "//button[@type='submit']"),
                    (By.XPATH, "//input[@type='submit']"),
                    # 텍스트 기반
                    (By.XPATH, "//button[contains(text(), 'Login') or contains(text(), '로그인') or contains(text(), 'Sign in') or contains(text(), 'Sign In')]"),
                    (By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]"),
                    # 클래스 기반
                    (By.CSS_SELECTOR, "button.btn-primary"),
                    (By.CSS_SELECTOR, "input.btn-primary"),
                    (By.CSS_SELECTOR, "button.btn-login"),
                    (By.CSS_SELECTOR, "button[class*='login' i]"),
                    (By.CSS_SELECTOR, "button[class*='submit' i]"),
                    # ID 기반
                    (By.ID, "login"),
                    (By.ID, "loginBtn"),
                    (By.ID, "submit"),
                    (By.ID, "signin"),
                    # 폼 내 첫 번째 submit 버튼
                    (By.XPATH, "//form//button[@type='submit'][1]"),
                    (By.XPATH, "//form//input[@type='submit'][1]"),
                ]
            
            # 이메일 입력 필드 찾기 및 입력 (메인 프레임에서 먼저 시도)
            email_field = self.find_element_multiple_ways(email_selectors)
            
            # 메인 프레임에서 찾지 못하면 iframe에서 시도
            if not email_field:
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            logger.info("iframe으로 전환하여 이메일 필드 찾기 시도...")
                            email_field = self.find_element_multiple_ways(email_selectors, timeout=5)
                            if email_field:
                                break
                            self.driver.switch_to.default_content()
                        except:
                            self.driver.switch_to.default_content()
                            continue
                except:
                    self.driver.switch_to.default_content()
            
            if not email_field:
                logger.error("이메일 필드를 찾을 수 없습니다. 디버깅 정보를 저장합니다.")
                self.save_debug_info("email_field_not_found")
                raise Exception("이메일 입력 필드를 찾을 수 없습니다.")
            
            email_field.clear()
            time.sleep(0.5)
            email_field.send_keys(email)
            logger.info(f"이메일 입력 완료: {email}")
            
            # 비밀번호 입력 필드 찾기 및 입력
            password_field = self.find_element_multiple_ways(password_selectors)
            
            # 메인 프레임에서 찾지 못하면 iframe에서 시도
            if not password_field:
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            logger.info("iframe으로 전환하여 비밀번호 필드 찾기 시도...")
                            password_field = self.find_element_multiple_ways(password_selectors, timeout=5)
                            if password_field:
                                break
                            self.driver.switch_to.default_content()
                        except:
                            self.driver.switch_to.default_content()
                            continue
                except:
                    self.driver.switch_to.default_content()
            
            if not password_field:
                logger.error("비밀번호 필드를 찾을 수 없습니다. 디버깅 정보를 저장합니다.")
                self.save_debug_info("password_field_not_found")
                raise Exception("비밀번호 입력 필드를 찾을 수 없습니다.")
            
            password_field.clear()
            time.sleep(0.5)
            password_field.send_keys(password)
            logger.info("비밀번호 입력 완료")
            
            # 로그인 버튼 찾기 및 클릭 (클릭 가능할 때까지 대기)
            login_btn = self.find_element_multiple_ways(login_button_selectors, wait_for_clickable=True)
            if not login_btn:
                logger.error("로그인 버튼을 찾을 수 없습니다. 디버깅 정보를 저장합니다.")
                self.save_debug_info("login_button_not_found")
                raise Exception("로그인 버튼을 찾을 수 없습니다.")
            
            # 스크롤하여 버튼이 보이도록
            self.driver.execute_script("arguments[0].scrollIntoView(true);", login_btn)
            time.sleep(1)
            
            # JavaScript로 클릭 시도 (일부 사이트에서 더 안정적)
            try:
                self.driver.execute_script("arguments[0].click();", login_btn)
                logger.info("로그인 버튼 클릭 완료 (JavaScript)")
            except:
                login_btn.click()
                logger.info("로그인 버튼 클릭 완료 (일반)")
            
            # 로그인 후 페이지 로드 대기
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"로그인 중 오류 발생: {str(e)}")
            self.save_debug_info("login_error")
            raise
    
    def find_element_safe(self, by, value, timeout=10):
        """
        안전하게 요소를 찾는 함수
        
        Args:
            by: 찾을 방법 (By.ID, By.NAME, By.CSS_SELECTOR 등)
            value: 찾을 값
            timeout: 대기 시간 (초)
        
        Returns:
            찾은 요소 또는 None
        """
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located((by, value)))
            return element
        except Exception as e:
            logger.debug(f"요소를 찾을 수 없습니다 ({by}={value}): {str(e)}")
            return None
    
    def click_element(self, by, value):
        """요소를 클릭하는 함수"""
        element = self.find_element_safe(by, value)
        if element:
            element.click()
            logger.info(f"요소 클릭 완료: {by}={value}")
            return True
        return False
    
    def input_text(self, by, value, text):
        """텍스트를 입력하는 함수"""
        element = self.find_element_safe(by, value)
        if element:
            element.clear()
            element.send_keys(text)
            logger.info(f"텍스트 입력 완료: {text}")
            return True
        return False
    
    def fill_form_fields(self, form_data, progress_callback=None):
        """
        JSON 형식의 폼 데이터를 받아서 필드에 입력하는 함수
        
        Args:
            form_data: 딕셔너리 형태의 폼 데이터
                예: {
                    "fieldName": {
                        "tag": "input",
                        "type": "text",
                        "value": "값"
                    }
                }
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
                element = self.find_element_safe(By.NAME, field_name, timeout=10)
                
                if not element:
                    logger.warning(f"  ⚠️ 필드를 찾을 수 없습니다: {field_name}")
                    continue
                
                # 요소가 보이도록 스크롤
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                    time.sleep(0.5)
                except:
                    pass
                
                # 요소가 활성화될 때까지 대기
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(element)
                    )
                except:
                    pass
                
                # tag와 type에 따라 처리
                if tag == "input":
                    if field_type == "text":
                        try:
                            # Angular 앱을 위한 강력한 입력 방법
                            # 1단계: 기존 값 제거
                            element.clear()
                            time.sleep(0.2)
                            
                            # 2단계: 포커스 및 선택
                            element.click()
                            time.sleep(0.2)
                            element.send_keys("")  # 포커스 확보
                            
                            # 3단계: JavaScript로 직접 값 설정 및 Angular 이벤트 트리거
                            self.driver.execute_script("""
                                var element = arguments[0];
                                var value = arguments[1];
                                
                                // 값 설정
                                element.value = value;
                                
                                // 모든 관련 이벤트 발생
                                var events = ['focus', 'keydown', 'keypress', 'input', 'keyup', 'change', 'blur'];
                                events.forEach(function(eventType) {
                                    var event = new Event(eventType, { bubbles: true, cancelable: true });
                                    element.dispatchEvent(event);
                                });
                                
                                // Angular ngModel 업데이트 (있는 경우)
                                if (element.ngModelController) {
                                    element.ngModelController.$setViewValue(value);
                                    element.ngModelController.$render();
                                }
                                
                                // Angular FormControl 업데이트 (있는 경우)
                                if (window.ng && element.getAttribute('ng-model')) {
                                    var scope = angular.element(element).scope();
                                    if (scope) {
                                        scope.$apply(function() {
                                            scope[element.getAttribute('ng-model')] = value;
                                        });
                                    }
                                }
                                
                                // Angular Reactive Forms 지원
                                if (element.form && element.name) {
                                    var formControl = element.form[element.name];
                                    if (formControl && formControl.setValue) {
                                        formControl.setValue(value);
                                    }
                                }
                            """, element, value)
                            
                            time.sleep(0.3)
                            
                            # 4단계: JavaScript 입력 확인
                            final_value = element.get_attribute("value")
                            
                            # JavaScript로 입력이 성공했는지 확인
                            if final_value == value or (final_value and value in final_value):
                                logger.info(f"  ✓ JavaScript 입력 성공: {value}")
                            else:
                                # JavaScript 입력 실패 시에만 Selenium send_keys 시도
                                logger.warning(f"  ⚠️ JavaScript 입력 실패, Selenium send_keys 시도...")
                                try:
                                    element.clear()
                                    element.click()
                                    time.sleep(0.2)
                                    element.send_keys(value)
                                    time.sleep(0.3)
                                    # send_keys 후 다시 확인
                                    final_value = element.get_attribute("value")
                                except Exception as e:
                                    logger.warning(f"  ⚠️ send_keys도 실패: {str(e)}")
                            
                            # 5단계: 최종 확인 및 재시도
                            final_value = element.get_attribute("value")
                            if final_value != value and value not in (final_value or ""):
                                logger.warning(f"  ⚠️ 입력 확인 실패, 강제 재설정...")
                                # 최종 강제 설정
                                self.driver.execute_script("""
                                    var element = arguments[0];
                                    var value = arguments[1];
                                    element.focus();
                                    element.value = '';
                                    element.value = value;
                                    element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                    element.dispatchEvent(new Event('blur', { bubbles: true, cancelable: true }));
                                """, element, value)
                                time.sleep(0.5)
                            
                            # 최종 확인
                            final_value = element.get_attribute("value")
                            if final_value == value or (final_value and value in final_value):
                                logger.info(f"  ✓ 텍스트 입력 완료: {value}")
                            else:
                                logger.warning(f"  ⚠️ 입력 확인 실패. 현재 값: {final_value}, 기대 값: {value}")
                        except Exception as e:
                            logger.warning(f"  ⚠️ 텍스트 입력 중 오류: {str(e)}")
                            # JavaScript로 재시도
                            try:
                                self.driver.execute_script("""
                                    var element = arguments[0];
                                    var value = arguments[1];
                                    element.value = value;
                                    element.dispatchEvent(new Event('input', { bubbles: true }));
                                    element.dispatchEvent(new Event('change', { bubbles: true }));
                                    element.dispatchEvent(new Event('blur', { bubbles: true }));
                                """, element, value)
                                logger.info(f"  ✓ JavaScript로 텍스트 입력 완료: {value}")
                            except Exception as e2:
                                logger.error(f"  ❌ JavaScript 입력도 실패: {str(e2)}")
                    elif field_type == "radio":
                        # 라디오 버튼의 경우 여러 방법으로 찾기
                        try:
                            radio = None
                            value_lower = value.lower().strip()
                            value_upper = value.upper().strip()
                            
                            # 1단계: 모든 라디오 버튼 가져오기
                            radios = self.driver.find_elements(By.CSS_SELECTOR, f"input[name='{field_name}'][type='radio']")
                            logger.info(f"  📻 라디오 버튼 개수: {len(radios)}")
                            
                            # 2단계: 여러 방법으로 매칭 시도
                            for r in radios:
                                # id로 찾기 (예: id="yes", value="Yes"인 경우)
                                r_id = (r.get_attribute("id") or "").lower().strip()
                                if value_lower == r_id:
                                    radio = r
                                    logger.info(f"  ✓ ID로 매칭: id='{r_id}'")
                                    break
                                
                                # value 속성으로 찾기
                                r_value = (r.get_attribute("value") or "").strip()
                                if value == r_value or value_lower == r_value.lower():
                                    radio = r
                                    logger.info(f"  ✓ value로 매칭: value='{r_value}'")
                                    break
                                
                                # label 텍스트로 찾기
                                try:
                                    r_id_for_label = r.get_attribute("id")
                                    if r_id_for_label:
                                        label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{r_id_for_label}']")
                                        label_text = (label.text or "").strip()
                                        if value == label_text or value_lower == label_text.lower():
                                            radio = r
                                            logger.info(f"  ✓ label 텍스트로 매칭: label='{label_text}'")
                                            break
                                except:
                                    pass
                                
                                # label의 부모 요소에서 텍스트 찾기
                                try:
                                    # label이 input의 형제 요소인 경우
                                    parent = r.find_element(By.XPATH, "./following-sibling::label[1]")
                                    label_text = (parent.text or "").strip()
                                    if value == label_text or value_lower == label_text.lower():
                                        radio = r
                                        logger.info(f"  ✓ 형제 label로 매칭: label='{label_text}'")
                                        break
                                except:
                                    pass
                            
                            # 3단계: 라디오 버튼 선택
                            if radio:
                                if not radio.is_selected():
                                    # JavaScript로 클릭 및 Angular 이벤트 트리거
                                    self.driver.execute_script("""
                                        var radio = arguments[0];
                                        var fieldName = arguments[1];
                                        
                                        // 라디오 버튼 클릭
                                        radio.click();
                                        
                                        // 모든 관련 이벤트 발생
                                        var events = ['focus', 'click', 'change', 'blur'];
                                        events.forEach(function(eventType) {
                                            var event = new Event(eventType, { bubbles: true, cancelable: true });
                                            radio.dispatchEvent(event);
                                        });
                                        
                                        // Angular ngModel 업데이트
                                        if (radio.ngModelController) {
                                            radio.ngModelController.$setViewValue(radio.value);
                                            radio.ngModelController.$render();
                                        }
                                        
                                        // Angular FormControl 업데이트
                                        if (radio.form && radio.name) {
                                            var formControl = radio.form[radio.name];
                                            if (formControl) {
                                                if (formControl.setValue) {
                                                    formControl.setValue(radio.value);
                                                }
                                                if (formControl.markAsTouched) {
                                                    formControl.markAsTouched();
                                                }
                                                if (formControl.markAsDirty) {
                                                    formControl.markAsDirty();
                                                }
                                            }
                                        }
                                        
                                        // 같은 name의 다른 라디오 버튼들 해제 (필요한 경우)
                                        var allRadios = document.querySelectorAll('input[name="' + fieldName + '"][type="radio"]');
                                        allRadios.forEach(function(r) {
                                            if (r !== radio && r.checked) {
                                                r.checked = false;
                                                r.dispatchEvent(new Event('change', { bubbles: true }));
                                            }
                                        });
                                    """, radio, field_name)
                                    time.sleep(0.5)
                                    
                                    # 선택 확인
                                    if radio.is_selected():
                                        logger.info(f"  ✓ 라디오 버튼 선택 완료: {value}")
                                    else:
                                        logger.warning(f"  ⚠️ 라디오 버튼 선택 확인 실패, 재시도...")
                                        # 강제 선택
                                        self.driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", radio)
                                        time.sleep(0.3)
                                        logger.info(f"  ✓ 라디오 버튼 강제 선택 완료: {value}")
                                else:
                                    logger.info(f"  ✓ 라디오 버튼 이미 선택됨: {value}")
                            else:
                                logger.warning(f"  ⚠️ 라디오 버튼을 찾을 수 없습니다: {field_name}={value}")
                                # 디버깅: 모든 라디오 버튼 정보 로깅
                                logger.info(f"  사용 가능한 라디오 버튼:")
                                for i, r in enumerate(radios):
                                    r_id = r.get_attribute("id") or "없음"
                                    r_value = r.get_attribute("value") or "없음"
                                    try:
                                        r_id_for_label = r.get_attribute("id")
                                        label_text = "없음"
                                        if r_id_for_label:
                                            label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{r_id_for_label}']")
                                            label_text = (label.text or "").strip()
                                    except:
                                        pass
                                    logger.info(f"    [{i}] id='{r_id}', value='{r_value}', label='{label_text}'")
                        except Exception as e:
                            logger.warning(f"  ⚠️ 라디오 버튼 선택 실패: {str(e)}")
                            import traceback
                            logger.error(f"  상세 오류: {traceback.format_exc()}")
                    else:
                        element.clear()
                        element.send_keys(value)
                        logger.info(f"  ✓ 입력 완료: {value}")
                
                elif tag == "select" or tag == "selection":
                    try:
                        # 먼저 모든 옵션 확인 및 로깅
                        select = Select(element)
                        options = select.options
                        logger.info(f"  📋 셀렉트 박스 옵션 개수: {len(options)}")
                        for i, opt in enumerate(options[:5]):  # 처음 5개만 로깅
                            opt_text = opt.text or ""
                            opt_value = opt.get_attribute("value") or ""
                            logger.info(f"    옵션 {i}: text='{opt_text}', value='{opt_value}'")
                        
                        # JavaScript로 직접 선택 시도 (가장 확실한 방법)
                        target_index = None
                        target_value = None
                        
                        # 옵션 검색
                        for i, option in enumerate(options):
                            option_text = (option.text or "").strip()
                            option_value = (option.get_attribute("value") or "").strip()
                            
                            # 정확한 매칭
                            if value == option_value or value == option_text:
                                target_index = i
                                target_value = option_value if option_value else option_text
                                break
                            # 부분 매칭 (대소문자 무시)
                            elif value.lower() == option_value.lower() or value.lower() == option_text.lower():
                                target_index = i
                                target_value = option_value if option_value else option_text
                                break
                            # 포함 검색
                            elif value.lower() in option_text.lower() or value.lower() in option_value.lower():
                                target_index = i
                                target_value = option_value if option_value else option_text
                                break
                        
                        if target_index is not None:
                            logger.info(f"  찾은 옵션: index={target_index}, value='{target_value}'")
                            
                            # JavaScript로 직접 선택 (Angular 앱에 가장 효과적)
                            self.driver.execute_script("""
                                var select = arguments[0];
                                var targetIndex = arguments[1];
                                var targetValue = arguments[2];
                                
                                // 옵션 선택
                                select.selectedIndex = targetIndex;
                                
                                // 모든 관련 이벤트 발생
                                var events = ['focus', 'click', 'change', 'blur'];
                                events.forEach(function(eventType) {
                                    var event = new Event(eventType, { bubbles: true, cancelable: true });
                                    select.dispatchEvent(event);
                                });
                                
                                // Angular ngModel 업데이트
                                if (select.ngModelController) {
                                    select.ngModelController.$setViewValue(targetValue);
                                    select.ngModelController.$render();
                                }
                                
                                // Angular FormControl 업데이트
                                if (select.form && select.name) {
                                    var formControl = select.form[select.name];
                                    if (formControl) {
                                        if (formControl.setValue) {
                                            formControl.setValue(targetValue);
                                        }
                                        if (formControl.markAsTouched) {
                                            formControl.markAsTouched();
                                        }
                                        if (formControl.markAsDirty) {
                                            formControl.markAsDirty();
                                        }
                                    }
                                }
                                
                                // Angular Reactive Forms (FormGroup)
                                if (select.form && select.name) {
                                    var formGroup = select.form;
                                    if (formGroup.get && formGroup.get(select.name)) {
                                        var control = formGroup.get(select.name);
                                        if (control.setValue) {
                                            control.setValue(targetValue);
                                        }
                                    }
                                }
                            """, element, target_index, target_value)
                            
                            time.sleep(0.5)
                            
                            # Selenium Select로도 시도 (이중 보장)
                            try:
                                if target_value:
                                    try:
                                        select.select_by_value(target_value)
                                    except:
                                        try:
                                            select.select_by_visible_text(target_value)
                                        except:
                                            select.select_by_index(target_index)
                            except:
                                pass
                            
                            time.sleep(0.3)
                            
                            # 최종 확인
                            current_value = element.get_attribute("value")
                            current_selected_index = element.get_attribute("selectedIndex")
                            
                            if current_value == target_value or str(current_selected_index) == str(target_index):
                                logger.info(f"  ✓ 셀렉트 박스 선택 완료: {target_value}")
                            else:
                                logger.warning(f"  ⚠️ 선택 확인 실패. 현재 값: {current_value}, 기대 값: {target_value}")
                                # 최종 강제 설정
                                self.driver.execute_script("""
                                    var select = arguments[0];
                                    var targetIndex = arguments[1];
                                    select.selectedIndex = targetIndex;
                                    select.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                """, element, target_index)
                                time.sleep(0.3)
                        else:
                            logger.warning(f"  ⚠️ 셀렉트 박스에서 값을 찾을 수 없습니다: {value}")
                            # 모든 옵션 로깅
                            logger.info(f"  사용 가능한 옵션:")
                            for i, opt in enumerate(options):
                                opt_text = opt.text or ""
                                opt_value = opt.get_attribute("value") or ""
                                logger.info(f"    [{i}] text='{opt_text}', value='{opt_value}'")
                            
                    except Exception as e:
                        logger.warning(f"  ⚠️ 셀렉트 박스 선택 실패: {str(e)}")
                        import traceback
                        logger.error(f"  상세 오류: {traceback.format_exc()}")
                
                time.sleep(0.5)  # 각 필드 입력 사이 대기
            
            logger.info("\n=== 폼 필드 입력 완료 ===\n")
            
        except Exception as e:
            logger.error(f"폼 입력 중 오류 발생: {str(e)}")
            self.save_debug_info("form_fill_error")
            raise
    
    def click_save_button(self, button_selectors=None):
        """
        Save 버튼을 찾아서 클릭하는 함수
        
        Args:
            button_selectors: 버튼을 찾을 선택자 리스트 (기본값: None)
        """
        try:
            if button_selectors is None:
                button_selectors = [
                    # "Save and continue" 텍스트를 포함하는 버튼 (대소문자 무시)
                    (By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save')]"),
                    # "Save" 텍스트를 포함하는 버튼
                    (By.XPATH, "//button[contains(text(), 'Save') or contains(text(), '저장')]"),
                    # type="submit"인 버튼 중에서 "Save" 텍스트 포함
                    (By.XPATH, "//button[@type='submit' and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save')]"),
                    # type="submit"인 모든 버튼
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    # 기타 선택자들
                    (By.NAME, "save"),
                    (By.ID, "save"),
                    (By.CSS_SELECTOR, "button.btn-primary"),
                    (By.CSS_SELECTOR, "input[type='submit'][value*='Save' i]"),
                ]
            
            save_btn = self.find_element_multiple_ways(button_selectors, wait_for_clickable=True, timeout=10)
            
            if not save_btn:
                logger.warning("Save 버튼을 찾을 수 없습니다. 모든 버튼 검색 중...")
                # 모든 submit 버튼 찾기
                try:
                    all_submit_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
                    logger.info(f"  발견된 submit 버튼 개수: {len(all_submit_buttons)}")
                    for i, btn in enumerate(all_submit_buttons):
                        btn_text = (btn.text or "").strip()
                        logger.info(f"    버튼 {i+1}: text='{btn_text}'")
                        if "save" in btn_text.lower():
                            save_btn = btn
                            logger.info(f"  ✓ 'Save' 텍스트를 포함한 버튼 발견: '{btn_text}'")
                            break
                except Exception as e:
                    logger.error(f"  버튼 검색 중 오류: {str(e)}")
            
            if not save_btn:
                logger.warning("Save 버튼을 찾을 수 없습니다.")
                self.save_debug_info("save_button_not_found")
                return False
            
            # 버튼 정보 로깅
            btn_text = (save_btn.text or "").strip()
            btn_type = save_btn.get_attribute("type") or ""
            logger.info(f"  찾은 Save 버튼: text='{btn_text}', type='{btn_type}'")
            
            # 현재 URL 저장 (저장 후 변경 확인용)
            current_url = self.driver.current_url
            logger.info(f"  저장 전 URL: {current_url}")
            
            # 스크롤하여 버튼이 보이도록
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", save_btn)
            time.sleep(0.5)
            
            # 버튼이 클릭 가능할 때까지 대기
            try:
                WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(save_btn))
            except:
                pass
            
            # form 찾기 (있는 경우)
            form_element = None
            try:
                form_element = save_btn.find_element(By.XPATH, "./ancestor::form[1]")
                logger.info("  form 요소 발견")
            except:
                try:
                    form_element = self.driver.find_element(By.TAG_NAME, "form")
                    logger.info("  페이지의 form 요소 발견")
                except:
                    pass
            
            # 방법 1: form 직접 제출 시도 (가장 확실한 방법)
            if form_element:
                try:
                    logger.info("  form 직접 제출 시도...")
                    self.driver.execute_script("""
                        var form = arguments[0];
                        var button = arguments[1];
                        
                        // Angular 폼 제출
                        if (form.ngForm) {
                            form.ngForm.ngSubmit.emit();
                        }
                        
                        // Angular Reactive Forms
                        if (form.ngFormGroup) {
                            form.ngFormGroup.markAllAsTouched();
                        }
                        
                        // form 제출
                        if (form.requestSubmit) {
                            form.requestSubmit(button);
                        } else {
                            form.submit();
                        }
                    """, form_element, save_btn)
                    logger.info("  form 제출 완료 (JavaScript)")
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"  form 제출 실패: {str(e)}")
            
            # 방법 2: JavaScript로 버튼 클릭 (이중 보장)
            try:
                self.driver.execute_script("""
                    var button = arguments[0];
                    
                    // 포커스
                    button.focus();
                    
                    // 클릭 이벤트 발생
                    var clickEvent = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        button: 0
                    });
                    button.dispatchEvent(clickEvent);
                    
                    // submit 이벤트도 발생 (form이 있는 경우)
                    if (button.form) {
                        var submitEvent = new Event('submit', {
                            bubbles: true,
                            cancelable: true
                        });
                        button.form.dispatchEvent(submitEvent);
                    }
                """, save_btn)
                logger.info("  Save 버튼 클릭 완료 (JavaScript)")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"  JavaScript 클릭 실패, 일반 클릭 시도: {str(e)}")
                try:
                    save_btn.click()
                    logger.info("  Save 버튼 클릭 완료 (일반)")
                    time.sleep(1)
                except Exception as e2:
                    logger.error(f"  일반 클릭도 실패: {str(e2)}")
            
            # 저장 후 대기 및 확인
            logger.info("  저장 후 대기 중...")
            time.sleep(2)
            
            # 페이지 전환 확인
            try:
                # URL 변경 확인
                new_url = self.driver.current_url
                if new_url != current_url:
                    logger.info(f"  ✓ 페이지 전환 확인: {new_url}")
                else:
                    logger.info("  URL 변경 없음 (같은 페이지)")
                
                # 성공 메시지나 특정 요소 확인 시도
                try:
                    # 성공 메시지 찾기
                    success_indicators = [
                        "//*[contains(text(), 'saved') or contains(text(), '저장') or contains(text(), 'success')]",
                        "//*[contains(@class, 'success') or contains(@class, 'alert-success')]"
                    ]
                    for indicator in success_indicators:
                        try:
                            success_element = WebDriverWait(self.driver, 2).until(
                                EC.presence_of_element_located((By.XPATH, indicator))
                            )
                            if success_element:
                                logger.info(f"  ✓ 저장 성공 메시지 발견")
                                break
                        except:
                            continue
                except:
                    pass
                
            except Exception as e:
                logger.warning(f"  페이지 전환 확인 중 오류: {str(e)}")
            
            # 추가 대기 (헤드리스 모드에서 더 긴 대기 필요)
            time.sleep(3)
            
            logger.info("  저장 프로세스 완료")
            return True
            
        except Exception as e:
            logger.error(f"Save 버튼 클릭 중 오류: {str(e)}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
            return False
    
    def close(self):
        """브라우저 종료"""
        if self.driver:
            self.driver.quit()
            logger.info("브라우저가 종료되었습니다.")

