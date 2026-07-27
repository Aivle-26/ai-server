from fastapi import APIRouter, HTTPException

from .graph import PlanningCostGraph
from .llm_service import CostLLMConfigurationError, CostLLMGenerationError
from .schemas import PlanningCostRequest, PlanningCostResponse


router = APIRouter(
    prefix="/api/v1/planning/costs",
    tags=["Planning Costs"],
)
planning_cost_graph = PlanningCostGraph()


@router.post(
    "/estimate",
    response_model=PlanningCostResponse,
    summary="프로젝트 예상 견적 생성",
    description=(
        "앞서 계산한 WBS별 MM과 사용자가 선택한 단가·운영 조건을 바탕으로 "
        "인건비, 서버비, 라이선스비, AI API 비용과 예비비 10%를 적용한 "
        "단일 권장 견적을 반환합니다."
    ),
)
def estimate_planning_cost(request: PlanningCostRequest) -> dict:
    try:
        return planning_cost_graph.invoke(request)
    except CostLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CostLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
