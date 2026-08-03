import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


SOURCE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SOURCE_DIR / "llm_true"
OUTPUT_DIR.mkdir(exist_ok=True)
client = TestClient(app)


def load(name: str) -> dict:
    return json.loads((SOURCE_DIR / name).read_text(encoding="utf-8"))


def save(name: str, payload: dict) -> None:
    (OUTPUT_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def post(path: str, payload: dict) -> dict:
    response = client.post(path, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"{path}: {response.status_code} {response.text}")
    return response.json()


summarize_request = load("01_summarize_request.json")
summarize_request["enable_llm"] = True
save("01_summarize_request.json", summarize_request)
summarize_response = post(
    "/api/v1/reports/weekly-scrum/summarize",
    summarize_request,
)
save("01_summarize_response.json", summarize_response)

review_request = {
    "project_id": summarize_request["project_id"],
    "project_name": summarize_request["project_name"],
    "week_start": summarize_request["week_start"],
    "week_end": summarize_request["week_end"],
    "sprint_goal": summarize_request["sprint_goal"],
    "fact_summary": summarize_response["fact_summary"],
    "team_summary": summarize_response["team_summary"],
    "reference_documents": [{
        "document_id": "REF-001",
        "document_type": "FUNCTION_SPEC",
        "title": "주간 스크럼 Agent 필수 기능",
        "content": (
            "사실과 AI 제안을 분리하고 누락, 모순, 의존성, 잠재 위험을 탐지한다. "
            "연동 기능은 통합 테스트를 거쳐야 한다."
        ),
    }],
    "analysis_date": "2026-08-02",
    "enable_llm": True,
}
save("02_review_request.json", review_request)
review_response = post(
    "/api/v1/reports/weekly-scrum/review",
    review_request,
)
save("02_review_response.json", review_response)

recommend_request = {
    "project_id": summarize_request["project_id"],
    "project_name": summarize_request["project_name"],
    "week_start": summarize_request["week_start"],
    "week_end": summarize_request["week_end"],
    "fact_summary": summarize_response["fact_summary"],
    "team_summary": summarize_response["team_summary"],
    "review_findings": review_response["review_findings"],
    "next_week_start": "2026-08-03",
    "next_week_end": "2026-08-09",
    "enable_llm": True,
}
save("03_recommend_request.json", recommend_request)
recommend_response = post(
    "/api/v1/reports/weekly-scrum/recommend-next-actions",
    recommend_request,
)
save("03_recommend_response.json", recommend_response)

reviewed_findings = []
for finding in review_response["review_findings"]:
    decision = dict(finding)
    if "미제출 팀원" in finding["title"]:
        decision.update({
            "review_status": "REJECTED",
            "review_comment": "해당 팀원은 이번 주 보고 대상이 아니므로 제외합니다.",
        })
    else:
        decision["review_status"] = "APPROVED"
    reviewed_findings.append(decision)

reviewed_actions = []
for action in recommend_response["recommended_next_actions"]:
    decision = dict(action)
    if action.get("source_finding_id") and any(
        finding["finding_id"] == action["source_finding_id"]
        and finding.get("rule_code") == "MISSING_INTEGRATION_TEST"
        for finding in review_response["review_findings"]
    ):
        decision.update({
            "review_status": "MODIFIED",
            "review_comment": "QA 담당자와 기한 및 완료 조건을 확정합니다.",
            "pm_modified_owner_id": "QA-01",
            "pm_modified_owner": "박승원",
            "pm_modified_due_date": "2026-08-06",
            "pm_modified_priority": "HIGH",
            "pm_modified_done_condition": "프로젝트 생성 핵심 흐름 통합 테스트 통과",
        })
    elif not (action.get("owner_id") or action.get("owner")):
        decision.update({
            "review_status": "REJECTED",
            "review_comment": "담당자가 확정되지 않아 PM 재배정 전까지 최종 계획에서 제외합니다.",
        })
    else:
        decision["review_status"] = "APPROVED"
    reviewed_actions.append(decision)

finalize_request = {
    "project_id": summarize_request["project_id"],
    "project_name": summarize_request["project_name"],
    "week_start": summarize_request["week_start"],
    "week_end": summarize_request["week_end"],
    "fact_summary": summarize_response["fact_summary"],
    "team_summary": summarize_response["team_summary"],
    "reviewed_findings": reviewed_findings,
    "recommended_next_actions": reviewed_actions,
    "source_finding_count": review_response["finding_count"],
    "source_action_count": recommend_response["action_count"],
    "enable_llm": True,
}
save("04_finalize_request.json", finalize_request)
finalize_response = post(
    "/api/v1/reports/weekly-scrum/finalize",
    finalize_request,
)
save("04_finalize_response.json", finalize_response)

print(
    "generated LLM=true:",
    review_response["finding_count"],
    "findings,",
    recommend_response["action_count"],
    "actions,",
    "final status",
    finalize_response["llm_status"],
)
