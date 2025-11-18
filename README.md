# PDF 서버 - XFA 폼 자동 채우기 API

XFA(XML Forms Architecture) 기반 PDF 폼을 자동으로 처리하는 FastAPI 기반 웹 서버입니다. PDF에서 필드를 추출하고, JSON 데이터를 사용하여 PDF를 자동으로 채울 수 있습니다.

## 📁 프로젝트 구조

```
pdf_server/
├── app/
│   ├── core/                    # 핵심 설정 및 미들웨어
│   │   ├── app.py               # FastAPI 앱 생성
│   │   ├── config.py            # 애플리케이션 설정
│   │   ├── exceptions.py        # 예외 핸들러
│   │   └── middleware.py        # CORS 미들웨어
│   ├── models/                  # 데이터 모델
│   │   └── schemas.py           # Pydantic 스키마
│   ├── routers/                 # API 라우터
│   │   ├── health.py            # Health check 엔드포인트
│   │   └── pdf.py               # PDF 처리 엔드포인트
│   ├── services/                # 비즈니스 로직
│   │   ├── pdf_extract_service.py      # PDF 필드 추출 서비스
│   │   ├── pdf_field_type_service.py   # 필드 타입 추출 서비스
│   │   └── pdf_filler_service.py       # PDF 채우기 서비스
│   ├── utils/                   # 유틸리티 함수
│   │   └── utils.py             # 공통 유틸리티 (XFA 추출/주입, XML 파싱)
│   └── main.py                  # 애플리케이션 진입점
├── uploads/                     # 업로드된 PDF 파일 저장 디렉토리
├── fields/                      # 추출된 필드 구조 JSON 파일
├── acroforms/                   # AcroForm 필드 구조 JSON 파일
├── forms/                       # XFA form.xml 파일
├── datasets/                    # XFA datasets.xml 파일
├── templates/                   # XFA 템플릿 파일
├── requirements.txt             # Python 패키지 의존성
├── Dockerfile                   # Docker 이미지 빌드 파일
└── README.md                    # 프로젝트 문서
```

## 🚀 설치 및 실행

### 로컬 환경에서 실행

1. **가상환경 생성 및 활성화:**
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. **필요한 패키지 설치:**
```bash
pip install -r requirements.txt
```

3. **서버 실행:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

서버가 실행되면 다음 URL에서 API 문서를 확인할 수 있습니다:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Docker를 사용한 실행

1. **Docker 이미지 빌드:**
```bash
docker build -t pdf-server .
```

2. **컨테이너 실행:**
```bash
docker run -d -p 8000:8000 --name pdf-server pdf-server
```

## 📖 API 사용 방법

### 1. Health Check

서버 상태를 확인합니다.

**요청:**
```bash
GET http://localhost:8000/
```

**응답:**
```json
{
  "message": "PDF Server is running",
  "status": "ok"
}
```

---

### 2. PDF 필드 추출 (`/upload-and-extract`)

PDF 파일을 업로드하고 XFA 폼의 필드 구조를 추출하여 JSON으로 반환합니다.

**요청:**
```bash
POST http://localhost:8000/upload-and-extract
Content-Type: multipart/form-data

file: [PDF 파일]
```

**cURL 예시:**
```bash
curl -X POST "http://localhost:8000/upload-and-extract" \
  -F "file=@IMM0800e.pdf"
```

**응답 예시:**
```json
{
  "filename": "IMM0800e.pdf",
  "fields": {
    "IMM_0800": {
      "Page1": {
        "PersonalDetails": {
          "Name": {
            "FamilyName": "",
            "GivenName": ""
          },
          "BirthDate": "",
          "Citizenship": ""
        }
      }
    }
  }
}
```

**동작:**
- PDF 파일을 `uploads/` 디렉토리에 저장
- XFA 폼의 필드 구조를 자동으로 추출
- JSON 형식으로 필드 구조 반환 (값은 빈 문자열)
- 동일한 파일이 이미 업로드된 경우 기존 필드 구조 재사용

---

### 3. PDF 필드 채우기 (`/fill-pdf`)

JSON 데이터를 사용하여 PDF 폼의 필드를 채우고 채워진 PDF 파일을 다운로드합니다.

