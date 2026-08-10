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
MAX_VISIBLE_MEMBERS = 5
MAX_VISIBLE_WBS_ITEMS = 3
MAX_VISIBLE_ROLE_GAPS = 3

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
            title=ImageFont.truetype(path, 42),
            heading=ImageFont.truetype(path, 28),
            body=ImageFont.truetype(path, 21),
            small=ImageFont.truetype(path, 18),
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
    role_label = " · ".join(team.primary_roles) or "역할 미정"
    lines: list[tuple[str, str]] = [
        ("small", "DELIVERY ROLE"),
        ("heading", role_label),
        ("body", team.team_name),
        (
            "body",
            "리더  "
            + (
                _member_label(request, team.leader_member_id)
                if team.leader_member_id is not None
                else "미지정"
            ),
        ),
    ]
    if team.member_ids:
        lines.append(("body", f"팀원  {len(team.member_ids)}명"))
        multi_role = set(team.multi_role_members)
        visible_members = team.member_ids[:MAX_VISIBLE_MEMBERS]
        for member_id in visible_members:
            suffix = " · 복수 역할" if member_id in multi_role else ""
            lines.append(("small", f"• {_member_label(request, member_id)}{suffix}"))
        hidden_member_count = len(team.member_ids) - len(visible_members)
        if hidden_member_count:
            lines.append(("small", f"+ {hidden_member_count}명"))
    else:
        lines.append(("body", "팀원: 배정 없음"))

    if team.assigned_wbs_ids:
        lines.append(("body", f"담당 WBS  {len(team.assigned_wbs_ids)}건"))
        visible_wbs_ids = team.assigned_wbs_ids[:MAX_VISIBLE_WBS_ITEMS]
        for wbs_id in visible_wbs_ids:
            lines.append(
                ("small", f"• {task_names.get(wbs_id, f'WBS {wbs_id}')}")
            )
        hidden_wbs_count = len(team.assigned_wbs_ids) - len(visible_wbs_ids)
        if hidden_wbs_count:
            lines.append(("small", f"+ {hidden_wbs_count}건"))
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
    return max(1, bottom - top) + 10


def _card_height(fonts: _Fonts, lines: Iterable[tuple[str, str]]) -> int:
    return 42 + sum(_line_height(getattr(fonts, style)) for style, _ in lines) + 26


def _warning_summary(organization: OrganizationView) -> tuple[str, ...]:
    lines = [
        f"부족 역할: {len(organization.role_gaps)}종",
        f"미배정 WBS: {len(organization.unassigned_wbs_ids)}건",
    ]
    visible_gaps = sorted(
        organization.role_gaps,
        key=lambda gap: gap.shortage_count,
        reverse=True,
    )[:MAX_VISIBLE_ROLE_GAPS]
    lines.extend(f"{gap.role_code}  +{gap.shortage_count}" for gap in visible_gaps)
    hidden_gap_count = len(organization.role_gaps) - len(visible_gaps)
    if hidden_gap_count:
        lines.append(f"+ {hidden_gap_count}개 역할")
    return tuple(lines)


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

    card_width = 500
    card_gap_x = 44
    card_gap_y = 48
    page_margin = 56
    team_count = max(1, len(organization.teams))
    columns = min(3, team_count)
    width = max(
        1400,
        page_margin * 2 + columns * card_width + (columns - 1) * card_gap_x,
    )
    pm_width = min(640, width - page_margin * 2)
    pm_label = (
        _member_label(request, organization.project_manager)
        if organization.project_manager is not None
        else "PM 정보 없음"
    )
    pm_lines = _wrap_text(
        measurement_draw,
        pm_label,
        fonts.heading,
        pm_width - 56,
    )

    prepared: list[tuple[OrganizationTeam, tuple[tuple[str, str], ...], int]] = []
    for team in organization.teams:
        lines = _wrapped_lines(
            measurement_draw,
            fonts,
            _team_content(request, team),
            card_width - 56,
        )
        prepared.append((team, lines, _card_height(fonts, lines)))

    title_bottom = 118
    pm_top = 142
    pm_height = 74 + len(pm_lines) * _line_height(fonts.heading) + 20
    teams_top = pm_top + pm_height + 92
    row_heights: list[int] = []
    for index in range(0, len(prepared), columns):
        row_heights.append(max(height for _, _, height in prepared[index:index + columns]))
    teams_height = sum(row_heights) + max(0, len(row_heights) - 1) * card_gap_y
    warnings = bool(organization.role_gaps or organization.unassigned_wbs_ids)
    warning_lines = _warning_summary(organization) if warnings else ()
    warnings_height = 86 + len(warning_lines) * 34 if warnings else 0
    content_bottom = teams_top + teams_height if organization.teams else teams_top + 100
    warning_top = content_bottom + 44
    height = (
        warning_top + warnings_height + page_margin
        if warnings
        else content_bottom + page_margin
    )

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
    draw.text((page_margin, 36), project_label, fill=dark, font=fonts.title)
    generated_label = organization.generated_at.isoformat()
    draw.text(
        (page_margin, title_bottom - 22),
        f"PROJECT ORGANIZATION  ·  {generated_label}",
        fill=muted,
        font=fonts.small,
    )

    pm_left = (width - pm_width) // 2
    draw.rounded_rectangle(
        (pm_left, pm_top, pm_left + pm_width, pm_top + pm_height),
        radius=14,
        fill=primary,
    )
    draw.text((pm_left + 28, pm_top + 18), "PROJECT MANAGER", fill="white", font=fonts.small)
    pm_text_y = pm_top + 54
    for line in pm_lines:
        draw.text((pm_left + 28, pm_text_y), line, fill="white", font=fonts.heading)
        pm_text_y += _line_height(fonts.heading)

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
        cursor_y = layout.y + 24
        for style, line in layout.lines:
            font = getattr(fonts, style)
            color = primary if style == "heading" else dark if style == "body" else muted
            draw.text((layout.x + 28, cursor_y), line, fill=color, font=font)
            cursor_y += _line_height(font)

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

    if warnings:
        draw.rounded_rectangle(
            (page_margin, warning_top, width - page_margin, warning_top + warnings_height),
            radius=12,
            fill="#f8fafc",
            outline=border,
            width=2,
        )
        draw.text(
            (page_margin + 28, warning_top + 20),
            "배정 현황",
            fill=dark,
            font=fonts.heading,
        )
        warning_y = warning_top + 66
        for index, line in enumerate(warning_lines):
            color = dark if index < 2 else muted
            draw.text(
                (page_margin + 28, warning_y),
                line,
                fill=color,
                font=fonts.body if index < 2 else fonts.small,
            )
            warning_y += 34

    output = BytesIO()
    image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return RenderedOrganizationChart(
        content=output.getvalue(),
        width=width,
        height=height,
    )
