"""Validated UI mockup contract and deterministic JPEG renderer."""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, model_validator


JPEG_CONTENT_TYPE = "image/jpeg"
JPEG_QUALITY = 92
BOARD_WIDTH = 1920
BOARD_HEIGHT = 1080

ComponentType = Literal[
    "header",
    "sidebar",
    "card",
    "table",
    "form",
    "chart",
    "kanban",
    "list",
    "modal",
    "search_bar",
    "filter_chips",
    "category_grid",
    "service_card",
    "map_preview",
    "date_picker",
    "time_slots",
    "option_selector",
    "price_summary",
    "payment_methods",
    "review_summary",
]
Platform = Literal["WEB", "MOBILE"]
Actor = Literal[
    "CUSTOMER",
    "PARTNER",
    "ADMIN",
    "PROJECT_MANAGER",
    "TEAM_MEMBER",
    "COMMUNITY_MEMBER",
    "OPERATOR",
    "PUBLIC",
]
PageType = Literal[
    "DASHBOARD",
    "LIST",
    "DETAIL",
    "FORM",
    "LANDING",
    "ECOMMERCE",
    "BOOKING",
    "MAP",
    "CHAT",
]
NavigationType = Literal["SIDEBAR", "TOP_NAV", "BOTTOM_NAV", "TABS", "NONE"]
LayoutType = Literal[
    "FULL_WIDTH",
    "TWO_COLUMN",
    "GRID",
    "MASTER_DETAIL",
    "FEED",
    "FORM_FLOW",
]

_GENERIC_SCREEN_NAMES = {
    "메인 화면",
    "목록 화면",
    "상세 화면",
    "폼 화면",
    "관리 화면",
}

_SEMANTIC_COMPONENTS = frozenset({
    "search_bar",
    "filter_chips",
    "category_grid",
    "service_card",
    "map_preview",
    "date_picker",
    "time_slots",
    "option_selector",
    "price_summary",
    "payment_methods",
    "review_summary",
})

_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
)


class UiMockupConfigurationError(RuntimeError):
    pass


class UiMockupRenderError(RuntimeError):
    pass


class UiMockupRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    category: str | None = Field(default=None, max_length=30)
    priority: str | None = Field(default=None, max_length=30)


class UiMockupGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    project_title: str = Field(min_length=1, max_length=200)
    project_description: str | None = Field(default=None, max_length=2000)
    confirmed_requirements: list[UiMockupRequirement] = Field(
        min_length=1,
        max_length=60,
    )


UiMockupNecessity = Literal["REQUIRED", "RECOMMENDED", "NOT_NEEDED"]


class UiMockupNecessityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: UiMockupNecessity
    reason: str = Field(min_length=1, max_length=300)
    evidence_requirement_ids: list[Annotated[int, Field(gt=0)]] = Field(
        default_factory=list,
        max_length=5,
    )
    candidate_screens: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def normalize(self) -> "UiMockupNecessityDecision":
        self.reason = " ".join(self.reason.split())
        if not re.search(r"[가-힣]", self.reason):
            raise ValueError("reason must be written in Korean")
        sentences = [
            sentence.strip()
            for sentence in re.split(r"[.!?。！？]+", self.reason)
            if sentence.strip()
        ]
        if len(sentences) > 2:
            raise ValueError("reason must contain at most two sentences")
        self.evidence_requirement_ids = list(
            dict.fromkeys(self.evidence_requirement_ids)
        )
        self.candidate_screens = list(dict.fromkeys(
            screen.strip()[:60]
            for screen in self.candidate_screens
            if screen.strip()
        ))
        if self.decision != "NOT_NEEDED" and not self.candidate_screens:
            raise ValueError(
                "REQUIRED or RECOMMENDED decisions need candidate screens"
            )
        return self


class UiMockupNecessityResponse(UiMockupNecessityDecision):
    project_id: int = Field(gt=0)


class UiMockupSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=50)
    component_type: ComponentType
    items: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def normalize(self) -> "UiMockupSection":
        self.title = self.title.strip()
        self.items = [item.strip()[:60] for item in self.items if item.strip()]
        if not self.title:
            raise ValueError("section title is required")
        return self


class UiMockupScreen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screen_name: str = Field(min_length=1, max_length=60)
    purpose: str = Field(min_length=1, max_length=160)
    actor: Actor
    journey_step: int = Field(ge=1, le=3)
    evidence_requirement_ids: list[Annotated[int, Field(gt=0)]] = Field(
        min_length=1,
        max_length=6,
    )
    page_type: PageType
    navigation_type: NavigationType
    layout_type: LayoutType
    navigation: list[str] = Field(default_factory=list, max_length=5)
    sections: list[UiMockupSection] = Field(min_length=1, max_length=6)
    primary_actions: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def normalize(self) -> "UiMockupScreen":
        self.screen_name = self.screen_name.strip()
        self.purpose = self.purpose.strip()
        self.navigation = [item.strip()[:30] for item in self.navigation if item.strip()]
        self.primary_actions = [
            item.strip()[:30] for item in self.primary_actions if item.strip()
        ]
        self.evidence_requirement_ids = list(
            dict.fromkeys(self.evidence_requirement_ids)
        )
        if not self.screen_name or not self.purpose:
            raise ValueError("screen name and purpose are required")
        if self.screen_name in _GENERIC_SCREEN_NAMES:
            raise ValueError("screen name must describe its domain purpose")
        if self.navigation_type == "NONE":
            self.navigation = []
        elif not self.navigation:
            raise ValueError("selected navigation type needs navigation labels")
        return self


class UiMockupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_title: str = Field(min_length=1, max_length=200)
    design_summary: str = Field(min_length=1, max_length=300)
    primary_actor: Actor
    journey_summary: str = Field(min_length=1, max_length=300)
    platform: Platform
    screens: list[UiMockupScreen] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_platform_navigation(self) -> "UiMockupSpec":
        if self.platform == "MOBILE" and any(
            screen.navigation_type == "SIDEBAR" for screen in self.screens
        ):
            raise ValueError("mobile screens cannot use sidebar navigation")
        if any(screen.actor != self.primary_actor for screen in self.screens):
            raise ValueError("all representative screens must use the primary actor")
        expected_steps = list(range(1, len(self.screens) + 1))
        if [screen.journey_step for screen in self.screens] != expected_steps:
            raise ValueError("screens must follow contiguous journey order")
        return self


class UiMockupGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    mockup: UiMockupSpec
    file_name: str
    content_type: str = JPEG_CONTENT_TYPE
    image_base64: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)


@dataclass(frozen=True)
class RenderedUiMockup:
    content: bytes
    width: int = BOARD_WIDTH
    height: int = BOARD_HEIGHT

    def to_base64(self) -> str:
        return base64.b64encode(self.content).decode("ascii")


@dataclass(frozen=True)
class _Fonts:
    title: ImageFont.FreeTypeFont
    screen: ImageFont.FreeTypeFont
    heading: ImageFont.FreeTypeFont
    body: ImageFont.FreeTypeFont
    small: ImageFont.FreeTypeFont


def _resolve_font_path() -> Path:
    configured = os.getenv("ORG_CHART_FONT_PATH")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return path
        raise UiMockupConfigurationError(
            "ORG_CHART_FONT_PATH does not reference a readable font file"
        )
    for candidate in _FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    raise UiMockupConfigurationError(
        "A Korean Noto Sans CJK font is required; configure ORG_CHART_FONT_PATH"
    )


def _load_fonts() -> _Fonts:
    path = str(_resolve_font_path())
    try:
        return _Fonts(
            title=ImageFont.truetype(path, 38),
            screen=ImageFont.truetype(path, 25),
            heading=ImageFont.truetype(path, 18),
            body=ImageFont.truetype(path, 15),
            small=ImageFont.truetype(path, 13),
        )
    except OSError as exc:
        raise UiMockupConfigurationError("The configured font could not be loaded") from exc


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text or " ", font=font)
    return right - left


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    value = " ".join(text.split())
    if _text_width(draw, value, font) <= max_width:
        return value
    suffix = "..."
    while value and _text_width(draw, value + suffix, font) > max_width:
        value = value[:-1]
    return value.rstrip() + suffix


