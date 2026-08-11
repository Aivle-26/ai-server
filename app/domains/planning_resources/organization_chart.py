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


class OrganizationChartRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planning_request: PlanningResourceRequest
    organization: OrganizationView


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
    return member.member_name


def _team_content(
    request: PlanningResourceRequest,
    team: OrganizationTeam,
    *,
    section_label: str = "PROJECT MEMBER",
    hierarchy_label: str,
    is_project_manager: bool = False,
) -> list[tuple[str, str]]:
    member_id = team.member_ids[0]
    member = next(
        (
            candidate
            for candidate in request.project_members
            if candidate.project_member_id == member_id
        ),
        None,
    )
    missing_capability = member is not None and not member.roles
    lines: list[tuple[str, str]] = [
        ("small", section_label),
        ("heading", _member_label(request, member_id)),
    ]
    if is_project_manager:
        lines.extend([
            ("body", "PROJECT MANAGER"),
            ("small", "최상위"),
        ])
    elif missing_capability:
        lines.extend([
            ("body", "역량 미등록"),
            ("small", "직무 미배정"),
            ("small", hierarchy_label),
        ])
    else:
        primary_role = team.primary_roles[0] if team.primary_roles else "직무 미배정"
        lines.extend([
            ("body", primary_role),
            ("small", hierarchy_label),
        ])

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


def _assignment_footer(organization: OrganizationView) -> str | None:
    if not organization.unassigned_wbs_ids and not organization.role_gaps:
        return None
    return (
        f"배정 요약 · 미배정 WBS {len(organization.unassigned_wbs_ids)}건"
        f" · 역할 Gap {len(organization.role_gaps)}개"
    )


def _validate_render_input(
    request: PlanningResourceRequest,
    organization: OrganizationView,
) -> None:
    if request.project_id != organization.project_id:
        raise OrganizationChartRenderError(
            "organization project_id does not match the planning request"
        )
    request_member_ids = {
        member.project_member_id for member in request.project_members
    }
    displayed_member_ids = [
        member_id
        for team in organization.teams
        for member_id in team.member_ids
    ]
    if len(displayed_member_ids) != len(set(displayed_member_ids)):
        raise OrganizationChartRenderError(
            "organization cannot display the same member more than once"
        )
    if not set(displayed_member_ids).issubset(request_member_ids):
        raise OrganizationChartRenderError(
            "organization members must come from the planning request"
        )
    if any(not team.member_ids for team in organization.teams):
        raise OrganizationChartRenderError(
            "organization cannot render empty role nodes"
        )
    member_count = len(displayed_member_ids)
    if member_count > len(request_member_ids):
        raise OrganizationChartRenderError(
            "organization exceeds the real project member count"
        )
    if member_count > MAX_RENDERED_MEMBERS:
        raise OrganizationChartRenderError(
            f"organization exceeds the {MAX_RENDERED_MEMBERS} member render limit"
        )


def _hierarchy_parent_by_team(
    organization: OrganizationView,
) -> dict[str, str | None]:
    if not organization.teams:
        return {}
    pm_team = next(
        (
            team
            for team in organization.teams
            if organization.project_manager in team.member_ids
        ),
        None,
    )
    if pm_team is None:
        raise OrganizationChartRenderError(
            "organization must contain one project manager root"
        )
    if pm_team.reports_to is not None:
        raise OrganizationChartRenderError(
            "project manager cannot report to another member"
        )

    known_team_ids = {team.team_id for team in organization.teams}
    parents: dict[str, str | None] = {}
    for team in organization.teams:
        if team is pm_team:
            parents[team.team_id] = None
            continue
        parent = team.reports_to or pm_team.team_id
        if parent not in known_team_ids or parent == team.team_id:
            raise OrganizationChartRenderError(
                "organization parent must reference another member"
            )
        parents[team.team_id] = parent

    for team_id in known_team_ids:
        path: set[str] = set()
        current: str | None = team_id
        while current is not None:
            if current in path:
                raise OrganizationChartRenderError(
                    "organization hierarchy cannot form a cycle"
                )
            path.add(current)
            current = parents[current]
        if pm_team.team_id not in path:
            raise OrganizationChartRenderError(
                "every organization member must report to the project manager"
            )
    return parents


def _hierarchy_depths(
    parents: dict[str, str | None],
) -> dict[str, int]:
    depths: dict[str, int] = {}
    for team_id in parents:
        depth = 0
        current = team_id
        while parents[current] is not None:
            depth += 1
            current = parents[current]  # type: ignore[assignment]
        depths[team_id] = depth
    return depths


