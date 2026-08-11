from __future__ import annotations

import base64
import hashlib
import json
import os
import unittest
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from openai import APITimeoutError
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from app.domains.planning_resources.ui_mockup import (
    UiMockupGenerationRequest,
    UiMockupNecessityDecision,
    UiMockupSpec,
    _fit_text,
    render_ui_mockup,
)
from app.domains.planning_resources.ui_mockup_service import (
    UiMockupLLMGenerationError,
    UiMockupLLMService,
)
from app.main import app


def request_payload() -> dict:
    return {
        "project_id": 17,
        "project_title": "AIPM 프로젝트 관리 플랫폼",
        "project_description": "요구사항과 프로젝트 계획을 통합 관리합니다.",
        "confirmed_requirements": [
            {
                "requirement_id": 1,
                "title": "프로젝트 대시보드",
                "description": "진행률과 주요 일정을 한 화면에서 확인합니다.",
                "category": "FUNCTIONAL",
                "priority": "HIGH",
            },
            {
                "requirement_id": 2,
                "title": "요구사항 관리",
                "description": "확정 요구사항을 조회하고 상태를 관리합니다.",
                "category": "FUNCTIONAL",
                "priority": "HIGH",
            },
            {
                "requirement_id": 3,
                "title": "업무 상세 처리",
                "description": "담당 업무의 상세 정보와 상태를 확인하고 처리합니다.",
                "category": "FUNCTIONAL",
                "priority": "HIGH",
            },
        ],
    }


def mockup_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "AIPM 프로젝트 관리 플랫폼",
            "design_summary": "핵심 업무를 빠르게 파악하는 밝은 업무용 화면",
            "primary_actor": "PROJECT_MANAGER",
            "journey_summary": "프로젝트 현황 확인 → 요구사항 및 업무 확인 → 상세 처리",
            "platform": "WEB",
            "screens": [
                {
                    "screen_name": "프로젝트 대시보드",
                    "purpose": "진행 상태와 주요 업무를 요약합니다.",
                    "actor": "PROJECT_MANAGER",
                    "journey_step": 1,
                    "evidence_requirement_ids": [1],
                    "page_type": "DASHBOARD",
                    "navigation_type": "SIDEBAR",
                    "layout_type": "GRID",
                    "navigation": ["대시보드", "요구사항", "WBS"],
                    "sections": [
                        {
                            "title": "프로젝트 현황",
                            "component_type": "card",
                            "items": ["전체 진행률", "지연 작업", "다가오는 일정"],
                        },
                        {
                            "title": "주간 진행 추이",
                            "component_type": "chart",
                            "items": [],
                        },
                    ],
                    "primary_actions": ["새 작업", "보고서 보기"],
                },
                {
                    "screen_name": "요구사항 관리",
                    "purpose": "확정 요구사항과 상태를 확인합니다.",
                    "actor": "PROJECT_MANAGER",
                    "journey_step": 2,
                    "evidence_requirement_ids": [2],
                    "page_type": "LIST",
                    "navigation_type": "TABS",
                    "layout_type": "MASTER_DETAIL",
                    "navigation": ["전체", "확정", "검토"],
                    "sections": [
                        {
                            "title": "확정 요구사항",
                            "component_type": "table",
                            "items": ["기능명", "우선순위", "상태"],
                        }
                    ],
                    "primary_actions": ["요구사항 보기"],
                },
                {
                    "screen_name": "업무 상세 및 처리",
                    "purpose": "선택한 업무의 맥락과 상태를 확인하고 후속 작업을 처리합니다.",
                    "actor": "PROJECT_MANAGER",
                    "journey_step": 3,
                    "evidence_requirement_ids": [3],
                    "page_type": "DETAIL",
                    "navigation_type": "SIDEBAR",
                    "layout_type": "TWO_COLUMN",
                    "navigation": ["대시보드", "요구사항", "WBS"],
                    "sections": [
                        {
                            "title": "업무 상세",
                            "component_type": "card",
                            "items": ["담당자", "상태", "완료 조건"],
                        },
                        {
                            "title": "처리 이력",
                            "component_type": "list",
                            "items": ["상태 변경", "검토 의견"],
                        },
                    ],
                    "primary_actions": ["업무 상태 변경"],
                },
            ],
        }
    )


def mobile_booking_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "지역 생활 서비스 예약 앱",
            "design_summary": "일반 고객의 탐색부터 예약 및 결제 완료까지 이어지는 대표 모바일 흐름",
            "primary_actor": "CUSTOMER",
            "journey_summary": "탐색 → 서비스 상세 및 예약 → 결제 및 예약 완료",
            "platform": "MOBILE",
            "screens": [
                {
                    "screen_name": "위치 기반 서비스 탐색",
                    "purpose": "현재 위치에서 카테고리와 조건을 적용해 예약 가능한 서비스를 찾습니다.",
                    "actor": "CUSTOMER",
                    "journey_step": 1,
                    "evidence_requirement_ids": [1, 2, 3, 11],
                    "page_type": "BOOKING",
                    "navigation_type": "BOTTOM_NAV",
                    "layout_type": "FEED",
                    "navigation": ["홈", "검색", "예약", "마이"],
                    "sections": [
                        {
                            "title": "위치 및 키워드 검색",
                            "component_type": "search_bar",
                            "items": ["현재 위치에서 서비스 검색"],
                        },
                        {
                            "title": "서비스 카테고리",
                            "component_type": "category_grid",
                            "items": ["전체", "생활", "전문", "지역"],
                        },
                        {
                            "title": "검색 조건",
                            "component_type": "filter_chips",
                            "items": ["가격", "거리", "평점", "예약 가능"],
                        },
                        {
                            "title": "추천 및 검색 결과",
                            "component_type": "service_card",
                            "items": ["추천 서비스", "가까운 서비스", "예약 가능 서비스"],
                        },
                    ],
                    "primary_actions": ["서비스 상세 보기"],
                },
                {
                    "screen_name": "서비스 상세 및 예약 선택",
                    "purpose": "서비스 정보와 위치를 확인하고 예약 날짜, 시간, 옵션을 선택합니다.",
                    "actor": "CUSTOMER",
                    "journey_step": 2,
                    "evidence_requirement_ids": [4, 5, 6, 7],
                    "page_type": "DETAIL",
                    "navigation_type": "BOTTOM_NAV",
                    "layout_type": "FORM_FLOW",
                    "navigation": ["홈", "검색", "예약", "마이"],
                    "sections": [
                        {
                            "title": "서비스 정보",
                            "component_type": "service_card",
                            "items": ["서비스 이미지와 설명", "가격과 평점", "운영 시간"],
                        },
                        {
                            "title": "서비스 위치",
                            "component_type": "map_preview",
                            "items": ["지도 위치"],
                        },
                        {
                            "title": "예약 날짜",
                            "component_type": "date_picker",
                            "items": ["예약 가능 날짜"],
                        },
                        {
                            "title": "예약 가능 시간",
                            "component_type": "time_slots",
                            "items": ["09:00", "11:00", "14:00", "16:00"],
                        },
                        {
                            "title": "서비스 옵션",
                            "component_type": "option_selector",
                            "items": ["기본 옵션", "추가 옵션"],
                        },
                    ],
                    "primary_actions": ["예약하기"],
                },
                {
                    "screen_name": "결제 및 예약 확정",
                    "purpose": "예약 정보, 쿠폰, 결제 수단과 최종 금액을 확인해 예약을 완료합니다.",
                    "actor": "CUSTOMER",
                    "journey_step": 3,
                    "evidence_requirement_ids": [8, 9, 10],
                    "page_type": "FORM",
                    "navigation_type": "NONE",
                    "layout_type": "FORM_FLOW",
                    "navigation": [],
                    "sections": [
                        {
                            "title": "예약 정보 요약",
                            "component_type": "card",
                            "items": ["선택 서비스", "예약 날짜와 시간", "선택 옵션"],
                        },
                        {
                            "title": "쿠폰 및 최종 금액",
                            "component_type": "price_summary",
                            "items": ["선택 옵션", "쿠폰 할인", "최종 결제 금액"],
                        },
                        {
                            "title": "결제 수단",
                            "component_type": "payment_methods",
                            "items": ["카드 결제", "간편 결제"],
                        },
                        {
                            "title": "예약 완료 안내",
                            "component_type": "card",
                            "items": ["결제 완료 후 예약 번호와 일정을 확인"],
                        },
                    ],
                    "primary_actions": ["결제하고 예약 확정"],
                },
            ],
        }
    )


