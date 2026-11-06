"""Read Claude Code session files from ~/.claude/projects."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".claude" / "projects"
MESSAGE_TYPES = {"user", "assistant"}

# Message uuids are only ever compared to each other (fork detection), never
# shown, so a short prefix is enough and keeps the on-disk cache small. See
# docs/plan-0.3.md: zero collisions across ~34k real uuids at this length.
UUID_PREFIX_LEN = 12


@dataclass
class Session:
    id: str
    path: Path
    cwd: str
    name: str
    first_ts: datetime
    last_ts: datetime
    branch: str
    created: float
    uuids: frozenset[str] = field(repr=False)
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def last_field(records: list[dict], key: str, record_type: str | None = None) -> str:
    for record in reversed(records):
        if record_type and record.get("type") != record_type:
            continue
        if record.get(key):
            return str(record[key])
    return ""


def title_sidecar_path(session_path: Path) -> Path:
    """Claude Code writes a rename here, alongside the custom-title record in
    the JSONL itself. Both agree today; see docs/plan-0.3.md."""
    return session_path.parent / session_path.stem / "custom-title.json"


def read_title_sidecar(session_path: Path) -> tuple[str, int]:
    """(title, mtime_ns); ("", 0) if the sidecar is absent or unreadable."""
    sidecar = title_sidecar_path(session_path)
    try:
        stat = sidecar.stat()
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", 0
    return str(data.get("customTitle") or ""), stat.st_mtime_ns


def display_name(records: list[dict], session_id: str, sidecar_title: str = "") -> str:
    """Highest to lowest priority: the title sidecar, the custom-title record,
    the AI title, the last prompt, the short id. Same order /resume uses,
    plus the sidecar, which is read first because it is the most likely to
    stay in sync with a rename (docs/plan-0.3.md)."""
    if sidecar_title:
        return sidecar_title
    custom = last_field(records, "customTitle", "custom-title")
    if custom:
        return custom
    ai = last_field(records, "aiTitle", "ai-title")
    if ai:
        return ai
    prompt = last_field(records, "lastPrompt", "last-prompt").strip()
    if prompt:
        return prompt.splitlines()[0][:60]
    return session_id[:8]


def parse_session(path: Path, sidecar_title: str = "") -> Session | None:
    records: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    messages = [
        r
        for r in records
        if r.get("type") in MESSAGE_TYPES and not r.get("isSidechain") and r.get("timestamp")
    ]
    if not messages:
        return None

    stamps = [parse_ts(r["timestamp"]) for r in messages]
    stat = path.stat()
    session_id = path.stem
    return Session(
        id=session_id,
        path=path,
        cwd=next((r["cwd"] for r in records if r.get("cwd")), ""),
        name=display_name(records, session_id, sidecar_title),
        first_ts=min(stamps),
        last_ts=max(stamps),
        branch=last_field(messages, "gitBranch"),
        created=getattr(stat, "st_birthtime", stat.st_ctime),
        uuids=frozenset(r["uuid"][:UUID_PREFIX_LEN] for r in messages if r.get("uuid")),
    )


def discover(root: Path = DEFAULT_ROOT, cache: "ScanCache | None" = None) -> dict[str, Session]:
    """Parse every session under root, using `cache` to skip unchanged files.

    A cache hit costs one stat() of the session file and one of its (usually
    absent) title sidecar -- no file content is read. See arvre.cache and
    docs/plan-0.3.md for the measured effect (2.8s -> ~6ms on 300 sessions).
    """
    from arvre.cache import MISS, ScanCache  # local import: cache.py imports Session from here

    sessions: dict[str, Session] = {}
    if not root.is_dir():
        return sessions
    cache = cache if cache is not None else ScanCache()
    for path in root.glob("*/*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        title, title_mtime_ns = read_title_sidecar(path)
        path_str = str(path)
        session = cache.lookup(path_str, stat.st_mtime_ns, stat.st_size, title_mtime_ns)
        if session is MISS:
            try:
                session = parse_session(path, sidecar_title=title)
            except OSError:
                session = None
            cache.store(path_str, stat.st_mtime_ns, stat.st_size, title_mtime_ns, session)
        if session:
            sessions[session.id] = session
    return sessions
