# AI Project Management Server

프로젝트 커뮤니케이션 위험 분석과 초기 기획 문서 분석을 제공하는 FastAPI 서버입니다.

## 실행

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

환경변수는 프로젝트 루트의 `.env`에 설정합니다.

```env
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
OPENAI_PDF_DETAIL=auto
```

API 키가 없거나 LLM 호출에 실패하면 규칙 기반 결과를 반환하며 `llm_status`에서 상태를 확인할 수 있습니다.

## API

- `GET /health`: 서버 상태 확인
- `POST /api/v1/risk/communication/analyze`: Slack 커뮤니케이션 위험 분석
- `POST /api/v1/planning/documents/extract`: 프로젝트 기본정보 및 요구사항 후보 추출

기획 문서 추출 API는 `multipart/form-data` 요청을 받습니다.

- `files`: PDF, HWP, HWPX, DOCX, TXT, MD, CSV 문서, 최대 10개
- 파일당 최대 크기: 20MB

요구사항 후보의 `category`는 LLM이 아래 값 중 하나로 분류합니다. LLM 호출이 실패한 경우에도
동일한 값 체계로 규칙 기반 분류를 수행합니다.

- `FUNCTIONAL`: 기능 요구사항
- `NON_FUNCTIONAL`: 성능·품질 등 비기능 요구사항
- `SECURITY`: 보안·개인정보 요구사항
- `DATA`: 데이터 요구사항
- `INTERFACE`: 외부 시스템·API 연계 요구사항
- `OPERATION`: 운영·유지보수 요구사항
- `PROJECT_MANAGEMENT`: 일정·산출물·교육·보고 등 사업관리 요구사항
- `UNSPECIFIED`: 분류가 불명확하거나 기타인 요구사항

프로젝트 산출물은 `project_info.required_artifacts`에 객체 목록으로 반환합니다. 문서에 버전이
명시되지 않은 경우 `required_version`은 `1.0`입니다.

```json
{
  "required_artifacts": [
    {
      "artifact_type": "REQUIREMENTS_DEFINITION",
      "artifact_name": "요구사항 정의서",
      "required_version": "1.0"
    }
  ]
}
```

허용되는 `artifact_type`은 `RFP`, `PROPOSAL`, `REQUIREMENTS_DEFINITION`,
`FUNCTION_SPECIFICATION`, `WBS`, `ERD`, `MEETING_MINUTES`, `TEST_RESULTS`,
`WEEKLY_REPORT`, `FINAL_REPORT`, `UI_DESIGN`입니다.

`acceptance_conditions`, `budget_contract_conditions`, `security_privacy_conditions`는
원문의 의미를 유지하되 `기능 테스트 통과`, `개인정보 암호화` 같은 짧은 명사형 목록으로 반환합니다.

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/planning/documents/extract" `
  -F "files=@sample-rfp.pdf"
```

일반 PDF는 텍스트를 추출해 저비용 경로로 분석하고, 텍스트가 부족한 스캔 PDF는 원본 PDF를
OpenAI 비전 입력으로 전달합니다. `OPENAI_PDF_DETAIL`은 `auto`, `low`, `high` 중 하나이며,
작은 글씨나 복잡한 표가 중요할 때만 `high`를 권장합니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```
