from __future__ import annotations

import os
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


load_dotenv()


class CommunicationRiskDecision(BaseModel):
    communication_risk_level: Literal["HIGH", "MEDIUM", "LOW"]
    reasons: list[str] = Field(min_length=1, max_length=3)
    evidence_message_ts: list[str] = Field(max_length=3)
    recommended_action: str


class CommunicationLLMDecisionService:
    """Lets the LLM judge only a small, precomputed fact set and candidates."""

    def decide(
        self,
        facts: dict[str, Any],
        project_name: str | None,
        enabled: bool,
        fallback: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        if not enabled:
            return fallback, "DISABLED"
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return fallback, "SKIPPED_NO_API_KEY"

        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                temperature=0,
                api_key=api_key,
            ).with_structured_output(CommunicationRiskDecision)
            decision = llm.invoke({
                "role": "IT project communication risk analyst",
                "project_name": project_name or "unnamed project",
                "facts": facts,
                "instruction": (
                    "Return HIGH, MEDIUM, or LOW for the project communication risk. "
                    "Use only the supplied facts and candidate messages; do not invent facts. "
                    "Give at most three short Korean reasons, choose evidence_message_ts only "
                    "from candidate_messages, and provide one practical PM action."
                ),
            }).model_dump()
            valid_ts = {item["message_ts"] for item in facts["candidate_messages"]}
            decision["evidence_message_ts"] = [
                message_ts
                for message_ts in decision["evidence_message_ts"]
                if message_ts in valid_ts
            ]
            return decision, "SUCCEEDED"
        except Exception:
            return fallback, "FALLBACK"
