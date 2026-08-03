# Weekly Scrum 4단계 FastAPI 테스트

## 1. 서버 실행

프로젝트 루트에서 실행한다.

```powershell
uvicorn app.main:app --reload
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## 2. Swagger 실행 순서

각 API의 `Try it out`을 누르고 다음 요청 파일 내용을 순서대로 붙여 넣는다.

- `LLM=false` 완성 체인: `llm_false/`
- `LLM=true` 완성 체인: `llm_true/`

각 폴더의 `01`부터 `04` 요청 JSON은 직전 단계의 실제 응답이 이미 복사된 상태다. 서로 다른 폴더의 요청과 응답을 섞지 않는다.

1. `POST /api/v1/reports/weekly-scrum/summarize`
   - 요청: `01_summarize_request.json`
   - 확인용 실제 응답: `01_summarize_response.json`
2. `POST /api/v1/reports/weekly-scrum/review`
   - 요청: `02_review_request.json`
   - 확인용 실제 응답: `02_review_response.json`
3. `POST /api/v1/reports/weekly-scrum/recommend-next-actions`
   - 요청: `03_recommend_request.json`
   - 확인용 실제 응답: `03_recommend_response.json`
4. `POST /api/v1/reports/weekly-scrum/finalize`
   - 요청: `04_finalize_request.json`
   - 확인용 실제 응답: `04_finalize_response.json`

응답 파일은 현재 FastAPI 앱을 `TestClient`로 실제 호출하여 생성한 결과다.

## 3. 이 샘플에서 확인할 AI/규칙 로직

`review` 응답에서 다음 `rule_code`를 확인한다.

- `BLOCKED_BY_UNFINISHED_DEPENDENCY`: 공통 스키마 미완료로 후속 업무가 막힌 의존성
- `REPEATED_CARRYOVER`: 같은 지연 업무가 3주 연속 이월된 위험
- `MISSING_INTEGRATION_TEST`: 연동 필요 업무는 있지만 통합 테스트 계획이 없는 누락
- `MEMBER_OVERLOAD`: 다음 주 예상 업무량이 가용 시간을 초과한 업무 집중 위험

`recommend-next-actions` 응답에서는 다음을 확인한다.

- 여러 일정 관련 finding이 하나의 실행 업무로 통합됨
- QA 가용 담당자에게 통합 테스트가 추천됨
- 과부하 finding의 재배정 업무가 가용 담당자에게 추천됨
- 모든 추천 기한이 `next_week_start`와 `next_week_end` 사이임
- `source_finding_ids`로 하나의 action과 여러 finding의 관계를 추적할 수 있음
- 병합 후에도 `action_id`가 `ACT-WEEKLY-001`부터 연속으로 다시 부여됨

`finalize` 요청은 모든 finding/action에 `APPROVED`, `MODIFIED`, `REJECTED` 중 하나를 지정한다.
`REJECTED`에는 `review_comment`가 필수이며, `MODIFIED`에는 하나 이상의 PM 수정값이 필요하다.
최종 반영할 action은 담당자가 필수다. 담당자가 자동 결정되지 않은 action은 PM이 담당자를 지정해 `MODIFIED`로 제출하거나 `REJECTED`로 처리한다.

`excluded_next_actions`에는 PM의 원래 `review_status`와 별도로 시스템 최종 판정인 `effective_status`, `exclusion_reason`이 반환된다.

## 4. LLM 보강 테스트

기본 예제는 규칙 엔진의 재현성을 확인하기 위해 `enable_llm`이 `false`다.
OpenAI API 키가 설정된 환경에서 다음 두 요청의 `enable_llm`을 `true`로 변경하면 LLM 보강을 확인할 수 있다.

- `02_review_request.json`
- `03_recommend_request.json`

LLM 결과도 규칙 결과와 병합·중복 제거되고, 다음 주 범위를 벗어난 기한과 존재하지 않는 finding 연결은 후처리 단계에서 제거된다.

`item_id`는 기능 ID가 아니라 실제 업무 한 건의 고유 ID다. 같은 기능의 FE/BE 업무는 서로 다른 `item_id`를 사용하고 `related_task_ids` 또는 `dependency_ids`로 연결한다.

## 5. 예제 재생성

스키마나 로직을 변경한 후 다음 명령으로 요청·응답 파일을 다시 생성한다.

```powershell
python examples\weekly_scrum\generate_examples.py
```
