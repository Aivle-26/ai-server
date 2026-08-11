"""OpenAI-backed structured UI mockup design service."""

from __future__ import annotations

import json
import logging
import os
import time

from openai import APITimeoutError, OpenAI
from pydantic import ValidationError

from .ui_mockup import (
    UiMockupGenerationRequest,
    UiMockupNecessityDecision,
    UiMockupSpec,
)


logger = logging.getLogger("uvicorn.error")


class UiMockupLLMConfigurationError(RuntimeError):
    pass


class UiMockupLLMGenerationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        diagnostic_code: str | None = None,
        affected_count: int | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code
        self.affected_count = affected_count


class UiMockupLLMService:
    def generate(self, request: UiMockupGenerationRequest) -> UiMockupSpec:
        started_at = time.monotonic()
        requirement_count = len(request.confirmed_requirements)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise UiMockupLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")
        context = self._context(request)
        try:
            client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
        except Exception as exc:
            self._log_generation_failure(
                phase="client_init",
                exc=exc,
                started_at=started_at,
                requirement_count=requirement_count,
            )
            raise UiMockupLLMGenerationError("UI 목업 화면 설계 생성에 실패했습니다.") from exc
        try:
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=UiMockupSpec,
                store=False,
            )
        except ValidationError as exc:
            self._log_generation_failure(
                phase="structured_parse",
                exc=exc,
                started_at=started_at,
                requirement_count=requirement_count,
            )
            raise UiMockupLLMGenerationError("UI 목업 화면 설계 생성에 실패했습니다.") from exc
        except Exception as exc:
            self._log_generation_failure(
                phase="openai_request",
                exc=exc,
                started_at=started_at,
                requirement_count=requirement_count,
            )
            raise UiMockupLLMGenerationError("UI 목업 화면 설계 생성에 실패했습니다.") from exc
        if response.output_parsed is None:
            exc = UiMockupLLMGenerationError(
                "구조화된 UI 목업 설계가 반환되지 않았습니다.",
                diagnostic_code="UI_MOCKUP_STRUCTURED_OUTPUT_MISSING",
            )
            self._log_generation_failure(
                phase="structured_parse",
                exc=exc,
                started_at=started_at,
                requirement_count=requirement_count,
            )
            raise exc
        try:
            spec = self._validate_generated_spec(request, response.output_parsed)
        except UiMockupLLMGenerationError as exc:
            self._log_generation_failure(
                phase="spec_validation",
                exc=exc,
                started_at=started_at,
                requirement_count=requirement_count,
            )
            raise
        self._log_generation_success(started_at=started_at, spec=spec)
        return spec

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, round((time.monotonic() - started_at) * 1000))

    @classmethod
    def _log_generation_failure(
        cls,
        *,
        phase: str,
        exc: Exception,
        started_at: float,
        requirement_count: int,
    ) -> None:
        cause = exc.__cause__ or exc.__context__
        timeout = cls._is_timeout(exc) or (cause is not None and cls._is_timeout(cause))
        validation_errors = cls._safe_validation_errors(exc)
        payload: dict[str, object] = {
            "event": "ui_mockup_generation_failed",
            "phase": phase,
            "exception_type": type(exc).__name__,
            "cause_type": type(cause).__name__ if cause is not None else None,
            "timeout": timeout,
            "validation_error_count": len(exc.errors())
            if isinstance(exc, ValidationError)
            else 0,
            "elapsed_ms": cls._elapsed_ms(started_at),
            "confirmed_requirement_count": requirement_count,
        }
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            payload["status_code"] = status_code
        if validation_errors:
            payload["validation_errors"] = validation_errors
        if isinstance(exc, UiMockupLLMGenerationError):
            if exc.diagnostic_code:
                payload["rule_code"] = exc.diagnostic_code
            if exc.affected_count is not None:
                payload["affected_count"] = exc.affected_count
        logger.error(
            "ui_mockup_generation_diagnostic %s",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    @classmethod
    def _log_generation_success(
        cls,
        *,
        started_at: float,
        spec: UiMockupSpec,
    ) -> None:
        payload = {
            "event": "ui_mockup_generation_succeeded",
            "phase": "success",
            "elapsed_ms": cls._elapsed_ms(started_at),
            "screen_count": len(spec.screens),
            "journey_count": len(spec.journeys),
        }
        logger.info(
            "ui_mockup_generation_diagnostic %s",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def _is_timeout(exc: BaseException) -> bool:
        return isinstance(exc, (APITimeoutError, TimeoutError)) or type(exc).__name__ in {
            "ConnectTimeout",
            "ReadTimeout",
            "WriteTimeout",
            "PoolTimeout",
        }

    @staticmethod
    def _safe_validation_errors(exc: Exception) -> list[dict[str, object]]:
        if not isinstance(exc, ValidationError):
            return []
        safe_errors = []
        for error in exc.errors()[:10]:
            safe_errors.append(
                {
                    "loc": [
                        item if isinstance(item, int) else str(item)[:80]
                        for item in error.get("loc", ())
                    ],
                    "type": str(error.get("type", ""))[:120],
                    "msg": str(error.get("msg", ""))[:240],
                }
            )
        return safe_errors

    def assess(
        self,
        request: UiMockupGenerationRequest,
    ) -> UiMockupNecessityDecision:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise UiMockupLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")
        context = self._context(request)
        try:
            client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._assessment_instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=UiMockupNecessityDecision,
                store=False,
            )
        except Exception as exc:
            raise UiMockupLLMGenerationError(
                "UI 목업 필요성 판단에 실패했습니다."
            ) from exc
        if response.output_parsed is None:
            raise UiMockupLLMGenerationError(
                "구조화된 UI 목업 필요성 판단이 반환되지 않았습니다."
            )

        decision = response.output_parsed
        allowed_ids = {
            requirement.requirement_id
            for requirement in request.confirmed_requirements
        }
        unknown_ids = set(decision.evidence_requirement_ids) - allowed_ids
        if unknown_ids:
            raise UiMockupLLMGenerationError(
                "UI 목업 필요성 판단에 입력되지 않은 요구사항 ID가 포함되었습니다."
            )
        return decision

    @staticmethod
    def _context(request: UiMockupGenerationRequest) -> dict:
        return {
            "project_title": request.project_title,
            "project_description": request.project_description,
            "confirmed_requirements": [
                {
                    "id": requirement.requirement_id,
                    "title": requirement.title,
                    "description": requirement.description,
                    "category": requirement.category,
                    "priority": requirement.priority,
                }
                for requirement in request.confirmed_requirements
            ],
        }

    @staticmethod
    def _validate_generated_spec(
        request: UiMockupGenerationRequest,
        spec: UiMockupSpec,
    ) -> UiMockupSpec:
        allowed_ids = {
            requirement.requirement_id
            for requirement in request.confirmed_requirements
        }
        evidence_ids = {
            requirement_id
            for screen in spec.screens
            for requirement_id in screen.evidence_requirement_ids
        }
        journey_evidence_ids = {
            requirement_id
            for journey in spec.journeys
            for requirement_id in journey.evidence_requirement_ids
        }
        unknown_ids = (evidence_ids | journey_evidence_ids) - allowed_ids
        if unknown_ids:
            raise UiMockupLLMGenerationError(
                "UI 목업 화면에 입력되지 않은 요구사항 ID가 포함되었습니다.",
                diagnostic_code="UI_MOCKUP_UNKNOWN_EVIDENCE",
                affected_count=len(unknown_ids),
            )
        journeys_by_id = {
            journey.journey_id: journey for journey in spec.journeys
        }
        for screen in spec.screens:
            journey = journeys_by_id[screen.journey_id]
            outside_journey_ids = set(screen.evidence_requirement_ids) - set(
                journey.evidence_requirement_ids
            )
            if outside_journey_ids:
                raise UiMockupLLMGenerationError(
                    "UI 목업 화면 근거가 연결된 여정의 요구사항 범위를 벗어났습니다.",
                    diagnostic_code="UI_MOCKUP_SCREEN_EVIDENCE_OUTSIDE_JOURNEY",
                    affected_count=len(outside_journey_ids),
                )
        for journey in spec.journeys:
            covered_ids = {
                requirement_id
                for screen in spec.screens
                if screen.journey_id == journey.journey_id
                for requirement_id in screen.evidence_requirement_ids
            }
            uncovered_ids = set(journey.evidence_requirement_ids) - covered_ids
            if uncovered_ids:
                raise UiMockupLLMGenerationError(
                    "UI 목업 여정의 요구사항이 화면 근거에 모두 연결되지 않았습니다.",
                    diagnostic_code="UI_MOCKUP_JOURNEY_EVIDENCE_NOT_COVERED",
                    affected_count=len(uncovered_ids),
                )
        return spec

    @staticmethod
    def _screen_selection_principles() -> str:
        return (
            "confirmed_requirements를 유일한 기능 source of truth로 사용하고 프로젝트명만으로 "
            "기능을 추측하지 마세요. Requirement → Actor → Goal → Journey → Screen 순서로 분석하세요. "
            "먼저 요구사항에서 actor와 목표를 분리하고 가장 중요한 primary actor의 end-to-end journey를 "
            "완성하세요. PARTNER나 ADMIN처럼 다른 actor의 명시적인 HIGH/MUST 요구사항이 충분할 때만 "
            "별도 journey를 추가하고 핵심 actor는 최대 3종으로 제한하세요. actor가 다른 화면을 같은 "
            "journey에 섞지 마세요. priority가 HIGH, MUST 또는 필수인 요구사항, 명시적인 화면 interaction, "
            "검색-예약-결제나 탐색-구매 같은 거래 흐름, 여러 요구사항이 연결되는 단계를 우선하세요. "
            "화면 개수를 목표로 삼지 말고 독립된 사용자 목표나 상태, 필수 거래 단계, 새 요구사항 coverage가 "
            "있을 때만 화면을 추가하세요. 같은 목표와 상태를 표현하는 인접 단계는 한 화면으로 합치고 "
            "중복 화면은 만들지 마세요. 핵심 흐름과 명시된 UI 요구사항 coverage가 충족되면 즉시 멈추되 "
            "복잡한 프로젝트에서도 전체 화면은 12개를 넘기지 마세요."
        )

    @classmethod
    def _instructions(cls) -> str:
        return (
            "당신은 확정 요구사항을 분석해 프로젝트 도메인과 사용자 흐름에 맞는 제품 UI를 "
            "설계하는 UX architect입니다. "
            + cls._screen_selection_principles()
            + " UiMockupSpec의 primary_actor, platform, journey_summary는 첫 번째 핵심 journey를 요약해야 "
            "합니다. journeys에는 primary journey를 먼저 넣고 각 journey_id, actor, goal, summary, platform, "
            "evidence_requirement_ids를 채우세요. screens는 journeys 순서대로 묶고 각 화면의 journey_id와 "
            "actor, platform을 연결하며 journey_step은 각 journey 안에서 1부터 끊김 없이 배열하세요. "
            "각 screen.evidence_requirement_ids에는 그 화면의 근거가 된 입력 requirement ID를 1~6개 넣고 "
            "연결된 journey의 evidence_requirement_ids에도 포함하세요. 입력에 없는 ID는 절대 만들지 마세요. "
            "단순 기능은 1~3개 화면이면 충분하며, 복잡한 흐름은 coverage가 늘어나는 만큼만 확장하되 최대 "
            "12개 화면으로 제한하세요. 화면명은 지역 서비스 검색 결과, 서비스 상세 및 "
            "예약, 결제 및 예약 확정처럼 도메인과 목표가 드러나야 하며 메인 화면, 목록 화면, 상세 "
            "화면 같은 generic 이름이나 서로 의미가 겹치는 화면명을 사용하지 마세요. 화면별 page_type, "
            "navigation_type, layout_type을 선택하세요. 모바일 사용자나 모바일 앱이 명시되면 해당 journey와 "
            "screen의 platform을 MOBILE로 선택하고 SIDEBAR를 사용하지 마세요. 예약 서비스는 검색-일정 "
            "선택-예약 확인, "
            "쇼핑몰은 상품 목록-상세-장바구니/주문, 커뮤니티는 피드-상세-작성처럼 요구사항의 "
            "실제 사용자 흐름을 우선하세요. 프로젝트 관리 제품일 때만 dashboard/sidebar를 사용하세요. "
            "REST API, batch, ETL처럼 화면이 필요하지 않은 프로젝트에서 생성이 강제되더라도 "
            "관리자 대시보드를 발명하지 말고 요구사항에 표현된 정보 범위만 시각화하세요. "
            "sections에는 근거 요구사항의 실제 interaction과 정보를 넣으세요. 검색창은 search_bar, "
            "필터는 filter_chips, 카테고리는 category_grid, 서비스 결과는 service_card, 지도는 "
            "map_preview, 날짜는 date_picker, 예약 시간은 time_slots, 옵션은 option_selector, 가격과 "
            "쿠폰은 price_summary, 결제 수단은 payment_methods, 리뷰는 review_summary를 사용하세요. "
            "필요하지 않은 semantic component를 억지로 넣지 말고 기존 component_type으로 충분하면 "
            "재사용하세요. 모든 문구는 짧은 한국어로 작성하세요. Pmate AI, 프로젝트/요구사항/일정/리스크 "
            "메뉴, 주간 보고서처럼 입력에 없는 "
            "우리 서비스의 브랜드나 기능을 넣지 마세요. 진행률, D-day, 건수, 매출처럼 요구사항에 "
            "근거가 없는 실제 수치를 만들지 마세요. 화면마다 section은 최대 6개, primary_actions는 "
            "최대 3개로 제한하고 요구사항에 없는 화면이나 기능은 추가하지 마세요."
        )

    @classmethod
    def _assessment_instructions(cls) -> str:
        return (
            "당신은 프로젝트 산출물 검토자입니다. 확정 요구사항만 근거로 UI 목업 필요성을 "
            "REQUIRED, RECOMMENDED, NOT_NEEDED 중 하나로 판단하세요. project_description은 "
            "보조 정보이며 confirmed_requirements가 가장 강한 근거입니다. "
            + cls._screen_selection_principles()
            + " 로그인, 대시보드, "
            "목록, 상세, 입력 폼, 관리 화면, 모바일 사용자 흐름처럼 실제 화면 interaction이 "
            "명시되면 REQUIRED입니다. 화면이 명시되지 않아도 운영자나 사용자가 처리 결과를 "
            "확인하는 흐름이 있으면 RECOMMENDED입니다. REST API, batch, ETL, data pipeline, "
            "infrastructure, model serving, pure library만 요구되면 NOT_NEEDED입니다. 기술명이나 "
            "프로젝트명만으로 UI를 추측하지 마세요. evidence_requirement_ids에는 입력된 confirmed "
            "requirement ID만 최대 5개 사용하세요. REQUIRED 또는 RECOMMENDED이면 요구사항에서 "
            "직접 예상 가능한 대표 화면만 최대 5개 제시하고, candidate_screens도 선택한 primary "
            "actor의 같은 journey 순서와 도메인별 화면명을 따르세요. reason은 PM이 이해할 수 있는 "
            "한국어 최대 두 문장으로 작성하고, 이 판단이 생성 API를 차단하지는 않습니다."
        )
