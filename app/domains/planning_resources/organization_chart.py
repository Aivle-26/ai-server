"""Organization-chart request contract and deterministic JPG renderer."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field

from .schemas import PlanningResourceRequest
from .view_models import OrganizationMetadata, OrganizationTeam, OrganizationView


JPEG_CONTENT_TYPE = "image/jpeg"
JPEG_QUALITY = 92
MAX_IMAGE_WIDTH = 7200
MAX_IMAGE_HEIGHT = 7200
MAX_IMAGE_PIXELS = 36_000_000
MAX_RENDERED_MEMBERS = 500

_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
)


class OrganizationChartConfigurationError(RuntimeError):
    """Raised when a readable Korean font is not configured."""


class OrganizationChartRenderError(RuntimeError):
    """Raised when an organization cannot be rendered within safe bounds."""


class OrganizationChartGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planning_request: PlanningResourceRequest
    organization_metadata: OrganizationMetadata | None = None


class OrganizationChartGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: OrganizationView
    file_name: str
    content_type: str = JPEG_CONTENT_TYPE
    image_base64: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)


@dataclass(frozen=True)
class RenderedOrganizationChart:
    content: bytes
    width: int
    height: int

    def to_base64(self) -> str:
        return base64.b64encode(self.content).decode("ascii")


@dataclass(frozen=True)
class _Fonts:
    title: ImageFont.FreeTypeFont
    heading: ImageFont.FreeTypeFont
    body: ImageFont.FreeTypeFont
    small: ImageFont.FreeTypeFont


@dataclass(frozen=True)
class _CardLayout:
    team: OrganizationTeam
    x: int
    y: int
    width: int
    height: int
    lines: tuple[tuple[str, str], ...]


def _resolve_font_path() -> Path:
    configured = os.getenv("ORG_CHART_FONT_PATH")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return path
        raise OrganizationChartConfigurationError(
            "ORG_CHART_FONT_PATH does not reference a readable font file"
        )

    for candidate in _FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    raise OrganizationChartConfigurationError(
        "A Korean Noto Sans CJK font is required; configure ORG_CHART_FONT_PATH"
    )


def _load_fonts() -> _Fonts:
    path = str(_resolve_font_path())
    try:
        return _Fonts(
            title=ImageFont.truetype(path, 34),
            heading=ImageFont.truetype(path, 24),
            body=ImageFont.truetype(path, 18),
            small=ImageFont.truetype(path, 15),
        )
    except OSError as exc:
        raise OrganizationChartConfigurationError(
            "ORG_CHART_FONT_PATH could not be loaded as a TrueType/OpenType font"
        ) from exc


def _text_width(
    draw: ImageDraw.ImageDraw,
    value: str,
    font: ImageFont.ImageFont,
) -> int:
    left, _, right, _ = draw.textbbox((0, 0), value or " ", font=font)
    return right - left


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    value: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    normalized = " ".join(value.split())
    if not normalized:
        return ["-"]
    if _text_width(draw, normalized, font) <= max_width:
        return [normalized]

    lines: list[str] = []
    current = ""
    for character in normalized:
        candidate = current + character
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current.rstrip())
            current = character.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
    return lines


def _member_label(request: PlanningResourceRequest, member_id: int) -> str:
    member = next(
        (
            candidate
            for candidate in request.project_members
            if candidate.project_member_id == member_id
        ),
        None,
    )
    if member is None or member.member_name is None:
        return f"ID {member_id}"
    return f"{member.member_name} (ID {member_id})"


def _team_content(
    request: PlanningResourceRequest,
    team: OrganizationTeam,
) -> list[tuple[str, str]]:
    task_names = {
        task.wbs_id: task.wbs_name for task in request.wbs_tasks
    }
    lines: list[tuple[str, str]] = [
        ("heading", team.team_name),
        ("body", "대표 역할: " + ", ".join(team.primary_roles)),
        (
            "body",
            "팀장: "
            + (
                _member_label(request, team.leader_member_id)
                if team.leader_member_id is not None
                else "미지정"
            ),
        ),
    ]
    if team.member_ids:
        lines.append(("body", f"팀원 ({len(team.member_ids)}명)"))
        multi_role = set(team.multi_role_members)
        for member_id in team.member_ids:
            suffix = " · 복수 역할" if member_id in multi_role else ""
            lines.append(("small", f"- {_member_label(request, member_id)}{suffix}"))
    else:
        lines.append(("body", "팀원: 배정 없음"))

    if team.assigned_wbs_ids:
        lines.append(("body", "담당 WBS"))
        for wbs_id in team.assigned_wbs_ids:
            lines.append(
                ("small", f"- {task_names.get(wbs_id, f'WBS {wbs_id}')} (#{wbs_id})")
            )
    else:
        lines.append(("body", "담당 WBS: 없음"))

    lines.append(("small", f"상위 보고: {team.reports_to or '미지정'}"))
    collaborators = ", ".join(team.collaborates_with) or "미지정"
    lines.append(("small", f"협업 팀: {collaborators}"))
    return lines


def _wrapped_lines(
    draw: ImageDraw.ImageDraw,
    fonts: _Fonts,
    content: Iterable[tuple[str, str]],
    width: int,
) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for style, value in content:
        font = getattr(fonts, style)
        for line in _wrap_text(draw, value, font, width):
            result.append((style, line))
    return tuple(result)


def _line_height(font: ImageFont.ImageFont) -> int:
    left, top, right, bottom = font.getbbox("Ag한")
    return max(1, bottom - top) + 8


def _card_height(fonts: _Fonts, lines: Iterable[tuple[str, str]]) -> int:
    return 34 + sum(_line_height(getattr(fonts, style)) for style, _ in lines) + 22


def _validate_render_input(
    request: PlanningResourceRequest,
    organization: OrganizationView,
) -> None:
    if request.project_id != organization.project_id:
        raise OrganizationChartRenderError(
            "organization project_id does not match the planning request"
        )
    member_count = sum(len(team.member_ids) for team in organization.teams)
    if member_count > MAX_RENDERED_MEMBERS:
        raise OrganizationChartRenderError(
            f"organization exceeds the {MAX_RENDERED_MEMBERS} member render limit"
        )


def render_organization_chart(
    request: PlanningResourceRequest,
    organization: OrganizationView,
) -> RenderedOrganizationChart:
    """Render one validated organization view as a private-transfer JPG."""

    _validate_render_input(request, organization)
    fonts = _load_fonts()
    measurement_image = Image.new("RGB", (10, 10), "white")
    measurement_draw = ImageDraw.Draw(measurement_image)

    card_width = 440
    card_gap_x = 36
    card_gap_y = 42
    page_margin = 64
    team_count = max(1, len(organization.teams))
    columns = min(4, team_count)
    width = max(
        1200,
        page_margin * 2 + columns * card_width + (columns - 1) * card_gap_x,
    )

    prepared: list[tuple[OrganizationTeam, tuple[tuple[str, str], ...], int]] = []
    for team in organization.teams:
        lines = _wrapped_lines(
            measurement_draw,
            fonts,
            _team_content(request, team),
            card_width - 48,
        )
        prepared.append((team, lines, _card_height(fonts, lines)))

    title_bottom = 104
    pm_top = 126
    pm_height = 100
    teams_top = pm_top + pm_height + 86
    row_heights: list[int] = []
    for index in range(0, len(prepared), columns):
        row_heights.append(max(height for _, _, height in prepared[index:index + columns]))
    teams_height = sum(row_heights) + max(0, len(row_heights) - 1) * card_gap_y
    warnings = len(organization.role_gaps) + bool(organization.unassigned_wbs_ids)
    warnings_height = 82 + int(warnings) * 32 if warnings else 0
    height = teams_top + teams_height + warnings_height + page_margin
    if not organization.teams:
        height = teams_top + 120 + warnings_height + page_margin

    if (
        width > MAX_IMAGE_WIDTH
        or height > MAX_IMAGE_HEIGHT
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise OrganizationChartRenderError(
            "organization chart exceeds the safe image size limit"
        )

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    dark = "#172033"
    muted = "#667085"
    primary = "#2563eb"
    border = "#cbd5e1"
    pale = "#eff6ff"

    project_label = request.project_name or f"프로젝트 {request.project_id}"
    draw.text((page_margin, 42), project_label, fill=dark, font=fonts.title)
    generated_label = organization.generated_at.isoformat()
    draw.text(
        (page_margin, title_bottom - 24),
        f"조직도 · 생성 시각 {generated_label}",
        fill=muted,
        font=fonts.small,
    )

    pm_width = min(560, width - page_margin * 2)
    pm_left = (width - pm_width) // 2
    draw.rounded_rectangle(
        (pm_left, pm_top, pm_left + pm_width, pm_top + pm_height),
        radius=14,
        fill=primary,
    )
    draw.text((pm_left + 24, pm_top + 16), "PROJECT MANAGER", fill="white", font=fonts.small)
    pm_label = (
        _member_label(request, organization.project_manager)
        if organization.project_manager is not None
        else "PM 정보 없음"
    )
    draw.text((pm_left + 24, pm_top + 47), pm_label, fill="white", font=fonts.heading)

    layouts: list[_CardLayout] = []
    row_y = teams_top
    item_index = 0
    for row_height in row_heights:
        row_items = prepared[item_index:item_index + columns]
        row_width = len(row_items) * card_width + max(0, len(row_items) - 1) * card_gap_x
        row_x = (width - row_width) // 2
        for column, (team, lines, card_height) in enumerate(row_items):
            layouts.append(
                _CardLayout(
                    team=team,
                    x=row_x + column * (card_width + card_gap_x),
                    y=row_y,
                    width=card_width,
                    height=card_height,
                    lines=lines,
                )
            )
        row_y += row_height + card_gap_y
        item_index += columns

    pm_center = (width // 2, pm_top + pm_height)
    for layout in layouts:
        team_center = (layout.x + layout.width // 2, layout.y)
        draw.line(
            (pm_center[0], pm_center[1], pm_center[0], team_center[1] - 28),
            fill=border,
            width=3,
        )
        draw.line(
            (pm_center[0], team_center[1] - 28, team_center[0], team_center[1] - 28),
            fill=border,
            width=3,
        )
        draw.line(
            (team_center[0], team_center[1] - 28, team_center[0], team_center[1]),
            fill=border,
            width=3,
        )

    by_team_id = {layout.team.team_id: layout for layout in layouts}
    for layout in layouts:
        if layout.team.reports_to and layout.team.reports_to in by_team_id:
            parent = by_team_id[layout.team.reports_to]
            draw.line(
                (
                    parent.x + parent.width // 2,
                    parent.y + parent.height,
                    layout.x + layout.width // 2,
                    layout.y,
                ),
                fill="#475569",
                width=2,
            )

    for layout in layouts:
        draw.rounded_rectangle(
            (
                layout.x,
                layout.y,
                layout.x + layout.width,
                layout.y + layout.height,
            ),
            radius=12,
            fill="white",
            outline=border,
            width=2,
        )
        cursor_y = layout.y + 20
        for style, line in layout.lines:
            font = getattr(fonts, style)
            color = primary if style == "heading" else dark if style == "body" else muted
            draw.text((layout.x + 24, cursor_y), line, fill=color, font=font)
            cursor_y += _line_height(font)

    warning_y = teams_top + teams_height + 36
    if not organization.teams:
        draw.rounded_rectangle(
            (page_margin, teams_top, width - page_margin, teams_top + 90),
            radius=12,
            fill=pale,
            outline=border,
        )
        draw.text(
            (page_margin + 24, teams_top + 28),
            "추천된 역할별 팀이 없습니다.",
            fill=dark,
            font=fonts.body,
        )
        warning_y = teams_top + 126

    if warnings:
        draw.text((page_margin, warning_y), "인력 및 배정 경고", fill=dark, font=fonts.heading)
        warning_y += 38
        for gap in organization.role_gaps:
            draw.text(
                (page_margin, warning_y),
                f"- 부족 역할 {gap.role_code}: {gap.shortage_count}명",
                fill="#b42318",
                font=fonts.body,
            )
            warning_y += 32
        if organization.unassigned_wbs_ids:
            ids = ", ".join(str(item) for item in organization.unassigned_wbs_ids)
            for line in _wrap_text(
                draw,
                f"- 미배정 WBS: {ids}",
                fonts.body,
                width - page_margin * 2,
            ):
                draw.text((page_margin, warning_y), line, fill="#b54708", font=fonts.body)
                warning_y += 32

    output = BytesIO()
    image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return RenderedOrganizationChart(
        content=output.getvalue(),
        width=width,
        height=height,
    )