def render_organization_chart(
    request: PlanningResourceRequest,
    organization: OrganizationView,
) -> RenderedOrganizationChart:
    """Render a validated member hierarchy without recomputing allocation."""

    _validate_render_input(request, organization)
    parents = _hierarchy_parent_by_team(organization)
    depths = _hierarchy_depths(parents)
    fonts = _load_fonts()
    measurement_image = Image.new("RGB", (10, 10), "white")
    measurement_draw = ImageDraw.Draw(measurement_image)

    card_width = 400
    card_gap_x = 36
    card_gap_y = 32
    depth_gap_y = 96
    page_margin = 56
    title_bottom = 118
    tree_top = 154
    max_columns = max(
        1,
        min(
            12,
            (MAX_IMAGE_WIDTH - page_margin * 2 + card_gap_x)
            // (card_width + card_gap_x),
        ),
    )
    teams_by_id = {team.team_id: team for team in organization.teams}
    pm_team = next(
        team
        for team in organization.teams
        if organization.project_manager in team.member_ids
    )
    team_index = {
        team.team_id: index for index, team in enumerate(organization.teams)
    }
    children_by_parent: dict[str, list[OrganizationTeam]] = {}
    for team in organization.teams:
        parent_id = parents[team.team_id]
        if parent_id is not None:
            children_by_parent.setdefault(parent_id, []).append(team)
    for children in children_by_parent.values():
        children.sort(key=lambda team: team_index[team.team_id])
    hierarchy_order: list[OrganizationTeam] = []
    frontier = [pm_team]
    while frontier:
        hierarchy_order.extend(frontier)
        frontier = [
            child
            for parent in frontier
            for child in children_by_parent.get(parent.team_id, [])
        ]

    prepared_by_depth: dict[
        int,
        list[tuple[OrganizationTeam, tuple[tuple[str, str], ...], int]],
    ] = {}
    for team in hierarchy_order:
        parent_id = parents[team.team_id]
        parent = teams_by_id.get(parent_id) if parent_id is not None else None
        parent_label = (
            parent.primary_roles[0]
            if parent is not None and parent.primary_roles
            else parent.team_name
            if parent is not None
            else None
        )
        hierarchy_label = (
            "최상위"
            if team is pm_team
            else "PM 직속"
            if parent is pm_team
            else f"{parent_label} 산하"
            if parent_label is not None
            else "PM 직속"
        )
        lines = _wrapped_lines(
            measurement_draw,
            fonts,
            _team_content(
                request,
                team,
                section_label=(
                    "PROJECT MANAGER" if team is pm_team else "PROJECT MEMBER"
                ),
                hierarchy_label=hierarchy_label,
                is_project_manager=team is pm_team,
            ),
            card_width - 56,
        )
        prepared_by_depth.setdefault(depths[team.team_id], []).append(
            (team, lines, _card_height(fonts, lines))
        )

    layouts: list[_CardLayout] = []
    center_slot_by_team: dict[str, float] = {}

    def assign_subtree_slots(team: OrganizationTeam, start: int) -> int:
        children = children_by_parent.get(team.team_id, [])
        if not children:
            center_slot_by_team[team.team_id] = float(start)
            return 1
        cursor = start
        for child in children:
            cursor += assign_subtree_slots(child, cursor)
        center_slot_by_team[team.team_id] = (
            center_slot_by_team[children[0].team_id]
            + center_slot_by_team[children[-1].team_id]
        ) / 2
        return cursor - start

    leaf_slots = assign_subtree_slots(pm_team, 0)
    if leaf_slots <= max_columns:
        tree_width = (
            leaf_slots * card_width
            + max(0, leaf_slots - 1) * card_gap_x
        )
        width = max(1400, page_margin * 2 + tree_width)
        tree_x = (width - tree_width) // 2
        depth_y = tree_top
        for depth in sorted(prepared_by_depth):
            depth_items = prepared_by_depth[depth]
            row_height = max(item[2] for item in depth_items)
            for team, lines, card_height in depth_items:
                layouts.append(
                    _CardLayout(
                        team=team,
                        x=tree_x + round(
                            center_slot_by_team[team.team_id]
                            * (card_width + card_gap_x)
                        ),
                        y=depth_y,
                        width=card_width,
                        height=card_height,
                        lines=lines,
                    )
                )
            depth_y += row_height + depth_gap_y
    else:
        widest_row = max(
            min(max_columns, len(items))
            for items in prepared_by_depth.values()
        )
        width = max(
            1400,
            page_margin * 2
            + widest_row * card_width
            + max(0, widest_row - 1) * card_gap_x,
        )
        depth_y = tree_top
        for depth in sorted(prepared_by_depth):
            depth_items = prepared_by_depth[depth]
            for start in range(0, len(depth_items), max_columns):
                row_items = depth_items[start:start + max_columns]
                row_height = max(item[2] for item in row_items)
                row_width = (
                    len(row_items) * card_width
                    + max(0, len(row_items) - 1) * card_gap_x
                )
                row_x = (width - row_width) // 2
                for column, (team, lines, card_height) in enumerate(row_items):
                    layouts.append(
                        _CardLayout(
                            team=team,
                            x=row_x + column * (card_width + card_gap_x),
                            y=depth_y,
                            width=card_width,
                            height=card_height,
                            lines=lines,
                        )
                    )
                depth_y += row_height + card_gap_y
            depth_y += depth_gap_y - card_gap_y

    footer = _assignment_footer(organization)
    content_bottom = max(
        (layout.y + layout.height for layout in layouts),
        default=tree_top,
    )
    footer_top = content_bottom + 44
    height = footer_top + (54 if footer else 0) + page_margin
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

    project_label = request.project_name or f"프로젝트 {request.project_id}"
    draw.text((page_margin, 36), project_label, fill=dark, font=fonts.title)
    draw.text(
        (page_margin, title_bottom - 22),
        f"PROJECT ORGANIZATION  ·  {organization.generated_at.isoformat()}",
        fill=muted,
        font=fonts.small,
    )

    layouts_by_team = {layout.team.team_id: layout for layout in layouts}
    parent_groups_by_depth: dict[int, list[tuple[_CardLayout, list[_CardLayout]]]] = {}
    for parent_id, children in children_by_parent.items():
        child_layouts = [layouts_by_team[child.team_id] for child in children]
        child_depth = depths[children[0].team_id]
        parent_groups_by_depth.setdefault(child_depth, []).append(
            (layouts_by_team[parent_id], child_layouts)
        )
    for child_depth in sorted(parent_groups_by_depth):
        groups = sorted(
            parent_groups_by_depth[child_depth],
            key=lambda item: item[0].x,
        )
        parent_bottom = max(parent.y + parent.height for parent, _ in groups)
        child_top = min(child.y for _, children in groups for child in children)
        connector_gap = child_top - parent_bottom
        for index, (parent, children) in enumerate(groups):
            connector_y = parent_bottom + max(
                16,
                connector_gap * (index + 1) // (len(groups) + 1),
            )
            parent_center_x = parent.x + parent.width // 2
            child_centers = [child.x + child.width // 2 for child in children]
            draw.line(
                (
                    parent_center_x,
                    parent.y + parent.height,
                    parent_center_x,
                    connector_y,
                ),
                fill=border,
                width=3,
            )
            draw.line(
                (
                    min([parent_center_x, *child_centers]),
                    connector_y,
                    max([parent_center_x, *child_centers]),
                    connector_y,
                ),
                fill=border,
                width=3,
            )
            for child, child_center_x in zip(children, child_centers, strict=True):
                draw.line(
                    (
                        child_center_x,
                        connector_y,
                        child_center_x,
                        child.y,
                    ),
                    fill=border,
                    width=3,
                )

    for layout in layouts:
        is_pm = layout.team is pm_team
        draw.rounded_rectangle(
            (
                layout.x,
                layout.y,
                layout.x + layout.width,
                layout.y + layout.height,
            ),
            radius=12,
            fill=primary if is_pm else "white",
            outline=primary if is_pm else border,
            width=2,
        )
        cursor_y = layout.y + 24
        for style, line in layout.lines:
            font = getattr(fonts, style)
            color = (
                "white"
                if is_pm
                else primary
                if style == "heading"
                else dark
                if style == "body"
                else muted
            )
            draw.text((layout.x + 28, cursor_y), line, fill=color, font=font)
            cursor_y += _line_height(font)

    if footer:
        draw.line(
            (page_margin, footer_top, width - page_margin, footer_top),
            fill=border,
            width=2,
        )
        draw.text(
            (page_margin, footer_top + 20),
            footer,
            fill=muted,
            font=fonts.small,
        )

    output = BytesIO()
    image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return RenderedOrganizationChart(
        content=output.getvalue(),
        width=width,
        height=height,
    )
