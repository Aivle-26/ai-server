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
