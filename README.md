# PDF 서버 - XFA 폼 자동 채우기

XFA(XML Forms Architecture) 기반 PDF 폼을 자동으로 채우는 도구입니다. PDF에서 필드를 추출하고, JSON 데이터를 사용하여 PDF를 자동으로 채울 수 있습니다.

## 📁 프로젝트 구조

```
pdf_server/
├── app/
│   ├── pdfs/              # 원본 PDF 템플릿 파일들
│   ├── field_maps/        # 추출된 필드 구조 템플릿 (.json)
│   ├── input/             # 입력 JSON 데이터 파일들
│   ├── output/            # 생성된 PDF 파일들
│   └── utils/
│       ├── pdf_extract.py      # PDF 필드 추출 도구
│       ├── pdf_filler.py        # PDF 채우기 도구 (단일/일괄 처리)
│       └── utils.py            # 공통 유틸리티 함수 (XFA 추출/주입, XML 파싱)
```

## 🚀 설치

1. 가상환경 생성 및 활성화:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. 필요한 패키지 설치:
```bash
pip install pikepdf lxml fastapi
```

**설치되는 패키지:**
- `pikepdf`: PDF 파일 처리
- `lxml`: XML 파싱
- `fastapi`: 웹 서버 (선택사항)

## 📖 사용 방법

### 1. PDF 필드 추출 (`pdf_extract.py`)

PDF 파일에서 필드 구조를 추출하여 `field_maps` 폴더에 저장합니다.

**실행 명령어:**
```bash
python -m app.utils.pdf_extract
```

**동작:**
- `app/pdfs/` 폴더의 모든 PDF 파일을 자동으로 처리
- 각 PDF에서 필드 구조를 추출하여 JSON 템플릿 생성:
  - `app/field_maps/{폼명}.json` - 필드 구조 템플릿

**예시 출력:**
```
✅ IMM0800e.pdf → field_maps/IMM0800e.json 생성 완료 (base=IMM_0800, 190개 필드)
✅ imm5709e.pdf → field_maps/imm5709e.json 생성 완료 (base=form1, 268개 필드)
```

---

### 2. PDF 채우기 (`pdf_filler.py`) ⭐

JSON 데이터를 사용하여 PDF를 채웁니다. 단일 파일 처리와 일괄 처리 모두 지원합니다.

#### 일괄 처리

`input` 폴더의 모든 JSON 파일을 자동으로 처리합니다.

**실행 명령어:**
```bash
python -m app.utils.pdf_filler
```

**동작:**
- `app/input/` 폴더의 모든 `.json` 파일을 자동으로 처리
- 각 JSON 파일명과 동일한 이름의 PDF를 `app/pdfs/` 폴더에서 찾아서 채움
- 결과를 `app/output/` 폴더에 저장

**예시 출력:**
```
📁 2개의 JSON 파일을 처리합니다...

처리 중: IMM0800e.json
✅ IMM0800e: JSON 로드 완료 (base=IMM_0800)
✅ IMM0800e: PDF 생성 완료 → app/output/IMM0800e.pdf

처리 중: imm5709e.json
✅ imm5709e: JSON 로드 완료 (base=form1)
✅ imm5709e: PDF 생성 완료 → app/output/imm5709e.pdf

✅ 완료: 2/2개 파일 처리 성공
```

**파일 매핑 규칙:**
- `input/IMM0800e.json` → `pdfs/IMM0800e.pdf` → `output/IMM0800e.pdf`
- `input/imm5709e.json` → `pdfs/imm5709e.pdf` → `output/imm5709e.pdf`

---

#### 단일 파일 처리

특정 PDF 파일 하나만 처리합니다.

**실행 명령어:**
```bash
python -m app.utils.pdf_filler <input.pdf> <data.json> <output.pdf>
```

**파라미터 설명:**
- `input.pdf`: 원본 PDF 템플릿 파일 경로
- `data.json`: 채울 데이터 JSON 파일 경로
- `output.pdf`: 생성될 PDF 파일 경로

**예시:**
```bash
python -m app.utils.pdf_filler app/pdfs/IMM0800e.pdf app/input/IMM0800e.json app/output/IMM0800e.pdf
```

**동작 방식:**
- 인자 없음: `input` 폴더 일괄 처리
- 인자 3개: 단일 파일 처리 (base_tag는 JSON에서 자동 추론)

