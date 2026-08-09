"""KOSA 직무별 공수 산정 흐름."""

from __future__ import annotations

from typing import Any

from .effort_llm_service import PlanningEffortLLMService
from .effort_schemas import PlanningEffortEstimateRequest
from .effort_service import PlanningEffortService


class PlanningEffortGraph:
    def __init__(
        self,
        effort_service: PlanningEffortService | None = None,
        llm_service: PlanningEffortLLMService | None = None,
    ) -> None:
        self.effort_service = effort_service or PlanningEffortService()
        self.llm_service = llm_service or PlanningEffortLLMService()

    def invoke(self, request: PlanningEffortEstimateRequest) -> dict[str, Any]:
        context = self.effort_service.prepare_context(request)
        generated = self.llm_service.generate(context)
        return self.effort_service.build_response(request, generated)
