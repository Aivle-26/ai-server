from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.config.planning_cost_policy import (
    AI_API_MONTHLY_COST,
    CURRENCY,
    CONTINGENCY_RATE,
    LICENSE_MONTHLY_UNIT_PRICE,
    SERVER_MONTHLY_COST,
    VAT_RATE,
)
from app.schemas.planning_cost import PlanningCostRequest
from app.services.planning_cost_llm_service import GeneratedCostAnalysis


ONE_WON = Decimal("1")
MM_OUTPUT_PRECISION = Decimal("0.0001")


class PlanningCostService:
    def prepare_context(self, request: PlanningCostRequest) -> dict[str, Any]:
        return {
            "project_id": request.project_id,
            "project_name": request.project_name,
            "already_priced_cost_types": [
                "LABOR",
                "SERVER",
                "LICENSE",
                "AI_API",
            ],
            "wbs_items": [
                {
                    "wbs_id": effort.wbs_id,
                    "wbs_name": effort.wbs_name,
                    "description": effort.description[:500],
                }
                for effort in request.wbs_efforts
            ],
        }

    def calculate(
        self,
        request: PlanningCostRequest,
        analysis: GeneratedCostAnalysis,
    ) -> dict[str, Any]:
        monthly_rate = Decimal(request.average_monthly_unit_price)
        months = Decimal(request.operation_months)
        scale = request.service_scale

        total_mm = Decimal("0")
        labor_cost = Decimal("0")
        for effort in request.wbs_efforts:
            estimated_mm = Decimal(str(effort.estimated_mm))
            item_labor_cost = self._won(estimated_mm * monthly_rate)
            total_mm += estimated_mm
            labor_cost += item_labor_cost

        server_cost = self._won(SERVER_MONTHLY_COST[scale] * months)
        license_cost = self._won(
            LICENSE_MONTHLY_UNIT_PRICE
            * Decimal(request.paid_license_user_count)
            * months
        )
        ai_api_cost = (
            self._won(AI_API_MONTHLY_COST[scale] * months)
            if request.uses_ai_api
            else Decimal("0")
        )

        base_cost = labor_cost + server_cost + license_cost + ai_api_cost
        estimate = self._estimate_amount(base_cost, request.include_vat)
        return {
            "project_id": request.project_id,
            "currency": CURRENCY,
            "total_estimated_mm": self._mm(total_mm),
            "cost_summary": {
                "labor_cost": int(labor_cost),
                "server_cost": int(server_cost),
                "license_cost": int(license_cost),
                "ai_api_cost": int(ai_api_cost),
                "base_cost": int(base_cost),
            },
            "estimate": estimate,
            "unpriced_items": self._unpriced_items(analysis),
            "warning": (
                "초기 기획용 예상 견적으로 실제 클라우드 사용량, 라이선스 제품 및 "
                "계약 조건에 따라 금액이 달라질 수 있습니다."
            ),
        }

    def _estimate_amount(
        self,
        base_cost: Decimal,
        include_vat: bool,
    ) -> dict[str, int]:
        contingency_amount = self._won(base_cost * CONTINGENCY_RATE)
        supply_amount = base_cost + contingency_amount
        vat = self._won(supply_amount * VAT_RATE) if include_vat else Decimal("0")
        return {
            "contingency_rate": int(CONTINGENCY_RATE * Decimal("100")),
            "contingency_amount": int(contingency_amount),
            "supply_amount": int(supply_amount),
            "vat": int(vat),
            "total_amount": int(supply_amount + vat),
        }

    def _unpriced_items(
        self,
        analysis: GeneratedCostAnalysis,
    ) -> list[str]:
        result = []
        seen = set()
        for cost in analysis.potential_additional_costs:
            key = cost.cost_name.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(cost.cost_name)
        return result

    def _won(self, value: Decimal) -> Decimal:
        return value.quantize(ONE_WON, rounding=ROUND_HALF_UP)

    def _mm(self, value: Decimal) -> float:
        return float(value.quantize(
            MM_OUTPUT_PRECISION,
            rounding=ROUND_HALF_UP,
        ))