def ecommerce_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "로컬 브랜드 온라인 쇼핑몰",
            "design_summary": "상품 탐색에서 상세 확인과 주문으로 이어지는 웹 쇼핑 흐름",
            "primary_actor": "CUSTOMER",
            "journey_summary": "상품 탐색 → 상품 상세 → 장바구니 및 결제",
            "platform": "WEB",
            "screens": [
                {
                    "screen_name": "상품 탐색",
                    "purpose": "상품을 검색하고 카테고리별로 비교합니다.",
                    "actor": "CUSTOMER",
                    "journey_step": 1,
                    "evidence_requirement_ids": [1],
                    "page_type": "ECOMMERCE",
                    "navigation_type": "TOP_NAV",
                    "layout_type": "GRID",
                    "navigation": ["신상품", "카테고리", "장바구니"],
                    "sections": [
                        {
                            "title": "상품 검색",
                            "component_type": "search_bar",
                            "items": ["상품명 검색"],
                        },
                        {
                            "title": "상품 카테고리",
                            "component_type": "category_grid",
                            "items": ["리빙", "패션", "푸드", "지역 브랜드 상품"],
                        },
                        {
                            "title": "상품 결과",
                            "component_type": "service_card",
                            "items": ["신상품", "추천 상품", "지역 브랜드 상품"],
                        }
                    ],
                    "primary_actions": ["상품 보기"],
                },
                {
                    "screen_name": "상품 상세",
                    "purpose": "상품 정보와 배송 조건을 확인하고 장바구니에 담습니다.",
                    "actor": "CUSTOMER",
                    "journey_step": 2,
                    "evidence_requirement_ids": [2],
                    "page_type": "DETAIL",
                    "navigation_type": "TOP_NAV",
                    "layout_type": "TWO_COLUMN",
                    "navigation": ["상품", "리뷰", "배송"],
                    "sections": [
                        {
                            "title": "상품 정보",
                            "component_type": "service_card",
                            "items": ["상품 설명", "옵션 선택", "배송 안내"],
                        },
                        {
                            "title": "리뷰 요약",
                            "component_type": "review_summary",
                            "items": ["평점", "구매 후기"],
                        }
                    ],
                    "primary_actions": ["장바구니 담기"],
                },
                {
                    "screen_name": "장바구니 및 주문 결제",
                    "purpose": "선택 상품과 금액을 확인하고 결제 수단을 선택해 주문을 완료합니다.",
                    "actor": "CUSTOMER",
                    "journey_step": 3,
                    "evidence_requirement_ids": [3],
                    "page_type": "FORM",
                    "navigation_type": "TOP_NAV",
                    "layout_type": "FORM_FLOW",
                    "navigation": ["장바구니", "주문 정보", "결제"],
                    "sections": [
                        {
                            "title": "주문 상품",
                            "component_type": "card",
                            "items": ["선택 상품", "수량과 옵션"],
                        },
                        {
                            "title": "주문 금액",
                            "component_type": "price_summary",
                            "items": ["상품 금액", "배송비", "최종 결제 금액"],
                        },
                        {
                            "title": "결제 수단",
                            "component_type": "payment_methods",
                            "items": ["카드 결제", "간편 결제"],
                        },
                    ],
                    "primary_actions": ["주문 결제"],
                },
            ],
        }
    )


def api_etl_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "주문 데이터 ETL API",
            "design_summary": "요구사항에 명시된 데이터 입력과 변환 범위만 설명하는 화면",
            "primary_actor": "OPERATOR",
            "journey_summary": "API 입력 범위 확인 → ETL 변환 규칙 확인",
            "platform": "WEB",
            "screens": [
                {
                    "screen_name": "처리 범위 명세",
                    "purpose": "API 입력과 ETL 변환 규칙을 읽기 전용으로 확인합니다.",
                    "actor": "OPERATOR",
                    "journey_step": 1,
                    "evidence_requirement_ids": [1, 2],
                    "page_type": "DETAIL",
                    "navigation_type": "NONE",
                    "layout_type": "FULL_WIDTH",
                    "navigation": [],
                    "sections": [
                        {
                            "title": "API 입력",
                            "component_type": "list",
                            "items": ["주문 데이터 수집", "입력 형식 검증"],
                        },
                        {
                            "title": "ETL 변환",
                            "component_type": "list",
                            "items": ["필드 정규화", "저장 대상 전달"],
                        },
                    ],
                    "primary_actions": [],
                }
            ],
        }
    )


def community_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "동네 이야기 커뮤니티",
            "design_summary": "커뮤니티 회원이 글을 탐색하고 읽은 뒤 작성과 댓글 참여로 이어지는 흐름",
            "primary_actor": "COMMUNITY_MEMBER",
            "journey_summary": "피드 탐색 → 게시글 상세 및 댓글 → 글 작성",
            "platform": "MOBILE",
            "screens": [
                {
                    "screen_name": "관심 주제 피드 탐색",
                    "purpose": "관심 주제와 최신 게시글을 탐색합니다.",
                    "actor": "COMMUNITY_MEMBER",
                    "journey_step": 1,
                    "evidence_requirement_ids": [1],
                    "page_type": "LIST",
                    "navigation_type": "BOTTOM_NAV",
                    "layout_type": "FEED",
                    "navigation": ["피드", "검색", "작성", "내 활동"],
                    "sections": [
                        {
                            "title": "게시글 피드",
                            "component_type": "list",
                            "items": ["최신 글", "관심 주제", "인기 글"],
                        }
                    ],
                    "primary_actions": ["게시글 보기"],
                },
                {
                    "screen_name": "게시글 상세 및 댓글",
                    "purpose": "게시글 내용을 읽고 댓글로 의견을 나눕니다.",
                    "actor": "COMMUNITY_MEMBER",
                    "journey_step": 2,
                    "evidence_requirement_ids": [2],
                    "page_type": "DETAIL",
                    "navigation_type": "BOTTOM_NAV",
                    "layout_type": "FEED",
                    "navigation": ["피드", "검색", "작성", "내 활동"],
                    "sections": [
                        {
                            "title": "게시글 내용",
                            "component_type": "card",
                            "items": ["제목과 본문", "작성자", "작성 시각"],
                        },
                        {
                            "title": "댓글 대화",
                            "component_type": "list",
                            "items": ["댓글 목록", "답글"],
                        },
                    ],
                    "primary_actions": ["댓글 작성"],
                },
                {
                    "screen_name": "게시글 작성 및 발행",
                    "purpose": "주제와 내용을 입력해 새 게시글을 발행합니다.",
                    "actor": "COMMUNITY_MEMBER",
                    "journey_step": 3,
                    "evidence_requirement_ids": [3],
                    "page_type": "FORM",
                    "navigation_type": "BOTTOM_NAV",
                    "layout_type": "FORM_FLOW",
                    "navigation": ["피드", "검색", "작성", "내 활동"],
                    "sections": [
                        {
                            "title": "게시글 작성",
                            "component_type": "form",
                            "items": ["주제", "제목", "본문"],
                        }
                    ],
                    "primary_actions": ["게시글 발행"],
                },
            ],
        }
    )


def adaptive_screen(
    screen_name: str,
    purpose: str,
    journey_id: str,
    actor: str,
    platform: str,
    journey_step: int,
    evidence_requirement_ids: list[int],
    page_type: str,
    sections: list[tuple[str, str, list[str]]],
    *,
    navigation_type: str = "NONE",
    layout_type: str = "FULL_WIDTH",
    navigation: list[str] | None = None,
    primary_actions: list[str] | None = None,
) -> dict:
    return {
        "screen_name": screen_name,
        "purpose": purpose,
        "journey_id": journey_id,
        "actor": actor,
        "platform": platform,
        "journey_step": journey_step,
        "evidence_requirement_ids": evidence_requirement_ids,
        "page_type": page_type,
        "navigation_type": navigation_type,
        "layout_type": layout_type,
        "navigation": navigation or [],
        "sections": [
            {
                "title": title,
                "component_type": component_type,
                "items": items,
            }
            for title, component_type, items in sections
        ],
        "primary_actions": primary_actions or [],
    }


def simple_login_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "간편 회원 서비스",
            "design_summary": "이메일 로그인 후 개인 서비스를 시작하는 간결한 웹 흐름",
            "primary_actor": "CUSTOMER",
            "journey_summary": "이메일 로그인 → 개인 서비스 시작",
            "platform": "WEB",
            "journeys": [
                {
                    "journey_id": "CUSTOMER_ACCESS",
                    "actor": "CUSTOMER",
                    "goal": "계정으로 안전하게 서비스에 진입",
                    "summary": "이메일로 로그인하고 개인 시작 화면을 확인합니다.",
                    "platform": "WEB",
                    "evidence_requirement_ids": [1, 2],
                }
            ],
            "screens": [
                adaptive_screen(
                    "이메일 로그인",
                    "이메일과 비밀번호로 계정을 인증합니다.",
                    "CUSTOMER_ACCESS",
                    "CUSTOMER",
                    "WEB",
                    1,
                    [1],
                    "FORM",
                    [("계정 인증", "form", ["이메일", "비밀번호"])],
                    layout_type="FORM_FLOW",
                    primary_actions=["로그인"],
                ),
                adaptive_screen(
                    "개인 서비스 시작",
                    "로그인한 사용자가 자신의 서비스를 시작합니다.",
                    "CUSTOMER_ACCESS",
                    "CUSTOMER",
                    "WEB",
                    2,
                    [2],
                    "LANDING",
                    [("내 서비스", "card", ["최근 이용", "서비스 시작"])],
                    primary_actions=["서비스 시작"],
                ),
            ],
        }
    )


