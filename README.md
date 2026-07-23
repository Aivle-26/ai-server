# AI Project Management Server

## 프로젝트 목적

프로젝트 문서와 협업 데이터를 AI로 분석하여 프로젝트 관리 업무를 지원하는 FastAPI 기반 AI 서버입니다.
백엔드의 요청을 받아 분석 결과를 JSON으로 반환합니다.

## 에이전트

- 커뮤니케이션 위험 분석: Slack 메시지에서 프로젝트 위험 신호를 분석합니다.
- 초기 문서 분석: 기획서, 제안서, RFP에서 프로젝트 정보와 요구사항을 추출합니다.
- WBS 생성: 프로젝트 정보와 요구사항을 바탕으로 작업분해구조를 생성합니다.

## 실행 방법

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

프로젝트 루트에 `.env` 파일을 만들고 OpenAI 설정을 입력합니다.

```env
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
```

서버를 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

실행 후 [Swagger UI](http://127.0.0.1:8000/docs)에서 API를 확인하고 테스트할 수 있습니다.

테스트는 다음 명령으로 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```