**요청:**
```bash
POST http://localhost:8000/fill-pdf
Content-Type: application/json

{
  "filename": "IMM0800e.pdf",
  "fields": {
    "IMM_0800": {
      "Page1": {
        "PersonalDetails": {
          "Name": {
            "FamilyName": "홍",
            "GivenName": "길동"
          },
          "BirthDate": "1990-01-01",
          "Citizenship": "Canada"
        }
      }
    }
  }
}
```

**cURL 예시:**
```bash
curl -X POST "http://localhost:8000/fill-pdf" \
  -H "Content-Type: application/json" \
  -d '{
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
  }' \
  --output filled.pdf
```

**응답:**
- Content-Type: `application/pdf`
- 채워진 PDF 파일 바이너리

**주의사항:**
- 먼저 `/upload-and-extract` 엔드포인트로 PDF 파일을 업로드해야 합니다.
- `fields` 구조는 추출된 필드 구조와 일치해야 합니다.

---

### 4. PDF 필드 타입 추출 (`/extract-field-types`)

업로드된 PDF 파일에서 필드 타입, 옵션, 포맷 정보를 추출합니다.

**요청:**
```bash
POST http://localhost:8000/extract-field-types
Content-Type: application/json

{
  "filename": "IMM0800e.pdf"
}
```

**응답 예시:**
```json
{
  "IMM_0800": {
    "Page1": {
      "PersonalDetails": {
        "Name": {
          "FamilyName": {"type": "text"},
          "GivenName": {"type": "text"}
        },
        "BirthDate": {"type": "date", "format": "YYYY-MM-DD"},
        "Citizenship": {"type": "select", "options": ["Canada", "USA"]},
        "Agree": {"type": "checkbox"},
        "Language": {"type": "radio", "options": ["English", "French"]}
      }
    }
  }
}
```

**지원하는 필드 타입:**
- `text`: 텍스트 입력 필드
- `select`: 드롭다운 선택 필드 (옵션 목록 포함)
- `checkbox`: 체크박스 필드
- `radio`: 라디오 버튼 필드 (옵션 목록 포함)
- `date`: 날짜 필드 (포맷 정보 포함)
- `time`: 시간 필드 (포맷 정보 포함)

---

### 5. PDF 필드 값 추출 (`/extract-field-values`)

업로드된 PDF 파일에서 필드 키와 실제 값을 모두 추출합니다.

**요청:**
```bash
POST http://localhost:8000/extract-field-values
Content-Type: application/json

{
  "filename": "IMM0800e_filled.pdf"
}
```

**응답 예시:**
```json
{
  "IMM_0800": {
    "Page1": {
      "PersonalDetails": {
        "Name": {
          "FamilyName": "홍",
          "GivenName": "길동"
        },
        "BirthDate": "1990-01-01",
        "Citizenship": "Canada"
      }
    }
  }
}
```

**동작:**
- 필드 구조와 함께 실제 값까지 추출
- `datasets.xml`과 `form.xml`에서 값을 읽어옴
- 빈 필드는 빈 문자열로 표시

---

## 🔄 전체 워크플로우

### 1단계: PDF 업로드 및 필드 추출
```bash
curl -X POST "http://localhost:8000/upload-and-extract" \
  -F "file=@IMM0800e.pdf"
```

### 2단계: 필드 타입 확인 (선택사항)
```bash
curl -X POST "http://localhost:8000/extract-field-types" \
  -H "Content-Type: application/json" \
  -d '{"filename": "IMM0800e.pdf"}'
```

### 3단계: JSON 데이터 준비
추출된 필드 구조를 참고하여 데이터 작성

### 4단계: PDF 채우기
```bash
curl -X POST "http://localhost:8000/fill-pdf" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "IMM0800e.pdf",
    "fields": { ... }
  }' \
  --output filled.pdf
```

---

## 📋 주요 기능

### PDF 필드 추출
- XFA 기반 PDF에서 필드 구조 자동 추출
- JSON 템플릿 자동 생성
- 베이스 태그 자동 감지

### PDF 채우기
- JSON 구조를 직접 XFA 경로로 변환하여 매핑
- 베이스 태그 자동 추론 (JSON에서)
- 채워진 PDF 파일 다운로드

### 필드 타입 추출
- 필드 타입 자동 감지 (text, select, checkbox, radio, date, time 등)
- select/radio 필드의 옵션 목록 추출
- date/time 필드의 포맷 정보 추출

