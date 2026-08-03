from fastapi import APIRouter, HTTPException

from .graph import PlanningWBSGraph
from .llm_service import WBSLLMConfigurationError, WBSLLMGenerationError
from .schemas import WBSGenerationRequest, WBSGenerationResponse


router = APIRouter(
    prefix="/api/v1/planning/wbs",
    tags=["Planning WBS"],
)
planning_wbs_graph = PlanningWBSGraph()


@router.post(
    "/generate",
    response_model=WBSGenerationResponse,
    summary="프로젝트 WBS 작업분해구조 생성",
    description=(
        "프로젝트 기본정보와 요구사항을 바탕으로 일정·담당자를 제외한 "
        "PHASE, WORK_PACKAGE, TASK 3단계 WBS를 생성합니다."
    ),
)
def generate_planning_wbs(request: WBSGenerationRequest) -> dict:
    try:
        return planning_wbs_graph.invoke(request)
    except WBSLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WBSLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