def adaptive_ecommerce_spec() -> UiMockupSpec:
    journey_id = "CUSTOMER_PURCHASE"
    common_navigation = ["상품", "카테고리", "장바구니", "주문"]
    return UiMockupSpec.model_validate(
        {
            "project_title": "로컬 브랜드 온라인 쇼핑몰",
            "design_summary": "상품 탐색부터 주문 완료까지 요구사항을 빠짐없이 잇는 웹 구매 흐름",
            "primary_actor": "CUSTOMER",
            "journey_summary": "탐색 → 상세 → 장바구니 → 배송 및 쿠폰 → 결제 완료",
            "platform": "WEB",
            "journeys": [
                {
                    "journey_id": journey_id,
                    "actor": "CUSTOMER",
                    "goal": "원하는 상품을 찾아 결제 완료",
                    "summary": "검색과 비교, 상세 확인, 장바구니, 배송 정보, 결제를 순서대로 진행합니다.",
                    "platform": "WEB",
                    "evidence_requirement_ids": [1, 2, 3, 4, 5],
                }
            ],
            "screens": [
                adaptive_screen(
                    "상품 검색 및 카테고리 탐색",
                    "키워드와 카테고리로 상품을 탐색합니다.",
                    journey_id,
                    "CUSTOMER",
                    "WEB",
                    1,
                    [1],
                    "ECOMMERCE",
                    [
                        ("상품 검색", "search_bar", ["상품명 검색"]),
                        ("카테고리", "category_grid", ["의류", "생활", "식품"]),
                        ("검색 조건", "filter_chips", ["가격", "평점", "배송"]),
                    ],
                    navigation_type="TOP_NAV",
                    layout_type="GRID",
                    navigation=common_navigation,
                    primary_actions=["상품 보기"],
                ),
                adaptive_screen(
                    "상품 상세 및 옵션 선택",
                    "상품 정보와 리뷰를 확인하고 옵션을 선택합니다.",
                    journey_id,
                    "CUSTOMER",
                    "WEB",
                    2,
                    [2],
                    "DETAIL",
                    [
                        ("상품 정보", "service_card", ["상품 이미지", "가격", "배송 조건"]),
                        ("상품 옵션", "option_selector", ["색상", "사이즈"]),
                        ("구매 후기", "review_summary", ["평점", "후기 요약"]),
                    ],
                    navigation_type="TOP_NAV",
                    layout_type="TWO_COLUMN",
                    navigation=common_navigation,
                    primary_actions=["장바구니 담기"],
                ),
                adaptive_screen(
                    "장바구니 상품 검토",
                    "선택 상품과 수량 및 금액을 검토합니다.",
                    journey_id,
                    "CUSTOMER",
                    "WEB",
                    3,
                    [3],
                    "ECOMMERCE",
                    [
                        ("선택 상품", "table", ["상품", "옵션", "수량"]),
                        ("주문 예정 금액", "price_summary", ["상품 금액", "배송비"]),
                    ],
                    navigation_type="TOP_NAV",
                    layout_type="TWO_COLUMN",
                    navigation=common_navigation,
                    primary_actions=["주문하기"],
                ),
                adaptive_screen(
                    "배송 정보 및 쿠폰 적용",
                    "배송지와 쿠폰을 입력해 최종 결제 금액을 확인합니다.",
                    journey_id,
                    "CUSTOMER",
                    "WEB",
                    4,
                    [4],
                    "FORM",
                    [
                        ("배송 정보", "form", ["받는 사람", "주소", "연락처"]),
                        ("쿠폰 및 금액", "price_summary", ["쿠폰 할인", "최종 금액"]),
                    ],
                    navigation_type="TABS",
                    layout_type="FORM_FLOW",
                    navigation=["장바구니", "배송", "결제"],
                    primary_actions=["결제로 이동"],
                ),
                adaptive_screen(
                    "결제 및 주문 완료",
                    "결제 수단을 선택하고 주문 결과를 확인합니다.",
                    journey_id,
                    "CUSTOMER",
                    "WEB",
                    5,
                    [5],
                    "FORM",
                    [
                        ("결제 수단", "payment_methods", ["카드", "간편 결제"]),
                        ("주문 요약", "price_summary", ["결제 금액", "배송지"]),
                        ("주문 완료", "card", ["주문 번호", "배송 예정 안내"]),
                    ],
                    navigation_type="TABS",
                    layout_type="FORM_FLOW",
                    navigation=["장바구니", "배송", "결제"],
                    primary_actions=["결제하기"],
                ),
            ],
        }
    )


