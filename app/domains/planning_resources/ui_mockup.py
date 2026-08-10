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
]

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
        if not self.screen_name or not self.purpose:
            raise ValueError("screen name and purpose are required")
        return self


class UiMockupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_title: str = Field(min_length=1, max_length=200)
    design_summary: str = Field(min_length=1, max_length=300)
    screens: list[UiMockupScreen] = Field(min_length=1, max_length=3)


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
    items = section.items or ["핵심 정보", "상태 및 세부 내용", "사용자 작업"]
    for index, item in enumerate(items[:3]):
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


def render_ui_mockup(spec: UiMockupSpec) -> RenderedUiMockup:
    fonts = _load_fonts()
    image = Image.new("RGB", (BOARD_WIDTH, BOARD_HEIGHT), "#F4F7FB")
    draw = ImageDraw.Draw(image)
    draw.text((60, 34), _fit_text(draw, spec.project_title, fonts.title, 1220), fill="#111827", font=fonts.title)
    draw.text((62, 88), _fit_text(draw, spec.design_summary, fonts.body, 1500), fill="#64748B", font=fonts.body)

    screen_count = len(spec.screens)
    gap = 28
    margin = 56
    top = 135
    bottom = 1025
    screen_width = (BOARD_WIDTH - margin * 2 - gap * (screen_count - 1)) // screen_count
    for index, screen in enumerate(spec.screens):
        x1 = margin + index * (screen_width + gap)
        x2 = x1 + screen_width
        draw.rounded_rectangle((x1, top, x2, bottom), radius=18, fill="#FFFFFF", outline="#CBD5E1", width=2)
        draw.rounded_rectangle((x1, top, x2, top + 44), radius=18, fill="#EAF0FF")
        draw.rectangle((x1, top + 25, x2, top + 44), fill="#EAF0FF")
        for dot, color in enumerate(("#F87171", "#FBBF24", "#34D399")):
            cx = x1 + 20 + dot * 20
            draw.ellipse((cx, top + 15, cx + 9, top + 24), fill=color)
        draw.text((x1 + 18, top + 58), _fit_text(draw, screen.screen_name, fonts.screen, screen_width - 36), fill="#172033", font=fonts.screen)
        draw.text((x1 + 18, top + 94), _fit_text(draw, screen.purpose, fonts.small, screen_width - 36), fill="#6B778C", font=fonts.small)

        content_top = top + 128
        action_height = 46 if screen.primary_actions else 0
        available = bottom - content_top - action_height - 18
        section_gap = 10
        section_height = max(92, (available - section_gap * (len(screen.sections) - 1)) // len(screen.sections))
        for section_index, section in enumerate(screen.sections):
            section_top = content_top + section_index * (section_height + section_gap)
            section_bottom = min(section_top + section_height, bottom - action_height - 14)
            if section_bottom - section_top < 70:
                break
            _draw_component(draw, section, (x1 + 16, section_top, x2 - 16, section_bottom), fonts)

        if screen.primary_actions:
            cursor = x2 - 18
            for action in reversed(screen.primary_actions):
                label = _fit_text(draw, action, fonts.small, min(130, screen_width // 3))
                width = min(150, _text_width(draw, label, fonts.small) + 28)
                cursor -= width
                draw.rounded_rectangle((cursor, bottom - 49, cursor + width, bottom - 17), radius=7, fill="#315EC7")
                draw.text((cursor + 14, bottom - 42), label, fill="#FFFFFF", font=fonts.small)
                cursor -= 8

    output = BytesIO()
    try:
        image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except OSError as exc:
        raise UiMockupRenderError("The UI mockup could not be encoded as JPEG") from exc
    content = output.getvalue()
    if not content.startswith(b"\xff\xd8\xff"):
        raise UiMockupRenderError("The rendered UI mockup is not a JPEG image")
    return RenderedUiMockup(content=content)
