import json
import logging
import os
import re
from datetime import date, datetime

from .schemas import (
    AiReviewFinding,
    DeliverableRagRequest,
    DeliverableRagResponse,
    FinalReportRequest,
    FinalReportResponse,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    NextWeekActionPlan,
    RagSource,
    ReferenceDocument,
    ReviewedAiReviewFinding,
    WeeklyReportRequest,
    WeeklyReportResponse,
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
                            "너는 PM AI 플랫폼의 Report Agent다. "
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

    def analyze_meeting(self, request: MeetingAnalysisRequest) -> MeetingAnalysisResponse | None:
        prompt = f"""
너는 PM AI 플랫폼의 Report Agent다.
아래 회의록을 분석하여 회의 요약, 결정 로그, 액션 아이템, 이슈 리스크 변경 후보를 JSON으로만 반환하라.

분석 기준:
1. 회의록에 실제로 존재하는 내용만 추출한다.
2. 결정 로그는 회의에서 확정된 결정사항만 작성한다.
3. 액션 아이템은 누가, 무엇을, 언제까지 해야 하는지를 추출한다.
4. 담당자가 명시되지 않으면 owner는 null로 둔다.
5. 마감일이 명시되지 않으면 due_date는 null로 둔다.
6. requirement_id, wbs_id가 문장에 있으면 반드시 related_requirement_id, related_wbs_id에 연결한다.
7. "이번 주 안에", "다음 회의 전까지"처럼 상대적 날짜는 회의일을 기준으로 확정 가능한 경우에만 YYYY-MM-DD로 변환한다.
8. 날짜를 확정할 수 없으면 null로 둔다.
9. 입력 회의록에 없는 내용은 절대 추측하지 않는다.
10. 모든 decision_logs, action_items, issue_risk_changes에는 반드시 source.excerpt를 포함한다.
11. source.excerpt는 판단 근거가 되는 회의록 원문 일부를 그대로 넣는다.
12. JSON 외의 설명 문장은 절대 출력하지 않는다.

허용 status:
- TODO
- IN_PROGRESS
- DONE
- BLOCKED

허용 change_type:
- NEW
- UPDATE
- CLOSE

허용 risk_level:
- LOW
- MEDIUM
- HIGH

리스크 유형은 다음 중 하나만 사용하라:
- 일정 리스크
- 요구사항 리스크
- 인력/역할 리스크
- 커뮤니케이션 리스크
- 품질/산출물 리스크
- 기술 리스크
- 비용/정산 리스크
- 보안/개인정보 리스크
- 외부 의존성 리스크
- 운영/유지보수 리스크
- 법·규제 리스크
- 기타

리스크 등급 기준:
- HIGH: 일정 지연, 담당자 부재, 산출물 미제출, 장애, 차단 이슈가 명확하고 프로젝트 진행에 즉시 영향이 있는 경우
- MEDIUM: 담당자, 마감일, 검토 상태가 불명확하거나 추적이 필요한 경우
- LOW: 단순 확인 또는 경미한 주의가 필요한 경우

반환 형식:
{{
  "meeting_summary": "회의 전체 내용을 2~3문장으로 요약",
  "decision_logs": [
    {{
      "decision_title": "결정사항 제목",
      "decision_detail": "결정사항 상세 설명",
      "related_requirement_id": null,
      "related_wbs_id": null,
      "owner": null,
      "source": {{
        "document_id": "{request.meeting_document.document_id}",
        "document_name": "{request.meeting_document.file_name}",
        "page": null,
        "excerpt": "근거 문장"
      }}
    }}
  ],
  "action_items": [
    {{
      "action_item": "해야 할 작업",
      "owner": null,
      "due_date": null,
      "status": "TODO",
      "related_requirement_id": null,
      "related_wbs_id": null,
      "source": {{
        "document_id": "{request.meeting_document.document_id}",
        "document_name": "{request.meeting_document.file_name}",
        "page": null,
        "excerpt": "근거 문장"
      }}
    }}
  ],
  "issue_risk_changes": [
    {{
      "risk_title": "리스크 제목",
      "risk_type": "리스크 유형",
      "change_type": "NEW",
      "risk_level": "LOW",
      "reason": "리스크로 판단한 이유",
      "related_issue_id": null,
      "related_requirement_id": null,
      "related_wbs_id": null,
      "source": {{
        "document_id": "{request.meeting_document.document_id}",
        "document_name": "{request.meeting_document.file_name}",
        "page": null,
        "excerpt": "근거 문장"
      }}
    }}
  ]
}}

프로젝트명:
{request.project_name}

회의일:
{request.meeting_document.meeting_date}

참석자:
{request.meeting_document.attendees}

회의록:
{request.meeting_document.text}
"""
        data = self._call_llm_json(prompt)
        if not data:
            return None

        try:
            action_items = data.get("action_items", [])
            risk_items = data.get("issue_risk_changes", [])

            return MeetingAnalysisResponse(
                project_id=request.project_id,
                meeting_summary=data.get("meeting_summary", ""),
                decision_logs=data.get("decision_logs", []),
                action_items=action_items,
                issue_risk_changes=risk_items,
                missing_owner_count=sum(
                    1 for item in action_items
                    if not item.get("owner")
                ),
                missing_due_date_count=sum(
                    1 for item in action_items
                    if not item.get("due_date")
                ),
                risk_missing_owner_count=sum(
                    1 for risk in risk_items
                    if "담당자" in risk.get("reason", "")
                    or "담당자" in risk.get("risk_title", "")
                ),
                risk_missing_link_count=sum(
                    1 for risk in risk_items
                    if not risk.get("related_issue_id")
                    and not risk.get("related_requirement_id")
                    and not risk.get("related_wbs_id")
                ),
                generated_at=datetime.now(),
                llm_status="SUCCEEDED",
            )
        except Exception:
            return None

    def generate_weekly_report(self, request: WeeklyReportRequest) -> WeeklyReportResponse | None:
        prompt = f"""
너는 PM AI 플랫폼의 Report Agent다.
아래 WBS 작업, 완료 액션 아이템, 열린 리스크를 바탕으로 PM이 공유할 수 있는 주간 보고서 초안을 JSON으로만 생성하라.

작성 기준:
1. WBS 작업의 status, progress_rate, due_date를 기준으로 진행 현황을 판단한다.
2. 완료 작업은 status가 DONE인 WBS와 completed_action_items를 기준으로 작성한다.
3. 지연 작업은 due_date가 주간 종료일 이전이면서 status가 DONE이 아닌 작업을 기준으로 작성한다.
4. assignee_id가 null인 작업은 담당자 미지정 작업으로 보고 인력/역할 리스크로 언급한다.
5. open_risks는 과장하지 말고 입력된 내용만 근거로 요약한다.
6. 다음 주 계획은 지연 작업, 진행 중 작업, 열린 리스크를 기준으로 작성한다.
7. 보고서 문체는 PM이 팀원 또는 관리자에게 공유하는 공식적이고 간결한 문체로 작성한다.
8. 입력 데이터에 없는 내용은 추측하지 않는다.
9. JSON 외의 설명 문장은 절대 출력하지 않는다.
10. 가능한 경우 requirement_id, wbs_id, deliverable_id를 보고서 내용에 함께 언급하여 추적 가능하게 작성한다.
반환 형식:
{{
  "progress_summary": "이번 주 전체 진행 상황 요약",
  "completed_work": ["완료된 작업명"],
  "delayed_work": ["지연되었거나 병목이 있는 작업명"],
  "risk_summary": ["주요 리스크 요약"],
  "next_week_plan": ["다음 주 계획"],
  "report_draft": "PM이 바로 공유할 수 있는 주간 보고서 초안"
}}

프로젝트명:
{request.project_name}

보고 기간:
{request.week_start} ~ {request.week_end}

WBS 작업 목록:
{[task.model_dump(mode="json") for task in request.wbs_tasks]}

완료 액션 아이템:
{[item.model_dump(mode="json") for item in request.completed_action_items]}

열린 리스크:
{[risk.model_dump(mode="json") for risk in request.open_risks]}
"""
        data = self._call_llm_json(prompt)
        if not data:
            return None

        try:
            return WeeklyReportResponse(
                project_id=request.project_id,
                week_start=request.week_start,
                week_end=request.week_end,
                progress_summary=data.get("progress_summary", ""),
                completed_work=data.get("completed_work", []),
                delayed_work=data.get("delayed_work", []),
                risk_summary=data.get("risk_summary", []),
                next_week_plan=data.get("next_week_plan", []),
                report_draft=data.get("report_draft", ""),
                generated_at=datetime.now(),
                llm_status="SUCCEEDED",
            )
        except Exception:
            return None

    def generate_final_report(self, request: FinalReportRequest) -> FinalReportResponse | None:
        prompt = f"""
너는 PM AI 플랫폼의 Report Agent다.
아래 승인된 보고서, 이행 결과, 잔여 리스크를 바탕으로 프로젝트 최종 보고서 초안을 JSON으로만 생성하라.

작성 기준:
1. 승인된 보고서 내용은 프로젝트 진행 과정의 공식 근거로 사용한다.
2. execution_results에서 status가 DONE인 항목은 완료 성과로 정리한다.
3. status가 PARTIAL 또는 NOT_DONE인 항목은 미완료 항목으로 정리한다.
4. remaining_risks는 프로젝트 종료 시점에 남은 리스크로 요약한다.
5. 최종 보고서에는 프로젝트 성과, 미완료 사항, 잔여 리스크, 후속 조치가 드러나야 한다.
6. 입력 데이터에 없는 성과나 수치를 임의로 만들지 않는다.
7. 문체는 고객 또는 관리자에게 제출 가능한 공식 보고서 문체로 작성한다.
8. JSON 외의 설명 문장은 절대 출력하지 않는다.

반환 형식:
{{
  "final_summary": "프로젝트 최종 요약",
  "achievement_summary": ["완료 성과 요약"],
  "incomplete_items": ["미완료 또는 부분 완료 항목"],
  "remaining_risk_summary": ["잔여 리스크 요약"],
  "final_report_draft": "최종 보고서 초안 본문"
}}

프로젝트명:
{request.project_name}

승인된 보고서:
{[report.model_dump(mode="json") for report in request.approved_reports]}

이행 결과:
{[result.model_dump(mode="json") for result in request.execution_results]}

잔여 리스크:
{[risk.model_dump(mode="json") for risk in request.remaining_risks]}
"""
        data = self._call_llm_json(prompt)
        if not data:
            return None

        try:
            return FinalReportResponse(
                project_id=request.project_id,
                final_summary=data.get("final_summary", ""),
                achievement_summary=data.get("achievement_summary", []),
                incomplete_items=data.get("incomplete_items", []),
                remaining_risk_summary=data.get("remaining_risk_summary", []),
                final_report_draft=data.get("final_report_draft", ""),
                generated_at=datetime.now(),
                llm_status="SUCCEEDED",
            )
        except Exception:
            return None

    def answer_deliverable_rag(
        self,
        request: DeliverableRagRequest,
        sources: list[RagSource],
    ) -> DeliverableRagResponse | None:
        prompt = f"""
너는 PM AI 플랫폼의 산출물 기반 RAG 챗봇이다.
아래 제공된 산출물 근거 문서만 사용하여 사용자의 질문에 답하라.

답변 기준:
1. 반드시 제공된 sources 안의 내용만 근거로 답변한다.
2. sources에 없는 내용은 추측하지 않는다.
3. 근거가 부족하면 "제공된 산출물 근거만으로는 확인할 수 없습니다."라고 답한다.
4. 답변은 짧고 명확하게 작성한다.
5. 가능한 경우 담당자, 날짜, 문서명, 페이지를 함께 언급한다.
6. JSON 외의 설명 문장은 절대 출력하지 않는다.
7. sources에 requirement_id, wbs_id, deliverable_id, review_status가 포함되어 있으면 답변에 함께 언급한다.

반환 형식:
{{
  "answer": "질문에 대한 답변"
}}

질문:
{request.question}

산출물 근거:
{[source.model_dump(mode="json") for source in sources]}
"""
        data = self._call_llm_json(prompt)
        if not data:
            return None

        try:
            return DeliverableRagResponse(
                project_id=request.project_id,
                answer=data.get("answer", ""),
                sources=sources,
                generated_at=datetime.now(),
                llm_status="SUCCEEDED",
            )
        except Exception:
            return None