---

## 📝 JSON 데이터 형식

JSON 파일은 필드 매핑 구조에 맞춰 작성해야 합니다. `field_maps/{폼명}.json` 파일을 참고하여 데이터를 작성하세요.

**예시 (IMM0800e.json):**
```json
{
  "IMM_0800": {
    "Page1": {
      "PersonalDetails": {
        "Name": {
          "FamilyName": "Diana",
          "GivenName": "Shin"
        }
      }
    }
  }
}
```

---

## 🔄 전체 워크플로우

### 1단계: PDF 필드 추출
```bash
# pdfs 폴더에 PDF 파일 추가 후
python -m app.utils.pdf_extract
```

### 2단계: JSON 데이터 준비
- `field_maps/{폼명}.json` 파일을 참고하여 데이터 구조 파악
- `input/{폼명}.json` 파일에 데이터 작성

### 3단계: PDF 채우기
```bash
# 방법 1: 일괄 처리
python -m app.utils.pdf_filler

# 방법 2: 단일 파일 처리
python -m app.utils.pdf_filler app/pdfs/IMM0800e.pdf app/input/IMM0800e.json app/output/IMM0800e.pdf
```

---

## 📋 주요 기능

### 필드 추출 (`pdf_extract.py`)
- XFA 기반 PDF에서 필드 구조 자동 추출
- JSON 템플릿 자동 생성
- 베이스 태그 자동 감지

### PDF 채우기 (`pdf_filler.py`)
- JSON 구조를 직접 XFA 경로로 변환하여 매핑
- 베이스 태그 자동 추론 (JSON에서)
- 단일 파일 처리 및 일괄 처리 모두 지원
- 파일명 기반 자동 매칭
- 에러 처리 및 진행 상황 표시

---

## ⚠️ 주의사항

1. **PDF 파일 형식**: XFA(XML Forms Architecture) 기반 PDF만 지원합니다.
2. **파일명 규칙**: JSON 파일명과 PDF 파일명이 일치해야 합니다 (대소문자 구분).
3. **필드 구조**: 먼저 `pdf_extract.py`를 실행하여 JSON 템플릿을 생성해야 합니다.
4. **베이스 태그**: JSON 데이터에서 자동으로 추론됩니다.
5. **JSON 구조**: JSON의 키 구조가 XFA 경로와 일치해야 합니다 (점(.)이 슬래시(/)로 변환됨).

---

## 🛠️ 문제 해결

### JSON 템플릿 파일을 찾을 수 없음
```bash
# field_maps 폴더에 해당 폼의 .json 파일이 있는지 확인
ls app/field_maps/

# 없다면 pdf_extract.py를 먼저 실행
python -m app.utils.pdf_extract
```

### PDF 파일을 찾을 수 없음
- `input/{폼명}.json` 파일명과 `pdfs/{폼명}.pdf` 파일명이 일치하는지 확인
- 대소문자 구분 확인

### 필드가 채워지지 않음
- JSON 데이터 구조가 `field_maps/{폼명}.json`의 구조와 일치하는지 확인
- 베이스 태그가 JSON의 최상위 키와 일치하는지 확인 (예: `IMM_0800`, `form1`)
- JSON 경로가 XFA 경로와 일치하는지 확인 (점(.)이 슬래시(/)로 변환됨)

---

## 📚 추가 정보

- **XFA**: XML Forms Architecture - PDF 폼의 구조를 XML로 정의하는 표준
- **JSON 경로 변환**: JSON의 점 표기법(예: `IMM_0800.Page1.Name`)이 자동으로 XFA 경로(예: `./Page1/Name`)로 변환됩니다
- **베이스 태그**: XFA 폼의 최상위 루트 태그 (예: `IMM_0800`, `form1`). JSON의 최상위 키에서 자동 추론됩니다
- **배열 인덱스**: JSON에서는 배열의 첫 번째 요소가 `[0]`이지만, XFA 형식에서는 첫 번째 요소가 `[1]`입니다. 자동으로 변환되므로 JSON에서는 일반적인 프로그래밍 언어처럼 `[0]`, `[1]`, `[2]`... 형식으로 작성하면 됩니다.
  - 예: JSON의 `items[0]` → XFA의 `items[1]` (첫 번째 항목)
  - 예: JSON의 `items[1]` → XFA의 `items[2]` (두 번째 항목)

