import json
import os
from typing import Any

from openai import OpenAI

from app.schemas.report import LLMStatus


class ReportLLMService:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def analyze_meeting(
        self,
        project_name: str,
        meeting_title: str,
        meeting_text: str,
        enabled: bool = True,
    ) -> tuple[dict[str, Any], LLMStatus]:
        if not enabled:
            return self._fallback_result(meeting_text), "FALLBACK"

        if not self.client:
            return self._fallback_result(meeting_text), "SKIPPED_NO_API_KEY"

        try:
            prompt = self._build_meeting_prompt(
                project_name=project_name,
                meeting_title=meeting_title,
                meeting_text=meeting_text,
            )

            response = self.client.responses.create(
                model=self.model,
                input=prompt,
                temperature=0.2,
            )

            content = response.output_text
            parsed = json.loads(content)

            return parsed, "SUCCEEDED"

        except Exception:
            return self._fallback_result(meeting_text), "FALLBACK"

    def _build_meeting_prompt(
        self,
        project_name: str,
        meeting_title: str,
        meeting_text: str,
    ) -> str:
        return f"""
너는 PM AI Agent의 Report Agent이다.
아래 회의록을 분석하여 프로젝트 관리에 필요한 정보를 JSON으로 추출하라.

프로젝트명: {project_name}
회의 제목: {meeting_title}

분석 목표:
1. 회의 요약
2. 결정사항 로그 추출
3. 액션 아이템 추출
4. 이슈/리스크 변경 후보 추출
5. 담당자 누락, 마감일 누락이 있으면 표시

반드시 아래 JSON 형식만 반환하라. Markdown은 쓰지 마라.

{{
  "meeting_summary": "회의 요약",
  "decision_logs": [
    {{
      "decision_title": "결정사항 제목",
      "decision_detail": "결정사항 상세",
      "related_requirement_id": null,
      "related_wbs_id": null,
      "owner": null,
      "source_excerpt": "근거 문장"
    }}
  ],
  "action_items": [
    {{
      "action_item": "해야 할 일",
      "owner": "담당자 또는 null",
      "due_date": "YYYY-MM-DD 또는 null",
      "status": "TODO",
      "related_requirement_id": null,
      "related_wbs_id": null,
      "source_excerpt": "근거 문장"
    }}
  ],
  "issue_risk_changes": [
    {{
      "risk_title": "리스크 제목",
      "risk_type": "일정/커뮤니케이션/요구사항/품질/기타",
      "change_type": "NEW",
      "risk_level": "LOW 또는 MEDIUM 또는 HIGH",
      "reason": "판단 사유",
      "related_issue_id": null,
      "related_requirement_id": null,
      "related_wbs_id": null,
      "source_excerpt": "근거 문장"
    }}
  ]
}}

회의록:
{meeting_text}
""".strip()

    def _fallback_result(self, meeting_text: str) -> dict[str, Any]:
        short_text = meeting_text[:300].replace("\n", " ")

        return {
            "meeting_summary": f"LLM 분석을 사용할 수 없어 회의록 앞부분을 기반으로 임시 요약을 생성했습니다: {short_text}",
            "decision_logs": [],
            "action_items": [],
            "issue_risk_changes": [],
        }