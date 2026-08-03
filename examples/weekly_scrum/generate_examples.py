import json
from pathlib import Path
import sys
import shutil

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


OUTPUT_DIR = Path(__file__).resolve().parent
client = TestClient(app)


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


summarize_request = {
    "project_id": 1,
    "project_name": "AI Multi Agent 기반 프로젝트 통합 관리 플랫폼",
    "week_start": "2026-07-27",
    "week_end": "2026-08-02",
    "sprint_goal": "프로젝트 생성 기능과 주간 스크럼 AI 파이프라인 구현",
    "expected_members": ["김남효", "정다영", "윤명세", "박승원", "이서연"],
    "team_members": [
        {
            "member_id": "AI-01",
            "member_name": "김남효",
            "role": "AI",
            "skills": ["Python", "LLM"],
            "availability_hours": 40,
            "current_workload_hours": 34
        },
        {
            "member_id": "BE-01",
            "member_name": "정다영",
            "role": "BACKEND",
            "skills": ["Spring", "FastAPI"],
            "availability_hours": 40,
            "current_workload_hours": 38
        },
        {
            "member_id": "FE-01",
            "member_name": "윤명세",
            "role": "FRONTEND",
            "skills": ["React"],
            "availability_hours": 40,
            "current_workload_hours": 36
        },
        {
            "member_id": "QA-01",
            "member_name": "박승원",
            "role": "QA",
            "skills": ["Integration Test"],
            "availability_hours": 40,
            "current_workload_hours": 8
        }
    ],
    "member_updates": [
        {
            "member_id": "AI-01",
            "member_name": "김남효",
            "role": "AI",
            "weekly_goal": ["공통 데이터 스키마와 review Agent 구현"],
            "completed_tasks": [],
            "in_progress_tasks": [],
            "delayed_tasks": [
                {
                    "item_id": "TASK-SCHEMA",
                    "title": "공통 데이터 스키마 확정",
                    "description": "AI·백엔드·프론트가 사용할 JSON 계약을 확정한다.",
                    "task_type": "DATA",
                    "owner_id": "AI-01",
                    "owner": "김남효",
                    "due_date": "2026-08-01",
                    "status": "BLOCKED",
                    "done_condition": "4개 API OpenAPI 스키마 합의",
                    "estimated_hours": 10,
                    "carryover_count": 3,
                    "source_type": "WBS_TASK",
                    "source_reference_id": "WBS-AI-01",
                    "wbs_id": "WBS-AI-01",
                    "evidence_text": "데이터 형식 합의가 끝나지 않아 3주째 이월되고 있다."
                }
            ],
            "issues": [],
            "reported_risks": [],
            "next_week_tasks": [],
            "requests": []
        },
        {
            "member_id": "BE-01",
            "member_name": "정다영",
            "role": "BACKEND",
            "weekly_goal": ["프로젝트 생성 API 구현"],
            "completed_tasks": [
                {
                    "item_id": "TASK-BE-PROJECT-CREATE",
                    "title": "프로젝트 생성 API 구현",
                    "task_type": "BACKEND",
                    "owner_id": "BE-01",
                    "owner": "정다영",
                    "due_date": "2026-07-31",
                    "status": "DONE",
                    "integration_required": True,
                    "source_type": "JIRA_ISSUE",
                    "source_reference_id": "PM-101",
                    "requirement_id": "REQ-001",
                    "related_task_ids": ["TASK-FE-PROJECT-CREATE"],
                    "wbs_id": "WBS-BE-01",
                    "evidence_text": "프로젝트 생성 API 개발은 완료했지만 프론트 연동 테스트는 하지 못했다."
                }
            ],
            "in_progress_tasks": [],
            "delayed_tasks": [],
            "issues": [],
            "reported_risks": [],
            "next_week_tasks": [],
            "requests": []
        },
        {
            "member_id": "FE-01",
            "member_name": "윤명세",
            "role": "FRONTEND",
            "weekly_goal": ["프로젝트 생성 화면과 대시보드 연결"],
            "completed_tasks": [],
            "in_progress_tasks": [
                {
                    "item_id": "TASK-FE-PROJECT-CREATE",
                    "title": "프로젝트 생성 화면 연동",
                    "task_type": "FRONTEND",
                    "owner_id": "FE-01",
                    "owner": "윤명세",
                    "due_date": "2026-08-01",
                    "status": "IN_PROGRESS",
                    "integration_required": True,
                    "dependency_ids": ["TASK-SCHEMA", "TASK-BE-PROJECT-CREATE"],
                    "related_task_ids": ["TASK-BE-PROJECT-CREATE"],
                    "source_type": "JIRA_ISSUE",
                    "source_reference_id": "PM-102",
                    "requirement_id": "REQ-001",
                    "wbs_id": "WBS-FE-01",
                    "evidence_text": "화면은 구현했지만 API 응답 형식이 확정되지 않아 연동이 진행 중이다."
                }
            ],
            "delayed_tasks": [],
            "issues": [],
            "reported_risks": [],
            "next_week_tasks": [
                {
                    "item_id": "TASK-DASHBOARD",
                    "title": "대시보드 프로젝트 정보 연결",
                    "task_type": "FRONTEND",
                    "owner_id": "FE-01",
                    "owner": "윤명세",
                    "due_date": "2026-08-07",
                    "status": "TODO",
                    "estimated_hours": 12,
                    "dependency_ids": ["TASK-SCHEMA"],
                    "source_type": "WBS_TASK",
                    "source_reference_id": "WBS-FE-02",
                    "wbs_id": "WBS-FE-02",
                    "done_condition": "확정된 API 스키마로 대시보드 조회 성공"
                }
            ],
            "requests": []
        },
        {
            "member_id": "QA-01",
            "member_name": "박승원",
            "role": "QA",
            "weekly_goal": ["테스트 시나리오 준비"],
            "completed_tasks": [],
            "in_progress_tasks": [],
            "delayed_tasks": [],
            "issues": [],
            "reported_risks": [],
            "next_week_tasks": [],
            "requests": []
        }
    ],
    "enable_llm": False
}

