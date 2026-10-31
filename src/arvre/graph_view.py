"""Clickable, keyboard-navigable widget that draws the session graph."""

from __future__ import annotations

from datetime import datetime

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.geometry import Region
from textual.message import Message
from textual.widget import Widget

from arvre.flowchart import BOX_H, BOX_W, FlowLayout, flow_layout, flow_text
from arvre.layout import Row, row_label, row_segments
from arvre.scanner import Session
from arvre.themes import THEMES, Theme


class GraphView(Widget, can_focus=True):
    BINDINGS = [
        Binding("up,k", "move(-1)", "Up", show=False),
        Binding("down,j", "move(1)", "Down", show=False),
        Binding("left,h", "parent", "Parent"),
        Binding("right,l", "child", "Child"),
        Binding("enter", "activate", "Open"),
    ]

    class Highlighted(Message):
        def __init__(self, session_id: str | None) -> None:
            super().__init__()
            self.session_id = session_id

    class Activated(Message):
        def __init__(self, session_id: str | None) -> None:
            super().__init__()
            self.session_id = session_id

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.sessions: dict[str, Session] = {}
        self.rows: list[Row] = []
        self.now = datetime.now().astimezone()
        self.style_name = "compact"
        self.theme: Theme = THEMES["classic"]
        self._index = 0
        self._flow: FlowLayout | None = None

    # --- data ---------------------------------------------------------------

    def set_data(
        self,
        sessions: dict[str, Session],
        rows: list[Row],
        now: datetime,
        style_name: str,
        theme: Theme,
    ) -> None:
        selected = self.selected_id
        self.sessions = sessions
        self.rows = rows
        self.now = now
        self.style_name = style_name
        self.theme = theme
        self._index = next((i for i, r in enumerate(rows) if r.session.id == selected), 0)

        if style_name == "flow":
            self._flow = flow_layout(rows)
            width, height = self._flow.width, self._flow.height
        else:
            self._flow = None
            labels = [row_label(row, sessions, now) for row in rows]
            width = max((cell_len(label) for label in labels), default=0)
            height = len(labels)
        self.styles.width = max(width, 1)
        self.styles.height = max(height, 1)
        self.refresh(layout=True)
        self.post_message(self.Highlighted(self.selected_id))

    @property
    def selected_id(self) -> str | None:
        if not self.rows:
            return None
        return self.rows[self._index].session.id

    def select_id(self, session_id: str) -> bool:
        for i, row in enumerate(self.rows):
            if row.session.id == session_id:
                self._select(i)
                return True
        return False

    def _select(self, index: int) -> None:
        if not self.rows:
            return
        self._index = max(0, min(index, len(self.rows) - 1))
        self.refresh()
        self._reveal()
        self.post_message(self.Highlighted(self.selected_id))

    def _reveal(self) -> None:
        if self._flow:
            box = self._flow.boxes[self.selected_id]
            region = Region(box.x, box.y, BOX_W, BOX_H)
        else:
            region = Region(0, self._index, 1, 1)
        self.scroll_to_region(region, animate=False)

    def _index_at(self, x: int, y: int) -> int | None:
        if self._flow:
            for i, row in enumerate(self.rows):
                box = self._flow.boxes[row.session.id]
                if box.x <= x < box.x + BOX_W and box.y <= y < box.y + BOX_H:
                    return i
            return None
        return y if 0 <= y < len(self.rows) else None

    # --- rendering ----------------------------------------------------------

    def render(self) -> Text:
        if not self.rows:
            return Text("")
        if self._flow:
            return flow_text(self._flow, self.sessions, self.now, self.selected_id, self.theme)
        lines = []
        for i, row in enumerate(self.rows):
            selected = i == self._index
            line = Text(no_wrap=True)
            for segment, role in row_segments(row, self.sessions, self.now):
                line.append(segment, style=self.theme.style(role, selected))
            lines.append(line)
        return Text("\n").join(lines)

    # --- keyboard -----------------------------------------------------------

    def action_move(self, step: int) -> None:
        if self._flow:
            self._move_same_level(step)
        else:
            self._select(self._index + step)

    def _move_same_level(self, step: int) -> None:
        """Flowchart: up/down step through sessions in the same column (same depth)."""
        depth = self.rows[self._index].depth
        level = [i for i, row in enumerate(self.rows) if row.depth == depth]
        level.sort(key=lambda i: self._flow.boxes[self.rows[i].session.id].y)
        target = level.index(self._index) + step
        if 0 <= target < len(level):
            self._select(level[target])

    def action_parent(self) -> None:
        if self.selected_id is None:
            return
        parent = self.sessions[self.selected_id].parent_id
        if parent:
            self.select_id(parent)

    def action_child(self) -> None:
        if self.selected_id is None:
            return
        child = next(
            (i for i, row in enumerate(self.rows) if row.session.parent_id == self.selected_id),
            None,
        )
        if child is not None:
            self._select(child)

    def action_activate(self) -> None:
        self.post_message(self.Activated(self.selected_id))

    # --- mouse --------------------------------------------------------------

    def on_click(self, event: events.Click) -> None:
        offset = event.get_content_offset(self)
        if offset is None:
            return
        index = self._index_at(offset.x, offset.y)
        if index is None:
            return
        if index == self._index:
            self.post_message(self.Activated(self.selected_id))
        else:
            self._select(index)