def adaptive_mobile_rfp_spec() -> UiMockupSpec:
    customer_nav = ["홈", "검색", "예약", "마이"]
    customer_screens = [
        adaptive_screen(
            "고객 로그인 및 온보딩",
            "계정을 인증하고 위치 사용 안내를 확인합니다.",
            "CUSTOMER_BOOKING",
            "CUSTOMER",
            "MOBILE",
            1,
            [1, 21],
            "FORM",
            [("계정 인증", "form", ["이메일", "비밀번호", "위치 사용 동의"])],
            layout_type="FORM_FLOW",
            primary_actions=["로그인"],
        ),
        adaptive_screen(
            "위치 기반 홈 및 통합 검색",
            "위치, 키워드, 카테고리와 조건으로 예약 가능한 서비스를 찾습니다.",
            "CUSTOMER_BOOKING",
            "CUSTOMER",
            "MOBILE",
            2,
            [2, 3, 4, 5, 21],
            "BOOKING",
            [
                ("위치 및 키워드", "search_bar", ["현재 위치에서 검색"]),
                ("서비스 카테고리", "category_grid", ["청소", "수리", "레슨"]),
                ("검색 조건", "filter_chips", ["가격", "거리", "평점", "예약 가능"]),
                ("예약 가능 서비스", "service_card", ["가까운 서비스", "추천 서비스"]),
            ],
            navigation_type="BOTTOM_NAV",
            layout_type="FEED",
            navigation=customer_nav,
            primary_actions=["서비스 보기"],
        ),
        adaptive_screen(
            "서비스 상세 및 지도 확인",
            "서비스 정보와 리뷰 및 위치를 확인합니다.",
            "CUSTOMER_BOOKING",
            "CUSTOMER",
            "MOBILE",
            3,
            [6, 7, 21],
            "DETAIL",
            [
                ("서비스 정보", "service_card", ["설명", "가격", "운영 시간"]),
                ("서비스 위치", "map_preview", ["지도 위치"]),
                ("이용 후기", "review_summary", ["평점", "후기 요약"]),
            ],
            navigation_type="BOTTOM_NAV",
            layout_type="FEED",
            navigation=customer_nav,
            primary_actions=["예약 일정 선택"],
        ),
        adaptive_screen(
            "예약 날짜·시간 및 옵션 선택",
            "예약 가능한 일정과 서비스 옵션을 선택합니다.",
            "CUSTOMER_BOOKING",
            "CUSTOMER",
            "MOBILE",
            4,
            [8, 9, 21],
            "BOOKING",
            [
                ("예약 날짜", "date_picker", ["예약 가능 날짜"]),
                ("예약 시간", "time_slots", ["09:00", "11:00", "14:00"]),
                ("서비스 옵션", "option_selector", ["기본 옵션", "추가 옵션"]),
            ],
            navigation_type="BOTTOM_NAV",
            layout_type="FORM_FLOW",
            navigation=customer_nav,
            primary_actions=["결제로 이동"],
        ),
        adaptive_screen(
            "쿠폰 적용 및 PG 결제",
            "쿠폰과 결제 수단을 선택해 예약 금액을 결제합니다.",
            "CUSTOMER_BOOKING",
            "CUSTOMER",
            "MOBILE",
            5,
            [10, 11, 21],
            "FORM",
            [
                ("쿠폰 및 최종 금액", "price_summary", ["쿠폰 할인", "결제 금액"]),
                ("PG 결제 수단", "payment_methods", ["카드", "간편 결제"]),
            ],
            layout_type="FORM_FLOW",
            primary_actions=["결제하기"],
        ),
        adaptive_screen(
            "예약 완료 및 확정 상세",
            "예약 번호와 확정된 일정 및 옵션을 확인합니다.",
            "CUSTOMER_BOOKING",
            "CUSTOMER",
            "MOBILE",
            6,
            [12, 21],
            "DETAIL",
            [("예약 확정", "card", ["예약 번호", "날짜와 시간", "선택 옵션"])],
            navigation_type="BOTTOM_NAV",
            layout_type="FULL_WIDTH",
            navigation=customer_nav,
            primary_actions=["예약 상세 보기"],
        ),
        adaptive_screen(
            "예약 내역 및 마이페이지",
            "예약 이력과 리뷰 및 파트너 문의를 관리합니다.",
            "CUSTOMER_BOOKING",
            "CUSTOMER",
            "MOBILE",
            7,
            [13, 14, 21],
            "LIST",
            [
                ("예약 내역", "list", ["예정 예약", "완료 예약"]),
                ("리뷰 및 문의", "review_summary", ["리뷰 작성", "파트너 문의"]),
            ],
            navigation_type="BOTTOM_NAV",
            layout_type="FEED",
            navigation=customer_nav,
            primary_actions=["예약 관리"],
        ),
    ]
    partner_screens = [
        adaptive_screen(
            "파트너 예약 현황 및 승인",
            "신규 예약을 확인하고 승인 또는 거절합니다.",
            "PARTNER_OPERATIONS",
            "PARTNER",
            "WEB",
            1,
            [15, 16, 21],
            "LIST",
            [("예약 요청", "table", ["고객", "예약 일정", "상태"])],
            navigation_type="SIDEBAR",
            layout_type="MASTER_DETAIL",
            navigation=["예약", "서비스", "일정"],
            primary_actions=["예약 승인", "예약 거절"],
        ),
        adaptive_screen(
            "파트너 서비스 및 일정 관리",
            "제공 서비스와 예약 가능 일정을 관리합니다.",
            "PARTNER_OPERATIONS",
            "PARTNER",
            "WEB",
            2,
            [17],
            "FORM",
            [("서비스 정보", "form", ["서비스명", "가격", "가능 일정"])],
            navigation_type="SIDEBAR",
            layout_type="FORM_FLOW",
            navigation=["예약", "서비스", "일정"],
            primary_actions=["서비스 저장"],
        ),
    ]
    admin_screens = [
        adaptive_screen(
            "관리자 운영 현황 및 거래 검색",
            "회원, 파트너와 거래 현황을 조회합니다.",
            "ADMIN_CONTROL",
            "ADMIN",
            "WEB",
            1,
            [18, 19, 21],
            "DASHBOARD",
            [
                ("운영 현황", "chart", ["예약 상태", "거래 흐름"]),
                ("회원 및 거래", "table", ["회원", "파트너", "거래 상태"]),
            ],
            navigation_type="SIDEBAR",
            layout_type="GRID",
            navigation=["운영 현황", "회원", "파트너", "거래"],
            primary_actions=["거래 조회"],
        ),
        adaptive_screen(
            "관리자 CS 및 신고 처리",
            "고객 문의와 신고 내역을 검토하고 처리합니다.",
            "ADMIN_CONTROL",
            "ADMIN",
            "WEB",
            2,
            [20],
            "LIST",
            [("CS 및 신고", "table", ["접수 유형", "처리 상태", "담당자"])],
            navigation_type="SIDEBAR",
            layout_type="MASTER_DETAIL",
            navigation=["CS", "신고", "처리 이력"],
            primary_actions=["처리 상태 변경"],
        ),
    ]
    return UiMockupSpec.model_validate(
        {
            "project_title": "지역 생활 서비스 예약 플랫폼",
            "design_summary": "고객 예약 전 과정과 파트너 및 관리자 운영 흐름을 actor별로 구분한 서비스",
            "primary_actor": "CUSTOMER",
            "journey_summary": "로그인 → 탐색 → 상세 → 예약 → 결제 → 완료 → 마이페이지",
            "platform": "MOBILE",
            "journeys": [
                {
                    "journey_id": "CUSTOMER_BOOKING",
                    "actor": "CUSTOMER",
                    "goal": "서비스를 찾아 예약하고 결제 완료",
                    "summary": "로그인부터 검색, 상세, 일정 선택, 결제, 예약 관리까지 진행합니다.",
                    "platform": "MOBILE",
                    "evidence_requirement_ids": list(range(1, 15)) + [21],
                },
                {
                    "journey_id": "PARTNER_OPERATIONS",
                    "actor": "PARTNER",
                    "goal": "예약과 제공 서비스 운영",
                    "summary": "예약 요청을 처리하고 서비스와 가능 일정을 관리합니다.",
                    "platform": "WEB",
                    "evidence_requirement_ids": [15, 16, 17, 21],
                },
                {
                    "journey_id": "ADMIN_CONTROL",
                    "actor": "ADMIN",
                    "goal": "플랫폼 운영 및 CS 통제",
                    "summary": "회원과 거래를 조회하고 CS 및 신고를 처리합니다.",
                    "platform": "WEB",
                    "evidence_requirement_ids": [18, 19, 20, 21],
                },
            ],
            "screens": customer_screens + partner_screens + admin_screens,
        }
    )


def multi_actor_service_spec() -> UiMockupSpec:
    payload = adaptive_mobile_rfp_spec().model_dump()
    payload["project_title"] = "고객·파트너·관리자 방문 서비스"
    payload["design_summary"] = "세 actor의 핵심 업무를 분리한 모바일 및 웹 서비스"
    payload["journeys"][0]["evidence_requirement_ids"] = list(range(1, 13))
    payload["screens"] = (
        payload["screens"][1:4]
        + payload["screens"][7:9]
        + payload["screens"][9:10]
    )
    for journey in payload["journeys"]:
        journey_screens = [
            screen
            for screen in payload["screens"]
            if screen["journey_id"] == journey["journey_id"]
        ]
        journey["evidence_requirement_ids"] = list(dict.fromkeys(
            requirement_id
            for screen in journey_screens
            for requirement_id in screen["evidence_requirement_ids"]
        ))
        for step, screen in enumerate(journey_screens, start=1):
            screen["journey_step"] = step
    return UiMockupSpec.model_validate(payload)


def generation_payload(
    project_title: str,
    project_description: str,
    *requirements: str,
) -> dict:
    return {
        "project_id": 71,
        "project_title": project_title,
        "project_description": project_description,
        "confirmed_requirements": [
            {
                "requirement_id": index,
                "title": f"확정 요구사항 {index}",
                "description": description,
                "category": "FUNCTIONAL",
                "priority": "HIGH",
            }
            for index, description in enumerate(requirements, start=1)
        ],
    }


def mobile_rfp_payload() -> dict:
    requirements = [
        ("위치 기반 통합 검색", "일반 고객은 현재 위치와 키워드로 서비스를 검색합니다.", "HIGH"),
        ("카테고리 검색", "일반 고객은 서비스 카테고리를 선택해 탐색합니다.", "HIGH"),
        ("복합 검색 필터", "가격, 거리, 평점, 예약 가능 여부를 함께 필터링합니다.", "HIGH"),
        ("서비스 상세", "서비스 이미지, 설명, 가격, 평점과 운영 시간을 확인합니다.", "HIGH"),
        ("서비스 지도", "서비스 위치와 주변 정보를 지도에서 확인합니다.", "HIGH"),
        ("예약 가능 슬롯", "예약 가능한 날짜와 시간 슬롯을 선택합니다.", "HIGH"),
        ("서비스 옵션", "예약 전에 제공 옵션과 추가 옵션을 선택합니다.", "HIGH"),
        ("쿠폰 적용", "결제 전에 사용 가능한 쿠폰을 선택해 적용합니다.", "HIGH"),
        ("PG 결제", "카드 또는 간편 결제 수단으로 PG 결제를 완료합니다.", "HIGH"),
        ("예약 완료", "결제 성공 후 예약 번호와 확정 일정을 확인합니다.", "HIGH"),
        ("맞춤 추천", "일반 고객에게 위치와 관심사 기반 서비스를 추천합니다.", "MEDIUM"),
        ("리뷰", "일반 고객은 서비스 리뷰를 조회하고 작성합니다.", "MEDIUM"),
        ("채팅", "일반 고객은 서비스 파트너와 채팅합니다.", "MEDIUM"),
        ("즐겨찾기", "일반 고객은 관심 서비스를 즐겨찾기에 저장합니다.", "MEDIUM"),
        ("파트너 포털", "파트너는 웹 포털에서 예약과 서비스를 관리합니다.", "MEDIUM"),
        ("관리자 포털", "관리자는 웹 포털에서 사용자와 거래를 관리합니다.", "MEDIUM"),
    ]
    return {
        "project_id": 72,
        "project_title": "지역 생활 서비스 예약 앱",
        "project_description": "일반 고객용 모바일 앱과 별도 파트너 및 관리자 포털을 제공합니다.",
        "confirmed_requirements": [
            {
                "requirement_id": index,
                "title": title,
                "description": description,
                "category": "FUNCTIONAL",
                "priority": priority,
            }
            for index, (title, description, priority) in enumerate(
                requirements,
                start=1,
            )
        ],
    }


