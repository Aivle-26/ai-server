from fastapi import APIRouter, HTTPException

from .effort_graph import PlanningEffortGraph
from .effort_llm_service import (
    EffortLLMConfigurationError,
    EffortLLMGenerationError,
)
from .effort_schemas import (
    PlanningEffortEstimateRequest,
    PlanningEffortEstimateResponse,
)
from .effort_service import InvalidEffortLLMResponseError
from .graph import PlanningCostGraph
from .llm_service import CostLLMConfigurationError, CostLLMGenerationError
from .schemas import PlanningCostRequest, PlanningCostResponse


router = APIRouter(
    prefix="/api/v1/planning/costs",
    tags=["Planning Costs"],
)
planning_cost_graph = PlanningCostGraph()
planning_effort_graph = PlanningEffortGraph()


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


@router.post(
    "/effort-estimate",
    response_model=PlanningEffortEstimateResponse,
    summary="KOSA 직무별 프로젝트 공수 산정",
    description=(
        "WBS별로 2026년 적용 KOSA 세부직무와 예상 인일을 AI가 산정하고, "
        "공식 상위직무를 서버에서 매핑합니다. 20.5 근무일을 1 M/M으로 적용한 "
        "WBS별 상세 근거와 세부직무별 합계를 반환합니다."
    ),
)
def estimate_planning_effort(
    request: PlanningEffortEstimateRequest,
) -> dict:
    try:
        return planning_effort_graph.invoke(request)
    except EffortLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (EffortLLMGenerationError, InvalidEffortLLMResponseError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
