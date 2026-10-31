"""Read Claude Code session files from ~/.claude/projects."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".claude" / "projects"
MESSAGE_TYPES = {"user", "assistant"}


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


def display_name(records: list[dict], session_id: str) -> str:
    """Same priority as /resume: custom title, AI title, last prompt, short id."""
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


def parse_session(path: Path) -> Session | None:
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
        name=display_name(records, session_id),
        first_ts=min(stamps),
        last_ts=max(stamps),
        branch=last_field(messages, "gitBranch"),
        created=getattr(stat, "st_birthtime", stat.st_ctime),
        uuids=frozenset(r["uuid"] for r in messages if r.get("uuid")),
    )


def discover(root: Path = DEFAULT_ROOT, cache: dict | None = None) -> dict[str, Session]:
    """Parse every session under root. `cache` maps path -> (mtime, size, Session)."""
    sessions: dict[str, Session] = {}
    if not root.is_dir():
        return sessions
    cache = {} if cache is None else cache
    for path in root.glob("*/*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        key = (stat.st_mtime_ns, stat.st_size)
        cached = cache.get(path)
        if cached and cached[0] == key:
            session = cached[1]
        else:
            try:
                session = parse_session(path)
            except OSError:
                session = None
            cache[path] = (key, session)
        if session:
            sessions[session.id] = session
    return sessions
