from fastapi import APIRouter, HTTPException

from .graph import PlanningResourceGraph
from .llm_service import (
    ResourceLLMConfigurationError,
    ResourceLLMGenerationError,
)
from .schemas import PlanningResourceRequest, PlanningResourceResponse


router = APIRouter(
    prefix="/api/v1/planning/resources",
    tags=["Planning Resources"],
)
planning_resource_graph = PlanningResourceGraph()


@router.post(
    "/recommend",
    response_model=PlanningResourceResponse,
    summary="프로젝트 필요 인력·담당자·MM 추천",
    description=(
        "선택된 WBS TASK 일정과 프로젝트 참여자의 역할·기술·숙련도·경력·"
        "주간 가용시간을 바탕으로 TASK별 공수와 MM, 역할별 필요 인력 및 "
        "추천 담당자를 반환합니다."
    ),
)
def recommend_planning_resources(request: PlanningResourceRequest) -> dict:
    try:
        return planning_resource_graph.invoke(request)
    except ResourceLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ResourceLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
