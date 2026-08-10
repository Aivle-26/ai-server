from fastapi import APIRouter, HTTPException

from .ui_mockup import (
    UiMockupConfigurationError,
    UiMockupGenerationRequest,
    UiMockupGenerationResponse,
    UiMockupRenderError,
    render_ui_mockup,
)
from .ui_mockup_service import (
    UiMockupLLMConfigurationError,
    UiMockupLLMGenerationError,
    UiMockupLLMService,
)


router = APIRouter(
    prefix="/api/v1/planning/ui-mockup",
    tags=["Planning UI Mockup"],
)
ui_mockup_service = UiMockupLLMService()


@router.post(
    "/generate",
    response_model=UiMockupGenerationResponse,
    summary="Generate a requirements-based UI mockup JPG",
)
def generate_ui_mockup(
    request: UiMockupGenerationRequest,
) -> UiMockupGenerationResponse:
    try:
        spec = ui_mockup_service.generate(request)
        rendered = render_ui_mockup(spec)
        return UiMockupGenerationResponse(
            project_id=request.project_id,
            mockup=spec,
            file_name=f"project-{request.project_id}-ui-mockup.jpg",
            image_base64=rendered.to_base64(),
            width=rendered.width,
            height=rendered.height,
        )
    except UiMockupLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UiMockupLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except UiMockupConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (UiMockupRenderError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
