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
PROFILE_FORM_DATA = {
      "profileForm-correspondence" : {
              "tag": "select",
              "value": "English"
	},
      "profileForm-familyName" : {
              "tag": "input",
              "type": "text",
              "Value": "Jeongwook"
      },
      "personalDetailsForm-givenName" : {
              "tag": "input",
              "type": "text",
              "Value": "Kim",
      },
      "personalDetailsForm-dob" : {
              "tag": "input",
              "type": "text",
              "Value": "1992/11/14"
      },
      "postOfficeBox" : {
              "tag": "input",
              "type": "text",
              "Value": "123"
      },
      "apartmentUnit" : {
              "tag": "input",
              "type": "text",
              "Value": "3611"
      },
      "streetNumber" : {
              "tag": "input",
              "type": "text",
              "Value": "4168"
      },
      "streetName" : {
              "tag": "input",
              "type": "text",
              "Value": "Lougheed Hwy"
      },
      "city" : {
              "tag": "input",
              "type": "text",
              "Value": "Burnaby"
      },
      "country" : {
              "tag": "select",
              "Value": "Canada"
      },
      "postalCode" : {
              "tag": "input",
              "type": "text",
              "Value": "V5C 0N9"
      },
      "residentialSameAsMailingAddress" : {
              "tag": "input",
              "type": "radio",
              "Value": "Yes"
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
        # 백그라운드 실행을 원하지 않으면 아래 주석 해제
        # options.add_argument("--headless")
        # 자동화 감지 방지
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
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
    
    def fill_form_fields(self, form_data):
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
        """
        try:
            logger.info("\n=== 폼 필드 입력 시작 ===")
            
            for field_name, field_info in form_data.items():
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
                            # 먼저 일반적인 방법으로 시도
                            element.clear()
                            time.sleep(0.3)
                            element.click()  # 클릭하여 포커스
                            time.sleep(0.3)
                            element.send_keys(value)
                            time.sleep(0.5)
                            
                            # 입력이 제대로 되었는지 확인
                            current_value = element.get_attribute("value")
                            if current_value != value:
                                # JavaScript로 직접 값 설정 (Angular 앱의 경우)
                                logger.warning(f"  ⚠️ 일반 입력 실패, JavaScript로 재시도...")
                                self.driver.execute_script("arguments[0].value = arguments[1];", element, value)
                                # Angular 이벤트 트리거
                                self.driver.execute_script("""
                                    var element = arguments[0];
                                    var value = arguments[1];
                                    element.value = value;
                                    element.dispatchEvent(new Event('input', { bubbles: true }));
                                    element.dispatchEvent(new Event('change', { bubbles: true }));
                                """, element, value)
                                time.sleep(0.5)
                            
                            # 최종 확인
                            final_value = element.get_attribute("value")
                            if final_value == value or value in final_value:
                                logger.info(f"  ✓ 텍스트 입력 완료: {value}")
                            else:
                                logger.warning(f"  ⚠️ 입력 확인 실패. 현재 값: {final_value}, 기대 값: {value}")
                        except Exception as e:
                            logger.warning(f"  ⚠️ 텍스트 입력 중 오류: {str(e)}")
                            # JavaScript로 재시도
                            try:
                                self.driver.execute_script("arguments[0].value = arguments[1];", element, value)
                                self.driver.execute_script("""
                                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                """, element)
                                logger.info(f"  ✓ JavaScript로 텍스트 입력 완료: {value}")
                            except Exception as e2:
                                logger.error(f"  ❌ JavaScript 입력도 실패: {str(e2)}")
                    elif field_type == "radio":
                        # 라디오 버튼의 경우 value 속성으로 찾기
                        try:
                            radio = self.driver.find_element(
                                By.CSS_SELECTOR, 
                                f"input[name='{field_name}'][type='radio'][value='{value}']"
                            )
                            if not radio.is_selected():
                                self.driver.execute_script("arguments[0].click();", radio)
                                logger.info(f"  ✓ 라디오 버튼 선택 완료: {value}")
                            else:
                                logger.info(f"  ✓ 라디오 버튼 이미 선택됨: {value}")
                        except Exception as e:
                            logger.warning(f"  ⚠️ 라디오 버튼 선택 실패: {str(e)}")
                    else:
                        element.clear()
                        element.send_keys(value)
                        logger.info(f"  ✓ 입력 완료: {value}")
                
                elif tag == "select":
                    try:
                        select = Select(element)
                        # value로 선택 시도
                        try:
                            select.select_by_value(value)
                            logger.info(f"  ✓ 셀렉트 박스 선택 완료 (value): {value}")
                        except:
                            # visible text로 선택 시도
                            try:
                                select.select_by_visible_text(value)
                                logger.info(f"  ✓ 셀렉트 박스 선택 완료 (text): {value}")
                            except:
                                # index로 선택 시도
                                options = select.options
                                for i, option in enumerate(options):
                                    if value in option.text or value in option.get_attribute("value"):
                                        select.select_by_index(i)
                                        logger.info(f"  ✓ 셀렉트 박스 선택 완료 (index): {value}")
                                        break
                    except Exception as e:
                        logger.warning(f"  ⚠️ 셀렉트 박스 선택 실패: {str(e)}")
                
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
                    (By.XPATH, "//button[contains(text(), 'Save') or contains(text(), '저장')]"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.NAME, "save"),
                    (By.ID, "save"),
                    (By.CSS_SELECTOR, "button.btn-primary"),
                    (By.CSS_SELECTOR, "input[type='submit'][value*='Save' i]"),
                ]
            
            save_btn = self.find_element_multiple_ways(button_selectors, wait_for_clickable=True, timeout=10)
            
            if not save_btn:
                logger.warning("Save 버튼을 찾을 수 없습니다.")
                self.save_debug_info("save_button_not_found")
                return False
            
            # 스크롤하여 버튼이 보이도록
            self.driver.execute_script("arguments[0].scrollIntoView(true);", save_btn)
            time.sleep(1)
            
            # JavaScript로 클릭 시도
            try:
                self.driver.execute_script("arguments[0].click();", save_btn)
                logger.info("Save 버튼 클릭 완료 (JavaScript)")
            except:
                save_btn.click()
                logger.info("Save 버튼 클릭 완료 (일반)")
            
            time.sleep(3)  # 저장 후 페이지 로드 대기
            return True
            
        except Exception as e:
            logger.error(f"Save 버튼 클릭 중 오류: {str(e)}")
            return False
    
    def close(self):
        """브라우저 종료"""
        if self.driver:
            self.driver.quit()
            logger.info("브라우저가 종료되었습니다.")

