from fastapi import APIRouter, HTTPException

from .graph import PlanningScheduleGraph
from .llm_service import (
    ScheduleLLMConfigurationError,
    ScheduleLLMGenerationError,
)
from .schemas import PlanningScheduleRequest, PlanningScheduleResponse


router = APIRouter(
    prefix="/api/v1/planning/schedules",
    tags=["Planning Schedule"],
)
planning_schedule_graph = PlanningScheduleGraph()


@router.post(
    "/recommend",
    response_model=PlanningScheduleResponse,
    summary="WBS 기반 프로젝트 일정 추천",
    description=(
        "WBS 작업을 바탕으로 Monte Carlo 방식을 적용하여 각 WBS의 "
        "예상·권장·보수적 시작일과 종료일을 반환합니다."
    ),
)
def recommend_planning_schedule(request: PlanningScheduleRequest) -> dict:
    try:
        return planning_schedule_graph.invoke(request)
    except ScheduleLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScheduleLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