save("01_summarize_request.json", summarize_request)
summarize_response = post(
    "/api/v1/reports/weekly-scrum/summarize",
    summarize_request,
)
save("01_summarize_response.json", summarize_response)

review_request = {
    "project_id": 1,
    "project_name": summarize_request["project_name"],
    "week_start": summarize_request["week_start"],
    "week_end": summarize_request["week_end"],
    "sprint_goal": summarize_request["sprint_goal"],
    "fact_summary": summarize_response["fact_summary"],
    "team_summary": summarize_response["team_summary"],
    "reference_documents": [
        {
            "document_id": "REF-001",
            "document_type": "FUNCTION_SPEC",
            "title": "주간 스크럼 Agent 필수 기능",
            "content": "사실과 AI 제안을 분리하고 누락, 모순, 의존성, 잠재 위험을 탐지한다. 연동 기능은 통합 테스트를 거쳐야 한다."
        }
    ],
    "analysis_date": "2026-08-02",
    "enable_llm": False
}
save("02_review_request.json", review_request)
review_response = post(
    "/api/v1/reports/weekly-scrum/review",
    review_request,
)
save("02_review_response.json", review_response)

recommend_request = {
    "project_id": 1,
    "project_name": summarize_request["project_name"],
    "week_start": summarize_request["week_start"],
    "week_end": summarize_request["week_end"],
    "fact_summary": summarize_response["fact_summary"],
    "team_summary": summarize_response["team_summary"],
    "review_findings": review_response["review_findings"],
    "next_week_start": "2026-08-03",
    "next_week_end": "2026-08-09",
    "enable_llm": False
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
    if finding.get("rule_code") == "TASK_STATUS_CONFLICT":
        decision.update({
            "review_status": "MODIFIED",
            "review_comment": "PM 확인 결과 상태 확정 업무로 반영합니다.",
            "pm_modified_title": "프로젝트 생성 기능 실제 상태 확정",
            "pm_modified_action": "FE·BE 담당자가 통합 완료 여부를 공동 확인합니다."
        })
    elif "미제출 팀원" in finding["title"]:
        decision.update({
            "review_status": "REJECTED",
            "review_comment": "해당 팀원은 이번 주 보고 대상이 아니므로 제외합니다."
        })
    else:
        decision["review_status"] = "APPROVED"
    reviewed_findings.append(decision)

reviewed_actions = []
integration_finding_id = next(
    finding["finding_id"]
    for finding in review_response["review_findings"]
    if finding.get("rule_code") == "MISSING_INTEGRATION_TEST"
)
overload_finding_id = next(
    finding["finding_id"]
    for finding in review_response["review_findings"]
    if finding.get("rule_code") == "MEMBER_OVERLOAD"
)
for action in recommend_response["recommended_next_actions"]:
    decision = dict(action)
    if action.get("source_finding_id") == integration_finding_id:
        decision.update({
            "review_status": "MODIFIED",
            "review_comment": "QA 담당자와 완료 조건을 확정합니다.",
            "pm_modified_owner_id": "QA-01",
            "pm_modified_owner": "박승원",
            "pm_modified_due_date": "2026-08-06",
            "pm_modified_priority": "HIGH",
            "pm_modified_done_condition": "프로젝트 생성 핵심 흐름 통합 테스트 통과"
        })
    elif action.get("source_finding_id") == overload_finding_id:
        decision.update({
            "review_status": "REJECTED",
            "review_comment": "동일 직군 가용 담당자가 없어 PM이 별도로 재배정하기 전까지 제외합니다."
        })
    else:
        decision["review_status"] = "APPROVED"
    reviewed_actions.append(decision)

finalize_request = {
    "project_id": 1,
    "project_name": summarize_request["project_name"],
    "week_start": summarize_request["week_start"],
    "week_end": summarize_request["week_end"],
    "fact_summary": summarize_response["fact_summary"],
    "team_summary": summarize_response["team_summary"],
    "reviewed_findings": reviewed_findings,
    "recommended_next_actions": reviewed_actions,
    "source_finding_count": review_response["finding_count"],
    "source_action_count": recommend_response["action_count"],
    "enable_llm": False
}
save("04_finalize_request.json", finalize_request)
finalize_response = post(
    "/api/v1/reports/weekly-scrum/finalize",
    finalize_request,
)
save("04_finalize_response.json", finalize_response)

print(
    "generated:",
    review_response["finding_count"],
    "findings,",
    recommend_response["action_count"],
    "actions",
)

# 기존 경로 호환성을 유지하면서 LLM=false 전용 폴더에도 같은 체인을 제공한다.
false_output_dir = OUTPUT_DIR / "llm_false"
false_output_dir.mkdir(exist_ok=True)
for example_file in OUTPUT_DIR.glob("0[1-4]_*.json"):
    shutil.copy2(example_file, false_output_dir / example_file.name)