def _draw_component(
    draw: ImageDraw.ImageDraw,
    section: UiMockupSection,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=9, fill="#FFFFFF", outline="#DDE4EE", width=2)
    draw.text(
        (x1 + 14, y1 + 11),
        _fit_text(draw, section.title, fonts.heading, x2 - x1 - 28),
        fill="#172033",
        font=fonts.heading,
    )
    top = y1 + 42
    component = section.component_type
    if component == "search_bar":
        bottom = min(y2 - 12, top + 42)
        if bottom > top:
            _draw_search(
                draw,
                (x1 + 12, top, x2 - 12, bottom),
                fonts,
                section.items[0] if section.items else "",
            )
        return
    if component in {"filter_chips", "option_selector"}:
        cursor_x = x1 + 12
        cursor_y = top
        row_height = 30
        for item in section.items[:6]:
            width = min(
                x2 - x1 - 24,
                max(58, _text_width(draw, item, fonts.small) + 24),
            )
            if cursor_x + width > x2 - 12:
                cursor_x = x1 + 12
                cursor_y += row_height + 7
            if cursor_y + row_height > y2 - 10:
                break
            selected = component == "option_selector" and cursor_x == x1 + 12
            draw.rounded_rectangle(
                (cursor_x, cursor_y, cursor_x + width, cursor_y + row_height),
                radius=15,
                fill="#DDE9FF" if selected else "#F7F9FC",
                outline="#9CB9EA" if selected else "#D6DEE9",
            )
            draw.text(
                (cursor_x + 12, cursor_y + 6),
                _fit_text(draw, item, fonts.small, width - 24),
                fill="#2458B5" if selected else "#526074",
                font=fonts.small,
            )
            cursor_x += width + 7
        return
    if component == "category_grid":
        items = section.items[:6]
        columns = 3
        gap = 7
        cell_width = (x2 - x1 - 24 - gap * (columns - 1)) // columns
        rows = max(1, (len(items) + columns - 1) // columns)
        cell_height = max(30, min(48, (y2 - top - 12 - gap * (rows - 1)) // rows))
        for index, item in enumerate(items):
            row, column = divmod(index, columns)
            left = x1 + 12 + column * (cell_width + gap)
            cell_top = top + row * (cell_height + gap)
            if cell_top + cell_height > y2 - 10:
                break
            draw.rounded_rectangle(
                (left, cell_top, left + cell_width, cell_top + cell_height),
                radius=8,
                fill="#F2F6FC",
                outline="#D7E1EF",
            )
            draw.ellipse(
                (left + 9, cell_top + 9, left + 25, cell_top + 25),
                fill="#C9DBFA",
            )
            draw.text(
                (left + 8, cell_top + cell_height - 19),
                _fit_text(draw, item, fonts.small, cell_width - 16),
                fill="#42526A",
                font=fonts.small,
            )
        return
    if component == "service_card":
        items = section.items[:3]
        row_height = max(46, min(62, (y2 - top - 10) // max(1, len(items))))
        for index, item in enumerate(items):
            row_top = top + index * row_height
            if row_top + row_height - 6 > y2 - 8:
                break
            draw.rounded_rectangle(
                (x1 + 12, row_top, x2 - 12, row_top + row_height - 6),
                radius=8,
                fill="#F9FBFE",
                outline="#DCE4EF",
            )
            draw.rounded_rectangle(
                (x1 + 20, row_top + 8, x1 + 64, row_top + row_height - 14),
                radius=6,
                fill="#D5E2F3",
            )
            draw.text(
                (x1 + 74, row_top + 11),
                _fit_text(draw, item, fonts.small, x2 - x1 - 100),
                fill="#334155",
                font=fonts.small,
            )
            draw.rounded_rectangle(
                (x1 + 74, row_top + 34, x2 - 28, row_top + 41),
                radius=3,
                fill="#E5EAF1",
            )
        return
    if component == "map_preview":
        map_box = (x1 + 12, top, x2 - 12, y2 - 12)
        draw.rounded_rectangle(map_box, radius=8, fill="#DFEADF")
        mx1, my1, mx2, my2 = map_box
        draw.line((mx1 + 12, my1 + 8, mx2 - 18, my2 - 14), fill="#FFFFFF", width=5)
        draw.line((mx1 + 34, my2 - 6, mx2 - 10, my1 + 18), fill="#FFFFFF", width=5)
        cx = mx1 + (mx2 - mx1) * 2 // 3
        cy = my1 + (my2 - my1) // 2
        draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill="#2563EB", outline="#FFFFFF", width=2)
        return
    if component == "date_picker":
        columns = 7
        gap = 5
        cell = max(16, min(28, (x2 - x1 - 24 - gap * (columns - 1)) // columns))
        for index in range(14):
            row, column = divmod(index, columns)
            left = x1 + 12 + column * (cell + gap)
            cell_top = top + row * (cell + 7)
            if cell_top + cell > y2 - 10:
                break
            selected = index == 9
            draw.rounded_rectangle(
                (left, cell_top, left + cell, cell_top + cell),
                radius=5,
                fill="#2563EB" if selected else "#F5F7FB",
                outline="#D9E1EC",
            )
        return
    if component == "time_slots":
        items = section.items[:6]
        columns = 3
        gap = 7
        width = (x2 - x1 - 24 - gap * (columns - 1)) // columns
        for index, item in enumerate(items):
            row, column = divmod(index, columns)
            left = x1 + 12 + column * (width + gap)
            slot_top = top + row * 37
            if slot_top + 30 > y2 - 8:
                break
            draw.rounded_rectangle(
                (left, slot_top, left + width, slot_top + 30),
                radius=7,
                fill="#EAF1FF" if index == 1 else "#FFFFFF",
                outline="#AFC3E1",
            )
            draw.text(
                (left + 8, slot_top + 6),
                _fit_text(draw, item, fonts.small, width - 16),
                fill="#315EC7",
                font=fonts.small,
            )
        return
    if component == "price_summary":
        for index, item in enumerate(section.items[:4]):
            row_top = top + index * 27
            if row_top + 21 > y2 - 8:
                break
            draw.text(
                (x1 + 14, row_top),
                _fit_text(draw, item, fonts.small, x2 - x1 - 95),
                fill="#475569",
                font=fonts.small,
            )
            draw.rounded_rectangle(
                (x2 - 78, row_top + 5, x2 - 14, row_top + 13),
                radius=4,
                fill="#BDD0EE" if index + 1 < len(section.items[:4]) else "#4F7FEF",
            )
        return
    if component == "payment_methods":
        for index, item in enumerate(section.items[:4]):
            row_top = top + index * 34
            if row_top + 28 > y2 - 8:
                break
            draw.rounded_rectangle(
                (x1 + 12, row_top, x2 - 12, row_top + 28),
                radius=7,
                fill="#F8FAFD",
                outline="#DCE3ED",
            )
            draw.ellipse(
                (x1 + 21, row_top + 8, x1 + 33, row_top + 20),
                fill="#2563EB" if index == 0 else "#FFFFFF",
                outline="#8FA3BF",
            )
            draw.text(
                (x1 + 42, row_top + 6),
                _fit_text(draw, item, fonts.small, x2 - x1 - 64),
                fill="#475569",
                font=fonts.small,
            )
        return
    if component == "review_summary":
        for index in range(5):
            left = x1 + 14 + index * 22
            draw.ellipse((left, top, left + 14, top + 14), fill="#F4B740")
        for index, item in enumerate(section.items[:3]):
            row_top = top + 27 + index * 25
            if row_top + 18 > y2 - 8:
                break
            draw.text(
                (x1 + 14, row_top),
                _fit_text(draw, item, fonts.small, 90),
                fill="#526074",
                font=fonts.small,
            )
            draw.rounded_rectangle(
                (x1 + 105, row_top + 5, x2 - 18, row_top + 12),
                radius=3,
                fill="#D8E3F4",
            )
        return
    if component == "chart":
        chart_bottom = y2 - 15
        colors = ("#B9CCFF", "#82A6FF", "#4F7FEF", "#315EC7")
        for index, height in enumerate((34, 58, 47, 76)):
            left = x1 + 18 + index * max(30, (x2 - x1 - 50) // 4)
            draw.rounded_rectangle(
                (left, chart_bottom - height, left + 22, chart_bottom),
                radius=4,
                fill=colors[index],
            )
        return
    if component == "table":
        row_height = max(24, min(34, (y2 - top - 10) // 4))
        for row in range(4):
            y = top + row * row_height
            fill = "#EFF4FF" if row == 0 else "#FFFFFF"
            draw.rectangle((x1 + 12, y, x2 - 12, y + row_height), fill=fill)
            draw.line((x1 + 12, y + row_height, x2 - 12, y + row_height), fill="#E4E9F1")
        return
    if component == "kanban":
        gap = 8
        width = (x2 - x1 - 32 - gap * 2) // 3
        for column in range(3):
            left = x1 + 12 + column * (width + gap)
            draw.rounded_rectangle((left, top, left + width, y2 - 12), radius=6, fill="#F5F7FB")
            draw.rounded_rectangle((left + 7, top + 27, left + width - 7, top + 65), radius=5, fill="#FFFFFF", outline="#DFE5EE")
        return
    if component == "form":
        for row in range(3):
            y = top + row * 38
            if y + 28 > y2 - 8:
                break
            draw.rounded_rectangle((x1 + 14, y, x2 - 14, y + 27), radius=5, fill="#F6F8FC", outline="#E1E6EF")
        return
    if component == "modal":
        inset = 22
        draw.rounded_rectangle((x1 + inset, top, x2 - inset, y2 - 12), radius=8, fill="#F9FAFC", outline="#CAD3E1")
    if not section.items:
        for index, width_ratio in enumerate((0.82, 0.66, 0.74)):
            y = top + index * 28
            if y + 12 > y2 - 8:
                break
            draw.rounded_rectangle(
                (x1 + 16, y + 3, x1 + 16 + int((x2 - x1 - 38) * width_ratio), y + 11),
                radius=4,
                fill="#E7ECF4",
            )
        return
    for index, item in enumerate(section.items[:3]):
        y = top + index * 28
        if y + 18 > y2 - 8:
            break
        draw.ellipse((x1 + 16, y + 6, x1 + 22, y + 12), fill="#4F7FEF")
        draw.text(
            (x1 + 30, y),
            _fit_text(draw, item, fonts.body, x2 - x1 - 46),
            fill="#526074",
            font=fonts.body,
        )


def _screen_labels(screen: UiMockupScreen, limit: int = 10) -> list[str]:
    labels: list[str] = []
    for section in screen.sections:
        for value in (section.title, *section.items):
            normalized = " ".join(value.split())
            if normalized and normalized not in labels:
                labels.append(normalized)
            if len(labels) >= limit:
                return labels
    return labels


def _draw_search(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    label: str,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=8, fill="#FFFFFF", outline="#D8E0EC", width=2)
    draw.ellipse((x1 + 14, y1 + 12, x1 + 25, y1 + 23), outline="#718096", width=2)
    draw.line((x1 + 24, y1 + 22, x1 + 30, y1 + 28), fill="#718096", width=2)
    draw.text(
        (x1 + 39, y1 + max(7, (y2 - y1 - 16) // 2)),
        _fit_text(draw, label, fonts.small, x2 - x1 - 52),
        fill="#64748B",
        font=fonts.small,
    )


def _draw_action(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    label: str,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=8, fill="#2563EB")
    fitted = _fit_text(draw, label, fonts.small, x2 - x1 - 20)
    draw.text(
        (x1 + max(10, (x2 - x1 - _text_width(draw, fitted, fonts.small)) // 2), y1 + 9),
        fitted,
        fill="#FFFFFF",
        font=fonts.small,
    )


def _draw_dashboard(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    columns = 2 if mobile else 3
    gap = 8 if mobile else 12
    card_height = 72 if mobile else 92
    card_width = (x2 - x1 - gap * (columns - 1)) // columns
    for index in range(columns):
        left = x1 + index * (card_width + gap)
        draw.rounded_rectangle(
            (left, y1, left + card_width, y1 + card_height),
            radius=9,
            fill="#FFFFFF",
            outline="#DBE3EE",
        )
        if index < len(labels):
            draw.text(
                (left + 10, y1 + 10),
                _fit_text(draw, labels[index], fonts.small, card_width - 20),
                fill="#475569",
                font=fonts.small,
            )
        draw.rounded_rectangle(
            (left + 10, y1 + card_height - 24, left + max(42, card_width - 30), y1 + card_height - 14),
            radius=4,
            fill="#DCE8FF",
        )

    chart_top = y1 + card_height + gap
    chart_bottom = min(y2, chart_top + (150 if mobile else 220))
    draw.rounded_rectangle(
        (x1, chart_top, x2, chart_bottom),
        radius=10,
        fill="#FFFFFF",
        outline="#DBE3EE",
    )
    chart_width = x2 - x1 - 36
    for index, ratio in enumerate((0.38, 0.58, 0.46, 0.72, 0.64)):
        left = x1 + 18 + index * chart_width // 5
        height = int((chart_bottom - chart_top - 55) * ratio)
        draw.rounded_rectangle(
            (left, chart_bottom - 18 - height, left + max(12, chart_width // 9), chart_bottom - 18),
            radius=4,
            fill=("#AFC8FF", "#7EA5FA", "#4F7FEF")[index % 3],
        )

    list_top = chart_bottom + gap
    for index, label in enumerate(labels[columns:columns + 3]):
        row_top = list_top + index * 42
        if row_top + 34 > y2:
            break
        draw.rounded_rectangle((x1, row_top, x2, row_top + 34), radius=7, fill="#FFFFFF", outline="#E3E8F0")
        draw.ellipse((x1 + 11, row_top + 12, x1 + 19, row_top + 20), fill="#4F7FEF")
        draw.text((x1 + 28, row_top + 8), _fit_text(draw, label, fonts.small, x2 - x1 - 40), fill="#526074", font=fonts.small)


def _draw_list_page(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    _draw_search(draw, (x1, y1, x2, y1 + 42), fonts, labels[0] if labels else "검색")
    chip_top = y1 + 52
    cursor = x1
    for label in (screen.navigation or labels[1:])[:3]:
        width = min(105, max(54, _text_width(draw, label, fonts.small) + 22))
        if cursor + width > x2:
            break
        draw.rounded_rectangle((cursor, chip_top, cursor + width, chip_top + 28), radius=14, fill="#EAF1FF")
        draw.text((cursor + 11, chip_top + 6), _fit_text(draw, label, fonts.small, width - 20), fill="#315EC7", font=fonts.small)
        cursor += width + 7
    row_top = chip_top + 40
    row_height = 62 if mobile else 70
    for index, label in enumerate(labels[1:7] or [""] * 5):
        top = row_top + index * (row_height + 8)
        if top + row_height > y2:
            break
        draw.rounded_rectangle((x1, top, x2, top + row_height), radius=9, fill="#FFFFFF", outline="#DDE4EE")
        draw.rounded_rectangle((x1 + 11, top + 11, x1 + 47, top + 47), radius=7, fill="#DCE8FF")
        if label:
            draw.text((x1 + 58, top + 12), _fit_text(draw, label, fonts.body, x2 - x1 - 72), fill="#334155", font=fonts.body)
        draw.rounded_rectangle((x1 + 58, top + 39, x2 - 22, top + 47), radius=4, fill="#E9EDF3")


def _draw_detail(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    hero_height = 150 if mobile else 210
    draw.rounded_rectangle((x1, y1, x2, y1 + hero_height), radius=12, fill="#DCE8F8")
    draw.polygon(
        ((x1 + 18, y1 + hero_height - 20), (x1 + 85, y1 + 65), (x1 + 145, y1 + hero_height - 20)),
        fill="#B5CAE6",
    )
    content_top = y1 + hero_height + 14
    for index, label in enumerate(labels[:4]):
        top = content_top + index * (54 if mobile else 60)
        if top + 45 > y2 - 48:
            break
        draw.text((x1 + 2, top), _fit_text(draw, label, fonts.body, x2 - x1 - 4), fill="#334155", font=fonts.body)
        draw.rounded_rectangle((x1 + 2, top + 28, x2 - 18 - index * 13, top + 36), radius=4, fill="#E5EAF1")
    if screen.primary_actions and y2 - 40 > content_top:
        _draw_action(draw, (x1, y2 - 40, x2, y2), fonts, screen.primary_actions[0])


def _draw_form(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    step_width = (x2 - x1 - 12) // 3
    for index in range(3):
        left = x1 + index * (step_width + 6)
        draw.rounded_rectangle((left, y1, left + step_width, y1 + 8), radius=4, fill="#2563EB" if index == 0 else "#DCE3ED")
    top = y1 + 28
    field_height = 62 if mobile else 70
    for index, label in enumerate(labels[:6] or [""] * 4):
        field_top = top + index * field_height
        if field_top + 50 > y2 - 48:
            break
        if label:
            draw.text((x1, field_top), _fit_text(draw, label, fonts.small, x2 - x1), fill="#475569", font=fonts.small)
        draw.rounded_rectangle((x1, field_top + 23, x2, field_top + 50), radius=7, fill="#FFFFFF", outline="#CDD6E3")
    if screen.primary_actions:
        _draw_action(draw, (x1, y2 - 40, x2, y2), fonts, screen.primary_actions[0])


def _draw_landing(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    hero_bottom = y1 + (210 if mobile else 260)
    draw.rounded_rectangle((x1, y1, x2, hero_bottom), radius=14, fill="#E8F0FF")
    if labels:
        draw.text((x1 + 18, y1 + 24), _fit_text(draw, labels[0], fonts.heading, x2 - x1 - 36), fill="#1E3A5F", font=fonts.heading)
    for index, ratio in enumerate((0.72, 0.54)):
        draw.rounded_rectangle((x1 + 18, y1 + 65 + index * 22, x1 + 18 + int((x2 - x1 - 36) * ratio), y1 + 76 + index * 22), radius=5, fill="#BFD2F2")
    if screen.primary_actions:
        _draw_action(draw, (x1 + 18, hero_bottom - 56, min(x2 - 18, x1 + 190), hero_bottom - 18), fonts, screen.primary_actions[0])
    feature_top = hero_bottom + 14
    columns = 1 if mobile else 3
    gap = 10
    width = (x2 - x1 - gap * (columns - 1)) // columns
    for index, label in enumerate(labels[1:1 + columns] or [""] * columns):
        left = x1 + index * (width + gap)
        bottom = min(y2, feature_top + 130)
        draw.rounded_rectangle((left, feature_top, left + width, bottom), radius=10, fill="#FFFFFF", outline="#DDE4EE")
        draw.ellipse((left + 14, feature_top + 14, left + 40, feature_top + 40), fill="#D7E5FF")
        if label:
            draw.text((left + 14, feature_top + 55), _fit_text(draw, label, fonts.small, width - 28), fill="#475569", font=fonts.small)


def _draw_ecommerce(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    _draw_search(draw, (x1, y1, x2, y1 + 42), fonts, labels[0] if labels else "상품 검색")
    columns = 2 if mobile else 3
    gap = 9 if mobile else 12
    grid_top = y1 + 55
    card_width = (x2 - x1 - gap * (columns - 1)) // columns
    card_height = 150 if mobile else 178
    for index in range(min(6, max(len(labels) - 1, 4))):
        row, column = divmod(index, columns)
        left = x1 + column * (card_width + gap)
        top = grid_top + row * (card_height + gap)
        if top + card_height > y2:
            break
        draw.rounded_rectangle((left, top, left + card_width, top + card_height), radius=10, fill="#FFFFFF", outline="#DCE3EC")
        image_bottom = top + int(card_height * 0.62)
        draw.rounded_rectangle((left + 8, top + 8, left + card_width - 8, image_bottom), radius=7, fill="#E5EBF3")
        draw.polygon(((left + 18, image_bottom - 12), (left + card_width // 2, top + 30), (left + card_width - 18, image_bottom - 12)), fill="#C5D2E3")
        label = labels[index + 1] if index + 1 < len(labels) else ""
        if label:
            draw.text((left + 10, image_bottom + 12), _fit_text(draw, label, fonts.small, card_width - 20), fill="#334155", font=fonts.small)
        draw.rounded_rectangle((left + 10, top + card_height - 22, left + max(40, card_width - 30), top + card_height - 14), radius=4, fill="#DCE8FF")


def _draw_booking(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    _draw_search(draw, (x1, y1, x2, y1 + 44), fonts, labels[0] if labels else "장소 또는 서비스 검색")
    selector_top = y1 + 57
    chip_width = (x2 - x1 - 16) // 3
    for index in range(3):
        left = x1 + index * (chip_width + 8)
        draw.rounded_rectangle((left, selector_top, left + chip_width, selector_top + 52), radius=9, fill="#FFFFFF", outline="#D7E0EC")
        if index + 1 < len(labels):
            draw.text((left + 8, selector_top + 17), _fit_text(draw, labels[index + 1], fonts.small, chip_width - 16), fill="#475569", font=fonts.small)
    slots_top = selector_top + 66
    columns = 2 if mobile else 3
    slot_width = (x2 - x1 - 8 * (columns - 1)) // columns
    for index in range(6):
        row, column = divmod(index, columns)
        left = x1 + column * (slot_width + 8)
        top = slots_top + row * 49
        if top + 39 > y2 - 50:
            break
        draw.rounded_rectangle((left, top, left + slot_width, top + 39), radius=8, fill="#EFF5FF" if index == 1 else "#FFFFFF", outline="#BFD0E8")
        label_index = index + 4
        if label_index < len(labels):
            draw.text((left + 9, top + 10), _fit_text(draw, labels[label_index], fonts.small, slot_width - 18), fill="#315EC7", font=fonts.small)
    if screen.primary_actions:
        _draw_action(draw, (x1, y2 - 40, x2, y2), fonts, screen.primary_actions[0])


def _draw_map(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    map_bottom = y1 + int((y2 - y1) * (0.62 if mobile else 0.72))
    draw.rounded_rectangle((x1, y1, x2, map_bottom), radius=12, fill="#DCE7DD")
    for offset in (0.2, 0.45, 0.7):
        px = x1 + int((x2 - x1) * offset)
        draw.line((px, y1 + 8, px - 45, map_bottom - 8), fill="#FFFFFF", width=7)
    for offset in (0.28, 0.58):
        py = y1 + int((map_bottom - y1) * offset)
        draw.line((x1 + 8, py, x2 - 8, py + 35), fill="#FFFFFF", width=7)
    for index, (rx, ry) in enumerate(((0.28, 0.35), (0.62, 0.48), (0.77, 0.25))):
        cx = x1 + int((x2 - x1) * rx)
        cy = y1 + int((map_bottom - y1) * ry)
        draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill="#2563EB", outline="#FFFFFF", width=3)
    card_top = map_bottom + 10
    for index, label in enumerate(labels[:2]):
        top = card_top + index * 58
        if top + 50 > y2:
            break
        draw.rounded_rectangle((x1, top, x2, top + 50), radius=9, fill="#FFFFFF", outline="#DDE4EE")
        draw.text((x1 + 12, top + 14), _fit_text(draw, label, fonts.small, x2 - x1 - 24), fill="#334155", font=fonts.small)


def _draw_chat(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    labels = _screen_labels(screen)
    bubble_width = int((x2 - x1) * 0.72)
    top = y1
    for index in range(5):
        right_aligned = index % 2 == 1
        left = x2 - bubble_width if right_aligned else x1
        height = 54 if index % 3 else 68
        draw.rounded_rectangle((left, top, left + bubble_width, top + height), radius=13, fill="#DCE8FF" if right_aligned else "#FFFFFF", outline="#D8E0EA")
        if index < len(labels):
            draw.text((left + 12, top + 12), _fit_text(draw, labels[index], fonts.small, bubble_width - 24), fill="#334155", font=fonts.small)
        top += height + 12
        if top + 65 > y2:
            break
    draw.rounded_rectangle((x1, y2 - 44, x2, y2), radius=12, fill="#FFFFFF", outline="#CBD5E1")
    draw.ellipse((x2 - 36, y2 - 34, x2 - 12, y2 - 10), fill="#2563EB")


def _draw_semantic_page(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    x1, y1, x2, y2 = box
    gap = 8 if mobile else 10
    action_height = 40 if screen.primary_actions else 0
    action_gap = gap if action_height else 0
    sections_bottom = y2 - action_height - action_gap
    available = sections_bottom - y1 - gap * (len(screen.sections) - 1)
    section_height = max(86, available // len(screen.sections))

    top = y1
    for section in screen.sections:
        bottom = min(sections_bottom, top + section_height)
        if bottom - top < 72:
            break
        _draw_component(draw, section, (x1, top, x2, bottom), fonts)
        top = bottom + gap

    if screen.primary_actions:
        _draw_action(
            draw,
            (x1, y2 - action_height, x2, y2),
            fonts,
            screen.primary_actions[0],
        )


def _draw_page_content(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
    mobile: bool,
) -> None:
    if any(
        section.component_type in _SEMANTIC_COMPONENTS
        for section in screen.sections
    ):
        _draw_semantic_page(draw, screen, box, fonts, mobile)
        return
    renderer = {
        "DASHBOARD": _draw_dashboard,
        "LIST": _draw_list_page,
        "DETAIL": _draw_detail,
        "FORM": _draw_form,
        "LANDING": _draw_landing,
        "ECOMMERCE": _draw_ecommerce,
        "BOOKING": _draw_booking,
        "MAP": _draw_map,
        "CHAT": _draw_chat,
    }[screen.page_type]
    renderer(draw, screen, box, fonts, mobile)


def _draw_mobile_screen(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=36, fill="#111827")
    inner = (x1 + 8, y1 + 8, x2 - 8, y2 - 8)
    draw.rounded_rectangle(inner, radius=30, fill="#F8FAFC")
    draw.rounded_rectangle((x1 + (x2 - x1) // 2 - 42, y1 + 15, x1 + (x2 - x1) // 2 + 42, y1 + 23), radius=4, fill="#293548")
    draw.text((x1 + 22, y1 + 40), _fit_text(draw, screen.screen_name, fonts.screen, x2 - x1 - 44), fill="#172033", font=fonts.screen)
    draw.text((x1 + 22, y1 + 74), _fit_text(draw, screen.purpose, fonts.small, x2 - x1 - 44), fill="#64748B", font=fonts.small)

    content_top = y1 + 108
    if screen.navigation_type == "TABS":
        tab_width = max(54, (x2 - x1 - 44) // max(1, min(3, len(screen.navigation))))
        for index, label in enumerate(screen.navigation[:3]):
            left = x1 + 20 + index * tab_width
            draw.text((left, content_top), _fit_text(draw, label, fonts.small, tab_width - 8), fill="#2563EB" if index == 0 else "#64748B", font=fonts.small)
        draw.line((x1 + 20, content_top + 25, x2 - 20, content_top + 25), fill="#DCE3ED", width=2)
        content_top += 38

    bottom_navigation = screen.navigation_type == "BOTTOM_NAV"
    content_bottom = y2 - (76 if bottom_navigation else 24)
    _draw_page_content(draw, screen, (x1 + 20, content_top, x2 - 20, content_bottom), fonts, True)

    if bottom_navigation:
        nav_top = y2 - 66
        draw.rounded_rectangle((x1 + 12, nav_top, x2 - 12, y2 - 10), radius=18, fill="#FFFFFF", outline="#DDE4EE")
        labels = screen.navigation[:4]
        width = (x2 - x1 - 32) // max(1, len(labels))
        for index, label in enumerate(labels):
            center = x1 + 16 + index * width + width // 2
            draw.ellipse((center - 5, nav_top + 10, center + 5, nav_top + 20), fill="#2563EB" if index == 0 else "#A1ACBA")
            fitted = _fit_text(draw, label, fonts.small, width - 6)
            draw.text((center - _text_width(draw, fitted, fonts.small) // 2, nav_top + 27), fitted, fill="#2563EB" if index == 0 else "#64748B", font=fonts.small)


def _draw_web_screen(
    draw: ImageDraw.ImageDraw,
    screen: UiMockupScreen,
    box: tuple[int, int, int, int],
    fonts: _Fonts,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=18, fill="#FFFFFF", outline="#CBD5E1", width=2)
    draw.rounded_rectangle((x1, y1, x2, y1 + 42), radius=18, fill="#EAF0F8")
    draw.rectangle((x1, y1 + 24, x2, y1 + 42), fill="#EAF0F8")
    for dot, color in enumerate(("#F87171", "#FBBF24", "#34D399")):
        cx = x1 + 18 + dot * 18
        draw.ellipse((cx, y1 + 14, cx + 8, y1 + 22), fill=color)

    header_top = y1 + 42
    draw.rectangle((x1, header_top, x2, header_top + 66), fill="#FFFFFF")
    draw.text((x1 + 18, header_top + 10), _fit_text(draw, screen.screen_name, fonts.screen, x2 - x1 - 36), fill="#172033", font=fonts.screen)
    draw.text((x1 + 19, header_top + 41), _fit_text(draw, screen.purpose, fonts.small, x2 - x1 - 38), fill="#64748B", font=fonts.small)

    content_x1 = x1 + 18
    content_y1 = header_top + 122
    content_x2 = x2 - 18
    content_y2 = y2 - 18
    if screen.navigation_type == "SIDEBAR":
        sidebar_width = min(150, max(105, (x2 - x1) // 4))
        draw.rectangle((x1, header_top + 66, x1 + sidebar_width, y2), fill="#F4F7FB")
        for index, label in enumerate(screen.navigation[:5]):
            top = header_top + 86 + index * 42
            if index == 0:
                draw.rounded_rectangle((x1 + 10, top - 7, x1 + sidebar_width - 10, top + 25), radius=7, fill="#DDE9FF")
            draw.text((x1 + 18, top), _fit_text(draw, label, fonts.small, sidebar_width - 36), fill="#2458B5" if index == 0 else "#64748B", font=fonts.small)
        content_x1 = x1 + sidebar_width + 18
        content_y1 = header_top + 84
    elif screen.navigation_type in {"TOP_NAV", "TABS"}:
        nav_top = header_top + 66
        draw.rectangle((x1, nav_top, x2, nav_top + 43), fill="#F8FAFC")
        cursor = x1 + 18
        for index, label in enumerate(screen.navigation[:5]):
            fitted = _fit_text(draw, label, fonts.small, 90)
            draw.text((cursor, nav_top + 12), fitted, fill="#2563EB" if index == 0 else "#64748B", font=fonts.small)
            cursor += min(112, _text_width(draw, fitted, fonts.small) + 28)
        content_y1 = nav_top + 58
    else:
        content_y1 = header_top + 84

    _draw_page_content(draw, screen, (content_x1, content_y1, content_x2, content_y2), fonts, False)


def render_ui_mockup(spec: UiMockupSpec) -> RenderedUiMockup:
    fonts = _load_fonts()
    image = Image.new("RGB", (BOARD_WIDTH, BOARD_HEIGHT), "#F3F6FA")
    draw = ImageDraw.Draw(image)
    draw.text((60, 32), _fit_text(draw, spec.project_title, fonts.title, 1250), fill="#111827", font=fonts.title)
    draw.text((62, 86), _fit_text(draw, spec.design_summary, fonts.body, 1450), fill="#64748B", font=fonts.body)
    badge_width = 104
    draw.rounded_rectangle((BOARD_WIDTH - 60 - badge_width, 42, BOARD_WIDTH - 60, 78), radius=18, fill="#DDE9FF")
    platform_label = "모바일" if spec.platform == "MOBILE" else "웹"
    draw.text((BOARD_WIDTH - 60 - badge_width + 25, 51), platform_label, fill="#2458B5", font=fonts.body)

    screen_count = len(spec.screens)
    top = 135
    bottom = 1025
    if spec.platform == "MOBILE":
        gap = 54
        screen_width = min(420, (BOARD_WIDTH - 112 - gap * (screen_count - 1)) // screen_count)
        total_width = screen_width * screen_count + gap * (screen_count - 1)
        start = (BOARD_WIDTH - total_width) // 2
        for index, screen in enumerate(spec.screens):
            left = start + index * (screen_width + gap)
            _draw_mobile_screen(draw, screen, (left, top, left + screen_width, bottom), fonts)
    else:
        gap = 28
        margin = 56
        screen_width = (BOARD_WIDTH - margin * 2 - gap * (screen_count - 1)) // screen_count
        for index, screen in enumerate(spec.screens):
            left = margin + index * (screen_width + gap)
            _draw_web_screen(draw, screen, (left, top, left + screen_width, bottom), fonts)

    output = BytesIO()
    try:
        image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except OSError as exc:
        raise UiMockupRenderError("The UI mockup could not be encoded as JPEG") from exc
    content = output.getvalue()
    if not content.startswith(b"\xff\xd8\xff"):
        raise UiMockupRenderError("The rendered UI mockup is not a JPEG image")
    return RenderedUiMockup(content=content)
