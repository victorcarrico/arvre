"""Left-to-right flowchart rendering of a session tree."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rich.text import Text

from arvre.layout import Row, format_age
from arvre.scanner import Session
from arvre.themes import Theme

BOX_W = 28
BOX_H = 4
GAP_X = 6
GAP_Y = 1

UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8
LINE_CHARS = {
    UP | DOWN: "│",
    LEFT | RIGHT: "─",
    DOWN | RIGHT: "┌",
    DOWN | LEFT: "┐",
    UP | RIGHT: "└",
    UP | LEFT: "┘",
    UP | DOWN | RIGHT: "├",
    UP | DOWN | LEFT: "┤",
    DOWN | LEFT | RIGHT: "┬",
    UP | LEFT | RIGHT: "┴",
    UP | DOWN | LEFT | RIGHT: "┼",
    UP: "│",
    DOWN: "│",
    LEFT: "─",
    RIGHT: "─",
}


@dataclass(frozen=True)
class Box:
    sid: str
    x: int
    y: int


@dataclass
class FlowLayout:
    boxes: dict[str, Box]
    masks: list[list[int]]  # direction bits per cell, turned into line chars when drawn
    width: int
    height: int


def flow_layout(rows: list[Row]) -> FlowLayout:
    """Columns are tree depths; each parent is centred on its children."""
    kids: dict[str, list[str]] = {}
    for row in rows:
        if row.session.parent_id:
            kids.setdefault(row.session.parent_id, []).append(row.session.id)
    depth = {row.session.id: row.depth for row in rows}

    ys: dict[str, int] = {}
    slot = 0

    def place(sid: str) -> int:
        nonlocal slot
        children = kids.get(sid, [])
        if children:
            child_ys = [place(child) for child in children]
            ys[sid] = (child_ys[0] + child_ys[-1]) // 2
        else:
            ys[sid] = slot * (BOX_H + GAP_Y)
            slot += 1
        return ys[sid]

    for row in rows:
        if row.depth == 0:
            place(row.session.id)

    boxes = {sid: Box(sid, depth[sid] * (BOX_W + GAP_X), y) for sid, y in ys.items()}
    if not boxes:
        return FlowLayout({}, [], 0, 0)

    width = max(box.x for box in boxes.values()) + BOX_W
    height = max(box.y for box in boxes.values()) + BOX_H
    masks = [[0] * width for _ in range(height)]

    for parent_id, child_ids in kids.items():
        parent = boxes[parent_id]
        exit_x = parent.x + BOX_W
        exit_y = parent.y + 1
        bend_x = exit_x + GAP_X // 2
        for child_id in child_ids:
            child = boxes[child_id]
            enter_y = child.y + 1
            enter_x = child.x - 1
            _horizontal(masks, exit_y, exit_x, bend_x)
            _vertical(masks, bend_x, exit_y, enter_y)
            _horizontal(masks, enter_y, bend_x, enter_x)

    return FlowLayout(boxes, masks, width, height)


def _horizontal(masks: list[list[int]], y: int, x1: int, x2: int) -> None:
    masks[y][x1] |= RIGHT
    masks[y][x2] |= LEFT
    for x in range(x1 + 1, x2):
        masks[y][x] |= LEFT | RIGHT


def _vertical(masks: list[list[int]], x: int, y1: int, y2: int) -> None:
    if y1 == y2:
        return
    top, bottom = sorted((y1, y2))
    masks[top][x] |= DOWN
    masks[bottom][x] |= UP
    for y in range(top + 1, bottom):
        masks[y][x] |= UP | DOWN


def flow_text(
    layout: FlowLayout,
    sessions: dict[str, Session],
    now: datetime,
    selected: str | None,
    theme: Theme,
) -> Text:
    grid: list[list[tuple[str, str]]] = [
        [(LINE_CHARS.get(mask, "┼") if mask else " ", theme.style("connector") if mask else "") for mask in row]
        for row in layout.masks
    ]
    for box in layout.boxes.values():
        _draw_box(grid, box, sessions[box.sid], now, theme, box.sid == selected)

    text = Text(no_wrap=True)
    for y, row in enumerate(grid):
        for char, style in row:
            text.append(char, style=style)
        if y < len(grid) - 1:
            text.append("\n")
    return text


def _draw_box(
    grid: list[list[tuple[str, str]]],
    box: Box,
    session: Session,
    now: datetime,
    theme: Theme,
    selected: bool,
) -> None:
    inner = BOX_W - 2
    name = _fit(session.name, inner - 2)
    stats = _fit(f"{format_age(now, session.last_ts)} · {_children(session)}", inner - 2)
    lines = [
        ("┌" + "─" * inner + "┐", "border"),
        ("│ " + name.ljust(inner - 2) + " │", "name"),
        ("│ " + stats.ljust(inner - 2) + " │", "meta"),
        ("└" + "─" * inner + "┘", "border"),
    ]
    for dy, (line, role) in enumerate(lines):
        for dx, char in enumerate(line):
            frame = dy in (0, 3) or dx in (0, BOX_W - 1) or char == " "
            cell_role = "border" if frame else role
            grid[box.y + dy][box.x + dx] = (char, theme.style(cell_role, selected))


def _children(session: Session) -> str:
    count = len(session.child_ids)
    if count == 0:
        return "no children"
    return "1 child" if count == 1 else f"{count} children"


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"