def adaptive_mobile_rfp_payload() -> dict:
    requirements = [
        ("고객 로그인 및 온보딩", "고객은 로그인하고 위치 사용 안내를 확인합니다.", "HIGH"),
        ("위치 기반 홈", "고객은 현재 위치를 기준으로 서비스를 탐색합니다.", "HIGH"),
        ("통합 검색", "고객은 키워드로 서비스를 검색합니다.", "HIGH"),
        ("카테고리 검색", "고객은 카테고리를 선택해 서비스를 탐색합니다.", "HIGH"),
        ("복합 필터", "가격, 거리, 평점, 예약 가능 여부를 함께 필터링합니다.", "HIGH"),
        ("서비스 상세", "이미지, 설명, 가격, 평점과 운영 시간을 확인합니다.", "HIGH"),
        ("지도", "서비스 위치와 주변 정보를 지도에서 확인합니다.", "HIGH"),
        ("예약 일정", "예약 가능한 날짜와 시간 슬롯을 선택합니다.", "HIGH"),
        ("서비스 옵션", "예약할 서비스 옵션을 선택합니다.", "HIGH"),
        ("쿠폰", "결제 전에 사용 가능한 쿠폰을 적용합니다.", "HIGH"),
        ("PG 결제", "카드 또는 간편 결제로 예약 금액을 결제합니다.", "HIGH"),
        ("예약 완료", "예약 번호와 확정 일정을 확인합니다.", "HIGH"),
        ("예약 내역", "고객은 예약 내역과 상태를 확인합니다.", "HIGH"),
        ("리뷰 및 문의", "고객은 리뷰를 작성하고 파트너에게 문의합니다.", "MEDIUM"),
        ("파트너 예약 현황", "파트너는 신규 예약과 상태를 조회합니다.", "HIGH"),
        ("파트너 예약 승인", "파트너는 예약을 승인하거나 거절합니다.", "HIGH"),
        ("파트너 서비스 관리", "파트너는 서비스와 가능 일정을 관리합니다.", "HIGH"),
        ("관리자 운영 현황", "관리자는 플랫폼 운영 현황을 확인합니다.", "HIGH"),
        ("관리자 회원 및 거래", "관리자는 회원, 파트너와 거래를 조회합니다.", "HIGH"),
        ("관리자 CS 및 신고", "관리자는 고객 문의와 신고를 처리합니다.", "HIGH"),
        (
            "필수 UI 목업 화면",
            "로그인, 홈과 검색, 서비스 상세, 예약 확인, 결제, 마이페이지, 파트너 예약 관리, 운영자 통합 대시보드를 필수로 표현합니다.",
            "HIGH",
        ),
    ]
    return {
        "project_id": 73,
        "project_title": "지역 생활 서비스 예약 플랫폼",
        "project_description": "고객 모바일 앱과 파트너 및 관리자 웹 포털을 제공합니다.",
        "confirmed_requirements": [
            {
                "requirement_id": index,
                "title": title,
                "description": description,
                "category": "FUNCTIONAL",
                "priority": priority,
            }
            for index, (title, description, priority) in enumerate(
                requirements,
                start=1,
            )
        ],
    }


def community_payload() -> dict:
    return generation_payload(
        "동네 이야기 커뮤니티",
        "모바일 회원이 지역 이야기를 공유하는 커뮤니티",
        "커뮤니티 회원은 관심 주제와 최신 게시글 피드를 탐색합니다.",
        "게시글 상세를 읽고 댓글과 답글을 작성합니다.",
        "주제, 제목, 본문을 입력해 새 게시글을 발행합니다.",
    )


def usable_font_path() -> Path:
    windows_font = Path("C:/Windows/Fonts/malgun.ttf")
    if windows_font.is_file():
        return windows_font
    return Path(ImageFont.truetype("DejaVuSans.ttf", 12).path)


class StubUiMockupService:
    def generate(self, request: UiMockupGenerationRequest) -> UiMockupSpec:
        return mockup_spec()

    def assess(
        self,
        request: UiMockupGenerationRequest,
    ) -> UiMockupNecessityDecision:
        return UiMockupNecessityDecision(
            decision="REQUIRED",
            reason="로그인과 대시보드 화면 상호작용이 명시되어 UI 목업이 필요합니다.",
            evidence_requirement_ids=[1, 2],
            candidate_screens=["로그인", "프로젝트 대시보드"],
        )


def assessment_payload(*descriptions: str) -> dict:
    payload = request_payload()
    payload["confirmed_requirements"] = [
        {
            "requirement_id": index,
            "title": f"확정 요구사항 {index}",
            "description": description,
            "category": "FUNCTIONAL",
            "priority": "HIGH",
        }
        for index, description in enumerate(descriptions, start=1)
    ]
    return payload


