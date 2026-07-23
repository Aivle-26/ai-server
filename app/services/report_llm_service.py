import json
import os
import re
from datetime import datetime

from app.schemas.report import (
    DeliverableRagRequest,
    DeliverableRagResponse,
    FinalReportRequest,
    FinalReportResponse,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    RagSource,
    WeeklyReportRequest,
    WeeklyReportResponse,
)


class ReportLlmService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")

    def _parse_json_content(self, content: str) -> dict:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"^```\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        return json.loads(cleaned)

    def _call_llm_json(self, prompt: str) -> dict | None:
        if not self.api_key:
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
                            "프로젝트 회의록, WBS, 보고서, 산출물 문서를 분석하여 "
                            "PM 의사결정에 필요한 구조화된 JSON을 생성한다. "
                            "반드시 JSON만 반환하고, JSON 밖에는 어떤 설명도 쓰지 않는다."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or "{}"
            return self._parse_json_content(content)
        except Exception:
            return None

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
4. 담당자가 없는 작업은 인력/역할 리스크로 언급한다.
5. open_risks는 과장하지 말고 입력된 내용만 근거로 요약한다.
6. 다음 주 계획은 지연 작업, 진행 중 작업, 열린 리스크를 기준으로 작성한다.
7. 보고서 문체는 PM이 팀원 또는 관리자에게 공유하는 공식적이고 간결한 문체로 작성한다.
8. 입력 데이터에 없는 내용은 추측하지 않는다.
9. JSON 외의 설명 문장은 절대 출력하지 않는다.

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