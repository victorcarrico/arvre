"""Filtering and tree layout for the session graph."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from arvre.scanner import Session

WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Row:
    session: Session
    prefix: str
    depth: int
    archived: bool = False


def visible_ids(
    sessions: dict[str, Session],
    now: datetime,
    window_24h: bool,
    all_projects: bool,
    cwd: str,
) -> set[str]:
    cutoff = now - WINDOW
    return {
        s.id
        for s in sessions.values()
        if (not window_24h or s.last_ts >= cutoff)
        and (all_projects or s.cwd == cwd)
    }


def tree_members(sessions: dict[str, Session], visible: set[str]) -> set[str]:
    """Every session in the family tree of any matching session."""
    roots = set()
    for sid in visible:
        current = sid
        while sessions[current].parent_id:
            current = sessions[current].parent_id
        roots.add(current)

    members: set[str] = set()
    stack = list(roots)
    while stack:
        sid = stack.pop()
        members.add(sid)
        stack.extend(sessions[sid].child_ids)
    return members


def _effective_parent(sessions: dict[str, Session], sid: str, shown: set[str]) -> str | None:
    """Walks up past any ancestor that archiving removed from `shown`, so a
    node's children stay nested under the nearest ancestor still on screen
    instead of scattering to the top level."""
    parent = sessions[sid].parent_id
    while parent is not None and parent not in shown:
        parent = sessions[parent].parent_id
    return parent


def build_rows(
    sessions: dict[str, Session],
    shown: set[str],
    archived: frozenset[str] = frozenset(),
) -> list[Row]:
    children: dict[str, list[str]] = defaultdict(list)
    roots: list[str] = []
    for sid in shown:
        parent = _effective_parent(sessions, sid, shown)
        if parent is not None:
            children[parent].append(sid)
        else:
            roots.append(sid)

    def newest_first(ids: list[str]) -> list[str]:
        return sorted(ids, key=lambda sid: sessions[sid].last_ts, reverse=True)

    rows: list[Row] = []

    def walk(sid: str, prefix: str, child_base: str, depth: int) -> None:
        rows.append(Row(sessions[sid], prefix, depth, archived=sid in archived))
        kids = newest_first(children[sid])
        for i, kid in enumerate(kids):
            last = i == len(kids) - 1
            walk(
                kid,
                child_base + ("└─ " if last else "├─ "),
                child_base + ("   " if last else "│  "),
                depth + 1,
            )

    for root in newest_first(roots):
        walk(root, "", "", 0)
    return rows


def format_age(now: datetime, then: datetime) -> str:
    seconds = int((now - then).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def inherited_name(session: Session, sessions: dict[str, Session]) -> bool:
    """True if this session still carries its parent's name -- the common
    case right after a fork, before Claude gives it (or the user gives it)
    its own title. Shown with a small marker so same-named siblings in the
    graph are still easy to tell apart."""
    return bool(session.parent_id) and sessions[session.parent_id].name == session.name


def row_segments(row: Row, sessions: dict[str, Session], now: datetime) -> list[tuple[str, str]]:
    """The compact row as (text, role) pairs; roles are styled by the theme."""
    s = row.session
    local = s.last_ts.astimezone().strftime("%Y-%m-%d %H:%M")
    meta = [f"{format_age(now, s.last_ts)} ({local})"]
    if s.parent_id:
        meta.append(f"↑ {sessions[s.parent_id].name}")
    if s.child_ids:
        count = len(s.child_ids)
        meta.append(f"{count} {'child' if count == 1 else 'children'}")
    if row.archived:
        meta.append("archived")

    bullet = "○ " if row.archived else "● "
    segments = [(row.prefix, "connector"), (bullet, "bullet"), (s.name, "name")]
    if inherited_name(s, sessions):
        segments.append((" ⑂", "meta"))
    for text in meta:
        segments.append(("  · ", "meta"))
        segments.append((text, "meta"))
    return segments


def row_label(row: Row, sessions: dict[str, Session], now: datetime) -> str:
    return "".join(text for text, _ in row_segments(row, sessions, now))
