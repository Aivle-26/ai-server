# AI Project Management Server

프로젝트 문서와 협업 데이터를 AI로 분석하여 프로젝트 관리 업무를 지원하는 FastAPI 기반 AI 서버입니다.
백엔드 요청이 있을 때 분석 결과를 JSON으로 반환합니다.

## 주요 기능

- 프로젝트 초기 문서 정보·요구사항 추출
- WBS 생성
- 일정 추천
- 필요 인력·담당자·MM 추천
- 예상 견적 생성
- 커뮤니케이션 및 프로젝트 위험 분석
- 회의·주간·최종 보고서 생성

## 구조

기능별 코드는 `app/domains` 아래에서 각자의 router, graph, schema와 service를 관리합니다.
`app/main.py`는 FastAPI 생성, 상태 확인과 도메인 라우터 조립만 담당합니다.

```text
app/
|-- core/
|-- domains/
|   |-- communication_risk/
|   |-- planning_documents/
|   |-- planning_wbs/
|   |-- planning_schedule/
|   |-- planning_resources/
|   |-- planning_costs/
|   |-- project_risk/
|   `-- reporting/
`-- main.py

tests/
`-- domains/
```

## 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

프로젝트 루트의 `.env`에 OpenAI 설정을 입력합니다.

```env
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
PLANNING_ANALYSIS_TIMEOUT_SECONDS=180
PLANNING_MAX_ANALYSIS_CHUNKS=2
PLANNING_ANALYSIS_RETRY_COUNT=0
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

실행 후 [Swagger UI](http://127.0.0.1:8000/docs)에서 API를 확인할 수 있습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```
