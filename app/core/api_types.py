from typing import Annotated, Literal

from pydantic import Field


LLMStatus = Literal[
    "SUCCEEDED",
    "SKIPPED_NO_API_KEY",
    "FALLBACK",
    "DISABLED",
]

PositiveId = Annotated[int, Field(gt=0)]
ProjectId = PositiveId
RequirementId = PositiveId
WbsId = PositiveId
MemberId = PositiveId