class UiMockupTest(unittest.TestCase):
    @staticmethod
    def _diagnostic_payload(log_output: str) -> dict:
        marker = "ui_mockup_generation_diagnostic "
        return json.loads(log_output.split(marker, 1)[1])

    def test_request_requires_confirmed_requirements(self):
        payload = request_payload()
        payload["confirmed_requirements"] = []
        with self.assertRaises(ValidationError):
            UiMockupGenerationRequest.model_validate(payload)

    def test_spec_accepts_twelve_and_rejects_more_than_twelve_screens(self):
        payload = adaptive_mobile_rfp_spec().model_dump()
        twelfth = deepcopy(payload["screens"][-1])
        twelfth["screen_name"] = "관리자 신고 처리 이력"
        twelfth["journey_step"] = 3
        payload["screens"].append(twelfth)
        self.assertEqual(len(UiMockupSpec.model_validate(payload).screens), 12)

        thirteenth = deepcopy(twelfth)
        thirteenth["screen_name"] = "관리자 신고 통계 확인"
        thirteenth["journey_step"] = 4
        payload["screens"].append(thirteenth)
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(payload)

    def test_representative_korean_fixture_renders_jpeg(self):
        with patch(
            "app.domains.planning_resources.ui_mockup._resolve_font_path",
            return_value=usable_font_path(),
        ):
            rendered = render_ui_mockup(mockup_spec())
        self.assertTrue(rendered.content.startswith(b"\xff\xd8\xff"))
        image = Image.open(BytesIO(rendered.content))
        self.assertEqual(image.format, "JPEG")
        self.assertEqual(image.size, (1920, 1080))

    def test_mobile_schema_rejects_sidebar_navigation(self):
        payload = mobile_booking_spec().model_dump()
        payload["screens"][0]["navigation_type"] = "SIDEBAR"
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(payload)

    def test_spec_requires_screen_evidence_and_primary_actor_consistency(self):
        missing_evidence = mobile_booking_spec().model_dump()
        missing_evidence["screens"][0]["evidence_requirement_ids"] = []
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(missing_evidence)

        mixed_actor = mobile_booking_spec().model_dump()
        mixed_actor["screens"][1]["actor"] = "ADMIN"
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(mixed_actor)

    def test_spec_requires_contiguous_journey_and_domain_screen_names(self):
        repeated_step = mobile_booking_spec().model_dump()
        repeated_step["screens"][2]["journey_step"] = 2
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(repeated_step)

        for name in ("메인 화면", "목록 화면", "상세 화면", "관리 화면"):
            with self.subTest(generic_name=name):
                generic_name = mobile_booking_spec().model_dump()
                generic_name["screens"][1]["screen_name"] = name
                with self.assertRaises(ValidationError):
                    UiMockupSpec.model_validate(generic_name)

    def test_generation_rejects_unknown_screen_evidence_requirement_id(self):
        payload = mobile_booking_spec().model_dump()
        payload["screens"][0]["evidence_requirement_ids"] = [999]
        parsed_spec = UiMockupSpec.model_validate(payload)
        with self.assertRaises(UiMockupLLMGenerationError):
            self._generate_with_mock(mobile_rfp_payload(), parsed_spec)

    def test_generation_logs_safe_timeout_diagnostics(self):
        payload = request_payload()
        payload["project_title"] = "SECRET_PROJECT_TITLE"
        payload["project_description"] = "SECRET_PROJECT_DESCRIPTION"
        payload["confirmed_requirements"][0]["description"] = "SECRET_REQUIREMENT"
        client = Mock()
        client.responses.parse.side_effect = APITimeoutError(
            request=httpx.Request("POST", "https://api.openai.com/v1/responses")
        )
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "SECRET_API_KEY"}),
            patch(
                "app.domains.planning_resources.ui_mockup_service.OpenAI",
                return_value=client,
            ),
            self.assertLogs("uvicorn.error", level="ERROR") as captured,
            self.assertRaises(UiMockupLLMGenerationError),
        ):
            UiMockupLLMService().generate(
                UiMockupGenerationRequest.model_validate(payload)
            )

        logged = "\n".join(captured.output)
        diagnostic = self._diagnostic_payload(captured.output[-1])
        self.assertEqual(diagnostic["phase"], "openai_request")
        self.assertEqual(diagnostic["exception_type"], "APITimeoutError")
        self.assertTrue(diagnostic["timeout"])
        self.assertEqual(diagnostic["confirmed_requirement_count"], 3)
        for secret in (
            "SECRET_API_KEY",
            "SECRET_PROJECT_TITLE",
            "SECRET_PROJECT_DESCRIPTION",
            "SECRET_REQUIREMENT",
        ):
            self.assertNotIn(secret, logged)

    def test_generation_logs_sanitized_pydantic_validation_metadata(self):
        try:
            UiMockupSpec.model_validate(
                {
                    "project_title": "SECRET_RAW_RESPONSE",
                    "screens": "SECRET_RESPONSE_BODY",
                }
            )
        except ValidationError as validation_error:
            parse_error = validation_error
        client = Mock()
        client.responses.parse.side_effect = parse_error
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "SECRET_API_KEY"}),
            patch(
                "app.domains.planning_resources.ui_mockup_service.OpenAI",
                return_value=client,
            ),
            self.assertLogs("uvicorn.error", level="ERROR") as captured,
            self.assertRaises(UiMockupLLMGenerationError),
        ):
            UiMockupLLMService().generate(
                UiMockupGenerationRequest.model_validate(request_payload())
            )

        logged = "\n".join(captured.output)
        diagnostic = self._diagnostic_payload(captured.output[-1])
        self.assertEqual(diagnostic["phase"], "structured_parse")
        self.assertEqual(diagnostic["exception_type"], "ValidationError")
        self.assertGreater(diagnostic["validation_error_count"], 0)
        self.assertLessEqual(len(diagnostic["validation_errors"]), 10)
        self.assertEqual(
            set(diagnostic["validation_errors"][0]),
            {"loc", "type", "msg"},
        )
        for secret in (
            "SECRET_API_KEY",
            "SECRET_RAW_RESPONSE",
            "SECRET_RESPONSE_BODY",
        ):
            self.assertNotIn(secret, logged)

    def test_generation_logs_custom_evidence_validation_rule(self):
        parsed_spec = mobile_booking_spec()
        parsed_spec.screens[0].evidence_requirement_ids = [999]
        with (
            self.assertLogs("uvicorn.error", level="ERROR") as captured,
            self.assertRaises(UiMockupLLMGenerationError) as raised,
        ):
            self._generate_with_mock(mobile_rfp_payload(), parsed_spec)

        diagnostic = self._diagnostic_payload(captured.output[-1])
        self.assertEqual(diagnostic["phase"], "spec_validation")
        self.assertEqual(diagnostic["rule_code"], "UI_MOCKUP_UNKNOWN_EVIDENCE")
        self.assertEqual(diagnostic["affected_count"], 1)
        self.assertEqual(
            raised.exception.diagnostic_code,
            "UI_MOCKUP_UNKNOWN_EVIDENCE",
        )
        self.assertNotIn("999", "\n".join(captured.output))

    def test_generation_logs_safe_success_counts(self):
        spec = mobile_booking_spec()
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            generated, _ = self._generate_with_mock(mobile_rfp_payload(), spec)

        diagnostic = self._diagnostic_payload(captured.output[-1])
        self.assertIs(generated, spec)
        self.assertEqual(diagnostic["event"], "ui_mockup_generation_succeeded")
        self.assertEqual(diagnostic["phase"], "success")
        self.assertEqual(diagnostic["screen_count"], len(spec.screens))
        self.assertEqual(diagnostic["journey_count"], len(spec.journeys))
        self.assertNotIn("project_id", diagnostic)
        self.assertNotIn("project_title", diagnostic)
        self.assertNotIn("confirmed_requirements", diagnostic)

    def test_generation_context_preserves_backend_requirement_fields(self):
        payload = mobile_rfp_payload()
        _, parse_call = self._generate_with_mock(payload, mobile_booking_spec())
        context = json.loads(parse_call.kwargs["input"])

        self.assertEqual(context["project_title"], payload["project_title"])
        self.assertEqual(
            context["project_description"],
            payload["project_description"],
        )
        self.assertEqual(
            len(context["confirmed_requirements"]),
            len(payload["confirmed_requirements"]),
        )
        first = context["confirmed_requirements"][0]
        self.assertEqual(
            set(first),
            {"id", "title", "description", "category", "priority"},
        )
        self.assertEqual(first["id"], 1)
        self.assertEqual(first["priority"], "HIGH")

    def test_mobile_rfp_journey_covers_core_must_requirements(self):
        spec = mobile_booking_spec()
        core_must_ids = set(range(1, 11))
        covered_ids = {
            requirement_id
            for screen in spec.screens
            for requirement_id in screen.evidence_requirement_ids
        }
        coverage = len(core_must_ids & covered_ids) / len(core_must_ids)

        self.assertEqual(spec.primary_actor, "CUSTOMER")
        self.assertEqual([screen.journey_step for screen in spec.screens], [1, 2, 3])
        self.assertGreaterEqual(coverage, 0.8)
        self.assertEqual(coverage, 1.0)
        self.assertTrue(all(screen.actor == "CUSTOMER" for screen in spec.screens))
        self.assertNotIn("DASHBOARD", {screen.page_type for screen in spec.screens})

        components = [
            {section.component_type for section in screen.sections}
            for screen in spec.screens
        ]
        self.assertTrue({"search_bar", "filter_chips"} <= components[0])
        self.assertTrue({"date_picker", "time_slots"} <= components[1])
        self.assertTrue({"price_summary", "payment_methods"} <= components[2])

    def test_screen_count_adapts_to_project_complexity(self):
        fixtures = {
            "simple_login": (simple_login_spec(), range(1, 4)),
            "ecommerce": (adaptive_ecommerce_spec(), range(3, 7)),
            "mobile_rfp": (adaptive_mobile_rfp_spec(), range(4, 13)),
            "pm_saas": (mockup_spec(), range(1, 4)),
            "multi_actor": (multi_actor_service_spec(), range(4, 13)),
        }

        for name, (spec, expected_range) in fixtures.items():
            with self.subTest(project=name):
                self.assertIn(len(spec.screens), expected_range)
                self.assertLessEqual(len(spec.screens), 12)

        self.assertEqual(len(simple_login_spec().screens), 2)
        self.assertEqual(len(adaptive_ecommerce_spec().screens), 5)
        self.assertEqual(len(adaptive_mobile_rfp_spec().screens), 11)
        self.assertEqual(len(mockup_spec().screens), 3)
        self.assertEqual(len(multi_actor_service_spec().screens), 6)

    def test_adaptive_mobile_rfp_covers_complete_customer_flow(self):
        spec = adaptive_mobile_rfp_spec()
        customer_screens = [
            screen for screen in spec.screens if screen.actor == "CUSTOMER"
        ]
        core_must_ids = set(range(1, 14))
        covered_ids = {
            requirement_id
            for screen in customer_screens
            for requirement_id in screen.evidence_requirement_ids
        }
        coverage = len(core_must_ids & covered_ids) / len(core_must_ids)
        names = " ".join(screen.screen_name for screen in customer_screens)
        components = {
            section.component_type
            for screen in customer_screens
            for section in screen.sections
        }

        self.assertEqual(coverage, 1.0)
        self.assertGreater(len(customer_screens), 3)
        for keyword in ("로그인", "검색", "상세", "예약", "결제", "완료", "마이페이지"):
            self.assertIn(keyword, names)
        self.assertTrue(
            {
                "search_bar",
                "filter_chips",
                "map_preview",
                "date_picker",
                "time_slots",
                "payment_methods",
            }
            <= components
        )

        explicit_screen_terms = {
            "로그인",
            "검색",
            "상세",
            "예약",
            "결제",
            "마이페이지",
            "파트너",
            "관리자",
        }
        explicit_names = " ".join(
            screen.screen_name
            for screen in spec.screens
            if 21 in screen.evidence_requirement_ids
        )
        self.assertTrue(
            all(term in explicit_names for term in explicit_screen_terms)
        )
        all_covered_ids = {
            requirement_id
            for screen in spec.screens
            for requirement_id in screen.evidence_requirement_ids
        }
        self.assertEqual(all_covered_ids, set(range(1, 22)))

        serialized = json.dumps(spec.model_dump(), ensure_ascii=False)
        for forbidden in ("Pmate AI", "68%", "D-42", "24건", "주간 보고서 생성"):
            self.assertNotIn(forbidden, serialized)

    def test_multi_actor_journeys_are_separate_and_traceable(self):
        spec = adaptive_mobile_rfp_spec()
        self.assertEqual(
            [journey.actor for journey in spec.journeys],
            ["CUSTOMER", "PARTNER", "ADMIN"],
        )
        self.assertEqual(
            list(dict.fromkeys(screen.journey_id for screen in spec.screens)),
            [journey.journey_id for journey in spec.journeys],
        )

        for journey in spec.journeys:
            journey_screens = [
                screen
                for screen in spec.screens
                if screen.journey_id == journey.journey_id
            ]
            with self.subTest(actor=journey.actor):
                self.assertTrue(journey_screens)
                self.assertTrue(
                    all(screen.actor == journey.actor for screen in journey_screens)
                )
                self.assertTrue(
                    all(
                        screen.platform == journey.platform
                        for screen in journey_screens
                    )
                )
                self.assertEqual(
                    [screen.journey_step for screen in journey_screens],
                    list(range(1, len(journey_screens) + 1)),
                )
                self.assertTrue(
                    all(
                        set(screen.evidence_requirement_ids)
                        <= set(journey.evidence_requirement_ids)
                        for screen in journey_screens
                    )
                )

    def test_spec_rejects_duplicate_screen_names_and_cross_actor_screens(self):
        duplicate = adaptive_ecommerce_spec().model_dump()
        duplicate["screens"][1]["screen_name"] = duplicate["screens"][0][
            "screen_name"
        ]
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(duplicate)

        cross_actor = adaptive_mobile_rfp_spec().model_dump()
        cross_actor["screens"][0]["actor"] = "ADMIN"
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(cross_actor)

    def test_generation_rejects_cross_journey_and_unknown_journey_evidence(self):
        cross_journey = adaptive_mobile_rfp_spec()
        cross_journey.screens[0].evidence_requirement_ids = [15]
        with self.assertRaises(UiMockupLLMGenerationError) as raised:
            self._generate_with_mock(adaptive_mobile_rfp_payload(), cross_journey)
        self.assertEqual(
            raised.exception.diagnostic_code,
            "UI_MOCKUP_SCREEN_EVIDENCE_OUTSIDE_JOURNEY",
        )

        unknown = adaptive_mobile_rfp_spec()
        unknown.journeys[0].evidence_requirement_ids.append(999)
        with self.assertRaises(UiMockupLLMGenerationError) as raised:
            self._generate_with_mock(adaptive_mobile_rfp_payload(), unknown)
        self.assertEqual(
            raised.exception.diagnostic_code,
            "UI_MOCKUP_UNKNOWN_EVIDENCE",
        )

        uncovered = adaptive_mobile_rfp_spec()
        uncovered.journeys[0].evidence_requirement_ids.append(20)
        with self.assertRaises(UiMockupLLMGenerationError) as raised:
            self._generate_with_mock(adaptive_mobile_rfp_payload(), uncovered)
        self.assertEqual(
            raised.exception.diagnostic_code,
            "UI_MOCKUP_JOURNEY_EVIDENCE_NOT_COVERED",
        )

    def test_spec_limits_actor_types_to_three(self):
        payload = adaptive_mobile_rfp_spec().model_dump()
        public_journey = deepcopy(payload["journeys"][-1])
        public_journey.update(
            {
                "journey_id": "PUBLIC_DISCOVERY",
                "actor": "PUBLIC",
                "goal": "공개 서비스 확인",
                "summary": "방문자가 공개 서비스를 확인합니다.",
            }
        )
        public_screen = deepcopy(payload["screens"][-1])
        public_screen.update(
            {
                "screen_name": "방문자 공개 서비스 안내",
                "journey_id": "PUBLIC_DISCOVERY",
                "actor": "PUBLIC",
                "journey_step": 1,
            }
        )
        payload["journeys"].append(public_journey)
        payload["screens"].append(public_screen)
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(payload)

    def test_adaptive_renderer_uses_dynamic_height_and_valid_jpeg(self):
        specs = [
            simple_login_spec(),
            adaptive_ecommerce_spec(),
            adaptive_mobile_rfp_spec(),
            multi_actor_service_spec(),
        ]
        with patch(
            "app.domains.planning_resources.ui_mockup._resolve_font_path",
            return_value=usable_font_path(),
        ):
            rendered = [render_ui_mockup(spec) for spec in specs]

        self.assertEqual(rendered[0].height, 1080)
        self.assertGreater(rendered[1].height, 1080)
        self.assertGreater(rendered[2].height, rendered[1].height)
        self.assertGreater(rendered[3].height, 1080)
        for result in rendered:
            self.assertEqual(result.width, 1920)
            self.assertLessEqual(result.height, 7200)
            self.assertTrue(result.content.startswith(b"\xff\xd8\xff"))
            image = Image.open(BytesIO(result.content))
            self.assertEqual(image.size, (result.width, result.height))

    def test_pm_saas_keeps_compact_web_dashboard_list_detail(self):
        spec = mockup_spec()
        self.assertEqual(spec.platform, "WEB")
        self.assertEqual(len(spec.screens), 3)
        self.assertEqual(
            [screen.page_type for screen in spec.screens],
            ["DASHBOARD", "LIST", "DETAIL"],
        )
        self.assertTrue(all(screen.platform == "WEB" for screen in spec.screens))

    def test_generation_prompt_uses_coverage_based_adaptive_selection(self):
        instructions = UiMockupLLMService._instructions()
        self.assertIn("Requirement → Actor → Goal → Journey → Screen", instructions)
        self.assertIn("coverage", instructions)
        self.assertIn("최대 12개", instructions)
        self.assertIn("journey_id", instructions)
        self.assertIn("중복 화면", instructions)
        self.assertNotIn("대표 화면 1~3개", instructions)
        self.assertNotIn("화면이 3개를 넘는", instructions)

    def test_cross_domain_fixtures_select_different_ordered_journeys(self):
        fixtures = {
            "mobile": mobile_booking_spec(),
            "ecommerce": ecommerce_spec(),
            "pm": mockup_spec(),
            "community": community_spec(),
        }
        expected_actors = {
            "mobile": "CUSTOMER",
            "ecommerce": "CUSTOMER",
            "pm": "PROJECT_MANAGER",
            "community": "COMMUNITY_MEMBER",
        }

        journeys = set()
        screen_sequences = set()
        for name, spec in fixtures.items():
            with self.subTest(name=name):
                self.assertEqual(spec.primary_actor, expected_actors[name])
                self.assertEqual(
                    [screen.journey_step for screen in spec.screens],
                    list(range(1, len(spec.screens) + 1)),
                )
                journeys.add(spec.journey_summary)
                screen_sequences.add(tuple(screen.screen_name for screen in spec.screens))

        self.assertEqual(len(journeys), 4)
        self.assertEqual(len(screen_sequences), 4)

    def test_generation_fixtures_preserve_domain_layout_semantics(self):
        fixtures = [
            (
                mobile_rfp_payload(),
                mobile_booking_spec(),
                "MOBILE",
                {"BOOKING", "DETAIL", "FORM"},
            ),
            (
                generation_payload(
                    "로컬 브랜드 온라인 쇼핑몰",
                    "상품 판매를 위한 웹 쇼핑몰",
                    "상품 목록을 카테고리와 검색으로 탐색합니다.",
                    "상품 상세와 리뷰 및 배송 조건을 확인합니다.",
                    "장바구니에 담고 결제를 완료합니다.",
                ),
                ecommerce_spec(),
                "WEB",
                {"ECOMMERCE", "DETAIL", "FORM"},
            ),
            (
                request_payload(),
                mockup_spec(),
                "WEB",
                {"DASHBOARD", "LIST", "DETAIL"},
            ),
            (
                generation_payload(
                    "주문 데이터 ETL API",
                    "화면이 없는 API와 배치 데이터 파이프라인",
                    "REST API로 주문 데이터를 수집합니다.",
                    "ETL 배치가 필드를 정규화해 저장 대상으로 전달합니다.",
                ),
                api_etl_spec(),
                "WEB",
                {"DETAIL"},
            ),
            (
                community_payload(),
                community_spec(),
                "MOBILE",
                {"LIST", "DETAIL", "FORM"},
            ),
        ]

        for payload, parsed_spec, platform, page_types in fixtures:
            with self.subTest(project=payload["project_title"]):
                generated, parse_call = self._generate_with_mock(payload, parsed_spec)
                self.assertEqual(generated.platform, platform)
                self.assertEqual(
                    {screen.page_type for screen in generated.screens},
                    page_types,
                )
                sent_context = json.loads(parse_call.kwargs["input"])
                self.assertEqual(
                    sent_context["confirmed_requirements"][0]["description"],
                    payload["confirmed_requirements"][0]["description"],
                )
                instructions = parse_call.kwargs["instructions"]
                self.assertIn("confirmed_requirements", instructions)
                self.assertIn("primary actor", instructions)
                self.assertIn("journey_step", instructions)
                self.assertIn("evidence_requirement_ids", instructions)
                self.assertIn("HIGH/MUST", instructions)
                self.assertIn("Pmate AI", instructions)
                self.assertIn("근거가 없는 실제 수치", instructions)
                self.assertNotIn("한국어 업무용 SaaS UX 설계자", instructions)

        mobile = fixtures[0][1]
        self.assertTrue(all(screen.page_type != "DASHBOARD" for screen in mobile.screens))
        self.assertTrue(all(screen.navigation_type != "SIDEBAR" for screen in mobile.screens))
        forced_api = fixtures[3][1]
        self.assertTrue(all(screen.page_type != "DASHBOARD" for screen in forced_api.screens))
        self.assertTrue(all(screen.navigation_type == "NONE" for screen in forced_api.screens))

    def test_domain_renderers_are_semantically_and_visually_distinct(self):
        specs = [mobile_booking_spec(), ecommerce_spec(), mockup_spec()]
        with patch(
            "app.domains.planning_resources.ui_mockup._resolve_font_path",
            return_value=usable_font_path(),
        ):
            rendered = [render_ui_mockup(spec) for spec in specs]

        hashes = {hashlib.sha256(item.content).hexdigest() for item in rendered}
        self.assertEqual(len(hashes), 3)
        for item in rendered:
            self.assertTrue(item.content.startswith(b"\xff\xd8\xff"))
            image = Image.open(BytesIO(item.content))
            self.assertEqual(image.size, (1920, 1080))

        mobile_image = Image.open(BytesIO(rendered[0].content)).convert("RGB")
        dark_phone_pixels = sum(
            1
            for red, green, blue in mobile_image.getdata()
            if red < 45 and green < 60 and blue < 85
        )
        self.assertGreater(dark_phone_pixels, 8_000)
        self.assertEqual(specs[0].platform, "MOBILE")
        self.assertEqual(specs[0].screens[0].page_type, "BOOKING")
        self.assertEqual(specs[1].screens[0].page_type, "ECOMMERCE")
        self.assertEqual(specs[2].screens[0].page_type, "DASHBOARD")
        self.assertEqual(specs[2].screens[0].navigation_type, "SIDEBAR")

    def test_long_korean_text_is_fitted_inside_renderer_bounds(self):
        image = Image.new("RGB", (400, 100), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(usable_font_path()), 18)
        fitted = _fit_text(
            draw,
            "모바일 예약 서비스의 매우 긴 화면 제목과 사용자 흐름 설명이 부모 영역을 넘지 않아야 합니다",
            font,
            180,
        )
        left, _, right, _ = draw.textbbox((0, 0), fitted, font=font)
        self.assertLessEqual(right - left, 180)
        self.assertTrue(fitted.endswith("..."))

    def test_endpoint_returns_validated_spec_and_base64_jpeg(self):
        client = TestClient(app)
        with (
            patch(
                "app.domains.planning_resources.ui_mockup_router.ui_mockup_service",
                StubUiMockupService(),
            ),
            patch(
                "app.domains.planning_resources.ui_mockup._resolve_font_path",
                return_value=usable_font_path(),
            ),
        ):
            response = client.post(
                "/api/v1/planning/ui-mockup/generate",
                json=request_payload(),
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_id"], 17)
        self.assertGreaterEqual(len(body["mockup"]["screens"]), 1)
        self.assertLessEqual(len(body["mockup"]["screens"]), 12)
        self.assertTrue(base64.b64decode(body["image_base64"]).startswith(b"\xff\xd8\xff"))

    def test_assessment_fixtures_use_structured_output(self):
        fixtures = [
            (
                assessment_payload(
                    "사용자는 로그인해야 합니다.",
                    "대시보드에서 진행률을 확인합니다.",
                    "프로젝트 정보를 입력 폼으로 등록합니다.",
                ),
                {
                    "decision": "REQUIRED",
                    "reason": "로그인, 대시보드, 입력 폼이 명시되어 UI 목업이 필요합니다.",
                    "evidence_requirement_ids": [1, 2, 3],
                    "candidate_screens": ["로그인", "대시보드", "프로젝트 등록"],
                },
            ),
            (
                assessment_payload(
                    "내부 운영자가 처리 결과를 확인할 수 있어야 합니다.",
                ),
                {
                    "decision": "RECOMMENDED",
                    "reason": "운영자의 결과 확인 흐름이 있어 간단한 화면 구조 검토가 권장됩니다.",
                    "evidence_requirement_ids": [1],
                    "candidate_screens": ["처리 결과 확인"],
                },
            ),
            (
                assessment_payload(
                    "REST API로 주문 데이터를 수집합니다.",
                    "배치 작업으로 데이터를 집계하고 DB pipeline에 저장합니다.",
                ),
                {
                    "decision": "NOT_NEEDED",
                    "reason": "API와 배치 데이터 처리만 요구되어 화면 설계는 기본적으로 생략 가능합니다.",
                    "evidence_requirement_ids": [1, 2],
                    "candidate_screens": [],
                },
            ),
            (
                assessment_payload(
                    "모바일 사용자가 예약 가능한 시간을 조회합니다.",
                    "예약 내용을 확인하고 결제를 완료합니다.",
                ),
                {
                    "decision": "REQUIRED",
                    "reason": "모바일 예약과 결제 사용자 흐름이 핵심 기능으로 명시되어 UI 목업이 필요합니다.",
                    "evidence_requirement_ids": [1, 2],
                    "candidate_screens": ["예약 조회", "예약 확인", "결제"],
                },
            ),
        ]

        for payload, decision_payload in fixtures:
            with self.subTest(decision=decision_payload["decision"]):
                decision, parse_call = self._assess_with_mock(
                    payload,
                    UiMockupNecessityDecision.model_validate(decision_payload),
                )
                self.assertEqual(decision.decision, decision_payload["decision"])
                self.assertIs(
                    parse_call.kwargs["text_format"],
                    UiMockupNecessityDecision,
                )
                sent_context = json.loads(parse_call.kwargs["input"])
                self.assertEqual(
                    len(sent_context["confirmed_requirements"]),
                    len(payload["confirmed_requirements"]),
                )
                instructions = parse_call.kwargs["instructions"]
                self.assertIn("primary actor", instructions)
                self.assertIn("end-to-end", instructions)
                self.assertIn("candidate_screens", instructions)
                self.assertIn("HIGH/MUST", instructions)

    def test_assessment_endpoint_returns_project_decision(self):
        client = TestClient(app)
        with patch(
            "app.domains.planning_resources.ui_mockup_router.ui_mockup_service",
            StubUiMockupService(),
        ):
            response = client.post(
                "/api/v1/planning/ui-mockup/assess",
                json=request_payload(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "project_id": 17,
                "decision": "REQUIRED",
                "reason": "로그인과 대시보드 화면 상호작용이 명시되어 UI 목업이 필요합니다.",
                "evidence_requirement_ids": [1, 2],
                "candidate_screens": ["로그인", "프로젝트 대시보드"],
            },
        )

    def test_assessment_rejects_empty_confirmed_requirements_before_service(self):
        payload = request_payload()
        payload["confirmed_requirements"] = []
        service = Mock()
        client = TestClient(app)
        with patch(
            "app.domains.planning_resources.ui_mockup_router.ui_mockup_service",
            service,
        ):
            response = client.post(
                "/api/v1/planning/ui-mockup/assess",
                json=payload,
            )
        self.assertEqual(response.status_code, 422)
        service.assess.assert_not_called()

    def test_assessment_rejects_unknown_evidence_requirement_id(self):
        decision = UiMockupNecessityDecision(
            decision="RECOMMENDED",
            reason="운영자 확인 흐름이 있어 화면 검토가 권장됩니다.",
            evidence_requirement_ids=[999],
            candidate_screens=["운영 결과"],
        )
        with self.assertRaises(UiMockupLLMGenerationError):
            self._assess_with_mock(request_payload(), decision)

    def test_assessment_schema_rejects_invalid_decision_and_list_limits(self):
        base = {
            "decision": "REQUIRED",
            "reason": "사용자 화면이 명시되어 UI 목업이 필요합니다.",
            "evidence_requirement_ids": [1],
            "candidate_screens": ["대시보드"],
        }
        with self.assertRaises(ValidationError):
            UiMockupNecessityDecision.model_validate({**base, "decision": "MAYBE"})
        with self.assertRaises(ValidationError):
            UiMockupNecessityDecision.model_validate({
                **base,
                "evidence_requirement_ids": [1, 2, 3, 4, 5, 6],
            })
        with self.assertRaises(ValidationError):
            UiMockupNecessityDecision.model_validate({
                **base,
                "candidate_screens": [f"화면 {index}" for index in range(6)],
            })

    def test_not_needed_allows_empty_candidate_screens(self):
        decision = UiMockupNecessityDecision(
            decision="NOT_NEEDED",
            reason="API와 배치 처리만 요구되어 UI 목업을 생략할 수 있습니다.",
            evidence_requirement_ids=[1],
            candidate_screens=[],
        )
        self.assertEqual(decision.candidate_screens, [])

    def _assess_with_mock(
        self,
        payload: dict,
        parsed_decision: UiMockupNecessityDecision,
    ) -> tuple[UiMockupNecessityDecision, Mock]:
        parsed_response = Mock(output_parsed=parsed_decision)
        client = Mock()
        client.responses.parse.return_value = parsed_response
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch(
                "app.domains.planning_resources.ui_mockup_service.OpenAI",
                return_value=client,
            ),
        ):
            decision = UiMockupLLMService().assess(
                UiMockupGenerationRequest.model_validate(payload)
            )
        return decision, client.responses.parse.call_args

    def _generate_with_mock(
        self,
        payload: dict,
        parsed_spec: UiMockupSpec,
    ) -> tuple[UiMockupSpec, Mock]:
        parsed_response = Mock(output_parsed=parsed_spec)
        client = Mock()
        client.responses.parse.return_value = parsed_response
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch(
                "app.domains.planning_resources.ui_mockup_service.OpenAI",
                return_value=client,
            ),
        ):
            generated = UiMockupLLMService().generate(
                UiMockupGenerationRequest.model_validate(payload)
            )
        return generated, client.responses.parse.call_args


if __name__ == "__main__":
    unittest.main()
