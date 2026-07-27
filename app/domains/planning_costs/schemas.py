"""프로젝트 예상 견적 요청 및 응답 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ServiceScale = Literal["SMALL", "MEDIUM", "LARGE"]
PotentialCostType = Literal[
    "DATABASE",
    "STORAGE",
    "EXTERNAL_API",
    "SPECIAL_LICENSE",
    "MONITORING",
    "SECURITY_SOLUTION",
    "HARDWARE",
    "OUTSOURCING",
    "DATA_PURCHASE",
    "OTHER",
]
class CostWBSEffort(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wbs_id: int = Field(gt=0)
    wbs_name: str
    description: str
    estimated_mm: float = Field(gt=0, le=10_000)

    @model_validator(mode="after")
    def normalize_effort(self) -> "CostWBSEffort":
        self.wbs_name = self.wbs_name.strip()
        self.description = self.description.strip()
        if not self.wbs_name or not self.description:
            raise ValueError("WBS 작업명과 설명은 비어 있을 수 없습니다.")
        return self


class PlanningCostRequest(BaseModel):
    project_id: int = Field(gt=0)
    project_name: str
    wbs_efforts: list[CostWBSEffort] = Field(min_length=1, max_length=200)
    average_monthly_unit_price: int = Field(gt=0, le=1_000_000_000)
    operation_months: int = Field(ge=1, le=120)
    service_scale: ServiceScale
    uses_ai_api: bool = False
    paid_license_user_count: int = Field(default=0, ge=0, le=10_000)
    include_vat: bool = True

    @model_validator(mode="after")
    def validate_request(self) -> "PlanningCostRequest":
        self.project_name = self.project_name.strip()
        if not self.project_name:
            raise ValueError("프로젝트명은 비어 있을 수 없습니다.")

        wbs_ids = [effort.wbs_id for effort in self.wbs_efforts]
        if len(wbs_ids) != len(set(wbs_ids)):
            raise ValueError("WBS ID는 중복될 수 없습니다.")
        return self


class CostSummary(BaseModel):
    labor_cost: int = Field(ge=0)
    server_cost: int = Field(ge=0)
    license_cost: int = Field(ge=0)
    ai_api_cost: int = Field(ge=0)
    base_cost: int = Field(ge=0)


class RecommendedEstimate(BaseModel):
    contingency_rate: int = Field(ge=0, le=100)
    contingency_amount: int = Field(ge=0)
    supply_amount: int = Field(ge=0)
    vat: int = Field(ge=0)
    total_amount: int = Field(ge=0)


class PlanningCostResponse(BaseModel):
    project_id: int = Field(gt=0)
    currency: Literal["KRW"]
    total_estimated_mm: float = Field(gt=0)
    cost_summary: CostSummary
    estimate: RecommendedEstimate
    unpriced_items: list[str] = Field(default_factory=list)
    warning: str
