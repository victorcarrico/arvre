"""Flowchart rendering of a session tree: left-to-right, or top-down for narrow screens."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from rich.text import Text

from arvre.layout import Row, format_age, inherited_name
from arvre.scanner import Session
from arvre.themes import Theme

BOX_W = 28
BOX_H = 4
GAP_X = 6
GAP_Y = 1
# Top-down layout: how far each level is indented under its parent.
INDENT = 4

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
    archived: bool = False
    running: bool = False


@dataclass
class FlowLayout:
    boxes: dict[str, Box]
    # Only the cells that carry a line are stored: row -> {x: direction bits}.
    lines: dict[int, dict[int, int]] = field(default_factory=dict)
    # Row -> boxes that cover that row, so drawing a row only touches nearby boxes.
    box_rows: dict[int, list[Box]] = field(default_factory=dict)
    width: int = 0
    height: int = 0
    vertical: bool = False  # top-down (children below their parent) rather than left-to-right


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

    by_id = {row.session.id: row for row in rows}
    boxes = {
        sid: Box(sid, depth[sid] * (BOX_W + GAP_X), y, archived=by_id[sid].archived, running=by_id[sid].running)
        for sid, y in ys.items()
    }
    if not boxes:
        return FlowLayout({})

    layout = FlowLayout(
        boxes=boxes,
        width=max(box.x for box in boxes.values()) + BOX_W,
        height=max(box.y for box in boxes.values()) + BOX_H,
    )
    for box in boxes.values():
        for dy in range(BOX_H):
            layout.box_rows.setdefault(box.y + dy, []).append(box)

    for parent_id, child_ids in kids.items():
        parent = boxes[parent_id]
        exit_x = parent.x + BOX_W
        exit_y = parent.y + 1
        bend_x = exit_x + GAP_X // 2
        for child_id in child_ids:
            child = boxes[child_id]
            enter_y = child.y + 1
            enter_x = child.x - 1
            _horizontal(layout.lines, exit_y, exit_x, bend_x)
            _vertical(layout.lines, bend_x, exit_y, enter_y)
            _horizontal(layout.lines, enter_y, bend_x, enter_x)

    return layout


def vertical_flow_layout(rows: list[Row]) -> FlowLayout:
    """Top-down, for narrow screens: boxes in tree order, one per band, each
    child indented under its parent. Width grows by INDENT per level instead
    of a whole box, so deep fork chains still fit."""
    if not rows:
        return FlowLayout({}, vertical=True)
    boxes: dict[str, Box] = {}
    parent_at_depth: dict[int, str] = {}  # rows are in tree order, so the last box seen one level up is the parent
    edges: list[tuple[str, str]] = []
    for i, row in enumerate(rows):
        sid = row.session.id
        boxes[sid] = Box(sid, row.depth * INDENT, i * (BOX_H + GAP_Y), archived=row.archived, running=row.running)
        parent_at_depth[row.depth] = sid
        if row.depth > 0 and row.depth - 1 in parent_at_depth:
            edges.append((parent_at_depth[row.depth - 1], sid))

    layout = FlowLayout(
        boxes=boxes,
        width=max(box.x for box in boxes.values()) + BOX_W,
        height=max(box.y for box in boxes.values()) + BOX_H,
        vertical=True,
    )
    for box in boxes.values():
        for dy in range(BOX_H):
            layout.box_rows.setdefault(box.y + dy, []).append(box)

    # A trunk drops from under the parent's left edge, then turns right into
    # each child's name row. Later children's trunks pass beside earlier
    # children's subtrees, which are always indented further, so nothing crosses.
    for parent_id, child_id in edges:
        parent, child = boxes[parent_id], boxes[child_id]
        trunk_x = parent.x + INDENT // 2
        enter_y = child.y + 1
        _vertical(layout.lines, trunk_x, parent.y + BOX_H, enter_y)
        _horizontal(layout.lines, enter_y, trunk_x, child.x - 1)
    return layout


def _mark(lines: dict[int, dict[int, int]], x: int, y: int, bits: int) -> None:
    row = lines.setdefault(y, {})
    row[x] = row.get(x, 0) | bits


def _horizontal(lines: dict[int, dict[int, int]], y: int, x1: int, x2: int) -> None:
    _mark(lines, x1, y, RIGHT)
    _mark(lines, x2, y, LEFT)
    for x in range(x1 + 1, x2):
        _mark(lines, x, y, LEFT | RIGHT)


def _vertical(lines: dict[int, dict[int, int]], x: int, y1: int, y2: int) -> None:
    if y1 == y2:
        return
    top, bottom = sorted((y1, y2))
    _mark(lines, x, top, DOWN)
    _mark(lines, x, bottom, UP)
    for y in range(top + 1, bottom):
        _mark(lines, x, y, UP | DOWN)


def flow_row(
    layout: FlowLayout,
    y: int,
    sessions: dict[str, Session],
    now: datetime,
    selected: str | None,
    theme: Theme,
) -> Text:
    """Draw one row of the chart. Cost depends on the row width, not the whole chart."""
    cells: list[tuple[str, str]] = [(" ", "")] * layout.width
    connector = theme.style("connector")
    for x, bits in layout.lines.get(y, {}).items():
        cells[x] = (LINE_CHARS.get(bits, "┼"), connector)
    for box in layout.box_rows.get(y, ()):
        session = sessions[box.sid]
        _draw_box_row(
            cells, box, y - box.y, session, now, theme,
            selected=box.sid == selected, inherited=inherited_name(session, sessions),
        )

    text = Text(no_wrap=True)
    for char, style in cells:
        text.append(char, style=style)
    return text


def _draw_box_row(
    cells: list[tuple[str, str]],
    box: Box,
    dy: int,
    session: Session,
    now: datetime,
    theme: Theme,
    selected: bool,
    inherited: bool,
) -> None:
    inner = BOX_W - 2
    label = session.name + (" ⑂" if inherited else "")
    if box.running:
        label = "▶ " + label
    elif box.archived:
        label = "○ " + label
    name = _fit(label, inner - 2)
    stats_text = f"{format_age(now, session.last_ts)} · {_children(session)}"
    if box.running:
        stats_text += " · running"
    if box.archived:
        stats_text += " · archived"
    stats = _fit(stats_text, inner - 2)
    line, role = {
        0: ("┌" + "─" * inner + "┐", "border"),
        1: ("│ " + name.ljust(inner - 2) + " │", "name"),
        2: ("│ " + stats.ljust(inner - 2) + " │", "meta"),
        3: ("└" + "─" * inner + "┘", "border"),
    }[dy]
    for dx, char in enumerate(line):
        frame = dy in (0, 3) or dx in (0, BOX_W - 1) or char == " "
        cell_role = "border" if frame else role
        cells[box.x + dx] = (char, theme.style(cell_role, selected))


def _children(session: Session) -> str:
    count = len(session.child_ids)
    if count == 0:
        return "no children"
    return "1 child" if count == 1 else f"{count} children"


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"