### 필드 값 추출
- 채워진 PDF에서 실제 값 추출
- 필드 구조와 값 모두 포함

---

## 📝 JSON 데이터 형식

JSON 파일은 필드 매핑 구조에 맞춰 작성해야 합니다. `/upload-and-extract` 엔드포인트로 추출한 필드 구조를 참고하여 데이터를 작성하세요.

**예시 (IMM0800e):**
```json
{
  "IMM_0800": {
    "Page1": {
      "PersonalDetails": {
        "Name": {
          "FamilyName": "홍",
          "GivenName": "길동"
        },
        "BirthDate": "1990-01-01",
        "Citizenship": "Canada"
      }
    }
  }
}
```

**베이스 태그:**
- JSON의 최상위 키가 XFA 폼의 베이스 태그입니다 (예: `IMM_0800`, `form1`)
- 베이스 태그는 자동으로 추론되므로 JSON 구조만 맞추면 됩니다

**경로 변환:**
- JSON의 점 표기법(예: `IMM_0800.Page1.Name`)이 자동으로 XFA 경로(예: `./Page1/Name`)로 변환됩니다

**배열 인덱스:**
- JSON에서는 배열의 첫 번째 요소가 `[0]`이지만, XFA 형식에서는 첫 번째 요소가 `[1]`입니다
- 자동으로 변환되므로 JSON에서는 일반적인 프로그래밍 언어처럼 `[0]`, `[1]`, `[2]`... 형식으로 작성하면 됩니다
  - 예: JSON의 `items[0]` → XFA의 `items[1]` (첫 번째 항목)
  - 예: JSON의 `items[1]` → XFA의 `items[2]` (두 번째 항목)

---

## ⚠️ 주의사항

1. **PDF 파일 형식**: XFA(XML Forms Architecture) 기반 PDF만 지원합니다.
2. **파일 업로드 순서**: PDF 채우기 전에 먼저 `/upload-and-extract` 엔드포인트로 PDF 파일을 업로드해야 합니다.
3. **필드 구조 일치**: JSON 데이터의 구조가 추출된 필드 구조와 일치해야 합니다.
4. **베이스 태그**: JSON의 최상위 키가 XFA 폼의 베이스 태그와 일치해야 합니다 (예: `IMM_0800`, `form1`).
5. **JSON 경로**: JSON의 키 구조가 XFA 경로와 일치해야 합니다 (점(.)이 슬래시(/)로 변환됨).

---

## 🛠️ 문제 해결

### PDF 파일을 찾을 수 없음
- 먼저 `/upload-and-extract` 엔드포인트로 PDF 파일을 업로드했는지 확인
- `uploads/` 디렉토리에 해당 파일이 있는지 확인

### 필드가 채워지지 않음
- JSON 데이터 구조가 추출된 필드 구조와 일치하는지 확인
- 베이스 태그가 JSON의 최상위 키와 일치하는지 확인 (예: `IMM_0800`, `form1`)
- JSON 경로가 XFA 경로와 일치하는지 확인 (점(.)이 슬래시(/)로 변환됨)

### 필드 타입 추출 실패
- PDF 파일이 XFA 형식인지 확인
- 먼저 `/upload-and-extract` 엔드포인트로 파일을 업로드했는지 확인

---

## 📚 기술 스택

- **FastAPI**: 웹 프레임워크
- **pikepdf**: PDF 파일 처리
- **lxml**: XML 파싱
- **pydantic**: 데이터 검증
- **uvicorn**: ASGI 서버

---

## 📚 추가 정보

- **XFA**: XML Forms Architecture - PDF 폼의 구조를 XML로 정의하는 표준
- **JSON 경로 변환**: JSON의 점 표기법(예: `IMM_0800.Page1.Name`)이 자동으로 XFA 경로(예: `./Page1/Name`)로 변환됩니다
- **베이스 태그**: XFA 폼의 최상위 루트 태그 (예: `IMM_0800`, `form1`). JSON의 최상위 키에서 자동 추론됩니다
- **배열 인덱스**: JSON에서는 배열의 첫 번째 요소가 `[0]`이지만, XFA 형식에서는 첫 번째 요소가 `[1]`입니다. 자동으로 변환되므로 JSON에서는 일반적인 프로그래밍 언어처럼 `[0]`, `[1]`, `[2]`... 형식으로 작성하면 됩니다.

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.
