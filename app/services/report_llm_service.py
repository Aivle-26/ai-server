import json
import logging
import os
import re
from datetime import date

from app.schemas.report import (
    AiReviewFinding,
    NextWeekActionPlan,
    ReferenceDocument,
    ReviewedAiReviewFinding,
    WeeklyScrumFactSummary,
    WeeklyScrumFinalizeRequest,
    WeeklyScrumSummarizeRequest,
    WeeklyTeamSummary,
)


logger = logging.getLogger(__name__)


class ReportLlmService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        logger.debug("Report LLM API key configured: %s", bool(self.api_key))

    def _parse_json_content(self, content: str) -> dict:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"^```\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        return json.loads(cleaned)

    def _call_llm_json(self, prompt: str) -> dict | None:
        if not self.api_key:
            logger.info("Report LLM disabled because OPENAI_API_KEY is missing")
            return None

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "너는 PM AI 플랫폼의 Weekly Scrum Review Agent다. "
                            "입력에 없는 사실을 만들지 않고, 사실과 추론을 구분한다. "
                            "반드시 JSON만 반환하고 JSON 밖에는 어떤 설명도 쓰지 않는다."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or "{}"
            logger.debug("Report LLM response received (length=%d)", len(content))
            return self._parse_json_content(content)
        except Exception as exc:
            logger.warning("Report LLM call failed: %s", exc)
            return None

    def summarize_weekly_scrum(
        self,
        request: WeeklyScrumSummarizeRequest,
        fact_summary: WeeklyScrumFactSummary,
        fallback_summary: WeeklyTeamSummary,
    ) -> dict | None:
        prompt = f"""
팀원별 주간 스크럼과 사실 기반 통합 데이터를 바탕으로 팀 전체 종합 요약을 작성하라.

중요 원칙:
1. 입력에 없는 사실을 만들지 않는다.
2. 팀원이 작성한 사실과 AI의 해석을 섞지 않는다.
3. 이슈와 위험을 구분한다.
4. executive_summary는 6문장 이내로 작성한다.
5. JSON만 반환한다.

반환 형식:
{{
  "overall_status": "ON_TRACK | AT_RISK | OFF_TRACK",
  "executive_summary": "팀 전체 핵심 요약",
  "team_progress": ["팀 차원의 주요 진행 사항"],
  "member_summaries": [
    {{
      "member_id": "user-01",
      "member_name": "이름",
      "role": "역할",
      "summary": "팀원별 요약",
      "key_completed_tasks": [],
      "key_in_progress_tasks": [],
      "key_issues": [],
      "key_risks": [],
      "next_week_focus": []
    }}
  ],
  "key_issues": [],
  "key_risks": [],
  "next_week_plan_summary": []
}}

프로젝트명:
{request.project_name}

보고 기간:
{request.week_start} ~ {request.week_end}

스프린트/주간 목표:
{request.sprint_goal}

팀원별 원본 스크럼:
{[update.model_dump(mode="json") for update in request.member_updates]}

사실 기반 통합 데이터:
{fact_summary.model_dump(mode="json")}

fallback 요약:
{fallback_summary.model_dump(mode="json")}
"""
        return self._call_llm_json(prompt)

    def review_weekly_scrum_against_references(
        self,
        project_name: str | None,
        fact_summary: WeeklyScrumFactSummary,
        team_summary: WeeklyTeamSummary,
        reference_documents: list[ReferenceDocument],
    ) -> dict | None:
        prompt = f"""
주간 스크럼 종합 요약과 기준문서를 비교하여 누락, 모순, 위험, 보강 후보를 찾아라.

중요 원칙:
1. 기준문서 또는 주간 스크럼에 근거가 있는 내용만 제안한다.
2. 근거가 약하면 confidence를 LOW로 둔다.
3. 확정 사실처럼 말하지 말고 검토 후보로 표현한다.
4. 이슈는 이미 발생한 문제, 위험은 앞으로 발생 가능성이 있는 문제다.
5. 이미 입력 JSON 구조에서 충족된 기준은 누락 후보로 생성하지 않는다.
   예를 들어 fact_summary와 team_summary가 별도 필드로 존재하면
   "fact_summary와 team_summary 분리 미흡" 후보를 만들지 않는다.
6. 기준문서의 모든 문장을 무조건 finding으로 만들지 않는다.
   실제 주간 스크럼 또는 종합 요약에서 부족하거나 충돌하는 경우에만 finding을 생성한다.
7. 같은 원인에서 나온 담당자 누락, 기한 누락, 대응 계획 누락은 가능하면 하나의 후보로 묶어 표현한다.
8. rule_code는 규칙 엔진 전용 필드이므로 기준문서 ID나 임의 값을 넣지 말고 null로 반환한다.
9. 기준문서 ID는 reference_document_ids에만 기록한다.
10. JSON만 반환한다.

반환 형식:
{{
  "review_findings": [
    {{
      "rule_code": null,
      "detection_source": "LLM",
      "reference_document_ids": ["REF-001"],
      "type": "MISSING_REQUIRED_WORK | MISSING_FOLLOW_UP | MISSING_RESPONSE_PLAN | POTENTIAL_RISK | DEPENDENCY | CONFLICT | MISSING_OWNER | MISSING_DUE_DATE | NEEDS_CLARIFICATION",
      "title": "검토 후보 제목",
      "description": "상세 설명",
      "evidence": [
        {{
          "source_type": "WEEKLY_SCRUM | REFERENCE_DOCUMENT | AI_INFERENCE",
          "member_id": null,
          "member_name": null,
          "role": null,
          "document_id": null,
          "document_title": null,
          "text": "근거 문장"
        }}
      ],
      "impact": "예상 영향",
      "recommended_action": "권고 조치",
      "confidence": "LOW | MEDIUM | HIGH",
      "target_item_ids": [],
      "suggested_owner_id": null,
      "suggested_owner": null,
      "suggested_due_date": null
    }}
  ]
}}

프로젝트명:
{project_name}

사실 기반 통합 데이터:
{fact_summary.model_dump(mode="json")}

LLM 종합 요약:
{team_summary.model_dump(mode="json")}

기준문서:
{[document.model_dump(mode="json") for document in reference_documents]}
"""
        return self._call_llm_json(prompt)

    def recommend_next_actions(
        self,
        project_name: str | None,
        fact_summary: WeeklyScrumFactSummary,
        team_summary: WeeklyTeamSummary,
        review_findings: list[AiReviewFinding],
        fallback_actions: list[NextWeekActionPlan],
        next_week_start: date,
        next_week_end: date,
    ) -> dict | None:
        prompt = f"""
주간 스크럼 요약과 검토 후보를 바탕으로 다음 주 실행 업무를 추천하라.

중요 원칙:
1. 기존 다음 주 계획은 유지한다.
2. 검토 후보에서 필요한 후속 업무를 추가한다.
3. 담당자, 기한, 우선순위, 완료 조건을 가능한 한 제안한다.
4. due_date는 {next_week_start}부터 {next_week_end} 사이만 허용한다.
5. 검토 후보에서 만든 업무는 source_finding_id를 반드시 유지한다.
6. 근거가 약한 항목은 reason에 확인 필요라고 적는다.
7. fallback 실행계획의 action_id와 source_item_id, source_finding_ids,
   dependency_action_ids, requirement_id, wbs_id, deliverable_id를 그대로 유지한다.
8. title은 위험 설명이 아니라 수행·확정·점검·조정처럼 실행 가능한 동사형 업무로 작성한다.
9. JSON만 반환한다.

반환 형식:
{{
  "recommended_next_actions": [
    {{
      "action_id": "ACT-WEEKLY-001",
      "source_item_id": null,
      "title": "다음 주 실행 업무",
      "owner_id": null,
      "owner": null,
      "due_date": null,
      "priority": "LOW | MEDIUM | HIGH",
      "done_condition": "완료 조건",
      "reason": "추천 이유",
      "source_finding_id": null,
      "source_finding_ids": [],
      "dependency_action_ids": [],
      "requirement_id": null,
      "wbs_id": null,
      "deliverable_id": null
    }}
  ]
}}

프로젝트명:
{project_name}

다음 주 실행 기간:
{next_week_start} ~ {next_week_end}

사실 기반 통합 데이터:
{fact_summary.model_dump(mode="json")}

팀 종합 요약:
{team_summary.model_dump(mode="json")}

검토 후보:
{[finding.model_dump(mode="json") for finding in review_findings]}

fallback 실행계획:
{[action.model_dump(mode="json") for action in fallback_actions]}
"""
        return self._call_llm_json(prompt)

    def finalize_weekly_scrum_report(
        self,
        request: WeeklyScrumFinalizeRequest,
        included_findings: list[ReviewedAiReviewFinding],
        excluded_findings: list[ReviewedAiReviewFinding],
        included_next_actions: list[NextWeekActionPlan],
        fallback_report: str,
    ) -> dict | None:
        prompt = f"""
PM 검토가 끝난 주간 스크럼 데이터를 바탕으로 최종 주간 프로젝트 상태 보고서를 작성하라.

중요 원칙:
1. APPROVED 또는 MODIFIED 항목만 최종 보고서에 반영한다.
2. PENDING 또는 REJECTED 항목은 최종 보고서에 포함하지 않는다.
3. MODIFIED 항목은 PM 수정 내용을 우선 사용한다.
4. 입력에 없는 사실을 만들지 않는다.
5. 사실 기반 업무와 AI 검토 결과를 구분한다.
6. 완료 업무, 진행 중 업무, 지연 업무, 이슈, 위험 섹션에는 fact_summary의 원본 항목만 작성한다.
7. PM이 수정 승인한 AI 검토 결과는 사실 기반 업무 섹션에 섞지 말고,
   반드시 "승인된 AI 검토 결과" 섹션에만 작성한다.
8. 동일한 AI 검토 결과를 여러 섹션에 중복 작성하지 않는다.
9. JSON만 반환한다.

반환 형식:
{{
  "final_report": "최종 주간 프로젝트 상태 보고서 본문"
}}

프로젝트명:
{request.project_name}

보고 기간:
{request.week_start} ~ {request.week_end}

사실 기반 통합 데이터:
{request.fact_summary.model_dump(mode="json")}

팀 종합 요약:
{request.team_summary.model_dump(mode="json")}

승인 또는 수정 승인된 검토 후보:
{[finding.model_dump(mode="json") for finding in included_findings]}

거절된 검토 후보:
{[finding.model_dump(mode="json") for finding in excluded_findings]}

최종 반영할 다음 주 실행계획:
{[action.model_dump(mode="json") for action in included_next_actions]}

fallback 보고서:
{fallback_report}
"""
        return self._call_llm_json(prompt)
